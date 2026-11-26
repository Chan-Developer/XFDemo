"""Review the image independently and render only linked, validated observations.

Coordinates are audit anchors, not proof that a VLM observation is correct.
Malformed/incomplete reviews cannot silently restore the draft's verdict.
"""
from __future__ import annotations

import re
from typing import Any

from backend.modules.inspection.image_evidence import image_review_content, normalized_box
from backend.modules.inspection.labels import APPEARANCE_LABELS, BRANCH_LABELS, INTERNAL_LABELS
from backend.modules.inspection.parser import extract_json_object, labels_from_report


# Require the cited observation to actually concern the checked component.
# In particular, a hose reel's soft tube is not evidence of a fire hose.
TARGET_TERMS = {
    "室内消火栓手轮缺失": (("手轮",),),
    "室内消火栓栓口方向错误": (("栓口", "接口", "出水口"), ("方向", "朝向")),
    "室内消火栓无消防水带": (("水带",),),
    "室内消火栓无消防水枪": (("水枪",),),
    "室内消火栓消防接口缺失": (("接口", "栓口", "出水口"),),
    "消防软管卷盘供水管道折弯严重": (("软管", "供水管"), ("折弯", "弯折", "压扁", "折痕")),
    "室内消火栓无箱体": (("箱体", "箱壁", "箱底"),),
    "室内消火栓箱锈蚀": (("箱",), ("锈", "腐蚀")),
    "室内消火栓箱门缺失": (("箱门", "门体"),),
    "室内消火栓箱门未清晰标注中文“消火栓”字样": (("箱门", "门面"), ("标识", "字样", "文字")),
    "室内消火栓箱门标识模糊": (("箱门", "门面"), ("标识", "字样", "文字")),
    "室内消火栓箱体或箱门被物品遮挡": (("箱",), ("遮挡", "挡住", "阻挡")),
    "室内消火栓箱操作说明缺失或不清晰": (("操作说明", "使用说明", "说明图"),),
    "室外消火栓本体缺失或无法确认": (("栓体", "消火栓"),),
    "室外消火栓被遮挡或圈占": (("消火栓", "栓体"), ("遮挡", "圈占", "通道", "阻挡")),
    "室外消火栓明显破损或锈蚀": (("栓体", "消火栓"), ("破损", "锈", "腐蚀", "变形")),
    "室外消火栓标识缺失或不可辨": (("标识", "铭牌", "字样"),),
    "灭火器缺失或数量不足": (("灭火器",),),
    "灭火器压力指示异常": (("表盘", "指针", "压力"),),
    "灭火器压力指示器不可辨": (("表盘", "指针", "压力"),),
    "灭火器喷管或压把缺失损坏": (("喷管", "压把", "保险"),),
    "灭火器瓶体明显破损或锈蚀": (("瓶体", "筒体"), ("破损", "锈", "腐蚀", "变形")),
    "灭火器被遮挡或取用受限": (("灭火器",), ("遮挡", "取用", "通道", "阻挡")),
}


def scope_labels(branch: str, scope: str) -> list[str]:
    if branch == "indoor_hydrant":
        return APPEARANCE_LABELS if scope == "箱体外观" else INTERNAL_LABELS
    return BRANCH_LABELS.get(branch, [])


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", value).strip()[:300] if isinstance(value, str) else ""


def validate_evidence(data: Any, allowed: list[str], detections: dict) -> dict:
    data = data if isinstance(data, dict) else {}
    observations, rejected, seen = {}, [], set()
    rows = data.get("observations")
    for row in (rows if isinstance(rows, list) else [])[:16]:
        if not isinstance(row, dict):
            continue
        key, text = _text(row.get("id")), _text(row.get("text"))
        box = normalized_box(row.get("bbox"))
        reason = ""
        if not key or key in seen or not text or not box:
            reason = "missing_or_invalid_visual_anchor"
        elif not isinstance(row.get("kind"), str) or row["kind"] not in {"visual", "reading", "absence"}:
            reason = "invalid_observation_kind"
        elif any(term in text for term in ("锈死", "运行正常", "功能正常", "启闭正常", "符合规范", "合格", "齐全", "应当", "必须", "建议", "YOLO", "候选框", "模型")):
            reason = "non_visual_claim"
        elif re.search(r"指针|读数|压力正常|压力异常|绿色区|红色区|黄色区", text) and row.get("kind") != "reading":
            reason = "reading_requires_readability_evidence"
        elif re.search(r"\d+(?:\.\d+)?\s*(?:cm|厘米|毫米|米)", text, re.I):
            reason = "unmeasured_distance"
        elif row.get("kind") == "reading" and row.get("readable") is not True:
            reason = "unreadable_detail"
        elif row.get("kind") == "reading" and re.search(r"指针|压力|绿色区|红色区|黄色区", text) and not (
            (box[2] - box[0]) * detections.get("imageWidth", 0) >= 32
            and (box[3] - box[1]) * detections.get("imageHeight", 0) >= 32
        ):
            reason = "insufficient_original_reading_pixels"
        elif "缺失" in text and row.get("kind") != "absence":
            reason = "absence_requires_complete_view"
        elif row.get("kind") == "absence" and row.get("coverage_complete") is not True:
            reason = "incomplete_view_cannot_prove_absence"
        elif re.search(r"取用|通道|周边环境|摆放位置", text) and data.get("capture_context") != "onsite":
            reason = "onsite_context_not_confirmed"
        elif (colors := re.search(r"^(红|黑|白|灰|蓝|黄|绿|银)色[^，；。]*?[，,].*?呈(红|黑|白|灰|蓝|黄|绿|银)色", text)) and colors[1] != colors[2]:
            reason = "contradictory_appearance_claim"
        if key in seen:
            observations.pop(key, None)
        seen.add(key)
        if reason:
            rejected.append({"id": key, "reason": reason})
        else:
            observations[key] = {"id": key, "text": text, "bbox": box, "kind": row["kind"],
                                 "readable": row.get("readable") is True,
                                 "coverage_complete": row.get("coverage_complete") is True}

    checks = {}
    duplicate_checks = set()
    rows = data.get("checks")
    for row in (rows if isinstance(rows, list) else []):
        if not isinstance(row, dict) or not isinstance(row.get("label"), str) or row["label"] not in allowed:
            continue
        label = row["label"]
        if label in checks:
            duplicate_checks.add(label)
        refs = row.get("evidence_ids")
        linked = [observations[k] for k in refs if isinstance(k, str) and k in observations] if isinstance(refs, list) else []
        state = row.get("state")
        valid = bool(linked) and len(linked) == len(refs) and isinstance(state, str) and state in {"supported", "refuted"}
        terms = TARGET_TERMS.get(label, ())
        valid = valid and any(all(any(term in o["text"] for term in group) for group in terms) for o in linked)
        if state == "supported" and ("缺失" in label or "无消防" in label or "无箱体" in label or "数量不足" in label):
            valid = valid and row.get("coverage_complete") is True and any(o["kind"] == "absence" for o in linked)
        if label == "灭火器压力指示异常":
            valid = valid and row.get("readable") is True and any(o["kind"] == "reading" and o["readable"] for o in linked)
            # A tiny original dial cannot become readable by enlarging a crop.
            width, height = detections.get("imageWidth", 0), detections.get("imageHeight", 0)
            valid = valid and any(
                (o["bbox"][2] - o["bbox"][0]) * width >= 32
                and (o["bbox"][3] - o["bbox"][1]) * height >= 32
                for o in linked if o["kind"] == "reading"
            )
        if label == "灭火器压力指示器不可辨" and state == "supported":
            valid = False  # Insufficient evidence is not a confirmed equipment defect.
        checks[label] = {"label": label, "state": state if valid else "uncertain",
                         "evidence_ids": [o["id"] for o in linked] if valid else []}
    for label in allowed:
        if label not in checks or label in duplicate_checks:
            checks[label] = {"label": label, "state": "uncertain", "evidence_ids": []}
    confirmed = [label for label, row in checks.items() if row["state"] == "supported"]
    uncertain = [label for label, row in checks.items() if row["state"] == "uncertain"]
    verdict = "不合规" if confirmed else (
        "合规" if allowed and not uncertain and observations and data.get("scope_complete") is True else "无法判断"
    )
    return {"observations": list(observations.values()), "checks": list(checks.values()),
            "labels": confirmed, "uncertain": uncertain, "verdict": verdict,
            "rejected": rejected, "scopeComplete": data.get("scope_complete") is True,
            "captureContext": data.get("capture_context") if data.get("capture_context") in ("onsite", "product", "unknown") else "unknown"}


def render_evidence(review: dict, scope: str, observation_only: bool = False) -> tuple[str, str]:
    # Numeric anchors stay in the trace; the report uses readable observations.
    observations = {row["id"]: {**row, "text": re.sub(
        r"(?:主体区域|区域|原图坐标)?\s*\[\s*\d[\d.,\s]*\]\s*(?:内)?", "", row["text"]
    ).strip()} for row in review["observations"]}
    lines = []
    used = set()
    for check in review["checks"]:
        if check["state"] == "supported":
            refs = check["evidence_ids"]
            lines.append(check["label"] + "：" + "；".join(observations[k]["text"] for k in refs))
            used.update(refs)
    lines.extend(row["text"] for key, row in observations.items() if key not in used)
    if not lines:
        lines.append("当前图片未形成可核验的图像证据，请补拍主体及关键部位的清晰照片。")
    if review["uncertain"] and not observation_only:
        lines.append("待核验项目：" + "、".join(review["uncertain"]) + "；现有图像证据不足，不能据此断言缺失或正常。")
    evidence = "；".join(lines)
    verdict = review["verdict"]
    structured = (f"检查范围：{scope}\n结论：{verdict}\n可见依据：{evidence}\n隐患标签："
                  + ("；".join(review["labels"]) or "无") + "\n建议项：无")
    conclusion = "未开展合规判定" if observation_only else {
        "不合规": "不合格", "合规": "合格", "无法判断": "无法判断"
    }[verdict]
    if not observation_only:
        lines.insert(0, "本结论仅针对下列图像证据对应的可见检查范围，未验证设备运行功能。")
    public = (f"一、检测结论：{conclusion}\n" + "\n".join(lines)
              + ("\n本次仅提供组件识别描述，不据此判定合格或不合格。" if observation_only else "")
              + "\n\n二、涉及法律法规\n本次图像核验未确认具体条款的适用性。"
              + "\n\n三、整改建议\n"
              + ("请现场复核上述有证据支持的异常，并补拍待核验部位。" if review["labels"]
                 else "请按上述观察范围进行现场核验；看不清或未拍到的部位需补拍确认。"))
    return structured, public


def review_image_evidence(model: Any, image: str, branch: str, scope: str,
                          draft: str, detections: dict, observation_only: bool = False) -> tuple[str, str, dict, dict]:
    allowed = [] if observation_only else scope_labels(branch, scope)
    prompt = (
        f"你是独立图像证据核验员，本次主体为{scope}。只核验上传的原图；候选名称可能错。"
        "逐项观察对象、所在位置与可见状态，观察必须给出原图归一化bbox。"
        "不要把灯具当探测器，不猜读模糊表盘或铭牌，不从外观推断锈死、功能或运行状态，"
        "不推测取景外的通道环境、数量、尺寸或配置要求。文字和指针读数用kind=reading，"
        "先判断capture_context：真实安装或使用现场为onsite，白底展示或商品宣传图为product，"
        "局部特写或无法确认现场为unknown。product/unknown不能断言现场通道、取用条件或摆放位置。"
        "只有原始像素足以分辨才可readable=true；表盘绿色背景不等于指针在绿色区。"
        "缺失用kind=absence，只有应存放区域完整可见、无遮挡且确实为空才可coverage_complete=true。"
        "YOLO未检出不是缺失证据；部分照片不能证明全部齐全。"
        "每条观察只能描述一项事实，保持简短，不输出建议、法规或合规结论。"
        "消防软管卷盘的软管不是消防水带，不能以软管在位排除水带缺失。"
        f"需要核验的标签为：{allowed}。每个标签都输出一个check，"
        "supported表示异常成立，refuted表示图像明确排除该异常，uncertain表示无法判断。"
        "supported/refuted必须引用实际支持该项判断的observation id，不得借用无关位置或否定句作异常依据。"
        "若只做组件描述，checks为空。最多4条核心观察，每条不超过50字。"
        "不描述材质、内部结构、型号、认证、无关背景，也不猜测两个设备之间的连线关系。"
        "主体以确认区域为准，避免把旁边的照明灯作为探测器。"
        f"主体确认区域（原图归一化坐标）：{detections.get('subjectBox')}。"
        "所有bbox仅保留4位小数，不要输出计算表达式、注释或省略号。"
        '\n严格JSON：{"observations":[{"id":"e1","text":"位置+可见事实",'
        '"bbox":[0.1,0.1,0.5,0.5],"kind":"visual|reading|absence",'
        '"readable":false,"coverage_complete":false}],'
        '"checks":[{"label":"指定标签","state":"supported|refuted|uncertain",'
        '"evidence_ids":["e1"],"readable":false,"coverage_complete":false}],'
        '"scope_complete":false,"capture_context":"onsite|product|unknown"}。scope_complete仅在本次检查范围全部可清楚核验时为true。'
    )
    usage, error, retry_count, excerpt = {}, "", 0, ""
    try:
        messages = [{"role": "user", "content": image_review_content(image, prompt, detections)}]
        response = model.invoke(messages)
        usage = response.usage
        data = extract_json_object(response.content)
        if data is None:
            retry_count = 1
            messages[0]["content"].append({"type": "text", "text": "上次输出无法作为JSON解析。请重新从原图核验，严格输出一个完整JSON对象；数值只能用十进制常数，禁止算式、注释、尾逗号及省略号。"})
            response = model.invoke(messages)
            usage = {key: (usage or {}).get(key, 0) + (response.usage or {}).get(key, 0)
                     for key in set(usage or {}) | set(response.usage or {})}
            data = extract_json_object(response.content)
            if data is None:
                error, excerpt = "invalid_evidence_json", response.content[:500] + response.content[-500:]
    except Exception:
        data, error = None, "evidence_review_unavailable"
    review = validate_evidence(data, allowed, detections)
    review["error"] = error
    review["formatRetries"] = retry_count
    if excerpt:
        review["parseFailureExcerpt"] = excerpt
    review["removedDraftLabels"] = [label for label in labels_from_report(draft) if label not in review["labels"]]
    structured, public = render_evidence(review, scope, observation_only)
    return structured, public, review, usage
