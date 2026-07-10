import time
from typing import Any

from backend.yolo_detector import run_yolo_detection

from .client import QwenClient
from .messages import (
    apply_missing_equipment_visibility_review,
    build_judge_messages,
    build_messages,
    build_missing_equipment_verify_messages,
    parse_missing_equipment_verify,
)
from .parser import (
    detect_task,
    has_structured_report,
    pick_primary_structured_report,
    report_fields_for_trace,
    sanitize_final_report,
)
from .output_formatter import format_public_report
from .postprocess import guarded_format_judge_json
from .settings import get_settings
from .trace import build_trace_summary, trace_stage
from .types import InspectionState, Settings
from .utils import normalize_image, strip_reasoning, trim_output
from .yolo_context import apply_yolo_backstop, missing_equipment_fallback_labels, yolo_labels_for_trace, MISSING_EQUIPMENT_LABELS

def prepare_input(state: InspectionState) -> InspectionState:
    query = (state.get("query") or "").strip()
    if not query:
        raise ValueError("Query is required")
    image = normalize_image(state.get("image"))
    task = detect_task(query=query, explicit_task=state.get("task"))
    return {"query": query, "image": image, "task": task, "messages": build_messages(query=query, image=image, task=task)}


class InspectionAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = QwenClient(settings)
        self.judge_model = QwenClient(
            settings,
            api_key=settings.judge_api_key,
            base_url=settings.judge_base_url,
            model=settings.judge_model,
        )

    def prepare(self, data: dict[str, Any]) -> InspectionState:
        return prepare_input({
            "query": (data or {}).get("query", ""),
            "image": (data or {}).get("image"),
            "task": (data or {}).get("task", ""),
        })

    def invoke(self, data: dict[str, Any]) -> InspectionState:
        prepared = self.prepare(data)
        stages: list[dict[str, Any]] = []

        stage_started = time.perf_counter()
        first = self.model.invoke(prepared["messages"])
        raw_report = trim_output(strip_reasoning(first.content), self.settings.max_output_chars)
        raw_report = pick_primary_structured_report(raw_report)
        stages.append(trace_stage(
            "qwen_first",
            "QwenVL \u521d\u68c0",
            stage_started,
            output=report_fields_for_trace(raw_report),
            usage=first.usage,
        ))
        final_report = raw_report
        usage = dict(first.usage)

        image = prepared.get("image")
        yolo_result: dict[str, Any] = {"enabled": False, "detections": [], "reason": "no image"}
        if image:
            judge_task = detect_task(prepared.get("query", ""), prepared.get("task"), raw_report)
            if judge_task == "auto":
                judge_task = "internal_components" if "\u5185\u90e8" in raw_report else "appearance"

            stage_started = time.perf_counter()
            yolo_result = run_yolo_detection(image, task=judge_task)
            stages.append(trace_stage(
                "yolo_internal",
                "YOLO \u5185\u90e8\u7ec4\u4ef6\u8f85\u52a9\u68c0\u6d4b",
                stage_started,
                status="skipped" if yolo_result.get("skipped") else ("ok" if yolo_result.get("enabled") else "warn"),
                detectionCount=len(yolo_result.get("detections") or []),
                labels=yolo_labels_for_trace(yolo_result),
                reason=yolo_result.get("reason", ""),
                imageSize={"width": yolo_result.get("imageWidth", 0), "height": yolo_result.get("imageHeight", 0)},
            ))

            stage_started = time.perf_counter()
            judge_messages = build_judge_messages(prepared.get("query", ""), image, raw_report, judge_task, yolo_result=yolo_result)
            reviewed = self.judge_model.invoke(judge_messages)
            reviewed_text = trim_output(strip_reasoning(reviewed.content), self.settings.max_output_chars)
            formatted_review = guarded_format_judge_json(reviewed_text, raw_report)
            if formatted_review:
                final_report = formatted_review
            elif has_structured_report(reviewed_text):
                final_report = sanitize_final_report(reviewed_text)
            else:
                final_report = raw_report
            usage = merge_usage(usage, reviewed.usage)
            final_fields = report_fields_for_trace(final_report)
            fallback_labels = missing_equipment_fallback_labels(final_fields.get("labels") or [], yolo_labels_for_trace(yolo_result))
            stages.append(trace_stage(
                "judge_review",
                "\u4e8c\u6b21\u590d\u6838\u7efc\u5408\u5224\u65ad",
                stage_started,
                output=final_fields,
                rawOutput=trim_output(reviewed_text, 900),
                fallback="missing_equipment" if fallback_labels else "",
                fallbackLabels=fallback_labels,
                usage=reviewed.usage,
            ))

        final_report = sanitize_final_report(final_report)
        if image and judge_task == "internal_components" and any(label in final_report for label in MISSING_EQUIPMENT_LABELS):
            stage_started = time.perf_counter()
            verify_messages = build_missing_equipment_verify_messages(image, prepared.get("query", ""), final_report)
            verify_result = self.judge_model.invoke(verify_messages)
            verify_text = trim_output(strip_reasoning(verify_result.content), self.settings.max_output_chars)
            verify_data = parse_missing_equipment_verify(verify_text)
            updated_report = apply_missing_equipment_visibility_review(final_report, verify_data)
            usage = merge_usage(usage, verify_result.usage)
            stages.append(trace_stage(
                "missing_visibility_review",
                "水枪/水带可见性专项复核",
                stage_started,
                status="ok" if verify_data else "warn",
                output=report_fields_for_trace(updated_report),
                rawOutput=trim_output(verify_text, 600),
                changed=updated_report != final_report,
                usage=verify_result.usage,
            ))
            final_report = updated_report
        final_report = apply_yolo_backstop(final_report, raw_report, yolo_result)
        trace = {
            "version": "qwen-yolo-judge-v1",
            "stages": stages,
            "summary": build_trace_summary(raw_report, final_report, yolo_result, stages),
        }
        public_report = format_public_report(final_report)
        return {
            **prepared,
            "raw_report": raw_report,
            "structured_report": final_report,
            "report": public_report,
            "usage": usage,
            "yolo": yolo_result,
            "trace": trace,
        }
    def stream_checked(self, data: dict[str, Any]) -> InspectionState:
        return self.invoke(data)

    def stream(self, messages: list[dict[str, Any]]):
        return self.model.stream(messages)


def merge_usage(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    merged = dict(left or {})
    for key, value in (right or {}).items():
        if isinstance(value, int):
            merged[key] = merged.get(key, 0) + value
    return merged

_agent_cache: tuple[Settings, InspectionAgent] | None = None


def get_agent() -> InspectionAgent:
    global _agent_cache
    settings = get_settings()
    if _agent_cache and _agent_cache[0] == settings:
        return _agent_cache[1]
    agent = InspectionAgent(settings)
    _agent_cache = (settings, agent)
    return agent

class _SimpleCompiledGraph:
    def __init__(self, func: Any) -> None:
        self.func = func

    def invoke(self, state: InspectionState) -> InspectionState:
        return self.func(state)


def create_prepare_graph():
    return _SimpleCompiledGraph(prepare_input)


def create_inspection_graph(model: Any):
    def invoke_plain(state: InspectionState) -> InspectionState:
        prepared = prepare_input(state)
        response = model.invoke(prepared["messages"])
        return {**prepared, "report": trim_output(strip_reasoning(response.content), 1200), "usage": response.usage}
    return _SimpleCompiledGraph(invoke_plain)
