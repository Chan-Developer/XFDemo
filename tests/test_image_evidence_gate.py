import base64
import io
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from backend.modules.inspection.evidence_gate import render_evidence, review_image_evidence, validate_evidence
from backend.modules.inspection.image_evidence import image_review_content, normalized_box, conflicting_facility_evidence
from backend.modules.inspection.intent import resolve_intent
from backend.modules.inspection.output_formatter import format_public_report


MISSING = "室内消火栓无消防水枪"
PRESSURE = "灭火器压力指示异常"
RUST = "室内消火栓箱锈蚀"


def observation(**kwargs):
    return {"id": "e1", "text": "箱底左侧可见棕色锈斑", "bbox": [0.1, 0.2, 0.5, 0.6],
            "kind": "visual", **kwargs}


def check(label=RUST, **kwargs):
    return {"label": label, "state": "supported", "evidence_ids": ["e1"], **kwargs}


def review(obs=None, checks=None, **kwargs):
    return {"observations": [observation()] if obs is None else obs,
            "checks": [check()] if checks is None else checks, "scope_complete": True, **kwargs}


@pytest.mark.parametrize("box", [[0, 0, 2, 1], [0.5, 0, 0.1, 1], [0, 0, float("nan"), 1],
                                [0, 0, True, 1], [0, 1], "0,0,1,1"])
def test_invalid_regions_cannot_anchor_claims(box):
    assert normalized_box(box) is None
    result = validate_evidence(review(obs=[observation(bbox=box)]), [RUST], {})
    assert result["verdict"] == "无法判断"
    assert not result["labels"]


def test_supported_anomaly_survives_another_uncertain_item():
    result = validate_evidence(review(), [RUST, MISSING], {})
    assert result["labels"] == [RUST]
    assert result["uncertain"] == [MISSING]
    structured, public = render_evidence(result, "内部组件")
    assert "结论：不合规" in structured
    assert "棕色锈斑" in public
    assert "待核验项目" in public


@pytest.mark.parametrize("coverage", [False, "true", None])
def test_incomplete_or_coerced_coverage_cannot_prove_absence(coverage):
    data = review(obs=[observation(kind="absence", text="水枪存放区域为空", coverage_complete=coverage)],
                  checks=[check(MISSING, coverage_complete=coverage)])
    assert validate_evidence(data, [MISSING], {})["labels"] == []


def test_complete_empty_region_can_support_absence():
    data = review(obs=[observation(kind="absence", text="完整水枪存放区域为空", coverage_complete=True)],
                  checks=[check(MISSING, coverage_complete=True)])
    assert validate_evidence(data, [MISSING], {})["labels"] == [MISSING]


def test_pressure_requires_readable_original_pixels_even_for_normal_verdict():
    data = review(obs=[observation(kind="reading", text="表盘指针位于绿色区域", readable=True,
                                  bbox=[0.1, 0.1, 0.12, 0.12])],
                  checks=[check(PRESSURE, state="refuted", readable=True)])
    rejected = validate_evidence(data, [PRESSURE], {"imageWidth": 1000, "imageHeight": 1000})
    assert rejected["verdict"] == "无法判断"
    assert "指针位于绿色" not in render_evidence(rejected, "灭火器")[1]
    data["observations"][0]["bbox"] = [0.1, 0.1, 0.5, 0.5]
    assert validate_evidence(data, [PRESSURE], {"imageWidth": 1000, "imageHeight": 1000})["verdict"] == "合规"


def test_pressure_cannot_bypass_readability_using_visual_kind():
    data = review(obs=[observation(text="指针位于绿色区")], checks=[check(PRESSURE, state="refuted")])
    result = validate_evidence(data, [PRESSURE], {})
    assert not result["observations"]
    assert result["verdict"] == "无法判断"


@pytest.mark.parametrize("data", [None, [], {}, {"observations": "bad", "checks": "bad"},
                                  review(checks=[check(evidence_ids=["missing"])]),
                                  review(checks=[check(state=[])]),
                                  review(obs=[observation(kind=[])]),
                                  review(checks=[check(), check(state="refuted")])])
def test_incomplete_or_malformed_review_never_means_pass(data):
    assert validate_evidence(data, [RUST], {})["verdict"] == "无法判断"


def test_observation_ids_cannot_be_reused_to_change_the_evidence():
    data = review(obs=[observation(), observation(text="表面无锈蚀")])
    assert validate_evidence(data, [RUST], {})["labels"] == []


@pytest.mark.parametrize("text", ["阀门已经锈死", "设备功能正常", "植物距离接口不足20cm"])
def test_nonvisual_claims_do_not_reach_public_report(text):
    result = validate_evidence(review(obs=[observation(text=text)]), [RUST], {})
    assert text not in render_evidence(result, "内部组件")[1]


def test_review_failure_does_not_restore_draft_labels():
    model = Mock()
    model.invoke.side_effect = RuntimeError("not for user output")
    structured, public, result, _ = review_image_evidence(
        model, "image", "indoor_hydrant", "内部组件", f"隐患标签：{MISSING}", {})
    assert "结论：无法判断" in structured
    assert result["removedDraftLabels"] == [MISSING]
    assert "not for user output" not in public


def test_formatter_never_invents_visibility_from_yolo_or_empty_evidence():
    source = "检查范围：内部组件\n结论：合规\n可见依据：\n隐患标签：无"
    report = format_public_report(source, {"detections": [{"label": "水枪", "confidence": 0.99}]})
    assert "检测结论：无法判断" in report
    assert "配置齐全" not in report and "消防水枪" not in report


def test_image_crops_keep_original_and_do_not_enlarge_tiny_details():
    buffer = io.BytesIO()
    Image.new("RGB", (200, 100)).save(buffer, format="PNG")
    image = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
    result = {"detections": [{"className": "灭火器/压力指示器", "confidence": 0.9,
                              "bboxNorm": [0.1, 0.1, 0.2, 0.3]}]}
    content = image_review_content(image, "核验", result)
    assert content[0]["image_url"]["url"] == image
    crop = Image.open(io.BytesIO(base64.b64decode(content[-1]["image_url"]["url"].partition(",")[2])))
    assert crop.width < 50 and crop.height < 50


@pytest.mark.parametrize("branch", ["water_pump_connector", "water_supply"])
def test_grounded_route_accepts_specific_equipment_and_preserves_anchor(monkeypatch, branch):
    monkeypatch.setenv("YOLO_MODE", "unified")
    payload = {"inspection_type": branch, "confidence": 0.95, "scope_hint": "detection_only",
               "evidence": "设备可见结构", "identity_status": "confirmed",
               "evidence_bbox": [0.1, 0.1, 0.9, 0.9], "distinguishing_evidence": "已核对区别于相似设备的结构"}
    model = Mock()
    model.invoke.return_value = SimpleNamespace(content=json.dumps(payload), usage={})
    intent, meta = resolve_intent(model, "固定任务不能改变分流", "image", detections={})
    assert intent.inspection_type == branch
    assert meta["grounding"]["bbox"] == payload["evidence_bbox"]
    assert "固定任务不能改变分流" not in str(model.invoke.call_args)
    payload.pop("evidence_bbox")
    model.invoke.return_value.content = json.dumps(payload)
    assert resolve_intent(model, "", "image", detections={})[0].inspection_type == "unknown"


@pytest.mark.parametrize("first_available", [True, False])
def test_pipeline_applies_evidence_gate_after_legacy_report_rules(monkeypatch, first_available):
    from backend.modules.inspection import pipeline
    from backend.modules.inspection.intent import IntentResult
    monkeypatch.setenv("YOLO_MODE", "unified")
    raw = {"enabled": True, "detections": [], "imageWidth": 1000, "imageHeight": 1000}
    monkeypatch.setattr(pipeline, "resolve_yolo_route", lambda *a, **k: (
        IntentResult("unknown", 0, "unknown", "", "unified_yolo"), raw,
        {"unifiedResult": raw, "probes": []}))
    monkeypatch.setattr(pipeline, "resolve_intent", lambda *a, **k: (
        IntentResult("fire_extinguisher", 0.9, "extinguisher", "瓶体可见", "qwen_vl"), {"usage": {}}))
    draft = "检查范围：灭火器\n结论：合规\n可见依据：指针清晰位于绿色区域\n隐患标签：无"
    agent = object.__new__(pipeline.InspectionAgent)
    agent.settings = SimpleNamespace(max_output_chars=2000)
    agent.model = Mock(invoke=Mock(return_value=SimpleNamespace(content=draft, usage={})))
    if not first_available:
        agent.model.invoke.side_effect = ConnectionError("local model offline")
    agent.judge_model = Mock(invoke=Mock(return_value=SimpleNamespace(content=draft, usage={})))
    agent.evidence_model = Mock(invoke=Mock(return_value=SimpleNamespace(content="not json", usage={})))
    state = agent.invoke({"image": "data:image/jpeg;base64,test"})
    assert "结论：无法判断" in state["report"]
    assert "指针清晰位于绿色区域" not in state["report"]
    assert state["trace"]["stages"][-1]["name"] == "image_evidence_gate"
    if not first_available:
        agent.judge_model.invoke.assert_not_called()


def test_conflict_checks_only_the_selected_subject_region():
    raw = {"detections": [{"className": name, "bboxNorm": [0.1, 0.1, 0.4, 0.4], "confidence": 0.9}
                          for name in ("消防水泵接合器/本体", "消防水泵接合器/消防接口")]}
    assert conflicting_facility_evidence("outdoor_hydrant", [0, 0, 0.5, 0.5], raw) == "water_pump_connector"
    assert conflicting_facility_evidence("outdoor_hydrant", [0.6, 0.6, 1, 1], raw) is None
    raw["detections"].pop()
    assert conflicting_facility_evidence("outdoor_hydrant", [0, 0, 0.5, 0.5], raw) is None


@pytest.mark.parametrize("second_type,expected", [("outdoor_hydrant", "unknown"),
                                                 ("water_pump_connector", "water_pump_connector")])
def test_coherent_conflicting_components_require_new_image_review(monkeypatch, second_type, expected):
    monkeypatch.setenv("YOLO_MODE", "unified")
    def answer(branch):
        return SimpleNamespace(content=json.dumps({
            "inspection_type": branch, "confidence": 0.9, "evidence": "主体的可见结构",
            "identity_status": "confirmed", "evidence_bbox": [0.1, 0.1, 0.9, 0.9],
            "distinguishing_evidence": "从原图核对的区分特征", "scope_hint": "outdoor",
        }), usage={"total_tokens": 10})
    model = Mock()
    model.invoke.side_effect = [answer("outdoor_hydrant"), answer(second_type)]
    raw = {"detections": [{"className": name, "bboxNorm": [0.1, 0.1, 0.9, 0.9], "confidence": 0.9}
                          for name in ("消防水泵接合器/本体", "消防水泵接合器/消防接口")]}
    intent, meta = resolve_intent(model, "", "image", detections=raw)
    assert intent.inspection_type == expected
    assert meta["usage"]["total_tokens"] == 20
    assert model.invoke.call_count == 2


def test_detector_identity_must_refer_to_the_small_detector_not_another_lamp():
    raw = {"detections": [{"className": "火灾自动报警系统/点型火灾探测器",
                           "bboxNorm": [0.56, 0.47, 0.61, 0.52], "confidence": 0.9}]}
    assert conflicting_facility_evidence("fire_detector", [0.49, 0.57, 0.56, 0.67], raw) == "fire_detector"
    assert conflicting_facility_evidence("fire_detector", [0.55, 0.46, 0.62, 0.53], raw) is None


def test_json_retry_requires_a_fresh_valid_image_review():
    model = Mock()
    model.invoke.side_effect = [SimpleNamespace(content="invalid", usage={"total_tokens": 2}),
                               SimpleNamespace(content=json.dumps(review()), usage={"total_tokens": 3})]
    _, _, result, usage = review_image_evidence(model, "image", "indoor_hydrant", "内部组件", "", {})
    assert result["formatRetries"] == 1 and not result["error"]
    assert result["labels"] == [RUST]
    assert usage["total_tokens"] == 5


def test_soft_hose_is_not_evidence_that_fire_hose_is_present():
    label = "室内消火栓无消防水带"
    data = review(obs=[observation(text="软管盘绕于卷盘上")], checks=[check(label, state="refuted")])
    result = validate_evidence(data, [label], {})
    assert result["verdict"] == "无法判断" and result["uncertain"] == [label]


def test_unrelated_observation_cannot_support_an_anomaly():
    data = review(obs=[observation(text="墙上贴有操作说明")])
    assert validate_evidence(data, [RUST], {})["labels"] == []


@pytest.mark.parametrize("context", ["product", "unknown", None])
def test_product_or_partial_photos_cannot_prove_clear_access(context):
    text = "灭火器置于推车架上，取用路径无障碍"
    data = review(obs=[observation(text=text)], checks=[], capture_context=context)
    result = validate_evidence(data, ["灭火器被遮挡或取用受限"], {})
    assert text not in render_evidence(result, "灭火器")[1]
    assert result["verdict"] == "无法判断"


def test_self_contradictory_appearance_is_not_rendered():
    data = review(obs=[observation(text="红色手轮位于阀体顶部，完整可见，呈黑色圆形结构")])
    result = validate_evidence(data, [RUST], {})
    assert not result["observations"]


def test_coordinates_are_kept_in_trace_not_product_prose():
    result = validate_evidence(review(obs=[observation(text="主体区域[0.1,0.2,0.5,0.6]内箱底可见锈斑")]), [RUST], {})
    assert result["observations"][0]["bbox"] == [0.1, 0.2, 0.5, 0.6]
    assert "[0.1" not in render_evidence(result, "内部组件")[1]
