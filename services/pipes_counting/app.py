from __future__ import annotations

import base64
import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from flask import Flask, jsonify, request
from ultralytics import YOLO


WEIGHTS_PATH = Path(
    os.getenv(
        "PIPES_MODEL_PATH",
        "/data/clj/output/yolo/pipes_counting/final_weights.pt",
    )
).resolve()
DEVICE = os.getenv("PIPES_DEVICE", "cpu")
DEFAULT_CONFIDENCE = float(os.getenv("PIPES_CONFIDENCE", "0.25"))
DEFAULT_IOU = float(os.getenv("PIPES_IOU", "0.45"))
DEFAULT_IMAGE_SIZE = int(os.getenv("PIPES_IMAGE_SIZE", "640"))
DEFAULT_MAX_DETECTIONS = int(os.getenv("PIPES_MAX_DETECTIONS", "2000"))
MAX_IMAGE_BYTES = int(os.getenv("PIPES_MAX_IMAGE_BYTES", str(20 * 1024 * 1024)))

CLASS_MAP = {
    0: {"key": "round", "name": "圆管", "color": "#E53935"},
    1: {"key": "square", "name": "方管", "color": "#2878D0"},
    2: {"key": "angle", "name": "角钢", "color": "#F28C28"},
    3: {"key": "channel", "name": "槽钢", "color": "#2F8F5B"},
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_BYTES * 2

_model: YOLO | None = None
_model_error = ""
_model_lock = threading.Lock()


def _clamp(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _as_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _model_version() -> str:
    try:
        digest = hashlib.sha256(WEIGHTS_PATH.read_bytes()).hexdigest()[:12]
    except OSError:
        return "unknown"
    return f"pipes-counting-{digest}"


MODEL_VERSION = _model_version()


def load_model() -> YOLO:
    global _model, _model_error
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        if not WEIGHTS_PATH.exists():
            _model_error = f"weights not found: {WEIGHTS_PATH}"
            raise FileNotFoundError(_model_error)
        try:
            _model = YOLO(str(WEIGHTS_PATH))
            _model_error = ""
            return _model
        except Exception as exc:
            _model_error = str(exc)
            raise


def _decode_image(value: Any) -> np.ndarray:
    if not isinstance(value, str) or not value.startswith("data:image/"):
        raise ValueError("image must be a base64 data URL")
    _, separator, payload = value.partition(",")
    if not separator or not payload:
        raise ValueError("image data URL is incomplete")
    try:
        content = base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise ValueError("image base64 is invalid") from exc
    if len(content) > MAX_IMAGE_BYTES:
        raise ValueError("image exceeds the size limit")
    image = cv2.imdecode(np.frombuffer(content, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.ndim != 3:
        raise ValueError("image format is not supported")
    return image


def _selected_classes(value: Any) -> list[int]:
    if not isinstance(value, list):
        return list(CLASS_MAP)
    selected = []
    for item in value:
        try:
            class_id = int(item)
        except (TypeError, ValueError):
            continue
        if class_id in CLASS_MAP and class_id not in selected:
            selected.append(class_id)
    if not selected:
        raise ValueError("at least one profile class must be selected")
    return selected


def count_profiles(payload: dict[str, Any]) -> dict[str, Any]:
    request_started = time.perf_counter()
    image = _decode_image(payload.get("image"))
    height, width = image.shape[:2]
    confidence = _clamp(payload.get("confidence"), DEFAULT_CONFIDENCE, 0.05, 0.95)
    iou = _clamp(payload.get("iou"), DEFAULT_IOU, 0.10, 0.90)
    image_size = _as_int(payload.get("imageSize"), DEFAULT_IMAGE_SIZE, 320, 1280)
    max_detections = _as_int(
        payload.get("maxDetections"),
        DEFAULT_MAX_DETECTIONS,
        1,
        5000,
    )
    class_ids = _selected_classes(payload.get("classes"))

    model = load_model()
    inference_started = time.perf_counter()
    with _model_lock:
        results = model.predict(
            source=image,
            conf=confidence,
            iou=iou,
            imgsz=image_size,
            device=DEVICE,
            max_det=max_detections,
            classes=class_ids,
            verbose=False,
        )
    inference_ms = round((time.perf_counter() - inference_started) * 1000)

    counts = {meta["key"]: 0 for meta in CLASS_MAP.values()}
    detections: list[dict[str, Any]] = []
    boxes = results[0].boxes if results else None
    if boxes is not None:
        coordinates = boxes.xyxy.cpu().tolist()
        confidences = boxes.conf.cpu().tolist()
        classes = boxes.cls.cpu().tolist()
        for coords, score, raw_class_id in zip(coordinates, confidences, classes):
            class_id = int(raw_class_id)
            meta = CLASS_MAP.get(class_id)
            if not meta:
                continue
            x1, y1, x2, y2 = [float(item) for item in coords]
            counts[meta["key"]] += 1
            detections.append({
                "classId": class_id,
                "classKey": meta["key"],
                "className": meta["name"],
                "color": meta["color"],
                "confidence": round(float(score), 6),
                "bbox": [x1, y1, x2, y2],
                "bboxNorm": [
                    x1 / width,
                    y1 / height,
                    x2 / width,
                    y2 / height,
                ],
            })

    detections.sort(key=lambda item: item["confidence"], reverse=True)
    return {
        "total": sum(counts.values()),
        "counts": counts,
        "detections": detections,
        "classes": [
            {"classId": class_id, **meta}
            for class_id, meta in CLASS_MAP.items()
        ],
        "imageWidth": int(width),
        "imageHeight": int(height),
        "confidence": confidence,
        "iou": iou,
        "imageSize": image_size,
        "maxDetections": max_detections,
        "inferenceMs": inference_ms,
        "elapsedMs": round((time.perf_counter() - request_started) * 1000),
        "modelVersion": MODEL_VERSION,
        "device": DEVICE,
    }


@app.get("/health")
def health():
    try:
        load_model()
        status = "running"
        code = 200
    except Exception:
        status = "error"
        code = 503
    return jsonify({
        "status": status,
        "modelLoaded": _model is not None,
        "modelError": _model_error,
        "modelVersion": MODEL_VERSION,
        "weights": str(WEIGHTS_PATH),
        "device": DEVICE,
        "classes": [
            {"classId": class_id, **meta}
            for class_id, meta in CLASS_MAP.items()
        ],
    }), code


@app.post("/count")
def count():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(count_profiles(payload))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("PipesCounting inference failed")
        return jsonify({"error": f"inference failed: {exc}"}), 500


@app.errorhandler(413)
def payload_too_large(_error):
    return jsonify({"error": "request image exceeds the size limit"}), 413


if __name__ == "__main__":
    load_model()
    app.run(
        host=os.getenv("PIPES_HOST", "127.0.0.1"),
        port=int(os.getenv("PIPES_PORT", "9400")),
        debug=False,
        threaded=True,
    )
