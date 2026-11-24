from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

from backend.modules.inspection.utils import strip_reasoning, trim_output
from backend.modules.inspection.image_evidence import image_review_content, normalized_box, conflicting_facility_evidence
from backend.modules.inspection.parser import extract_json_object


INSPECTION_TYPES = {
    "indoor_hydrant": "室内消火栓",
    "outdoor_hydrant": "室外消火栓",
    "fire_extinguisher": "灭火器",
    "unknown": "无法判断",
}

DETECTION_ONLY_TYPES = {
    "water_pump_connector": "水泵接合器", "water_supply": "消防供水设施",
    "wet_alarm_valve": "湿式报警阀组", "fire_detector": "火灾探测器",
    "fire_alarm_controller": "火灾报警控制器", "sprinkler": "洒水喷头",
    "evacuation_passage": "疏散通道", "fire_door": "防火门",
}


INTENT_PROMPT = """你是消防设施图片的对象分类器。
只根据当前图片中的主体设备判断检测分支，不要参考任何固定任务文案，不要做合规结论。

可选 inspection_type：
1. indoor_hydrant：室内消火栓箱内部或箱体外观，包括水带、水枪、栓口、箱门、标识等。
2. outdoor_hydrant：室外地上/地下消火栓、道路或室外场景中的消火栓本体。
3. fire_extinguisher：灭火器本体、压力表、喷管、压把、铅封等。
4. unknown：图片不具备判断条件，或不是上述消防设施。

输出严格 JSON，不要输出 Markdown：
{
  "inspection_type": "indoor_hydrant|outdoor_hydrant|fire_extinguisher|unknown",
  "confidence": 0.0,
  "scope_hint": "internal_components|appearance|outdoor|extinguisher|unknown",
  "evidence": "一句话说明你看到的关键对象"
}
"""

IMAGE_INTENT_MIN_CONFIDENCE = 0.65


@dataclass(frozen=True)
class IntentResult:
    inspection_type: str
    confidence: float
    scope_hint: str
    evidence: str
    source: str
    raw_output: str = ""

    @property
    def display_name(self) -> str:
        return {**INSPECTION_TYPES, **DETECTION_ONLY_TYPES}.get(self.inspection_type, self.inspection_type)


def explicit_intent(value: str | None) -> IntentResult | None:
    normalized = (value or "").strip().lower()
    aliases = {
        "indoor": "indoor_hydrant",
        "indoor_hydrant": "indoor_hydrant",
        "internal": "indoor_hydrant",
        "internal_components": "indoor_hydrant",
        "室内": "indoor_hydrant",
        "室内消火栓": "indoor_hydrant",
        "outdoor": "outdoor_hydrant",
        "outdoor_hydrant": "outdoor_hydrant",
        "室外": "outdoor_hydrant",
        "室外消火栓": "outdoor_hydrant",
        "fire_extinguisher": "fire_extinguisher",
        "extinguisher": "fire_extinguisher",
        "灭火器": "fire_extinguisher",
    }
    mapped = aliases.get(normalized)
    if not mapped:
        return None
    scope = {
        "indoor_hydrant": "internal_components",
        "outdoor_hydrant": "outdoor",
        "fire_extinguisher": "extinguisher",
    }.get(mapped, "unknown")
    return IntentResult(mapped, 1.0, scope, "用户显式指定检测类型", "explicit")


def build_intent_messages(query: str, image: str | None, detections: dict | None = None) -> list[dict[str, Any]]:
    _ = query
    prompt = INTENT_PROMPT
    if os.getenv("YOLO_MODE", "legacy") == "unified":
        prompt = (
            "你是消防检查图片分类器。只根据原始图片判断主体设施或通道场景，不做合规判断。\n"
            "合法inspection_type与含义：" + json.dumps({**INSPECTION_TYPES, **DETECTION_ONLY_TYPES}, ensure_ascii=False)
            + "\n分类要求：室内消火栓是箱式消火栓及其内部部件，不以拍摄地点在室内外区分；"
            "室外消火栓是地上或地下室外式栓体；灭火器是便携或推车灭火器。"
            "evacuation_passage适用于楼梯、走廊、通道场景，包括被杂物占用的通道，"
            "不要求图中有独立消防设备；不得因只有通道而返回unknown。"
            "water_supply是消防泵、供水管路等设施，wet_alarm_valve是湿式报警阀及其附属仪表阀件。"
            "water_pump_connector是消防水泵接合器，可见并列的消防接口、连接主管及阀件，"
            "地上式外形可能与室外消火栓相似，不能仅凭红色、立柱或室外位置归为outdoor_hydrant。"
            "仔细阅读设备本身清晰可辨的名称标牌；与设备结构一致的‘水泵接合器’、"
            "‘喷淋水泵接合器’标识是water_pump_connector的直接类型证据。"
            "标牌不是合规必要条件，模糊文字不要猜读；无法区分接合器与消火栓时返回unknown。"
            "特别核对：低位并列双接口、汇入同一主管及手轮组合通常是接合器候选，"
            "不可仅因红色立柱套用室外消火栓类型；需结合整体结构确认。"
            "单立柱、侧面双口和顶部手轮也可能是接合器，不能因未见单独汇流主管而排除接合器；"
            "接口被盖帽盖住时不能声称已经看清内部螺纹或断定接口制式。"
            "water_supply还包括消防水泵控制柜和控制面板。清楚可见的‘1号泵/2号泵’、"
            "‘启动/停止’、‘手动/自动’与泵控制结构组合是供水控制候选。"
            "fire_alarm_controller需有报警主机身份依据（例如火警/故障/屏蔽分区与报警显示结构），"
            "仅有红色柜体、按钮、指示灯不能证明它是火灾报警控制器。"
            "探测器与照明灯必须按全图位置分别对应，不得把较大的吸顶灯当成小型探测器。"
            "主体选择：近景清晰拍摄的具体设备优先于背景环境；设备处于走廊、楼梯口或车库入口，"
            "不代表主体就是evacuation_passage。fire_door适用于以门扇、门框、闭门器为拍摄主体，"
            "且有防火门标识或其他清晰防火门证据的图片；门处于开启状态也不改变设备类别。"
            "普通门不能仅凭门扇或安全出口标志认定为防火门。"
            "sprinkler适用于喷头特写或以喷头为明确主体的图片；"
            "仅当整体通道是主体、多个设备只是环境中的小部分时选择evacuation_passage。"
            "透明箱门关闭仍是appearance，打开才是internal_components，不因看见内部组件改变开闭状态。"
            "多种主体无法确定或无关图片返回unknown，不要强行归入消火栓或灭火器。\n"
            '只输出JSON：{"inspection_type":"上述合法值", "confidence":0.0, '
            '"scope_hint":"internal_components|appearance|outdoor|extinguisher|detection_only|unknown", '
            '"evidence":"一句话说明实际可见主体"}'
        )
        prompt += (
            '\n另外必须输出 identity_status（confirmed或uncertain）、evidence_bbox '
            '（主体在原图中的[x1,y1,x2,y2]归一化坐标，不能使用裁剪图坐标），'
            '以及 distinguishing_evidence（实际可见的区分依据）。'
            '接合器/室外消火栓、泵控制柜/报警控制器必须说明为何排除另一类型；'
            '不能区分则identity_status=uncertain并返回unknown。候选框标签只是提示，'
            '请逐一与原图核对，可以否定候选，不以置信度高低直接决定类别。'
        )
    if image and detections is not None:
        return [{"role": "user", "content": image_review_content(image, prompt, detections)}]
    parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    if image:
        parts.insert(0, {"type": "image_url", "image_url": {"url": image}})
    return [{"role": "user", "content": parts}]


def parse_intent_output(text: str) -> IntentResult | None:
    raw = trim_output(strip_reasoning(text or ""), 8000).strip()
    if not raw:
        return None
    candidate = re.sub(r"^```(?:json)?\s*", "", raw)
    candidate = re.sub(r"\s*```$", "", candidate).strip()
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end > start:
        candidate = candidate[start : end + 1]
    try:
        data = json.loads(candidate)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    inspection_type = str(data.get("inspection_type") or "unknown").strip()
    allowed = {**INSPECTION_TYPES, **DETECTION_ONLY_TYPES} if os.getenv("YOLO_MODE", "legacy") == "unified" else INSPECTION_TYPES
    if inspection_type not in allowed:
        inspection_type = "unknown"
    try:
        confidence = float(data.get("confidence") or 0)
    except Exception:
        confidence = 0.0
    if not math.isfinite(confidence):
        confidence = 0.0
    scope_hint = str(data.get("scope_hint") or "unknown").strip()
    evidence = str(data.get("evidence") or "").strip()
    return IntentResult(inspection_type, max(0.0, min(confidence, 1.0)), scope_hint, evidence, "qwen_vl", raw)


def rule_based_intent(query: str, explicit_task: str | None = None) -> IntentResult:
    _ = query, explicit_task
    return IntentResult(
        "unknown",
        0.0,
        "unknown",
        "图像证据不足，禁止默认进入室内消火栓分支",
        "fallback",
    )


def resolve_intent(model: Any, query: str, image: str | None, explicit_task: str | None = None,
                   detections: dict | None = None) -> tuple[IntentResult, dict[str, Any]]:
    explicit = explicit_intent(explicit_task)
    if explicit:
        return explicit, {"latencyMs": 0, "usage": {}, "error": ""}

    started = time.perf_counter()
    try:
        response = model.invoke(build_intent_messages(query, image, detections))
        parsed = parse_intent_output(response.content)
        grounding = extract_json_object(response.content) or {}
        requires_grounding = os.getenv("YOLO_MODE", "legacy") == "unified"
        grounded = not requires_grounding or (
            grounding.get("identity_status") == "confirmed"
            and normalized_box(grounding.get("evidence_bbox")) is not None
            and isinstance(grounding.get("distinguishing_evidence"), str)
            and bool(grounding["distinguishing_evidence"].strip())
            and bool(parsed and parsed.evidence.strip())
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        if (
            parsed
            and parsed.inspection_type != "unknown"
            and parsed.confidence >= IMAGE_INTENT_MIN_CONFIDENCE
            and grounded
        ):
            competitor = conflicting_facility_evidence(parsed.inspection_type, grounding.get("evidence_bbox"), detections)
            if competitor:
                initial = parsed
                messages = build_intent_messages("", image, detections)
                messages[0]["content"].append({"type": "text", "text": (
                    f"存在主体身份冲突：第一次判断为{initial.inspection_type}，但同一区域存在"
                    f"{competitor}的成组组件候选。请重新看原图及局部，逐项核对两种身份。"
                    "不得仅因为候选标签而改判，也不得重复第一次判断作为证据。"
                    "单立柱、带盖侧接口、顶部手轮并不能单独排除水泵接合器；"
                    "盖帽遮住接口时不得臆测螺纹形式。不能凭空猜读标牌。"
                    "若冲突类型同为fire_detector，则是位置冲突：第一次圈定的可能是灯具，"
                    "须重新核对较小探测器候选的原图位置，不能仍把大圆灯圈作探测器。"
                    "若确实支持候选类型，请给出可见区分依据及原图区域；否则返回unknown等待人工确认。"
                    "仍使用前述JSON结构。"
                )})
                second = model.invoke(messages)
                resolved = parse_intent_output(second.content)
                second_grounding = extract_json_object(second.content) or {}
                combined_usage = dict(response.usage or {})
                for key, value in (second.usage or {}).items():
                    if isinstance(value, int):
                        combined_usage[key] = combined_usage.get(key, 0) + value
                resolved_ok = (
                    resolved and resolved.inspection_type == competitor
                    and resolved.confidence >= IMAGE_INTENT_MIN_CONFIDENCE
                    and resolved.evidence.strip()
                    and second_grounding.get("identity_status") == "confirmed"
                    and normalized_box(second_grounding.get("evidence_bbox")) is not None
                    and isinstance(second_grounding.get("distinguishing_evidence"), str)
                    and second_grounding["distinguishing_evidence"].strip()
                    and not conflicting_facility_evidence(resolved.inspection_type, second_grounding.get("evidence_bbox"), detections)
                )
                meta = {"latencyMs": int((time.perf_counter() - started) * 1000), "usage": combined_usage,
                        "error": "" if resolved_ok else "unresolved_facility_conflict",
                        "conflict": {"initialType": initial.inspection_type, "candidateType": competitor,
                                     "reviewedType": resolved.inspection_type if resolved else "unknown"},
                        "grounding": {"bbox": second_grounding.get("evidence_bbox"),
                                      "distinguishingEvidence": second_grounding.get("distinguishing_evidence")}}
                if resolved_ok:
                    return resolved, meta
                return IntentResult("unknown", 0.0, "unknown", "设施类型证据相互冲突，需补拍标牌或完整主体后确认", "image_conflict"), meta
            return parsed, {"latencyMs": latency_ms, "usage": response.usage, "error": "",
                            "grounding": {"bbox": grounding.get("evidence_bbox"),
                                          "distinguishingEvidence": grounding.get("distinguishing_evidence")}}
        unknown = IntentResult(
            "unknown",
            parsed.confidence if parsed else 0.0,
            "unknown",
            (parsed.evidence if parsed else "") or "图像对象分类置信度不足",
            "qwen_vl",
            parsed.raw_output if parsed else "",
        )
        return unknown, {
            "latencyMs": latency_ms,
            "usage": response.usage,
            "error": "missing_identity_evidence" if not grounded else "low_confidence_or_unknown",
            "rawOutput": trim_output(strip_reasoning(response.content), 800),
        }
    except Exception as exc:
        unknown = IntentResult(
            "unknown",
            0.0,
            "unknown",
            "图像对象分类服务异常，未强行选择检测分支",
            "qwen_vl_error",
        )
        return unknown, {
            "latencyMs": int((time.perf_counter() - started) * 1000),
            "usage": {},
            "error": str(exc),
        }


def intent_trace_payload(intent: IntentResult, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = asdict(intent)
    payload["displayName"] = intent.display_name
    payload.update(meta or {})
    return payload
