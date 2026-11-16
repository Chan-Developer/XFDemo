import os
import unittest
from unittest.mock import patch

from backend.infrastructure.vision.unified import canonical_name, project_result
from backend.modules.inspection.router import resolve_yolo_route
from backend.modules.inspection.pipeline import _probe_for_intent
from backend.modules.inspection.messages import build_messages, build_outlet_direction_verify_messages
from backend.modules.inspection.intent import build_intent_messages, parse_intent_output, DETECTION_ONLY_TYPES
from backend.modules.inspection.yolo_context import yolo_presence_veto_labels
from backend.modules.history.report_document import parse_report_document, render_report_document
from backend.modules.inspection.component_report import describe_components
from types import SimpleNamespace


def fixture():
    names = ["室内消火栓/消防水枪", "室内消火栓/消火栓箱门", "室外消火栓/消火栓栓体",
             "灭火器/瓶体", "灭火器/压力指示器", "防火门/门扇"]
    return {"enabled": True, "detectorMode": "unified", "detections": [
        {"className": name, "classId": i, "confidence": 0.8,
         "bbox": [1, 2, 30, 40], "bboxNorm": [0.01, 0.02, 0.3, 0.4]}
        for i, name in enumerate(names)]}


class UnifiedTests(unittest.TestCase):
    def test_unified_route_uses_original_image_and_object_priority(self):
        with patch.dict(os.environ, {"YOLO_MODE": "unified"}):
            messages = build_intent_messages("FIXED_QUERY_MUST_NOT_ROUTE", "original-image")
        content = messages[0]["content"]
        self.assertEqual(content[0]["image_url"]["url"], "original-image")
        self.assertIn("近景清晰拍摄的具体设备优先于背景环境", content[1]["text"])
        self.assertIn("普通门不能仅凭门扇或安全出口标志认定为防火门", content[1]["text"])
        self.assertNotIn("FIXED_QUERY_MUST_NOT_ROUTE", content[1]["text"])

    def test_scope_validation_accepts_codes_but_rejects_wrong_scope(self):
        from scripts.backend.validate_unified import validate_scope
        state = {"trace": {"summary": {"final": {"scope": "箱体外观"}}}}
        validate_scope(state, "appearance")
        validate_scope(state, "箱体外观")
        with self.assertRaises(AssertionError):
            validate_scope(state, "internal_components")

    def test_direction_review_does_not_copy_previous_claim(self):
        messages = build_outlet_direction_verify_messages("original-image", "检查", "FIRST_MARKER", "REVIEW_MARKER", fixture())
        text = messages[0]["content"][1]["text"]
        self.assertNotIn("FIRST_MARKER", text)
        self.assertNotIn("REVIEW_MARKER", text)

    def test_recognition_report_keeps_status_and_uses_image_and_boxes(self):
        from unittest.mock import Mock
        model = Mock()
        model.invoke.return_value = SimpleNamespace(content="画面中可见门扇和上方闭门器。", usage={})
        report, _ = describe_components(model, "original-image", "防火门", fixture())
        content = model.invoke.call_args.args[0][0]["content"]
        self.assertEqual(content[0]["image_url"]["url"], "original-image")
        self.assertIn("bboxNorm", content[1]["text"])
        self.assertIn("无需转录铭牌", content[1]["text"])
        document = parse_report_document(report)
        self.assertEqual(document["verdict"], "not_assessed")
        self.assertEqual(render_report_document(document), report)

    def test_valve_body_does_not_prove_cabinet_presence(self):
        missing = ["室内消火栓无箱体"]
        result = {"detections": [{"component": "栓体", "confidence": 0.9}]}
        self.assertEqual(yolo_presence_veto_labels(missing, result)[0], missing)
        result["detections"][0]["component"] = "消火栓"
        self.assertEqual(yolo_presence_veto_labels(missing, result)[0], [])

    def test_new_facilities_are_recognized_only_in_unified_mode(self):
        import json
        for branch in DETECTION_ONLY_TYPES:
            output = json.dumps({"inspection_type": branch, "confidence": 0.9})
            with patch.dict(os.environ, {"YOLO_MODE": "unified"}):
                self.assertEqual(parse_intent_output(output).inspection_type, branch)
            with patch.dict(os.environ, {"YOLO_MODE": "legacy"}):
                self.assertEqual(parse_intent_output(output).inspection_type, "unknown")

    def test_detector_failure_is_not_an_empty_success(self):
        with patch.dict(os.environ, {"YOLO_MODE": "unified"}), patch(
            "backend.modules.inspection.router.run_yolo_detection", return_value={"enabled": False, "reason": "missing weight"}
        ):
            with self.assertRaises(RuntimeError):
                resolve_yolo_route("image")

    def test_name_not_index(self):
        self.assertEqual(canonical_name("室内消火栓/室内消火栓使用说明"), "操作说明")
        self.assertEqual(canonical_name("室内消火栓/消火栓手轮"), "手轮")

    def test_three_branches_isolated(self):
        raw = fixture()
        for task, prefix in [("internal_components", "室内消火栓/"),
                             ("outdoor_hydrant", "室外消火栓/"), ("fire_extinguisher", "灭火器/")]:
            result = project_result(raw, task)
            self.assertTrue(result["detections"])
            self.assertTrue(all(x["className"].startswith(prefix) for x in result["detections"]))
        self.assertEqual(len(raw["detections"]), 6)

    def test_single_inference_and_cached_scope_switch(self):
        with patch.dict(os.environ, {"YOLO_MODE": "unified"}), patch(
            "backend.modules.inspection.router.run_yolo_detection", return_value=fixture()
        ) as infer:
            intent, _, meta = resolve_yolo_route("data:image/jpeg;base64,AA==")
            self.assertEqual(intent.inspection_type, "unknown")
            for branch, scope in [("indoor_hydrant", "internal_components"),
                                  ("outdoor_hydrant", "outdoor"), ("fire_extinguisher", "extinguisher")]:
                selected, task = _probe_for_intent(meta, branch, scope)
                self.assertTrue(selected["detections"])
                messages = build_messages("检查", "original-image", task, branch, selected)
                self.assertEqual(messages[0]["content"][0]["image_url"]["url"], "original-image")
                self.assertIn("bboxNorm", messages[0]["content"][1]["text"])
            appearance = project_result(meta["unifiedResult"], "appearance")
            self.assertEqual(appearance["classes"], ["箱门"])
            infer.assert_called_once()

    def test_empty_detections_do_not_default_to_indoor(self):
        with patch.dict(os.environ, {"YOLO_MODE": "unified"}), patch(
            "backend.modules.inspection.router.run_yolo_detection", return_value={"enabled": True, "detections": []}
        ):
            intent, _, _ = resolve_yolo_route("image")
            self.assertEqual(intent.inspection_type, "unknown")


if __name__ == "__main__":
    unittest.main()
