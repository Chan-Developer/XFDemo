from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Callable

from backend.infrastructure.vision.yolo_detector import run_yolo_detection
from backend.modules.inspection.intent import IntentResult, explicit_intent, rule_based_intent


ProgressCallback = Callable[[dict[str, Any]], None]

ROUTE_ORDER = (
    ("internal_components", "indoor_hydrant", "internal_components", "识别室内消火栓组件"),
    ("appearance", "indoor_hydrant", "appearance", "识别室内消火栓箱体"),
    ("outdoor_hydrant", "outdoor_hydrant", "outdoor", "识别室外消火栓"),
    ("fire_extinguisher", "fire_extinguisher", "extinguisher", "识别灭火器与压力指示器"),
)

INDOOR_CORE_LABELS = {"水带", "水枪", "软管", "栓体", "接口", "手轮", "阀门", "控制器"}
INDOOR_STRONG_SINGLE_LABELS = {"水带", "水枪", "软管", "栓体"}
APPEARANCE_LABELS = {"消火栓", "箱门", "中文标识", "操作说明"}


def _emit(callback: ProgressCallback | None, **payload: Any) -> None:
    if callback:
        callback(payload)


def _detections(result: dict[str, Any]) -> list[dict[str, Any]]:
    return list(result.get("detections") or [])


def _label(item: dict[str, Any]) -> str:
    return str(item.get("label") or item.get("component") or item.get("className") or "").strip()


def _confidence(item: dict[str, Any]) -> float:
    try:
        return float(item.get("confidence") or 0)
    except (TypeError, ValueError):
        return 0.0


def _route_match(task: str, result: dict[str, Any]) -> tuple[bool, float, str]:
    detections = _detections(result)
    labels = {_label(item) for item in detections if _label(item)}
    highest = max((_confidence(item) for item in detections), default=0.0)

    if task == "internal_components":
        core = labels & INDOOR_CORE_LABELS
        strong_single = any(
            _label(item) in INDOOR_STRONG_SINGLE_LABELS and _confidence(item) >= 0.55
            for item in detections
        )
        matched = len(core) >= 2 or strong_single
        reason = (
            f"发现 {len(core)} 类室内核心组件，最高置信度 {highest:.2f}"
            if matched
            else f"室内组件证据不足：{len(core)} 类，最高置信度 {highest:.2f}"
        )
        score = min(1.0, len(core) * 0.22 + highest * 0.58)
        return matched, score, reason

    if task == "appearance":
        visible = labels & APPEARANCE_LABELS
        has_box = "消火栓" in visible or "箱门" in visible
        has_identity = "中文标识" in visible or "操作说明" in visible
        matched = (has_box and has_identity) or len(visible) >= 3
        reason = (
            f"发现室内箱体组合证据：{'、'.join(sorted(visible))}"
            if matched
            else f"室内箱体组合证据不足：{'、'.join(sorted(visible)) or '无'}"
        )
        score = min(1.0, len(visible) * 0.20 + highest * 0.45)
        return matched, score, reason

    if task == "outdoor_hydrant":
        candidates = [item for item in detections if _label(item) == "室外消火栓"]
        top = max((_confidence(item) for item in candidates), default=0.0)
        matched = top >= 0.25
        return matched, top, f"室外消火栓最高置信度 {top:.2f}"

    extinguisher = max(
        (_confidence(item) for item in detections if _label(item) == "灭火器"),
        default=0.0,
    )
    pressure = max(
        (_confidence(item) for item in detections if _label(item) == "灭火器压力指示器"),
        default=0.0,
    )
    matched = extinguisher >= 0.30 or pressure >= 0.40
    paired_bonus = 0.12 if extinguisher >= 0.30 and pressure >= 0.40 else 0.0
    score = min(1.0, max(extinguisher, pressure) + paired_bonus)
    return matched, score, f"灭火器 {extinguisher:.2f}，压力指示器 {pressure:.2f}"


def _explicit_route(explicit_task: str | None) -> tuple[IntentResult, str] | None:
    intent = explicit_intent(explicit_task)
    if not intent:
        return None
    task = {
        "indoor_hydrant": "internal_components",
        "outdoor_hydrant": "outdoor_hydrant",
        "fire_extinguisher": "fire_extinguisher",
    }[intent.inspection_type]
    return intent, task


def resolve_yolo_route(
    image: str | None,
    query: str,
    explicit_task: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> tuple[IntentResult, dict[str, Any], dict[str, Any]]:
    started = time.perf_counter()
    probes: list[dict[str, Any]] = []

    explicit = _explicit_route(explicit_task)
    if explicit:
        intent, task = explicit
        _emit(
            progress_callback,
            stage="route",
            status="running",
            label=f"正在定位{intent.display_name}",
            detail="已采用用户指定的检测类型",
        )
        probe_started = time.perf_counter()
        result = run_yolo_detection(image, task=task)
        duration_ms = int((time.perf_counter() - probe_started) * 1000)
        probes.append({
            "task": task,
            "inspectionType": intent.inspection_type,
            "matched": True,
            "score": 1.0,
            "reason": "用户显式指定检测类型",
            "durationMs": duration_ms,
            "result": result,
        })
        return intent, result, {
            "source": "explicit",
            "latencyMs": int((time.perf_counter() - started) * 1000),
            "probes": probes,
            "selectedTask": task,
            "selectedReason": "用户显式指定检测类型",
        }

    if not image:
        fallback = rule_based_intent(query)
        return fallback, {"enabled": False, "detections": [], "reason": "no image"}, {
            "source": "rule_fallback",
            "latencyMs": 0,
            "probes": probes,
            "selectedTask": "",
            "selectedReason": "未提供图片，使用问题关键词兜底",
        }

    def run_probe(
        route: tuple[str, str, str, str],
        detail: str,
    ) -> dict[str, Any]:
        task, inspection_type, _scope_hint, label = route
        _emit(
            progress_callback,
            stage="route",
            substage=task,
            status="running",
            label=f"正在{label}",
            detail=detail,
        )
        probe_started = time.perf_counter()
        result = run_yolo_detection(image, task=task)
        duration_ms = int((time.perf_counter() - probe_started) * 1000)
        matched, score, reason = _route_match(task, result)
        probe = {
            "task": task,
            "inspectionType": inspection_type,
            "matched": matched,
            "score": round(score, 4),
            "reason": reason,
            "durationMs": duration_ms,
            "detectionCount": len(_detections(result)),
            "labels": sorted({_label(item) for item in _detections(result) if _label(item)}),
            "result": result,
        }
        probes.append(probe)
        _emit(
            progress_callback,
            stage="route",
            substage=task,
            status="complete",
            label=label.replace("识别", "") + ("已确认" if matched else "未确认"),
            detail=reason,
            durationMs=duration_ms,
            detectionCount=probe["detectionCount"],
        )
        return probe

    def selected_response(probe: dict[str, Any]) -> tuple[IntentResult, dict[str, Any], dict[str, Any]]:
        task = str(probe["task"])
        route = next(item for item in ROUTE_ORDER if item[0] == task)
        _task, inspection_type, scope_hint, _label_text = route
        reason = str(probe["reason"])
        intent = IntentResult(
            inspection_type=inspection_type,
            confidence=max(0.45, min(float(probe["score"]), 1.0)),
            scope_hint=scope_hint,
            evidence=reason,
            source="yolo_router",
        )
        return intent, probe["result"], {
            "source": "yolo_router",
            "latencyMs": int((time.perf_counter() - started) * 1000),
            "probes": probes,
            "selectedTask": task,
            "selectedReason": reason,
        }

    for route in ROUTE_ORDER[:2]:
        probe = run_probe(route, "优先核验室内消火栓组件与箱体证据")
        if probe["matched"]:
            return selected_response(probe)

    branch_candidates = [
        run_probe(
            route,
            "核验室外消火栓、灭火器与压力指示器，并在候选间比较证据强度",
        )
        for route in ROUTE_ORDER[2:]
    ]
    matched_candidates = [probe for probe in branch_candidates if probe["matched"]]
    if matched_candidates:
        selected = max(matched_candidates, key=lambda item: float(item["score"]))
        if len(matched_candidates) > 1:
            selected["reason"] = (
                f"{selected['reason']}；与其他分支比较后证据得分最高 "
                f"{float(selected['score']):.2f}"
            )
        return selected_response(selected)

    fallback = rule_based_intent(query)
    fallback = IntentResult(
        inspection_type=fallback.inspection_type,
        confidence=min(fallback.confidence, 0.45),
        scope_hint=fallback.scope_hint,
        evidence="所有 YOLO 路由候选均未达到阈值；" + fallback.evidence,
        source="rule_fallback",
    )
    selected_task = {
        "indoor_hydrant": "internal_components",
        "outdoor_hydrant": "outdoor_hydrant",
        "fire_extinguisher": "fire_extinguisher",
    }.get(fallback.inspection_type, "internal_components")
    selected_probe = next((item for item in probes if item["task"] == selected_task), probes[0])
    return fallback, selected_probe["result"], {
        "source": "rule_fallback",
        "latencyMs": int((time.perf_counter() - started) * 1000),
        "probes": probes,
        "selectedTask": selected_task,
        "selectedReason": fallback.evidence,
    }


def route_trace_payload(intent: IntentResult, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        **asdict(intent),
        "displayName": intent.display_name,
        "latencyMs": meta.get("latencyMs", 0),
        "source": meta.get("source", intent.source),
        "selectedTask": meta.get("selectedTask", ""),
        "selectedReason": meta.get("selectedReason", ""),
        "probes": [
            {key: value for key, value in probe.items() if key != "result"}
            for probe in meta.get("probes") or []
        ],
    }
