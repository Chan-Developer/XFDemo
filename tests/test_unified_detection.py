import os
import unittest
from unittest.mock import patch

from backend.infrastructure.vision.unified import canonical_name, project_result
from backend.modules.inspection.router import resolve_yolo_route
from backend.modules.inspection.pipeline import _probe_for_intent
from backend.modules.inspection.messages import build_messages


def fixture():
    names = ["室内消火栓/消防水枪", "室内消火栓/消火栓箱门", "室外消火栓/消火栓栓体",
             "灭火器/瓶体", "灭火器/压力指示器", "防火门/门扇"]
    return {"enabled": True, "detections": [
        {"className": name, "classId": i, "confidence": 0.8,
         "bbox": [1, 2, 30, 40], "bboxNorm": [0.01, 0.02, 0.3, 0.4]}
        for i, name in enumerate(names)]}


class UnifiedTests(unittest.TestCase):
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
            "backend.modules.inspection.router.run_yolo_detection", return_value={"detections": []}
        ):
            intent, _, _ = resolve_yolo_route("image")
            self.assertEqual(intent.inspection_type, "unknown")


if __name__ == "__main__":
    unittest.main()
