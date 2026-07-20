from flask import Blueprint, jsonify, request

from backend.modules.dataset.service import as_int
from backend.modules.history.inspection_history import clear_history, create_review, delete_history_record, delete_review, list_history, list_reviews, send_history_image

history_bp = Blueprint("history", __name__)


@history_bp.get("/history/inspections")
def inspection_history():
    page = as_int(request.args.get("page"), 1, 1, 100000)
    page_size = as_int(request.args.get("page_size"), 12, 1, 80)
    verdict_filter = request.args.get("verdict", "")
    query = request.args.get("q", "")
    return jsonify(list_history(page, page_size, verdict_filter, query))


@history_bp.delete("/history/inspections")
def clear_inspection_history():
    return jsonify(clear_history())


@history_bp.delete("/history/inspections/<record_id>")
def delete_inspection_history(record_id):
    try:
        return jsonify(delete_history_record(record_id))
    except KeyError:
        return jsonify({"error": "history record not found"}), 404


@history_bp.get("/history/inspections/<record_id>/reviews")
def inspection_reviews(record_id):
    return jsonify(list_reviews(record_id))


@history_bp.post("/history/inspections/<record_id>/reviews")
def create_inspection_review(record_id):
    payload = request.get_json(silent=True) or {}
    payload["recordId"] = record_id
    try:
        return jsonify(create_review(payload))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except KeyError:
        return jsonify({"error": "history record not found"}), 404


@history_bp.delete("/history/reviews/<review_id>")
def delete_inspection_review(review_id):
    try:
        return jsonify(delete_review(review_id))
    except KeyError:
        return jsonify({"error": "review not found"}), 404


@history_bp.get("/history/image/<path:filename>")
def history_image(filename):
    try:
        return send_history_image(filename)
    except ValueError:
        return jsonify({"error": "image path is outside allowed history root"}), 403
    except FileNotFoundError:
        return jsonify({"error": "image not found"}), 404
