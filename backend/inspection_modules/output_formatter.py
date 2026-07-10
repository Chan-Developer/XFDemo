from __future__ import annotations

from .labels import APPEARANCE_LABELS, INTERNAL_LABELS
from .parser import labels_from_report, report_fields_for_trace


APPEARANCE_ISSUE_TEXT = {
    "室内消火栓箱明显部位未采用耐久性文字或图形标注操作说明": "箱体明显部位未见室内消火栓使用说明，或使用说明残缺不清。",
    "室内消火栓箱门上未标注“消火栓”和英文“FIRE HYDRANT”字样": "箱门表面未清晰标注中文“消火栓”标识及英文“FIRE HYDRANT”标准字样。",
    "室内消火栓箱体无铭牌": "箱体铭牌缺失，未见清晰可核验的产品铭牌信息。",
    "室内消火栓箱门标识模糊": "箱门表面的中文“消火栓”或英文“FIRE HYDRANT”标识存在模糊、脱落或难以辨认情况。",
    "室内消火栓箱体铭牌模糊": "箱体铭牌内容模糊，铭牌信息难以清晰辨认。",
    "室内消火栓箱门为玻璃门": "箱门为透明或半透明玻璃门结构，不符合当前外观合规判断要求。",
    "室内消火栓箱体或箱门被物品遮挡": "箱体或箱门被物品遮挡，影响消火栓识别、开启或正常使用。",
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
        "消火栓箱门闭合完好，安装规范。"
        "箱门表面清晰印刷中文“消火栓”标识及英文“FIRE HYDRANT”标准字样。"
        "箱体表面张贴室内消火栓使用说明，内容完整、展示清晰。"
        "整体消火栓箱体各外观组件配置齐全，安装规范，外观状态完好，符合合规无隐患标准。"
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
    replacements = [
        ("按检测合格内容描述", "状态未见明确异常"),
        ("其余画面可见组件未发现明确异常，", "画面中其余可见组件未发现明确异常，"),
        ("其余画面可见组件未发现明确异常", "画面中其余可见组件未发现明确异常"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text.rstrip("。；; ") + "。"


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


def format_public_report(structured_report: str) -> str:
    fields = report_fields_for_trace(structured_report)
    scope = str(fields.get("scope") or "")
    verdict = str(fields.get("verdict") or "")
    labels = labels_from_report(structured_report)
    evidence = ""
    for line in (structured_report or "").splitlines():
        if line.strip().startswith("可见依据："):
            evidence = line.split("：", 1)[1].strip()
            break

    is_qualified = verdict == "合规" and not labels
    conclusion = "合格" if is_qualified else "不合格"
    body = _compliant_text(scope, evidence) if is_qualified else _noncompliant_text(labels, evidence, scope)

    return "\n".join([
        f"一、检测结论：{conclusion}",
        body,
        "",
        "二、涉及法律法规",
        "该功能建设中",
        "",
        "三、整改建议",
        "该功能建设中",
    ])
