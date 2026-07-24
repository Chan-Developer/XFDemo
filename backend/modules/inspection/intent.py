from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

from backend.modules.inspection.utils import strip_reasoning, trim_output


INSPECTION_TYPES = {
    "indoor_hydrant": "室内消火栓",
    "outdoor_hydrant": "室外消火栓",
    "fire_extinguisher": "灭火器",
    "unknown": "无法判断",
}


INTENT_PROMPT = """你是消防设施图片的任务分流器。
请只判断用户图片和问题最适合进入哪个检测分支，不要做合规结论。

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
        return INSPECTION_TYPES.get(self.inspection_type, self.inspection_type)


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


def build_intent_messages(query: str, image: str | None) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"type": "text", "text": f"{INTENT_PROMPT}\n用户问题：{query or '请判断图片中的消防设施异常'}"}]
    if image:
        parts.insert(0, {"type": "image_url", "image_url": {"url": image}})
    return [{"role": "user", "content": parts}]


def parse_intent_output(text: str) -> IntentResult | None:
    raw = trim_output(strip_reasoning(text or ""), 1200).strip()
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
    inspection_type = str(data.get("inspection_type") or "unknown").strip()
    if inspection_type not in INSPECTION_TYPES:
        inspection_type = "unknown"
    try:
        confidence = float(data.get("confidence") or 0)
    except Exception:
        confidence = 0.0
    scope_hint = str(data.get("scope_hint") or "unknown").strip()
    evidence = str(data.get("evidence") or "").strip()
    return IntentResult(inspection_type, max(0.0, min(confidence, 1.0)), scope_hint, evidence, "qwen_vl", raw)


def rule_based_intent(query: str, explicit_task: str | None = None) -> IntentResult:
    explicit = explicit_intent(explicit_task)
    if explicit:
        return explicit
    text = (query or "").lower()
    if any(token in text for token in ("灭火器", "压力表", "压力指示器", "extinguisher")):
        return IntentResult("fire_extinguisher", 0.72, "extinguisher", "问题中出现灭火器相关关键词", "rule")
    if any(token in text for token in ("室外消火栓", "地上消火栓", "地下消火栓", "outdoor hydrant")):
        return IntentResult("outdoor_hydrant", 0.72, "outdoor", "问题中出现室外消火栓相关关键词", "rule")
    if any(token in text for token in ("水带", "水枪", "栓口", "卷盘", "箱体外观", "室内消火栓", "消火栓箱")):
        scope = "appearance" if "外观" in text else "internal_components"
        return IntentResult("indoor_hydrant", 0.68, scope, "问题中出现室内消火栓箱相关关键词", "rule")
    return IntentResult("indoor_hydrant", 0.45, "internal_components", "未明确识别品类，默认进入室内消火栓分支", "fallback")


def resolve_intent(model: Any, query: str, image: str | None, explicit_task: str | None = None) -> tuple[IntentResult, dict[str, Any]]:
    explicit = explicit_intent(explicit_task)
    if explicit:
        return explicit, {"latencyMs": 0, "usage": {}, "error": ""}

    started = time.perf_counter()
    try:
        response = model.invoke(build_intent_messages(query, image))
        parsed = parse_intent_output(response.content)
        latency_ms = int((time.perf_counter() - started) * 1000)
        if parsed and parsed.inspection_type != "unknown" and parsed.confidence >= 0.45:
            return parsed, {"latencyMs": latency_ms, "usage": response.usage, "error": ""}
        fallback = rule_based_intent(query, explicit_task)
        return fallback, {
            "latencyMs": latency_ms,
            "usage": response.usage,
            "error": "low_confidence_or_unknown",
            "rawOutput": trim_output(strip_reasoning(response.content), 800),
        }
    except Exception as exc:
        fallback = rule_based_intent(query, explicit_task)
        return fallback, {
            "latencyMs": int((time.perf_counter() - started) * 1000),
            "usage": {},
            "error": str(exc),
        }


def intent_trace_payload(intent: IntentResult, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = asdict(intent)
    payload["displayName"] = intent.display_name
    payload.update(meta or {})
    return payload
