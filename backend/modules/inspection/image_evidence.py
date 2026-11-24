"""Bounded image context shared by routing and final evidence review."""
from __future__ import annotations

import base64
import io
import json
import math

from PIL import Image


def normalized_box(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in value):
        return None
    box = [float(v) for v in value]
    if not all(math.isfinite(v) and 0 <= v <= 1 for v in box):
        return None
    return box if box[0] < box[2] and box[1] < box[3] else None


def candidate_regions(result: dict | None) -> list[dict]:
    candidates = []
    for item in (result or {}).get("detections") or []:
        box = normalized_box(item.get("bboxNorm"))
        name = str(item.get("className") or item.get("label") or "")
        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            continue
        if not box or not name or not math.isfinite(confidence) or confidence < 0.2:
            continue
        candidates.append({"name": name, "bbox": [round(v, 4) for v in box], "confidence": round(confidence, 4)})
    candidates.sort(key=lambda item: item["confidence"], reverse=True)
    # Keep distinct component types ahead of repeated instances of one class.
    seen, distinct, repeated = set(), [], []
    for item in candidates:
        (repeated if item["name"] in seen else distinct).append(item)
        seen.add(item["name"])
    return (distinct + repeated)[:24]


def conflicting_facility_evidence(branch: str, subject_box, result: dict | None) -> str | None:
    """Only flag coherent rival components at the selected subject's location.

    This does not select a class: it requires a separate image-based resolution.
    """
    subject = normalized_box(subject_box)
    if not subject:
        return None

    def overlaps(box):
        intersection = max(0, min(box[2], subject[2]) - max(box[0], subject[0])) * max(
            0, min(box[3], subject[3]) - max(box[1], subject[1]))
        smaller = min((box[2] - box[0]) * (box[3] - box[1]),
                      (subject[2] - subject[0]) * (subject[3] - subject[1]))
        return intersection / smaller >= 0.5

    regions = [r for r in candidate_regions(result) if r["confidence"] >= 0.65]
    if branch == "fire_detector":
        detectors = [r for r in regions if r["name"] == "火灾自动报警系统/点型火灾探测器"]
        if detectors and not any(overlaps(r["bbox"]) for r in detectors):
            return branch  # Same class name, but the VLM is describing a different object.
    names = {r["name"] for r in regions if overlaps(r["bbox"])}
    connector = {"消防水泵接合器/本体", "消防水泵接合器/消防接口"}
    outdoor = {"室外消火栓/消火栓栓体", "室外消火栓/消防接口"}
    supply = {"消防供配电/消防设备控制柜", "消防供水设施/水泵控制柜/手动自动状态转换开关"}
    alarm = {"火灾自动报警系统/火灾报警控制器", "火灾自动报警系统/火灾报警控制器/报警控制器显示器"}
    for selected, alternative, required in (
        ("outdoor_hydrant", "water_pump_connector", connector),
        ("water_pump_connector", "outdoor_hydrant", outdoor),
        ("fire_alarm_controller", "water_supply", supply),
        ("water_supply", "fire_alarm_controller", alarm),
    ):
        if branch == selected and required <= names:
            return alternative
    return None


def image_review_content(image: str, prompt: str, result: dict | None = None) -> list[dict]:
    regions = candidate_regions(result)
    text = prompt + "\n候选区域（可能误检；不可直接当作事实）：" + json.dumps(regions, ensure_ascii=False)
    parts = [{"type": "image_url", "image_url": {"url": image}}, {"type": "text", "text": text}]
    if not image.startswith("data:"):
        return parts
    try:
        original = Image.open(io.BytesIO(base64.b64decode(image.partition(",")[2], validate=True)))
        original.load()
        original = original.convert("RGB")
    except (ValueError, OSError, Image.DecompressionBombError):
        return parts
    # Small identity/reading regions receive priority. Crops never invent resolution.
    priority = ("压力指示器", "铭牌", "状态转换开关", "点型火灾探测器", "消防水枪", "控制柜", "接合器/本体")
    selected = sorted(regions, key=lambda item: not any(term in item["name"] for term in priority))[:6]
    width, height = original.size
    for item in selected:
        x1, y1, x2, y2 = item["bbox"]
        crop = original.crop((max(0, int(x1 * width) - 8), max(0, int(y1 * height) - 8),
                              min(width, math.ceil(x2 * width) + 8), min(height, math.ceil(y2 * height) + 8)))
        native_size = crop.size
        crop.thumbnail((768, 768))
        buffer = io.BytesIO()
        crop.save(buffer, format="JPEG", quality=92)
        parts.extend([
            {"type": "text", "text": f"局部候选 {item['name']}，原图坐标 {item['bbox']}，"
             f"原始裁剪像素 {native_size}。须回到全图核对目标身份，模糊细节不可猜读。"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()}},
        ])
    return parts
