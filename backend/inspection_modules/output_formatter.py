from __future__ import annotations

import re

from .labels import APPEARANCE_LABELS, INTERNAL_LABELS
from .parser import labels_from_report, report_fields_for_trace, suggestions_from_report


APPEARANCE_ISSUE_TEXT = {
    "室内消火栓箱门未清晰标注中文“消火栓”字样": "箱门表面未清晰标注中文“消火栓”字样，影响设施识别。",
    "室内消火栓箱门标识模糊": "箱门表面的中文“消火栓”标识存在模糊、脱落或难以辨认情况。",
    "室内消火栓箱体或箱门被物品遮挡": "箱体或箱门被物品遮挡，影响消火栓识别、开启或正常使用。",
}

SUGGESTION_TEXT = {
    "室内消火栓箱体无铭牌": "画面中未见清晰铭牌，建议后续巡检时补充核验铭牌信息；该项不作为本次合格性判定依据。",
    "室内消火栓箱体铭牌模糊": "画面中铭牌信息不够清晰，建议后续巡检时补充核验铭牌信息；该项不作为本次合格性判定依据。",
    "室内消火栓箱操作说明缺失或不清晰": "画面中操作说明未见或不够清晰，建议后续巡检时补充核验；该项不作为本次合格性判定依据。",
    "室内消火栓箱门英文“FIRE HYDRANT”字样缺失或不清晰": "画面中英文“FIRE HYDRANT”字样未见或不够清晰，建议后续巡检时补充核验；该项不作为本次合格性判定依据。",
}

INTERNAL_ISSUE_TEXT = {
    "室内消火栓手轮缺失": "室内消火栓手轮缺失。",
    "室内消火栓栓口方向错误": "室内消火栓栓口方向错误。",
    "室内消火栓无消防水带": "室内消火栓消防水带缺失。",
    "室内消火栓无消防水枪": "室内消火栓消防水枪缺失。",
    "室内消火栓消防接口缺失": "室内消火栓消防接口缺失。",
    "消防软管卷盘供水管道折弯严重": "消防软管卷盘供水管道存在严重折弯。",
    "室内消火栓无箱体": "室内消火栓箱体缺失。",
    "室内消火栓箱锈蚀": "室内消火栓箱体存在锈蚀。",
    "室内消火栓箱门缺失": "室内消火栓箱门缺失。",
}



def _split_labels(labels: list[str]) -> tuple[list[str], list[str]]:
    appearance = [label for label in labels if label in APPEARANCE_LABELS]
    internal = [label for label in labels if label in INTERNAL_LABELS]
    return appearance, internal


def _join_sentences(items: list[str]) -> str:
    return "；".join(item.rstrip("。；;") for item in items if item).rstrip("；") + "。"


def _compliant_appearance_text() -> str:
    return (
        "画面主体为室内消火栓箱体，箱体外观完整规整，整体结构完好无破损、无变形。"
        "消火栓箱门闭合完好，箱门表面中文“消火栓”标识可识别，未见明显遮挡或影响开启使用的异常。"
        "整体外观状态符合本次必要合规判定要求。"
    )


def _compliant_internal_text() -> str:
    return (
        "该室内消火栓内部各组件配置齐全，消火栓手轮、消防接口、消防水带、消防水枪、"
        "消防软管卷盘及栓头阀体均完好在位，无缺失。"
    )


def _clean_evidence(evidence: str) -> str:
    text = (evidence or "").strip()
    if not text:
        return ""
    text = re.sub(
        r"^[^。；;，,]*(?:YOLO|辅助检测|大模型|二次复核|复核模型|首轮|QwenVL|模型)[^。；;，,]*[，,]\s*",
        "",
        text,
    )
    replacements = [
        ("按检测合格内容描述", "状态未见明确异常"),
        ("其余画面可见组件未发现明确异常，", "画面中其余可见组件未发现明确异常，"),
        ("其余画面可见组件未发现明确异常", "画面中其余可见组件未发现明确异常"),
        ("YOLO辅助检测", ""),
        ("YOLO 辅助检测", ""),
        ("YOLO", ""),
        ("大模型", ""),
        ("复核模型", ""),
        ("二次复核", ""),
        ("专项复核", ""),
        ("首轮", ""),
        ("QwenVL", ""),
        ("参考图", "画面"),
        ("与画面构成接近", "可见"),
        ("候选框", "可见区域"),
        ("已排除对应缺失类误报", "未见对应部件缺失的明确证据"),
        ("已排除对应缺失标签", "未见对应部件缺失的明确证据"),
        ("已排除缺失类标签", "未见对应部件缺失的明确证据"),
        ("当前不支持判定为", "未见明确证据表明"),
        ("当前不支持", "未见明确证据支持"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    text = re.sub(r"模型[^。；;，,]*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip("。；; ") + "。"


def _remove_suggestion_observations(evidence: str) -> str:
    text = _clean_evidence(evidence)
    if not text:
        return ""
    suggestion_terms = ("铭牌", "操作说明", "FIRE HYDRANT", "英文")
    negative_terms = ("未见", "缺失", "模糊", "不清晰", "未标注", "难以辨认", "未采用", "非耐久")
    cleaned_sentences: list[str] = []
    for raw in text.replace("；", "。").split("。"):
        sentence = raw.strip(" ，,;；。")
        if not sentence:
            continue
        if any(term in sentence for term in suggestion_terms) and any(term in sentence for term in negative_terms):
            sentence = re.sub(r"[，,；;]?\s*(但|但是)?[^。；;，,]*(铭牌|操作说明|FIRE HYDRANT|英文)[^。；;，,]*", "", sentence).strip(" ，,;；")
            if not sentence:
                continue
        cleaned_sentences.append(sentence)
    return "。".join(cleaned_sentences).strip("。") + ("。" if cleaned_sentences else "")


def _evidence_is_useful(evidence: str) -> bool:
    text = _clean_evidence(evidence)
    if len(text) < 12 or len(text) > 280:
        return False
    if text.count("、") + text.count("，") + text.count(",") > 14:
        return False
    repeated_terms = ("密封圈", "发黄", "发蓝", "发绿", "发紫", "发黑", "发白")
    if any(text.count(term) >= 4 for term in repeated_terms):
        return False
    vague_words = ("可见依据", "当前图片中存在不符合", "证据不足")
    return not any(word == text.rstrip("。") for word in vague_words)


def _compliant_text(scope: str, evidence: str = "") -> str:
    if _evidence_is_useful(evidence):
        return _clean_evidence(evidence)
    if "外观" in scope:
        return _compliant_appearance_text()
    if "内部" in scope:
        return _compliant_internal_text()
    return _compliant_appearance_text() + "\n\n" + _compliant_internal_text()


def _scope_issue_prefix(scope: str, labels: list[str]) -> str:
    appearance_labels, internal_labels = _split_labels(labels)
    if "外观" in scope or (appearance_labels and not internal_labels):
        return "室内消火栓外观具体隐患表现在："
    if "内部" in scope or (internal_labels and not appearance_labels):
        return "室内消火栓内部各组件具体隐患表现在："
    return "室内消火栓具体隐患表现在："


def _fallback_issue_text(labels: list[str], scope: str) -> str:
    appearance_labels, internal_labels = _split_labels(labels)
    parts: list[str] = []
    if appearance_labels:
        parts.extend(APPEARANCE_ISSUE_TEXT[label] for label in appearance_labels if label in APPEARANCE_ISSUE_TEXT)
    if internal_labels:
        parts.extend(INTERNAL_ISSUE_TEXT[label] for label in internal_labels if label in INTERNAL_ISSUE_TEXT)
    if parts:
        return _scope_issue_prefix(scope, labels) + _join_sentences(parts)
    return _scope_issue_prefix(scope, labels) + "当前图片中存在不符合合规要求的可见情况。"


def _noncompliant_text(labels: list[str], evidence: str, scope: str) -> str:
    evidence_text = _clean_evidence(evidence)
    if _evidence_is_useful(evidence_text):
        return _scope_issue_prefix(scope, labels) + evidence_text
    return _fallback_issue_text(labels, scope)


def _suggestions_text(suggestions: list[str]) -> str:
    return "该功能建设中"

def format_public_report(structured_report: str) -> str:
    fields = report_fields_for_trace(structured_report)
    scope = str(fields.get("scope") or "")
    verdict = str(fields.get("verdict") or "")
    labels = labels_from_report(structured_report)
    suggestions = suggestions_from_report(structured_report)
    evidence = ""
    for line in (structured_report or "").splitlines():
        if line.strip().startswith("可见依据："):
            evidence = line.split("：", 1)[1].strip()
            break

    is_qualified = verdict == "合规" and not labels
    conclusion = "合格" if is_qualified else "不合格"
    body_evidence = _remove_suggestion_observations(evidence) if is_qualified and suggestions else evidence
    body = _compliant_text(scope, body_evidence) if is_qualified else _noncompliant_text(labels, evidence, scope)

    return "\n".join([
        f"一、检测结论：{conclusion}",
        body,
        "",
        "二、涉及法律法规",
        "该功能建设中",
        "",
        "三、整改建议",
        _suggestions_text(suggestions),
    ])
