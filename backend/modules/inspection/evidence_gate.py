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
            "rejected": rejected, "scopeComplete": data.get("scope_complete") is True}


def render_evidence(review: dict, scope: str, observation_only: bool = False) -> tuple[str, str]:
    observations = {row["id"]: row for row in review["observations"]}
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
        "只有原始像素足以分辨才可readable=true；表盘绿色背景不等于指针在绿色区。"
        "缺失用kind=absence，只有应存放区域完整可见、无遮挡且确实为空才可coverage_complete=true。"
        "YOLO未检出不是缺失证据；部分照片不能证明全部齐全。"
        "每条观察只能描述一项事实，保持简短，不输出建议、法规或合规结论。"
        f"需要核验的标签为：{allowed}。每个标签都输出一个check，"
        "supported表示异常成立，refuted表示图像明确排除该异常，uncertain表示无法判断。"
        "supported/refuted必须引用实际支持该项判断的observation id，不得借用无关位置或否定句作异常依据。"
        "若只做组件描述，checks为空。最多8条观察，不逐字抄写设备编号。"
        '\n严格JSON：{"observations":[{"id":"e1","text":"位置+可见事实",'
        '"bbox":[0.1,0.1,0.5,0.5],"kind":"visual|reading|absence",'
        '"readable":false,"coverage_complete":false}],'
        '"checks":[{"label":"指定标签","state":"supported|refuted|uncertain",'
        '"evidence_ids":["e1"],"readable":false,"coverage_complete":false}],'
        '"scope_complete":false}。scope_complete仅在本次检查范围全部可清楚核验时为true。'
    )
    usage, error = {}, ""
    try:
        response = model.invoke([{"role": "user", "content": image_review_content(image, prompt, detections)}])
        usage = response.usage
        data = extract_json_object(response.content)
        if data is None:
            error = "invalid_evidence_json"
    except Exception:
        data, error = None, "evidence_review_unavailable"
    review = validate_evidence(data, allowed, detections)
    review["error"] = error
    review["removedDraftLabels"] = [label for label in labels_from_report(draft) if label not in review["labels"]]
    structured, public = render_evidence(review, scope, observation_only)
    return structured, public, review, usage
