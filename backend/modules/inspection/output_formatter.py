from __future__ import annotations

import re

from backend.modules.inspection.labels import APPEARANCE_LABELS, INTERNAL_LABELS
from backend.modules.inspection.parser import labels_from_report, report_fields_for_trace, suggestions_from_report


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


LEGAL_BASIS_TEXT = (
    "《中华人民共和国消防法》第十六条要求单位按照国家标准、行业标准配置消防设施、器材，"
    "并定期组织检验、维修，确保完好有效；第二十八条规定不得损坏、挪用或者擅自拆除、"
    "停用消防设施、器材。具体适用要求以现场核查、现行消防技术标准及主管部门意见为准。"
)


REMEDIATION_TEXT = {
    "室内消火栓箱门未清晰标注中文“消火栓”字样": "在箱门醒目位置补充清晰、耐久的中文“消火栓”标识，并复核远距离辨识效果。",
    "室内消火栓箱门标识模糊": "修复或更换模糊、脱落的箱门标识，确保中文“消火栓”字样清晰可辨。",
    "室内消火栓箱体或箱门被物品遮挡": "立即清理箱体和箱门周边遮挡物，保证设施易于识别、箱门能够正常开启。",
    "室内消火栓手轮缺失": "补装与阀体规格匹配的手轮，并由维保人员检查启闭是否顺畅。",
    "室内消火栓栓口方向错误": "由专业维保人员复核栓口安装方向并调整，确保水带连接和展开不受箱体结构影响。",
    "室内消火栓无消防水带": "补配规格匹配的消防水带，检查接口兼容性并按便于取用的方式放置。",
    "室内消火栓无消防水枪": "补配与现有水带接口匹配的消防水枪，固定放置后进行连接和取用检查。",
    "室内消火栓消防接口缺失": "补装规格匹配的消防接口，完成连接可靠性和密封性检查。",
    "消防软管卷盘供水管道折弯严重": "理顺或更换受压折弯的供水软管，确认管壁恢复、通水路径畅通后再投入使用。",
    "室内消火栓无箱体": "按现场条件补设符合要求的消火栓箱体，并检查内部组件固定和防护状态。",
    "室内消火栓箱锈蚀": "清理锈斑和剥落层，进行除锈、防腐及补漆；如箱体强度或启闭功能受影响，应更换受损部件。",
    "室内消火栓箱门缺失": "补装与箱体匹配的箱门，检查开启角度、闭合状态及取用空间。",
}


LABEL_EVIDENCE_TERMS = {
    "室内消火栓箱门未清晰标注中文“消火栓”字样": (("箱门",), ("消火栓", "标识", "字样")),
    "室内消火栓箱门标识模糊": (("箱门",), ("标识", "字样", "模糊")),
    "室内消火栓箱体或箱门被物品遮挡": (("遮挡",),),
    "室内消火栓手轮缺失": (("手轮",),),
    "室内消火栓栓口方向错误": (("栓口",), ("方向", "朝向")),
    "室内消火栓无消防水带": (("水带",),),
    "室内消火栓无消防水枪": (("水枪",),),
    "室内消火栓消防接口缺失": (("接口",),),
    "消防软管卷盘供水管道折弯严重": (("软管",), ("折弯", "锐角", "折痕", "压扁")),
    "室内消火栓无箱体": (("箱体",),),
    "室内消火栓箱锈蚀": (("锈蚀", "锈迹", "锈斑", "锈点", "腐蚀"),),
    "室内消火栓箱门缺失": (("箱门",),),
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


YOLO_COMPONENT_DISPLAY = {
    "水带": "消防水带",
    "水枪": "消防水枪",
    "软管": "消防软管卷盘供水软管",
    "手轮": "消火栓手轮",
    "接口": "消防接口",
    "栓体": "消火栓栓体",
    "阀门": "阀门",
    "控制器": "报警控制器",
}

YOLO_COMPONENT_ORDER = tuple(YOLO_COMPONENT_DISPLAY)


def _visible_yolo_components(yolo_result: dict | None) -> list[str]:
    detected: set[str] = set()
    for item in (yolo_result or {}).get("detections") or []:
        label = str(item.get("label") or item.get("component") or "").strip()
        if label in YOLO_COMPONENT_DISPLAY:
            detected.add(label)
    return [YOLO_COMPONENT_DISPLAY[label] for label in YOLO_COMPONENT_ORDER if label in detected]


def _visible_component_text(yolo_result: dict | None) -> str:
    components = _visible_yolo_components(yolo_result)
    if not components:
        return ""
    return f"画面中可见{'、'.join(components)}等组件，当前可见范围内未见上述组件缺失。"


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
    text = re.sub(r"根据复核原则第\d+条(?:及兜底提示)?[，,]?", "", text)
    text = re.sub(r"模型[^。；;，,]*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip("。；; ") + "。"


def _compact_evidence(evidence: str, max_chars: int = 900) -> str:
    text = _clean_evidence(evidence)
    if not text:
        return ""
    clauses: list[str] = []
    for raw in re.split(r"[。；;]", text):
        clause = raw.strip(" ，,;；。")
        if clause and clause not in clauses:
            clauses.append(clause)
    selected: list[str] = []
    current_length = 0
    for clause in clauses:
        extra = len(clause) + (1 if selected else 0)
        if selected and current_length + extra > max_chars:
            break
        if not selected and len(clause) > max_chars:
            selected.append(clause[:max_chars].rstrip("，,;； "))
            break
        selected.append(clause)
        current_length += extra
    return "。".join(selected).rstrip("。") + ("。" if selected else "")

# 当最终结论是合格时，从正文证据中删除铭牌、操作说明、英文标识等建议项描述
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
    text = _compact_evidence(evidence)
    if len(text) < 12:
        return False
    if text.count("、") + text.count("，") + text.count(",") > 40:
        return False
    repeated_terms = ("密封圈", "发黄", "发蓝", "发绿", "发紫", "发黑", "发白")
    if any(text.count(term) >= 4 for term in repeated_terms):
        return False
    vague_words = ("可见依据", "当前图片中存在不符合", "证据不足")
    return not any(word == text.rstrip("。") for word in vague_words)


def _compliant_text(scope: str, evidence: str = "", yolo_result: dict | None = None) -> str:
    evidence_text = _compact_evidence(evidence)
    component_text = _visible_component_text(yolo_result) if "内部" in scope else ""
    if _evidence_is_useful(evidence_text):
        return component_text + evidence_text
    if "外观" in scope:
        return _compliant_appearance_text()
    if "内部" in scope:
        return component_text or _compliant_internal_text()
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


def _unsupported_evidence_labels(labels: list[str], evidence: str) -> list[str]:
    text = _clean_evidence(evidence)
    unsupported: list[str] = []
    for label in labels:
        term_groups = LABEL_EVIDENCE_TERMS.get(label)
        if not term_groups:
            continue
        if not all(any(term in text for term in group) for group in term_groups):
            unsupported.append(label)
    return unsupported


def _noncompliant_text(labels: list[str], evidence: str, scope: str) -> str:
    evidence_text = _compact_evidence(evidence)
    if _evidence_is_useful(evidence_text):
        unsupported = _unsupported_evidence_labels(labels, evidence_text)
        if not unsupported:
            return _scope_issue_prefix(scope, labels) + evidence_text
        supported = [label for label in labels if label not in unsupported]
        fallback_parts = [
            APPEARANCE_ISSUE_TEXT.get(label) or INTERNAL_ISSUE_TEXT.get(label)
            for label in unsupported
        ]
        fallback_parts = [item for item in fallback_parts if item]
        if supported and fallback_parts:
            return _scope_issue_prefix(scope, labels) + _join_sentences([evidence_text, *fallback_parts])
        if fallback_parts:
            return _scope_issue_prefix(scope, labels) + _join_sentences(fallback_parts)
    return _fallback_issue_text(labels, scope)


def _suggestions_text(labels: list[str], suggestions: list[str], verdict: str) -> str:
    items = [REMEDIATION_TEXT[label] for label in labels if label in REMEDIATION_TEXT]
    items.extend(SUGGESTION_TEXT[item] for item in suggestions if item in SUGGESTION_TEXT)
    items = list(dict.fromkeys(items))
    if items:
        return "\n".join(f"{index}. {item}" for index, item in enumerate(items, 1))
    if verdict == "无法判断":
        return "建议补拍包含完整箱体或箱内主要存放区域的清晰照片，再由巡检人员复核。"
    return "建议保持设施现状并纳入日常巡检，定期检查组件在位、启闭和外观状态。"


def _unknown_text(evidence: str) -> str:
    evidence_text = _compact_evidence(evidence)
    if _evidence_is_useful(evidence_text):
        return evidence_text
    return "当前图片未形成可核验的室内消火栓目标或合规/隐患证据，建议重新上传包含消火栓箱体或内部组件的清晰图片。"

def format_public_report(structured_report: str, yolo_result: dict | None = None) -> str:
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

    is_unknown = verdict == "无法判断"
    is_qualified = verdict == "合规" and not labels
    conclusion = "无法判断" if is_unknown else ("合格" if is_qualified else "不合格")
    body_evidence = _remove_suggestion_observations(evidence) if is_qualified and suggestions else evidence
    if is_unknown:
        body = _unknown_text(evidence)
    else:
        body = _compliant_text(scope, body_evidence, yolo_result) if is_qualified else _noncompliant_text(labels, evidence, scope)

    return "\n".join([
        f"一、检测结论：{conclusion}",
        body,
        "",
        "二、涉及法律法规",
        LEGAL_BASIS_TEXT,
        "",
        "三、整改建议",
        _suggestions_text(labels, suggestions, verdict),
    ])
