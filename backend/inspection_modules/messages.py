from typing import Any

from backend.yolo_detector import format_yolo_for_prompt

from .parser import (
    _pick_report_field,
    detect_task,
    extract_json_object,
    labels_from_report,
    suggestions_from_report,
)
from .paths import APPEARANCE_REFERENCE_IMAGE, INTERNAL_REFERENCE_IMAGE
from .prompts import AUTO_PROMPT, MISSING_EQUIPMENT_VERIFY_PROMPT, STRICT_JUDGE_PROMPT_TEMPLATE
from .utils import file_to_data_url
from .yolo_context import build_missing_equipment_fallback_prompt

def build_messages(query: str, image: str | None, task: str) -> list[dict[str, Any]]:
    content_parts: list[dict[str, Any]] = [{"type": "text", "text": f"{AUTO_PROMPT}\n用户问题：{query}"}]
    if image:
        content_parts.insert(0, {"type": "image_url", "image_url": {"url": image}})
    return [{"role": "user", "content": content_parts}]


def build_judge_messages(query: str, image: str, raw_report: str, task: str, yolo_result: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    judge_scope = detect_task(query=query, explicit_task=task, report=raw_report)
    if judge_scope == "auto":
        judge_scope = "internal_components" if "内部" in raw_report else "appearance"
    scope_text = "内部组件" if judge_scope == "internal_components" else "箱体外观"
    yolo_text = format_yolo_for_prompt(yolo_result)
    fallback_text = build_missing_equipment_fallback_prompt(judge_scope, yolo_result)
    prompt = (
        STRICT_JUDGE_PROMPT_TEMPLATE
        + "\n\u672c\u6b21\u5efa\u8bae\u590d\u6838\u8303\u56f4\uff1a" + scope_text
        + "\n\u6ce8\u610f\uff1a\u8be5\u8303\u56f4\u53ea\u662f\u9996\u8f6e\u7ed3\u679c\u7684\u5efa\u8bae\uff1b\u5982\u679c\u539f\u56fe\u663e\u793a\u7bb1\u95e8\u5f00\u542f\u6216\u5173\u95ed\u72b6\u6001\u4e0e\u5efa\u8bae\u4e0d\u4e00\u81f4\uff0c\u4f60\u5fc5\u987b\u6309\u539f\u56fe\u91cd\u65b0\u9009\u62e9\u6b63\u786e\u8303\u56f4\u3002"
        + "\n\u7528\u6237\u95ee\u9898\uff1a" + query
        + "\n\n\u9996\u8f6e QwenVL \u5de1\u68c0\u8f93\u51fa\uff1a\n" + raw_report
        + "\n\nYOLO \u8f85\u52a9\u68c0\u6d4b\u7ed3\u679c\uff1a\n" + yolo_text
        + ("\n\n内部缺失类误报兜底提示：\n" + fallback_text if fallback_text else "")
        + "\n\n\u7efc\u5408\u8981\u6c42\uff1a\u8bf7\u540c\u65f6\u53c2\u8003\u539f\u56fe\u3001\u9996\u8f6e QwenVL \u8f93\u51fa\u548c YOLO \u8f85\u52a9\u68c0\u6d4b\u7ed3\u679c\u3002YOLO \u53ea\u63d0\u4f9b\u5185\u90e8\u7ec4\u4ef6\u9690\u60a3\u5b9a\u4f4d\u7ebf\u7d22\uff0c\u4e0d\u662f\u6700\u7ec8\u7ed3\u8bba\uff1b\u5982\u679c YOLO \u4e0e\u539f\u56fe\u53ef\u89c1\u8bc1\u636e\u4e0d\u4e00\u81f4\uff0c\u4ee5\u539f\u56fe\u4e3a\u51c6\uff1bYOLO \u672a\u68c0\u51fa\u4e5f\u4e0d\u80fd\u76f4\u63a5\u5224\u5b9a\u65e0\u9690\u60a3\u3002"
    )
    parts: list[dict[str, Any]] = []
    for ref_desc, reference_path in (
        ("内部组件合规参考图", INTERNAL_REFERENCE_IMAGE),
        ("箱体外观合规参考图", APPEARANCE_REFERENCE_IMAGE),
    ):
        reference_url = file_to_data_url(reference_path)
        if reference_url:
            parts.extend([
                {"type": "text", "text": f"{ref_desc}：仅用于理解合规状态的关键可见要素，不作为一比一模板。"},
                {"type": "image_url", "image_url": {"url": reference_url}},
            ])
    parts.extend([
        {"type": "text", "text": "用户待检图："},
        {"type": "image_url", "image_url": {"url": image}},
        {"type": "text", "text": prompt},
    ])
    return [{"role": "user", "content": parts}]

def build_missing_equipment_verify_messages(image: str, query: str, current_report: str) -> list[dict[str, Any]]:
    prompt = (
        MISSING_EQUIPMENT_VERIFY_PROMPT
        + "\n用户问题：" + query
        + "\n当前报告：\n" + current_report
    )
    parts = [
        {"type": "image_url", "image_url": {"url": image}},
        {"type": "text", "text": prompt},
    ]
    return [{"role": "user", "content": parts}]


def parse_missing_equipment_verify(text: str) -> dict[str, Any] | None:
    data = extract_json_object(text)
    if not data:
        return None
    return {
        "water_gun_visible": bool(data.get("water_gun_visible")),
        "water_hose_visible": bool(data.get("water_hose_visible")),
        "evidence": str(data.get("evidence") or "").strip(),
        "confidence": str(data.get("confidence") or "低").strip(),
    }


def apply_missing_equipment_visibility_review(report: str, verify: dict[str, Any] | None) -> str:
    if not verify:
        return report
    scope = _pick_report_field(report, "检查范围") or "内部组件"
    verdict = _pick_report_field(report, "结论") or "无法判断"
    evidence = _pick_report_field(report, "可见依据") or ""
    labels = labels_from_report(report)
    suggestions = suggestions_from_report(report)
    removed = []
    missing_water_gun = "室内消火栓无消防水枪"
    missing_water_hose = "室内消火栓无消防水带"
    if verify.get("water_gun_visible") and missing_water_gun in labels:
        labels = [label for label in labels if label != missing_water_gun]
        removed.append(missing_water_gun)
    if verify.get("water_hose_visible") and missing_water_hose in labels:
        labels = [label for label in labels if label != missing_water_hose]
        removed.append(missing_water_hose)
    if not removed:
        return report
    verify_evidence = verify.get("evidence") or "图中可见水枪或水带形态线索，对应缺失项证据不足。"
    if labels:
        verdict = "不合规"
        evidence = verify_evidence + "；已排除对应缺失类误报。"
    else:
        verdict = "合规"
        evidence = verify_evidence
    return "\n".join([
        f"检查范围：{scope}",
        f"结论：{verdict}",
        f"可见依据：{evidence}",
        "隐患标签：" + ("；".join(labels) if labels else "无"),
        "建议项：" + ("；".join(suggestions) if suggestions else "无"),
    ])
