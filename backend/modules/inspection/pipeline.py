import time
from typing import Any

from backend.infrastructure.vision.yolo_detector import run_yolo_detection

from backend.infrastructure.ai.model_client import create_model_client
from backend.modules.inspection.messages import (
    apply_bend_review,
    apply_missing_equipment_visibility_review,
    apply_outlet_direction_review,
    build_bend_verify_messages,
    build_judge_messages,
    build_messages,
    build_missing_equipment_verify_messages,
    build_outlet_direction_verify_messages,
    parse_bend_verify,
    parse_missing_equipment_verify,
    parse_outlet_direction_verify,
)
from backend.modules.inspection.parser import (
    detect_task,
    has_bend_candidate,
    has_structured_report,
    labels_from_report,
    pick_primary_structured_report,
    report_fields_for_trace,
    sanitize_final_report,
)
from backend.modules.inspection.output_formatter import format_public_report
from backend.modules.inspection.postprocess import guarded_format_judge_json
from backend.config.settings import get_settings
from backend.modules.inspection.trace import build_trace_summary, trace_stage
from backend.modules.inspection.types import InspectionState, Settings
from backend.modules.inspection.utils import normalize_image, strip_reasoning, trim_output
from backend.modules.inspection.yolo_context import apply_yolo_backstop, missing_equipment_fallback_labels, yolo_labels_for_trace, MISSING_EQUIPMENT_LABELS


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
        self.model = create_model_client(settings, provider=settings.first_provider)
        self.judge_model = create_model_client(
            settings,
            provider=settings.judge_provider,
            api_key=settings.judge_api_key,
            base_url=settings.judge_base_url,
            model=settings.judge_model,
        )
        self.direction_model = create_model_client(
            settings,
            provider=settings.direction_review_provider,
            api_key=settings.direction_review_api_key,
            base_url=settings.direction_review_base_url,
            model=settings.direction_review_model,
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
        # 多段报告中取主要报告
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
        reviewed_text = ""

        image = prepared.get("image")
        judge_task = prepared.get("task") or "auto"
        effective_task = judge_task
        yolo_result: dict[str, Any] = {"enabled": False, "detections": [], "reason": "no image"}
        if image:
            judge_task = detect_task(prepared.get("query", ""), prepared.get("task"), raw_report)
            if judge_task == "auto":
                judge_task = "internal_components" if "\u5185\u90e8" in raw_report else "appearance"

            stage_started = time.perf_counter()
            yolo_result = run_yolo_detection(image, task=judge_task)
            yolo_stage_id = "yolo_appearance" if judge_task == "appearance" else "yolo_internal"
            yolo_stage_name = "YOLO \u7bb1\u4f53\u5916\u89c2\u8f85\u52a9\u68c0\u6d4b" if judge_task == "appearance" else "YOLO \u5185\u90e8\u7ec4\u4ef6\u8f85\u52a9\u68c0\u6d4b"
            stages.append(trace_stage(
                yolo_stage_id,
                yolo_stage_name,
                stage_started,
                status="skipped" if yolo_result.get("skipped") else ("warn" if yolo_result.get("reason") else ("ok" if yolo_result.get("enabled") else "warn")),
                detectionCount=len(yolo_result.get("detections") or []),
                labels=yolo_labels_for_trace(yolo_result),
                reason=yolo_result.get("reason", ""),
                imageSize={"width": yolo_result.get("imageWidth", 0), "height": yolo_result.get("imageHeight", 0)},
                modelScope=yolo_result.get("modelScope", ""),
                adopted=True,
            ))

            stage_started = time.perf_counter()
            judge_messages = build_judge_messages(prepared.get("query", ""), image, raw_report, judge_task, yolo_result=yolo_result)
            reviewed = self.judge_model.invoke(judge_messages)
            reviewed_text = trim_output(strip_reasoning(reviewed.content), self.settings.max_output_chars)
            formatted_review = guarded_format_judge_json(reviewed_text, raw_report)
            if formatted_review:
                final_report = formatted_review
                # 判断模型是否输出了结构化报告
            elif has_structured_report(reviewed_text):
                # 清洗并纠正报告
                final_report = sanitize_final_report(reviewed_text)
            else:
                final_report = raw_report
            usage = merge_usage(usage, reviewed.usage)
            # 提取日志字段
            final_fields = report_fields_for_trace(final_report)
            # 找出可能需要兜底的缺失标签
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
        scope_changed = False
        if image:
            final_scope = report_fields_for_trace(final_report).get("scope") or ""
            desired_task = "appearance" if final_scope == "\u7bb1\u4f53\u5916\u89c2" else ("internal_components" if final_scope == "\u5185\u90e8\u7ec4\u4ef6" else "")
            effective_task = desired_task or judge_task
            scope_changed = bool(desired_task and desired_task != judge_task)
            desired_type = "appearance_presence" if desired_task == "appearance" else ("component_presence" if desired_task == "internal_components" else "")
            current_type = str(yolo_result.get("modelType") or "")
            if desired_task and current_type != desired_type:
                stage_started = time.perf_counter()
                aligned_result = run_yolo_detection(image, task=desired_task)
                if scope_changed:
                    for previous_stage in reversed(stages):
                        if previous_stage.get("name") in {"yolo_internal", "yolo_appearance"}:
                            previous_stage["status"] = "skipped"
                            previous_stage["adopted"] = False
                            previous_stage["superseded"] = True
                            previous_stage["reason"] = (
                                "\u6700\u7ec8\u68c0\u67e5\u8303\u56f4\u5df2\u8c03\u6574\uff0c\u672c\u9636\u6bb5\u5019\u9009\u6846\u4ec5\u4fdd\u7559\u7528\u4e8e\u8ffd\u6eaf\uff0c"
                                "\u4e0d\u53c2\u4e0e\u6700\u7ec8\u7ed3\u8bba\u3002"
                            )
                            break
                aligned_stage_id = "yolo_appearance_align" if desired_task == "appearance" else "yolo_internal_align"
                aligned_stage_name = "YOLO \u8303\u56f4\u5bf9\u9f50\u590d\u8dd1\uff08\u7bb1\u4f53\u5916\u89c2\uff09" if desired_task == "appearance" else "YOLO \u8303\u56f4\u5bf9\u9f50\u590d\u8dd1\uff08\u5185\u90e8\u7ec4\u4ef6\uff09"
                stages.append(trace_stage(
                    aligned_stage_id,
                    aligned_stage_name,
                    stage_started,
                    status="skipped" if aligned_result.get("skipped") else ("warn" if aligned_result.get("reason") else ("ok" if aligned_result.get("enabled") else "warn")),
                    detectionCount=len(aligned_result.get("detections") or []),
                    labels=yolo_labels_for_trace(aligned_result), # 把 YOLO 输出转换成日志可展示标签
                    reason=aligned_result.get("reason", ""),
                    imageSize={"width": aligned_result.get("imageWidth", 0), "height": aligned_result.get("imageHeight", 0)},
                    modelScope=aligned_result.get("modelScope", ""),
                    adopted=True,
                ))
                yolo_result = aligned_result

        missing_review_candidates: list[str] = []
        specialist_context_report = raw_report if not scope_changed else final_report
        if image and effective_task == "internal_components":
            # 读取隐患标签
            candidate_reports = [final_report]
            if not scope_changed:
                candidate_reports.insert(0, raw_report)
            for label in [item for report in candidate_reports for item in labels_from_report(report)]:
                # 定义哪些标签属于组件缺失
                if label in MISSING_EQUIPMENT_LABELS and label not in missing_review_candidates:
                    missing_review_candidates.append(label)
        if image and effective_task == "internal_components" and missing_review_candidates:
            stage_started = time.perf_counter()
            verify_messages = build_missing_equipment_verify_messages(
                image,
                prepared.get("query", ""),
                specialist_context_report,
                final_report,
                missing_review_candidates,
            )
            verify_result = self.judge_model.invoke(verify_messages)
            verify_text = trim_output(strip_reasoning(verify_result.content), self.settings.max_output_chars)
            verify_data = parse_missing_equipment_verify(verify_text)
            updated_report = apply_missing_equipment_visibility_review(final_report, verify_data, missing_review_candidates)
            usage = merge_usage(usage, verify_result.usage)
            stages.append(trace_stage(
                "missing_visibility_review",
                "\u6c34\u67aa/\u6c34\u5e26\u7f3a\u5931\u4e13\u9879\u590d\u6838",
                stage_started,
                status="ok" if verify_data else "warn",
                output=report_fields_for_trace(updated_report),
                rawOutput=trim_output(verify_text, 600),
                candidateLabels=missing_review_candidates,
                changed=updated_report != final_report,
                usage=verify_result.usage,
            ))
            final_report = updated_report

        bend_label = "消防软管卷盘供水管道折弯严重"
        bend_candidate = has_bend_candidate(raw_report, reviewed_text, final_report)
        if image and effective_task == "internal_components" and (
            bend_candidate or bend_label in labels_from_report(final_report)
        ):
            stage_started = time.perf_counter()
            bend_messages = build_bend_verify_messages(
                image,
                prepared.get("query", ""),
                specialist_context_report,
                final_report,
            )
            bend_result = self.direction_model.invoke(bend_messages)
            bend_text = trim_output(strip_reasoning(bend_result.content), self.settings.max_output_chars)
            bend_data = parse_bend_verify(bend_text)
            updated_report = apply_bend_review(final_report, bend_data)
            usage = merge_usage(usage, bend_result.usage)
            stages.append(trace_stage(
                "bend_review",
                "供水软管严重折弯专项复核",
                stage_started,
                status="ok" if bend_data else "warn",
                output=report_fields_for_trace(updated_report),
                rawOutput=trim_output(bend_text, 600),
                candidateDetected=bend_candidate,
                changed=updated_report != final_report,
                supported=bool((bend_data or {}).get("severe_bend_supported")),
                usage=bend_result.usage,
            ))
            final_report = updated_report

        # 使用 YOLO 结果对报告进行最后兜底
        direction_label = "室内消火栓栓口方向错误"
        yolo_components = set(yolo_labels_for_trace(yolo_result))
        direction_candidate = direction_label in labels_from_report(final_report)
        direction_components_visible = "接口" in yolo_components and bool({"栓体", "阀门"} & yolo_components)
        if image and effective_task == "internal_components" and (
            direction_candidate or direction_components_visible
        ):
            stage_started = time.perf_counter()
            direction_messages = build_outlet_direction_verify_messages(
                image,
                prepared.get("query", ""),
                specialist_context_report,
                final_report,
                yolo_result=yolo_result,
            )
            direction_result = self.direction_model.invoke(direction_messages)
            direction_text = trim_output(strip_reasoning(direction_result.content), self.settings.max_output_chars)
            direction_data = parse_outlet_direction_verify(direction_text)
            updated_report = apply_outlet_direction_review(final_report, direction_data)
            usage = merge_usage(usage, direction_result.usage)
            stages.append(trace_stage(
                "outlet_direction_review",
                "栓口方向专项复核",
                stage_started,
                status="ok" if direction_data else "warn",
                output=report_fields_for_trace(updated_report),
                rawOutput=trim_output(direction_text, 600),
                candidateDetected=direction_candidate,
                componentTriggered=direction_components_visible,
                changed=updated_report != final_report,
                supported=bool((direction_data or {}).get("wrong_direction_supported")),
                needsManualReview=bool((direction_data or {}).get("needs_manual_review")),
                usage=direction_result.usage,
            ))
            final_report = updated_report

        final_report = apply_yolo_backstop(final_report, raw_report, yolo_result)
        trace = {
            "version": "qwen-yolo-judge-v2",
            "stages": stages,
            "summary": build_trace_summary(raw_report, final_report, yolo_result, stages),
        }
        public_report = format_public_report(final_report, yolo_result=yolo_result)
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
