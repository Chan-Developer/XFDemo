from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    Image = None
    ImageDraw = None
from urllib.parse import quote
from zoneinfo import ZoneInfo

from flask import Flask, Response, jsonify, request, send_file, stream_with_context

from backend.api.pipes import pipes_bp

from backend.inspection import (
    get_agent,
    get_settings,
    has_repeated_tail,
    ndjson,
    normalize_text,
    strip_reasoning,
    trim_output,
    env_int,
)


app = Flask(__name__)
app.register_blueprint(pipes_bp)

DATASET_ROOT = Path("/data/clj/data/xfLLM").resolve()
ULTRA_STRICT_DIR = DATASET_ROOT / "training_data" / "20260630_hydrant_auto_visible_reasoning_v5_ultra_strict_cleaned"
DATASET_FILES = {
    "train": ULTRA_STRICT_DIR / "train.jsonl",
    "val": ULTRA_STRICT_DIR / "val.jsonl",
    "all": ULTRA_STRICT_DIR / "all.jsonl",
    "quarantine": ULTRA_STRICT_DIR / "quarantine_all_flagged.jsonl",
}

PROJECT_ROOT = Path("/data/clj/Project/XFDemo").resolve()
HISTORY_DIR = PROJECT_ROOT / "logs" / "inspection_history"
HISTORY_IMAGE_DIR = HISTORY_DIR / "images"
HISTORY_FILE = HISTORY_DIR / "records.jsonl"


def _as_int(value, default, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))

def _now_text():
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")


def _decode_data_url(image):
    if not isinstance(image, str) or not image.startswith("data:"):
        return None, None
    header, _, payload = image.partition(",")
    if not payload:
        return None, None
    mime = header[5:].split(";", 1)[0] or "image/jpeg"
    try:
        return base64.b64decode(payload), mime
    except Exception:
        return None, None


def _image_extension(mime):
    mapping = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
    return mapping.get(str(mime or "").lower(), ".jpg")


IMAGE_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _versioned_image_url(prefix, image_path):
    version = ""
    try:
        stat = image_path.stat()
        version = f"?v={stat.st_mtime_ns:x}-{stat.st_size:x}"
    except OSError:
        pass
    return f"{prefix}{quote(image_path.name)}{version}"


def _send_image(image_path):
    mimetype = IMAGE_MIME_TYPES.get(image_path.suffix.lower(), "application/octet-stream")
    response = send_file(image_path, mimetype=mimetype, conditional=True, max_age=0)
    response.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _history_image_path(filename):
    if not filename:
        return None
    path = (HISTORY_IMAGE_DIR / filename).resolve()
    try:
        path.relative_to(HISTORY_IMAGE_DIR.resolve())
    except ValueError:
        return None
    return path


def _store_history_image(image):
    if not image:
        return {"imageUrl": "", "imageName": "", "imageBytes": 0, "imagePath": None}
    if isinstance(image, str) and not image.startswith("data:"):
        filename = image.rsplit("/", 1)[-1]
        return {"imageUrl": image, "imageName": filename, "imageBytes": 0, "imagePath": _history_image_path(filename)}
    content, mime = _decode_data_url(image)
    if not content:
        return {"imageUrl": "", "imageName": "", "imageBytes": 0, "imagePath": None}
    HISTORY_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(content).hexdigest()[:16]
    filename = f"{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d_%H%M%S')}_{digest}{_image_extension(mime)}"
    path = HISTORY_IMAGE_DIR / filename
    if not path.exists():
        path.write_bytes(content)
    return {
        "imageUrl": _versioned_image_url("/api/history/image/", path),
        "imageName": filename,
        "imageBytes": len(content),
        "imagePath": path,
    }


def _render_yolo_history_image(image_path, yolo):
    if Image is None or ImageDraw is None or not image_path or not Path(image_path).exists():
        return {"yoloImageUrl": "", "yoloImageName": ""}
    detections = (yolo or {}).get("detections") or []
    if not detections:
        return {"yoloImageUrl": "", "yoloImageName": ""}
    try:
        image = Image.open(image_path).convert("RGB")
    except Exception:
        return {"yoloImageUrl": "", "yoloImageName": ""}
    draw = ImageDraw.Draw(image)
    width, height = image.size
    stroke = max(3, int(min(width, height) * 0.004))
    badge_size = max(22, int(min(width, height) * 0.032))
    for index, item in enumerate(detections, 1):
        bbox = item.get("bbox") or []
        if len(bbox) != 4:
            bbox_norm = item.get("bboxNorm") or []
            if len(bbox_norm) == 4:
                bbox = [bbox_norm[0] * width, bbox_norm[1] * height, bbox_norm[2] * width, bbox_norm[3] * height]
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = [float(v) for v in bbox]
        x1 = max(0, min(width - 1, x1))
        y1 = max(0, min(height - 1, y1))
        x2 = max(x1 + 1, min(width, x2))
        y2 = max(y1 + 1, min(height, y2))
        draw.rectangle([x1, y1, x2, y2], outline=(220, 38, 38), width=stroke)
        bx = max(2, min(width - badge_size - 2, x1 + 4))
        by = max(2, min(height - badge_size - 2, y1 + 4))
        draw.rounded_rectangle([bx, by, bx + badge_size, by + badge_size], radius=badge_size // 2, fill=(220, 38, 38), outline=(255, 255, 255), width=max(1, stroke // 2))
        number = str(index)
        try:
            tb = draw.textbbox((0, 0), number)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
        except Exception:
            tw, th = len(number) * 6, 10
        draw.text((bx + (badge_size - tw) / 2, by + (badge_size - th) / 2 - 1), number, fill=(255, 255, 255))
    output_name = f"{Path(image_path).stem}_yolo{Path(image_path).suffix or '.jpg'}"
    output_path = HISTORY_IMAGE_DIR / output_name
    try:
        image.save(output_path)
    except Exception:
        return {"yoloImageUrl": "", "yoloImageName": ""}
    return {
        "yoloImageUrl": _versioned_image_url("/api/history/image/", output_path),
        "yoloImageName": output_name,
    }


def _parse_report_fields(report):
    report = str(report or "")
    cn_colon = chr(0xFF1A)
    cn_period = chr(0x3002)
    cn_semicolon = chr(0xFF1B)
    cn_dot = chr(0x3001)
    cn_comma = chr(0xFF0C)

    def pick(name, stop_at_semicolon=True):
        separators = ":" + cn_colon
        stops = "\n" + (";" + cn_semicolon if stop_at_semicolon else "")
        pattern = re.escape(name) + r"\s*[" + re.escape(separators) + r"]\s*([^" + re.escape(stops) + r"]+)"
        match = re.search(pattern, report)
        return match.group(1).strip().strip(cn_period + cn_semicolon + ";") if match else ""

    labels_text = pick("\u9690\u60a3\u6807\u7b7e", stop_at_semicolon=False)
    suggestions_text = pick("\u5efa\u8bae\u9879", stop_at_semicolon=False)
    split_chars = cn_semicolon + ";" + cn_dot + "," + cn_comma
    labels = [part.strip().strip(cn_period) for part in re.split("[" + re.escape(split_chars) + "]", labels_text) if part.strip()]
    if labels == ["\u65e0"]:
        labels = []
    suggestions = [part.strip().strip(cn_period) for part in re.split("[" + re.escape(split_chars) + "]", suggestions_text) if part.strip()]
    if suggestions == ["\u65e0"]:
        suggestions = []
    return {
        "scope": pick("\u68c0\u67e5\u8303\u56f4"),
        "verdict": pick("\u7ed3\u8bba"),
        "labels": labels,
        "suggestions": suggestions,
    }


def _append_history(data, response, usage=None, finish_reason="", task="", yolo=None, trace=None):
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    image_info = _store_history_image((data or {}).get("image"))
    yolo_image_info = _render_yolo_history_image(image_info.get("imagePath"), yolo)
    parsed = _parse_report_fields(response)
    trace_final = ((trace or {}).get("summary") or {}).get("final") or {}
    if not parsed.get("scope") and trace_final.get("scope"):
        parsed["scope"] = trace_final.get("scope")
    if not parsed.get("verdict") and trace_final.get("verdict"):
        parsed["verdict"] = trace_final.get("verdict")
    if not parsed.get("labels") and trace_final.get("labels"):
        parsed["labels"] = trace_final.get("labels")
    record = {
        "id": uuid.uuid4().hex[:12],
        "createdAt": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "createdText": _now_text(),
        "query": (data or {}).get("query", ""),
        "imageUrl": image_info["imageUrl"],
        "imageName": image_info["imageName"],
        "imageBytes": image_info["imageBytes"],
        "yoloImageUrl": yolo_image_info.get("yoloImageUrl", ""),
        "yoloImageName": yolo_image_info.get("yoloImageName", ""),
        "response": response or "",
        "responseExcerpt": (response or "")[:500],
        "usage": usage or {},
        "finishReason": finish_reason,
        "task": task,
        "yolo": yolo or {},
        "trace": trace or {},
        **parsed,
    }
    with HISTORY_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _read_history_records(reverse=True):
    if not HISTORY_FILE.exists():
        return []
    records = []
    with HISTORY_FILE.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if reverse:
        records.reverse()
    return records


def _write_history_records(records):
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = HISTORY_FILE.with_suffix(".tmp")
    with temp_file.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    temp_file.replace(HISTORY_FILE)


def _delete_history_image(record):
    for field in ("imageName", "yoloImageName"):
        image_name = record.get(field) or ""
        image_path = _history_image_path(image_name)
        if not image_path:
            continue
        try:
            image_path.unlink(missing_ok=True)
        except TypeError:
            if image_path.exists():
                image_path.unlink()


def _normalize_scope(meta):
    scope = str(meta.get("scope_label_in_answer") or meta.get("task") or "unknown")
    if scope == "internal_components":
        return "\u5185\u90e8\u7ec4\u4ef6"
    return scope


def _assistant_text(row):
    return _message_text(row, "assistant")


def _message_text(row, role):
    for message in row.get("messages", []):
        if message.get("role") != role:
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("text"):
                    parts.append(item.get("text", ""))
                elif item.get("type") == "image" or item.get("image"):
                    parts.append("[image]")
            return "\n".join(parts)
    return ""


def _display_text(text):
    return str(text or "").replace("\n", "\uFF1B")


def _source_name(source):
    source = str(source or "unknown")
    if "/training_data/" in source:
        return source.split("/training_data/", 1)[1]
    if "/archive_extracted" in source:
        return "archive_extracted"
    return source


def _clean_label(label, verdict):
    label_text = str(label or "").strip().strip("\u3002.;\uff1b,\uff0c")
    if label_text in {"?/???", "???", "??", "", "\u65e0", "\u65e0\u9690\u60a3", "\u65e0\u9690\u60a3\u6807\u7b7e"}:
        return "\u5408\u89c4\u6837\u672c" if verdict == "\u5408\u89c4" else "\u672a\u6807\u6ce8\u9690\u60a3\u6807\u7b7e"
    return label_text


def _normalize_labels(labels, verdict):
    if isinstance(labels, str):
        labels = [labels]
    normalized = []
    for label in labels or []:
        label_text = _clean_label(label, verdict)
        if label_text not in normalized:
            normalized.append(label_text)
    if normalized:
        return normalized
    return ["\u5408\u89c4\u6837\u672c"] if verdict == "\u5408\u89c4" else ["\u672a\u6807\u6ce8\u9690\u60a3\u6807\u7b7e"]


def _assistant_field(assistant, field_name):
    prefix = f"{field_name}\uff1a"
    for line in assistant.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            return line.split("\uff1a", 1)[1].strip()
    return ""


def _assistant_labels(assistant, verdict):
    label_text = _assistant_field(assistant, "\u9690\u60a3\u6807\u7b7e")
    if not label_text:
        return _normalize_labels([], verdict)
    parts = [part.strip() for part in re.split("[;\uff1b\u3001,\uff0c]", label_text) if part.strip()]
    return _normalize_labels(parts, verdict)


def _label_source(meta, verdict):
    if meta.get("original_labels") or meta.get("categories") or meta.get("boxes"):
        return "\u539f\u59cb\u6807\u6ce8\u5b57\u6bb5"
    if verdict == "\u5408\u89c4":
        return "\u5408\u89c4\u6837\u672c\u96c6"
    return "meta.defect_labels"


def _label_status(true_labels, model_labels):
    truth = {label for label in true_labels if label not in {"\u672a\u6807\u6ce8\u9690\u60a3\u6807\u7b7e"}}
    model = {label for label in model_labels if label not in {"\u672a\u6807\u6ce8\u9690\u60a3\u6807\u7b7e"}}
    return "\u4e00\u81f4" if truth == model else "\u9700\u6838\u5bf9"


def _image_size(image_path, meta):
    width = int(meta.get("image_width") or 0)
    height = int(meta.get("image_height") or 0)
    if width > 0 and height > 0:
        return width, height
    try:
        with open(image_path, "rb") as handle:
            header = handle.read(24)
            if header.startswith(b"\x89PNG\r\n\x1a\n"):
                return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
            handle.seek(0)
            if handle.read(2) == b"\xff\xd8":
                while True:
                    marker_start = handle.read(1)
                    if not marker_start:
                        break
                    if marker_start != b"\xff":
                        continue
                    marker = handle.read(1)
                    while marker == b"\xff":
                        marker = handle.read(1)
                    if marker in {b"\xc0", b"\xc1", b"\xc2", b"\xc3", b"\xc5", b"\xc6", b"\xc7", b"\xc9", b"\xca", b"\xcb", b"\xcd", b"\xce", b"\xcf"}:
                        handle.read(3)
                        h = int.from_bytes(handle.read(2), "big")
                        w = int.from_bytes(handle.read(2), "big")
                        return w, h
                    segment_length = int.from_bytes(handle.read(2), "big")
                    if segment_length < 2:
                        break
                    handle.seek(segment_length - 2, 1)
    except Exception:
        pass
    return width, height


def _annotation_boxes(meta, fallback_labels, image_width=0, image_height=0):
    boxes = []
    image_width = float(image_width or meta.get("image_width") or 0)
    image_height = float(image_height or meta.get("image_height") or 0)
    for index, box in enumerate(meta.get("boxes") or []):
        coords = box.get("bbox_norm_xyxy") or []
        if len(coords) != 4:
            xyxy = box.get("bbox_xyxy") or []
            if len(xyxy) == 4 and image_width > 0 and image_height > 0:
                coords = [xyxy[0] / image_width, xyxy[1] / image_height, xyxy[2] / image_width, xyxy[3] / image_height]
        if len(coords) != 4:
            continue
        x1, y1, x2, y2 = [max(0, min(1, float(value))) for value in coords]
        if x2 <= x1 or y2 <= y1:
            continue
        label = _clean_label(box.get("label") or (fallback_labels[index] if index < len(fallback_labels) else fallback_labels[0] if fallback_labels else ""), "")
        boxes.append({
            "label": label,
            "left": x1 * 100,
            "top": y1 * 100,
            "width": (x2 - x1) * 100,
            "height": (y2 - y1) * 100,
        })
    return boxes


def _record_from_row(row, split):
    meta = row.get("meta") or {}
    verdict = str(meta.get("verdict", "unknown"))
    true_labels = _normalize_labels(meta.get("defect_labels") or meta.get("categories") or [], verdict)
    image_path = (row.get("images") or [""])[0]
    image_width, image_height = _image_size(image_path, meta)
    assistant_raw = _assistant_text(row)
    model_verdict = _assistant_field(assistant_raw, "\u7ed3\u8bba") or verdict
    model_scope = _assistant_field(assistant_raw, "\u68c0\u67e5\u8303\u56f4") or _normalize_scope(meta)
    model_labels = _assistant_labels(assistant_raw, model_verdict)
    label_status = _label_status(true_labels, model_labels)
    annotation_boxes = _annotation_boxes(meta, true_labels, image_width, image_height)
    assistant = _display_text(assistant_raw)
    return {
        "id": row.get("id", ""),
        "split": split,
        "imagePath": image_path,
        "imageUrl": f"/api/dataset/image?path={quote(image_path)}" if image_path else "",
        "imageWidth": image_width,
        "imageHeight": image_height,
        "annotationBoxes": annotation_boxes,
        "verdict": verdict,
        "scope": _normalize_scope(meta),
        "defectLabels": true_labels,
        "trueLabels": true_labels,
        "trueLabelSource": _label_source(meta, verdict),
        "originalLabels": meta.get("original_labels") or meta.get("categories") or [],
        "modelVerdict": model_verdict,
        "modelScope": model_scope,
        "modelLabels": model_labels,
        "modelSource": "assistant \u8f93\u51fa\u89e3\u6790",
        "labelStatus": label_status,
        "labelMatched": label_status == "\u4e00\u81f4",
        "primaryCategory": meta.get("primary_category", ""),
        "sourceDataset": _source_name(meta.get("source_dataset", "")),
        "promptVersion": meta.get("prompt_version", ""),
        "assistantExcerpt": assistant[:900],
        "assistantText": assistant,
    }


def _iter_dataset_rows(split):
    dataset_path = DATASET_FILES.get(split, DATASET_FILES["train"])
    if not dataset_path.exists():
        return
    with dataset_path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


@app.route("/dataset/ultra-strict/samples", methods=["GET"])
def ultra_strict_samples():
    split = request.args.get("split", "train")
    if split not in DATASET_FILES:
        split = "train"
    page = _as_int(request.args.get("page"), 1, 1, 100000)
    page_size = _as_int(request.args.get("page_size"), 24, 1, 80)
    verdict_filter = request.args.get("verdict", "")
    scope_filter = request.args.get("scope", "")
    defect_filter = request.args.get("defect", "")
    query = request.args.get("q", "").strip().lower()

    records = []
    total = 0
    start = (page - 1) * page_size
    end = start + page_size

    for row in _iter_dataset_rows(split):
        record = _record_from_row(row, split)
        if verdict_filter and record["verdict"] != verdict_filter:
            continue
        if scope_filter and record["scope"] != scope_filter:
            continue
        if defect_filter and defect_filter not in record["defectLabels"]:
            continue
        if query:
            haystack = " ".join(
                [
                    record["id"],
                    record["imagePath"],
                    record["verdict"],
                    record["scope"],
                    record["modelVerdict"],
                    record["modelScope"],
                    record["labelStatus"],
                    record["primaryCategory"],
                    record["sourceDataset"],
                    record["assistantExcerpt"],
                    " ".join(record["trueLabels"]),
                    " ".join(record["modelLabels"]),
                ]
            ).lower()
            if query not in haystack:
                continue
        if start <= total < end:
            records.append(record)
        total += 1

    return jsonify(
        {
            "records": records,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size,
        }
    )


@app.route("/dataset/image", methods=["GET"])
def dataset_image():
    raw_path = request.args.get("path", "")
    if not raw_path:
        return jsonify({"error": "missing image path"}), 400
    image_path = Path(raw_path).expanduser().resolve()
    try:
        image_path.relative_to(DATASET_ROOT)
    except ValueError:
        return jsonify({"error": "image path is outside allowed dataset root"}), 403
    if not image_path.exists() or not image_path.is_file():
        return jsonify({"error": "image not found"}), 404
    return _send_image(image_path)



@app.route("/history/inspections", methods=["GET"])
def inspection_history():
    page = _as_int(request.args.get("page"), 1, 1, 100000)
    page_size = _as_int(request.args.get("page_size"), 12, 1, 80)
    verdict_filter = request.args.get("verdict", "")
    query = request.args.get("q", "").strip().lower()
    records = []
    for original_record in _read_history_records():
        record = dict(original_record)
        image_name = record.get("imageName") or ""
        if image_name:
            record["imageUrl"] = _versioned_image_url(
                "/api/history/image/", HISTORY_IMAGE_DIR / image_name
            )
        yolo_image_name = record.get("yoloImageName") or ""
        if yolo_image_name:
            record["yoloImageUrl"] = _versioned_image_url("/api/history/image/", HISTORY_IMAGE_DIR / yolo_image_name)
        if verdict_filter and record.get("verdict") != verdict_filter:
            continue
        if query:
            haystack = " ".join([
                record.get("id", ""), record.get("createdText", ""), record.get("query", ""), record.get("imageName", ""),
                record.get("verdict", ""), record.get("scope", ""), " ".join(record.get("labels") or []), record.get("responseExcerpt", ""),
            ]).lower()
            if query not in haystack:
                continue
        records.append(record)
    total = len(records)
    start = (page - 1) * page_size
    return jsonify({"records": records[start:start + page_size], "total": total, "page": page, "page_size": page_size, "pages": (total + page_size - 1) // page_size})


@app.route("/history/inspections", methods=["DELETE"])
def clear_inspection_history():
    records = _read_history_records(reverse=False)
    for record in records:
        _delete_history_image(record)
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
    return jsonify({"deleted": True, "count": len(records)})


@app.route("/history/inspections/<record_id>", methods=["DELETE"])
def delete_inspection_history(record_id):
    records = _read_history_records(reverse=False)
    kept = []
    deleted = None
    for record in records:
        if record.get("id") == record_id:
            deleted = record
            continue
        kept.append(record)
    if deleted is None:
        return jsonify({"error": "history record not found"}), 404
    _write_history_records(kept)
    _delete_history_image(deleted)
    return jsonify({"deleted": True, "id": record_id})


@app.route("/history/image/<path:filename>", methods=["GET"])
def history_image(filename):
    image_path = (HISTORY_IMAGE_DIR / filename).resolve()
    try:
        image_path.relative_to(HISTORY_IMAGE_DIR.resolve())
    except ValueError:
        return jsonify({"error": "image path is outside allowed history root"}), 403
    if not image_path.exists() or not image_path.is_file():
        return jsonify({"error": "image not found"}), 404
    return _send_image(image_path)




def _trace_summary(record):
    trace = record.get("trace") or {}
    return trace.get("summary") or {}


def _trace_issues(record):
    return _trace_summary(record).get("issues") or []


def _trace_has_issue(record, issue_type):
    return any(issue.get("type") == issue_type for issue in _trace_issues(record))


@app.route("/monitor/inspection-stats", methods=["GET"])
def inspection_monitor_stats():
    limit = _as_int(request.args.get("limit"), 200, 1, 2000)
    records = _read_history_records()[:limit]
    traced = [record for record in records if record.get("trace")]
    stage_totals = {}
    for record in traced:
        for stage in (record.get("trace") or {}).get("stages") or []:
            name = stage.get("name") or "unknown"
            bucket = stage_totals.setdefault(name, {"name": name, "title": stage.get("title") or name, "count": 0, "warn": 0, "error": 0, "skipped": 0, "totalDurationMs": 0})
            bucket["count"] += 1
            bucket["totalDurationMs"] += int(stage.get("durationMs") or 0)
            if stage.get("status") == "warn":
                bucket["warn"] += 1
            if stage.get("status") == "error":
                bucket["error"] += 1
            if stage.get("status") == "skipped":
                bucket["skipped"] += 1
    stages = []
    for bucket in stage_totals.values():
        count = bucket["count"] or 1
        stages.append({**bucket, "avgDurationMs": round(bucket["totalDurationMs"] / count)})
    stages.sort(key=lambda item: item["name"])

    recent = []
    for record in records[:30]:
        image_name = record.get("imageName") or ""
        item = dict(record)
        if image_name:
            item["imageUrl"] = _versioned_image_url("/api/history/image/", HISTORY_IMAGE_DIR / image_name)
        yolo_image_name = item.get("yoloImageName") or ""
        if yolo_image_name:
            item["yoloImageUrl"] = _versioned_image_url("/api/history/image/", HISTORY_IMAGE_DIR / yolo_image_name)
        recent.append(item)

    return jsonify({
        "total": len(records),
        "withTrace": len(traced),
        "qwenCorrected": sum(1 for record in traced if _trace_has_issue(record, "qwen_corrected")),
        "yoloPossibleMiss": sum(1 for record in traced if _trace_has_issue(record, "yolo_possible_miss")),
        "yoloPossibleFalsePositive": sum(1 for record in traced if _trace_has_issue(record, "yolo_possible_false_positive")),
        "vlmFallbackUsed": sum(1 for record in traced if _trace_has_issue(record, "vlm_fallback_used")),
        "judgeNeedsManualReview": sum(1 for record in traced if _trace_has_issue(record, "judge_needs_manual_review")),
        "yoloUnavailable": sum(1 for record in traced if _trace_has_issue(record, "yolo_unavailable")),
        "stages": stages,
        "recent": recent,
    })

@app.route("/health", methods=["GET"])
def health():
    settings = get_settings()
    missing = []
    if not settings.api_key:
        missing.append("DASHSCOPE_API_KEY")

    return jsonify(
        {
            "status": "running",
            "provider": "aliyun-compatible-openai",
            "configured": not missing,
            "missing": missing,
            "base_url": settings.base_url,
            "model": settings.model,
            "enable_thinking": settings.enable_thinking,
        }
    )


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(silent=True) or {}
        state = get_agent().invoke(data)
        report = state.get("report", "")
        usage = state.get("usage", {})
        yolo = state.get("yolo", {})
        trace = state.get("trace", {})
        history = _append_history(data, report, usage, task=state.get("task", "auto"), yolo=yolo, trace=trace)
        return jsonify({"response": report, "usage": usage, "history": history, "yolo": yolo, "trace": trace})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        print(f"Chat error: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    try:
        data = request.get_json(silent=True) or {}
        agent = get_agent()
    except Exception as exc:
        print(f"Stream setup error: {exc}")
        return jsonify({"error": str(exc)}), 500

    @stream_with_context
    def generate():
        try:
            state = agent.stream_checked(data)
            final_text = trim_output(
                strip_reasoning(state.get("report", "")),
                max_chars=max(agent.settings.max_output_chars, 4000),
            )
            if final_text:
                yield ndjson({"type": "delta", "delta": final_text})
            yolo = state.get("yolo", {})
            trace = state.get("trace", {})
            history = _append_history(data, final_text, state.get("usage", {}), finish_reason="judge_checked", task=state.get("task", "auto"), yolo=yolo, trace=trace)
            yield ndjson(
                {
                    "type": "done",
                    "response": final_text,
                    "usage": state.get("usage", {}),
                    "finish_reason": "judge_checked",
                    "task": state.get("task", "auto"),
                    "history": history,
                    "yolo": yolo,
                    "trace": trace,
                }
            )
        except ValueError as exc:
            yield ndjson({"type": "error", "error": str(exc)})
        except Exception as exc:
            print(f"Stream error: {exc}")
            yield ndjson({"type": "error", "error": str(exc)})

    response = Response(generate(), mimetype="application/x-ndjson")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=env_int("BACKEND_PORT", "5000"), debug=False)
