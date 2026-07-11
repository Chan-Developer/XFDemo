from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path("/data/clj/Project/XFDemo").resolve()
YOLO_PYTHON = Path(os.getenv("YOLO_PYTHON", "/home/user/miniforge3/envs/yolo_clj/bin/python")).resolve()
YOLO_INFER_SCRIPT = Path(os.getenv("YOLO_INFER_SCRIPT", str(PROJECT_ROOT / "scripts" / "yolo_infer.py"))).resolve()
DEFAULT_MODEL_DIR = Path("/data/clj/output/yolo/fire_hydrant_v3_20260707").resolve()
INTERNAL_WEIGHTS = Path(os.getenv("YOLO_INTERNAL_WEIGHTS", str(DEFAULT_MODEL_DIR / "fire_hydrant_v3.pt"))).resolve()
CLASSES_FILE = Path(os.getenv("YOLO_CLASSES_FILE", str(DEFAULT_MODEL_DIR / "classes.json"))).resolve()
DEFAULT_CONF = float(os.getenv("YOLO_CONF", "0.20"))
DEFAULT_IMGSZ = int(os.getenv("YOLO_IMGSZ", "640"))
DEFAULT_DEVICE = os.getenv("YOLO_DEVICE", "0")
DEFAULT_TIMEOUT = int(os.getenv("YOLO_TIMEOUT", "90"))
TMP_DIR = PROJECT_ROOT / "logs" / "yolo_tmp"

DEFAULT_COMPONENT_CLASSES = ["手轮", "接口", "控制器", "栓体", "水带", "水枪", "软管", "阀门"]


def _load_class_labels() -> dict[str, str]:
    if CLASSES_FILE.exists():
        try:
            raw = json.loads(CLASSES_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return {str(index): str(name) for index, name in enumerate(raw)}
            if isinstance(raw, dict):
                return {str(key): str(value) for key, value in raw.items()}
        except Exception:
            pass
    return {str(index): name for index, name in enumerate(DEFAULT_COMPONENT_CLASSES)}


CLASS_LABELS = _load_class_labels()


def _enabled() -> bool:
    return os.getenv("YOLO_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


def _empty_result(enabled: bool = False, reason: str = "") -> dict[str, Any]:
    return {
        "enabled": enabled,
        "modelScope": "\u5185\u90e8\u7ec4\u4ef6",
        "modelType": "component_presence",
        "weights": str(INTERNAL_WEIGHTS),
        "classesFile": str(CLASSES_FILE),
        "classes": list(CLASS_LABELS.values()),
        "confThreshold": DEFAULT_CONF,
        "imgsz": DEFAULT_IMGSZ,
        "device": DEFAULT_DEVICE,
        "detections": [],
        "reason": reason,
    }


def _image_suffix(mime: str) -> str:
    mime = (mime or "").lower()
    if "png" in mime:
        return ".png"
    if "webp" in mime:
        return ".webp"
    return ".jpg"


def _write_temp_image(image: str | None) -> Path | None:
    if not image:
        return None
    value = image.strip()
    if not value.startswith("data:"):
        return None
    header, _, payload = value.partition(",")
    if not payload:
        return None
    mime = header[5:].split(";", 1)[0] if header.startswith("data:") else "image/jpeg"
    content = base64.b64decode(payload)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix="inspect_", suffix=_image_suffix(mime), dir=TMP_DIR, delete=False)
    try:
        handle.write(content)
        return Path(handle.name)
    finally:
        handle.close()


def _parse_stdout(stdout: str) -> dict[str, Any]:
    for line in reversed((stdout or "").splitlines()):
        if line.startswith("YOLO_JSON_RESULT="):
            return json.loads(line.split("=", 1)[1])
    raise ValueError("YOLO JSON result marker not found")



def _bbox_xyxy(item: dict[str, Any]) -> list[float]:
    bbox = item.get("bbox") or []
    if len(bbox) != 4:
        return []
    try:
        x1, y1, x2, y2 = [float(v) for v in bbox]
    except Exception:
        return []
    if x2 <= x1 or y2 <= y1:
        return []
    return [x1, y1, x2, y2]


def _area(box: list[float]) -> float:
    if len(box) != 4:
        return 0.0
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _iou(left: list[float], right: list[float]) -> float:
    if len(left) != 4 or len(right) != 4:
        return 0.0
    ix1 = max(left[0], right[0])
    iy1 = max(left[1], right[1])
    ix2 = min(left[2], right[2])
    iy2 = min(left[3], right[3])
    inter = _area([ix1, iy1, ix2, iy2])
    union = _area(left) + _area(right) - inter
    return inter / union if union > 0 else 0.0


def _contained_ratio(inner: list[float], outer: list[float]) -> float:
    if len(inner) != 4 or len(outer) != 4:
        return 0.0
    ix1 = max(inner[0], outer[0])
    iy1 = max(inner[1], outer[1])
    ix2 = min(inner[2], outer[2])
    iy2 = min(inner[3], outer[3])
    inter = _area([ix1, iy1, ix2, iy2])
    base = _area(inner)
    return inter / base if base > 0 else 0.0


def suppress_overlapping_detections(detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the prompt/display signal clean: remove duplicate boxes of the same component."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in detections:
        label = str(item.get("label") or item.get("component") or item.get("className") or "").strip()
        grouped.setdefault(label, []).append(item)

    kept: list[dict[str, Any]] = []
    for label, items in grouped.items():
        selected: list[dict[str, Any]] = []
        ordered = sorted(items, key=lambda x: float(x.get("confidence") or 0), reverse=True)
        for item in ordered:
            box = _bbox_xyxy(item)
            if not box:
                continue
            duplicate = False
            for chosen in selected:
                chosen_box = _bbox_xyxy(chosen)
                if _iou(box, chosen_box) >= 0.72 or _contained_ratio(box, chosen_box) >= 0.88 or _contained_ratio(chosen_box, box) >= 0.92:
                    duplicate = True
                    break
            if not duplicate:
                selected.append(item)
            if len(selected) >= 3:
                break
        kept.extend(selected)

    return sorted(kept, key=lambda x: float(x.get("confidence") or 0), reverse=True)[:24]


def compact_detections_for_prompt(detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in suppress_overlapping_detections(detections):
        label = str(item.get("label") or item.get("component") or item.get("className") or "").strip()
        grouped.setdefault(label, []).append(item)
    for label, items in sorted(grouped.items(), key=lambda pair: max(float(x.get("confidence") or 0) for x in pair[1]), reverse=True):
        top = max(items, key=lambda x: float(x.get("confidence") or 0))
        compact.append({
            "label": label,
            "count": len(items),
            "confidence": float(top.get("confidence") or 0),
            "bboxNorm": [round(float(v), 4) for v in (top.get("bboxNorm") or [])[:4]],
        })
    return compact

def run_yolo_detection(image: str | None, task: str = "auto") -> dict[str, Any]:
    normalized_task = (task or "auto").strip().lower()
    if normalized_task in {"appearance", "box_appearance", "\u7bb1\u4f53\u5916\u89c2", "\u5916\u89c2"}:
        return {**_empty_result(False, "YOLO component detector only supports internal component images; current scope is appearance"), "skipped": True}
    if not _enabled():
        return _empty_result(False, "YOLO disabled by YOLO_ENABLED")
    if not YOLO_PYTHON.exists():
        return _empty_result(False, f"YOLO python not found: {YOLO_PYTHON}")
    if not YOLO_INFER_SCRIPT.exists():
        return _empty_result(False, f"YOLO infer script not found: {YOLO_INFER_SCRIPT}")
    if not INTERNAL_WEIGHTS.exists():
        return _empty_result(False, f"YOLO weights not found: {INTERNAL_WEIGHTS}")
    temp_image = None
    try:
        temp_image = _write_temp_image(image)
        if not temp_image:
            return _empty_result(False, "YOLO currently supports uploaded data-url images only")
        cmd = [
            str(YOLO_PYTHON),
            str(YOLO_INFER_SCRIPT),
            "--weights", str(INTERNAL_WEIGHTS),
            "--image", str(temp_image),
            "--conf", str(DEFAULT_CONF),
            "--imgsz", str(DEFAULT_IMGSZ),
            "--device", str(DEFAULT_DEVICE),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT, check=False)
        if proc.returncode != 0:
            return {**_empty_result(True, "YOLO subprocess failed"), "stderr": (proc.stderr or "")[-2000:], "returncode": proc.returncode}
        payload = _parse_stdout(proc.stdout)
        detections = []
        for item in payload.get("detections") or []:
            class_name = str(item.get("className", ""))
            class_id = str(item.get("classId", ""))
            label = CLASS_LABELS.get(class_name) or CLASS_LABELS.get(class_id) or class_name
            detections.append({
                **item,
                "label": label,
                "component": label,
                "modelScope": "\u5185\u90e8\u7ec4\u4ef6",
                "modelType": "component_presence",
            })
        return {
            "enabled": True,
            "modelScope": "\u5185\u90e8\u7ec4\u4ef6",
            "modelType": "component_presence",
            "weights": str(INTERNAL_WEIGHTS),
            "classesFile": str(CLASSES_FILE),
            "classes": list(CLASS_LABELS.values()),
            "confThreshold": payload.get("confThreshold", DEFAULT_CONF),
            "imgsz": payload.get("imgsz", DEFAULT_IMGSZ),
            "device": payload.get("device", DEFAULT_DEVICE),
            "imageWidth": payload.get("imageWidth", 0),
            "imageHeight": payload.get("imageHeight", 0),
            "detections": suppress_overlapping_detections(detections),
            "rawDetectionCount": len(detections),
            "reason": "",
        }
    except subprocess.TimeoutExpired:
        return _empty_result(True, "YOLO subprocess timeout")
    except Exception as exc:
        return _empty_result(True, f"YOLO error: {exc}")
    finally:
        if temp_image:
            try:
                temp_image.unlink(missing_ok=True)
            except Exception:
                pass


def format_yolo_for_prompt(result: dict[str, Any] | None) -> str:
    result = result or _empty_result(False, "no yolo result")
    header = "YOLO\u8f85\u52a9\u68c0\u6d4b\u6a21\u578b\uff1a\u5185\u90e8\u7ec4\u4ef6\u5b58\u5728\u68c0\u6d4b\u6a21\u578b\uff08\u68c0\u6d4b\u624b\u8f6e\u3001\u63a5\u53e3\u3001\u63a7\u5236\u5668\u3001\u6813\u4f53\u3001\u6c34\u5e26\u3001\u6c34\u67aa\u3001\u8f6f\u7ba1\u3001\u9600\u95e8\uff09\u3002"
    guidance = (
        "\u4f7f\u7528\u89c4\u5219\uff1aYOLO\u53ea\u8bf4\u660e\u5bf9\u5e94\u5185\u90e8\u7ec4\u4ef6\u7591\u4f3c\u53ef\u89c1\uff0c\u4e0d\u76f4\u63a5\u7b49\u4e8e\u5408\u89c4\u6216\u4e0d\u5408\u89c4\uff1b"
        "\u82e5YOLO\u68c0\u51fa\u6c34\u5e26/\u6c34\u67aa/\u624b\u8f6e/\u63a5\u53e3\u7b49\u7ec4\u4ef6\uff0c\u5e94\u4f5c\u4e3a\u6392\u9664\u201c\u7f3a\u5931\u201d\u7c7b\u8bef\u62a5\u7684\u8bc1\u636e\u7ebf\u7d22\uff1b"
        "YOLO\u672a\u68c0\u51fa\u4e0d\u80fd\u76f4\u63a5\u5224\u5b9a\u7ec4\u4ef6\u7f3a\u5931\uff1b"
        "\u6700\u7ec8\u4ee5\u539f\u56fe\u6e05\u6670\u53ef\u89c1\u8bc1\u636e\u4e3a\u51c6\u3002"
    )
    if not result.get("enabled"):
        return f"{header}\n{guidance}\n\u72b6\u6001\uff1a\u672a\u542f\u7528\u6216\u4e0d\u53ef\u7528\uff08{result.get('reason', '')}\uff09"
    detections = result.get("detections") or []
    if not detections:
        return f"{header}\n{guidance}\n检测结果：未检出高于阈值的内部组件框。"
    compact = compact_detections_for_prompt(detections)
    lines = [
        header,
        guidance,
        "检测结果已做同类去重和嵌套框压缩；以下是给复核模型使用的组件级摘要，不提供带文字标注图，避免文字覆盖影响判断。",
        "组件摘要：",
    ]
    for index, item in enumerate(compact[:10], 1):
        lines.append(
            f"{index}. 组件={item['label']}；候选框数={item['count']}；最高置信度={item['confidence']:.2f}；主框bbox_norm_xyxy={item['bboxNorm']}"
        )
    return "\n".join(lines)
