import json
from typing import Any

from .parser import _pick_report_field, extract_json_object, labels_from_report, normalize_label_list


def evidence_is_unstable(evidence: str) -> bool:
    text = evidence or ""
    if len(text) > 280:
        return True
    if text.count("、") + text.count("，") + text.count(",") > 14:
        return True
    repeated_terms = ("密封圈", "发黄", "发蓝", "发绿", "发紫", "发黑", "发白")
    return any(text.count(term) >= 4 for term in repeated_terms)


def stable_evidence_or_raw(evidence: str, raw_report: str) -> str:
    if not evidence_is_unstable(evidence):
        return evidence
    raw_evidence = _pick_report_field(raw_report, "可见依据")
    if raw_evidence and not evidence_is_unstable(raw_evidence):
        return raw_evidence
    return ""

def evidence_says_component_visible(evidence: str, component: str) -> bool:
    text = evidence or ""
    water_gun = "\u6c34\u67aa"
    water_hose = "\u6c34\u5e26"
    if component == water_gun:
        suspect_terms = [
            "\u6c34\u67aa\u63a5\u53e3",
            "\u67aa\u5934",
            "\u67aa\u5934\u5ea7",
            "\u55b7\u5634",
            "\u55b7\u5c04\u5668",
            "\u91d1\u5c5e\u55b7\u5634",
            "\u94f6\u8272\u55b7\u5634",
            "\u94f6\u8272",
        ]
        visible_terms = ["\u53ef\u89c1", "\u770b\u5230", "\u6709", "\u6302\u6709", "\u5de6\u4fa7", "\u7bb1\u5185"]
        if any(term in text for term in suspect_terms) and any(term in text for term in visible_terms):
            return True
    if component not in text:
        return False
    negative_terms = [
        f"\u672a\u89c1{component}",
        f"\u770b\u4e0d\u5230{component}",
        f"\u6ca1\u6709{component}",
        f"\u65e0{component}",
        f"{component}\u7f3a\u5931",
        f"{component}\u672c\u4f53\u7f3a\u5931",
    ]
    if any(term in text for term in negative_terms):
        return False
    positive_terms = [
        "\u53ef\u89c1", "\u770b\u5230", "\u6709", "\u6302\u6709", "\u653e\u7f6e", "\u5806\u653e",
        "\u76d8\u7ed5", "\u5377\u653e", "\u6298\u53e0", "\u94f6\u8272", "\u91d1\u5c5e", "\u767d\u8272",
    ]
    return any(term in text for term in positive_terms)


def remove_contradictory_missing_labels(labels: list[str], evidence: str) -> tuple[list[str], list[str]]:
    cleaned = list(labels)
    removed: list[str] = []
    missing_water_gun = "\u5ba4\u5185\u6d88\u706b\u6813\u65e0\u6d88\u9632\u6c34\u67aa"
    missing_water_hose = "\u5ba4\u5185\u6d88\u706b\u6813\u65e0\u6d88\u9632\u6c34\u5e26"
    if evidence_says_component_visible(evidence, "\u6c34\u67aa") and missing_water_gun in cleaned:
        cleaned = [label for label in cleaned if label != missing_water_gun]
        removed.append(missing_water_gun)
    if evidence_says_component_visible(evidence, "\u6c34\u5e26") and missing_water_hose in cleaned:
        cleaned = [label for label in cleaned if label != missing_water_hose]
        removed.append(missing_water_hose)
    return cleaned, removed


REFERENCE_COMPONENT_GROUPS = {
    "reel": ["\u5377\u76d8", "\u8f6f\u7ba1\u5377\u76d8", "\u76d8\u7ed5", "\u5377\u653e"],
    "valve": ["\u624b\u8f6e", "\u9600\u4f53", "\u6813\u53e3", "\u63a5\u53e3"],
    "hose": ["\u6c34\u5e26", "\u767d\u8272\u7ec7\u7269", "\u6298\u53e0", "\u76d8\u7ed5\u7684\u767d\u8272"],
    "gun": ["\u6c34\u67aa", "\u55b7\u5634", "\u55b7\u5c04\u5668", "\u67aa\u5934", "\u9525\u5f62", "\u94f6\u8272\u91d1\u5c5e"],
}

REFERENCE_NEGATIVE_TERMS = ["\u672a\u89c1", "\u6ca1\u6709", "\u65e0", "\u770b\u4e0d\u5230", "\u7f3a\u5931"]


def reference_like_component_visibility(text: str) -> dict[str, bool]:
    candidate = text or ""
    visible: dict[str, bool] = {}
    for group, terms in REFERENCE_COMPONENT_GROUPS.items():
        matched = any(term in candidate for term in terms)
        if not matched:
            visible[group] = False
            continue
        if group in {"reel", "valve"}:
            visible[group] = True
            continue
        positive = any(term in candidate for term in ["\u53ef\u89c1", "\u770b\u5230", "\u6709", "\u7bb1\u5185", "\u5de6\u4fa7", "\u6302\u6709", "\u76d8\u7ed5", "\u5377\u653e", "\u6298\u53e0", "\u767d\u8272", "\u94f6\u8272", "\u91d1\u5c5e"])
        negative = any((neg + term) in candidate for neg in REFERENCE_NEGATIVE_TERMS for term in terms)
        visible[group] = positive or not negative
    return visible


def remove_reference_like_missing_labels(labels: list[str], context_text: str) -> tuple[list[str], list[str], dict[str, bool]]:
    cleaned = list(labels)
    removed: list[str] = []
    groups = reference_like_component_visibility(context_text)
    visible_count = sum(1 for value in groups.values() if value)
    missing_water_gun = "\u5ba4\u5185\u6d88\u706b\u6813\u65e0\u6d88\u9632\u6c34\u67aa"
    missing_water_hose = "\u5ba4\u5185\u6d88\u706b\u6813\u65e0\u6d88\u9632\u6c34\u5e26"

    gun_supported = groups.get("gun") or (visible_count >= 3 and groups.get("reel") and groups.get("valve"))
    hose_supported = groups.get("hose") or (visible_count >= 3 and groups.get("reel") and groups.get("valve"))

    if gun_supported and missing_water_gun in cleaned:
        cleaned = [label for label in cleaned if label != missing_water_gun]
        removed.append(missing_water_gun)
    if hose_supported and missing_water_hose in cleaned:
        cleaned = [label for label in cleaned if label != missing_water_hose]
        removed.append(missing_water_hose)
    return cleaned, removed, groups




def remove_glass_door_label(labels: list[str], evidence: str) -> tuple[list[str], bool, str]:
    glass_label = "室内消火栓箱门为玻璃门"
    text = evidence or ""
    glass_terms = ("玻璃门", "透明", "半透明", "透视", "玻璃反光", "玻璃边框", "箱门材质")
    removed = glass_label in labels or any(term in text for term in glass_terms)
    cleaned = [label for label in labels if label != glass_label]
    clauses: list[str] = []
    for raw in text.replace("；", "。").split("。"):
        clause = raw.strip("；。 ，,")
        if not clause:
            continue
        if any(term in clause for term in glass_terms):
            continue
        clauses.append(clause)
    return cleaned, removed, "。".join(clauses).strip("。")

def evidence_supports_severe_bend(evidence: str) -> bool:
    text = evidence or ""
    negative_patterns = [
        "未见明显", "无明显", "不存在明显", "未见挤压", "未见压扁", "未见变形",
        "自然下垂", "普通弧度", "正常弧度", "正常弯曲", "正常转弯", "盘绕", "弧形", "轻微", "略微",
    ]
    if any(term in text for term in negative_patterns):
        return False
    # Generic “明显/严重弯折” is not enough; require concrete visual evidence of flow-blocking deformation.
    strict_patterns = [
        "锐角折弯", "锐角弯折", "死弯", "压扁", "明显压扁", "挤压变形",
        "折痕闭合", "管道闭合", "通水路径被阻断", "通水受阻", "近乎闭合", "严重扭曲变形",
    ]
    return any(term in text for term in strict_patterns)


def remove_unsupported_bend_label(labels: list[str], evidence: str) -> tuple[list[str], bool]:
    bend_label = "\u6d88\u9632\u8f6f\u7ba1\u5377\u76d8\u4f9b\u6c34\u7ba1\u9053\u6298\u5f2f\u4e25\u91cd"
    if bend_label in labels and not evidence_supports_severe_bend(evidence):
        return [label for label in labels if label != bend_label], True
    return list(labels), False

def format_judge_json(reviewed_text: str, raw_report: str = "") -> str | None:
    data = extract_json_object(reviewed_text)
    if not data:
        return None
    labels = normalize_label_list(data.get("labels"))
    scope = str(data.get("scope") or "无法判断").strip()
    if "外观" in scope:
        scope = "箱体外观"
    elif "内部" in scope:
        scope = "内部组件"
    elif scope not in {"箱体外观", "内部组件", "无法判断"}:
        scope = "无法判断"
    verdict = str(data.get("verdict") or "无法判断").strip()
    if verdict not in {"合规", "不合规", "无法判断"}:
        verdict = "不合规" if labels else "无法判断"
    if labels and verdict == "合规":
        verdict = "不合规"
    if not labels and verdict == "不合规":
        verdict = "无法判断" if data.get("needs_manual_review") else "合规"
    evidence = stable_evidence_or_raw(str(data.get("visible_evidence") or "").strip(), raw_report)
    labels, removed_glass, evidence = remove_glass_door_label(labels, evidence)
    labels, removed_missing = remove_contradictory_missing_labels(labels, evidence)
    context_text = "\n".join(part for part in [evidence, reviewed_text, raw_report] if part)
    labels, removed_reference_missing, reference_groups = remove_reference_like_missing_labels(labels, context_text)
    labels, removed_bend = remove_unsupported_bend_label(labels, evidence)
    if removed_glass and not labels and not removed_bend:
        verdict = "合规"
        evidence = evidence or "当前未见其他明确外观隐患。"
    if removed_bend and not labels:
        verdict = "\u5408\u89c4"
        evidence = "\u672a\u89c1\u4f9b\u6c34\u7ba1\u9053\u660e\u663e\u9510\u89d2\u6298\u5f2f\u6216\u6324\u538b\u53d8\u5f62\uff0c\u5f53\u524d\u4e0d\u652f\u6301\u5224\u5b9a\u4e3a\u201c\u6d88\u9632\u8f6f\u7ba1\u5377\u76d8\u4f9b\u6c34\u7ba1\u9053\u6298\u5f2f\u4e25\u91cd\u201d\u3002"
    elif removed_bend:
        evidence = evidence + "\uff1b\u4f9b\u6c34\u7ba1\u9053\u672a\u89c1\u660e\u663e\u9510\u89d2\u6298\u5f2f\u6216\u6324\u538b\u53d8\u5f62\uff0c\u5df2\u6392\u9664\u201c\u6298\u5f2f\u4e25\u91cd\u201d\u6807\u7b7e\u3002"
    if removed_reference_missing and not labels:
        verdict = "\u5408\u89c4"
        visible_parts = []
        if reference_groups.get("reel"):
            visible_parts.append("\u5377\u76d8")
        if reference_groups.get("valve"):
            visible_parts.append("\u624b\u8f6e/\u6813\u53e3")
        if reference_groups.get("hose"):
            visible_parts.append("\u6c34\u5e26")
        if reference_groups.get("gun"):
            visible_parts.append("\u6c34\u67aa\u5f62\u6001\u7269")
        part_text = "\u3001".join(visible_parts) if visible_parts else "\u4e3b\u8981\u5185\u90e8\u7ec4\u4ef6"
        evidence = f"\u56fe\u4e2d{part_text}\u4e0e\u53c2\u8003\u56fe\u6784\u6210\u63a5\u8fd1\uff0c\u5f53\u524d\u4e0d\u652f\u6301\u2018\u6c34\u67aa/\u6c34\u5e26\u7f3a\u5931\u2019\u7c7b\u7ed3\u8bba\u3002"
    elif removed_reference_missing:
        evidence = evidence + "\uff1b\u56fe\u4e2d\u4e3b\u8981\u5185\u90e8\u7ec4\u4ef6\u4e0e\u53c2\u8003\u56fe\u6784\u6210\u63a5\u8fd1\uff0c\u5df2\u6392\u9664\u7f3a\u5931\u7c7b\u6807\u7b7e\u3002"
    elif removed_missing and not labels:
        verdict = "\u65e0\u6cd5\u5224\u65ad"
        evidence = "\u56fe\u4e2d\u53ef\u89c1\u7591\u4f3c\u6c34\u67aa\u6216\u6c34\u5e26\u5f62\u6001\u7269\uff0c\u5bf9\u5e94\u7f3a\u5931\u9879\u8bc1\u636e\u4e0d\u8db3\uff0c\u5efa\u8bae\u4eba\u5de5\u590d\u6838\u3002"
    elif removed_missing:
        evidence = evidence + "\uff1b\u7591\u4f3c\u6c34\u67aa/\u6c34\u5e26\u5f62\u6001\u7269\u53ef\u89c1\uff0c\u5df2\u6392\u9664\u5bf9\u5e94\u7f3a\u5931\u6807\u7b7e\u3002"
    if labels and verdict == "\u5408\u89c4":
        verdict = "\u4e0d\u5408\u89c4"
    if not labels and verdict == "\u4e0d\u5408\u89c4":
        verdict = "\u65e0\u6cd5\u5224\u65ad" if data.get("needs_manual_review") else "\u5408\u89c4"
    if not evidence:
        evidence = "该项隐患在当前图片中未形成清晰、可核验的视觉证据。" if verdict == "无法判断" else "未见明确隐患。"
    return "\n".join([
        f"\u68c0\u67e5\u8303\u56f4\uff1a{scope}",
        f"\u7ed3\u8bba\uff1a{verdict}",
        f"\u53ef\u89c1\u4f9d\u636e\uff1a{evidence}",
        "\u9690\u60a3\u6807\u7b7e\uff1a" + ("\uff1b".join(labels) if labels else "\u65e0"),
    ])

def guarded_format_judge_json(reviewed_text: str, raw_report: str) -> str | None:
    data = extract_json_object(reviewed_text)
    if not data:
        return None
    first_labels = labels_from_report(raw_report)
    labels = normalize_label_list(data.get("labels"))
    added = [x for x in labels if x not in first_labels]
    confidence = str(data.get("confidence") or "\u4e2d").strip()
    needs_manual = bool(data.get("needs_manual_review")) or confidence == "\u4f4e"

    # Block additions only when the judge itself says confidence is low or manual review is needed.
    if added and (confidence == "低" or needs_manual):
        labels = [x for x in labels if x in first_labels]
        data["labels"] = labels
        data["added_to_first"] = []
        data["verdict"] = "无法判断" if not labels else "不合规"
        data["needs_manual_review"] = True
        data["confidence"] = "低"
        needs_manual = True

    formatted = format_judge_json(json.dumps(data, ensure_ascii=False), raw_report=raw_report)
    return formatted
