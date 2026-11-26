"""Resolve an uncertain pressure reading using the dial and visible needle tip."""
import math

from backend.modules.inspection.image_evidence import image_review_content, normalized_box
from backend.modules.inspection.parser import extract_json_object


PRESSURE_LABEL = "灭火器压力指示异常"


def review_pressure(model, image, detections):
    candidates = [item for item in detections.get("detections", [])
                  if item.get("className") == "灭火器/压力指示器"
                  or item.get("label") == "灭火器压力指示器"]
    if not candidates:
        return None, {}, "no_dial_candidate"
    prompt = (
        "只复核灭火器压力表。不要判断设备整体合规性。"
        "沿中心轴向外找真正细长指针及针尖，不要把色区分界、粗刻度、弹簧反光当作指针。"
        "照片可能倾斜，针尖所在颜色区域不随画面旋转改变。"
        "分别检查针尖和色带是否能从原始像素辨认，不能凭表盘有绿色就说正常。"
        "只有针尖与色带均清晰时readable=true，否则false并band=unknown。"
        "返回原图归一化坐标，不用局部裁剪坐标。只输出严格JSON："
        '{"readable":false,"band":"red|green|yellow|unknown","confidence":0.0,'
        '"dial_bbox":[0.1,0.1,0.5,0.5],"needle_tip":[0.3,0.4]}。'
        "最多选择一个清楚的表盘；多个表盘读数不一致则返回unknown。"
    )
    try:
        response = model.invoke([{"role": "user", "content": image_review_content(
            image, prompt, {**detections, "detections": candidates})}])
    except Exception:
        return None, {}, "pressure_review_unavailable"
    data = extract_json_object(response.content) or {}
    box, tip = normalized_box(data.get("dial_bbox")), data.get("needle_tip")
    confidence = data.get("confidence")
    valid = (
        data.get("readable") is True and data.get("band") in ("red", "green", "yellow")
        and isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
        and math.isfinite(confidence) and 0.85 <= confidence <= 1
        and box and isinstance(tip, list) and len(tip) == 2
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in tip)
        and box[0] <= tip[0] <= box[2] and box[1] <= tip[1] <= box[3]
    )
    if not valid:
        return None, response.usage, "needle_or_band_uncertain"
    if (box[2] - box[0]) * detections.get("imageWidth", 0) < 32 or (
        box[3] - box[1]) * detections.get("imageHeight", 0) < 32:
        return None, response.usage, "insufficient_original_pixels"
    # A precise reading must refer to a detected dial, not a whole-scene box.
    def same_dial(item):
        candidate = normalized_box(item.get("bboxNorm"))
        if not candidate:
            return False
        intersection = max(0, min(box[2], candidate[2]) - max(box[0], candidate[0])) * max(
            0, min(box[3], candidate[3]) - max(box[1], candidate[1]))
        area = (box[2] - box[0]) * (box[3] - box[1])
        other_area = (candidate[2] - candidate[0]) * (candidate[3] - candidate[1])
        return intersection / (area + other_area - intersection) >= 0.5
    if not any(same_dial(item) for item in candidates):
        return None, response.usage, "dial_location_mismatch"
    color = {"red": "红", "green": "绿", "yellow": "黄"}[data["band"]]
    observation = {"id": "pressure_detail", "text": f"表盘针尖清晰可辨，位于{color}色区域。",
                   "bbox": box, "kind": "reading", "readable": True,
                   "coverage_complete": False, "needleTip": tip}
    return {"observation": observation, "state": "refuted" if data["band"] == "green" else "supported"}, response.usage, ""
