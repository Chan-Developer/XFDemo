from __future__ import annotations

import base64
from typing import Any, Dict, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from prompt import system_prompt


class InspectState(TypedDict, total=False):
    query: str
    image: str
    usage: Dict[str, int]
    report: str


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                parts.append(str(item.get("text", "")))
        return "".join(parts)
    return str(content or "")


def _extract_usage(metadata: Any) -> Dict[str, int]:
    if not isinstance(metadata, dict):
        return {}
    token_usage = metadata.get("token_usage")
    if not isinstance(token_usage, dict):
        return {}
    out: Dict[str, int] = {}
    for k, v in token_usage.items():
        if isinstance(v, int):
            out[k] = v
    return out


def _normalize_image(image: str | None) -> str | None:
    """
    Accept:
    - http(s) URL
    - data URL: data:image/...;base64,...
    - raw base64 (we will wrap as data URL)
    """
    if not image:
        return None
    s = image.strip()
    if not s:
        return None
    if s.startswith("http://") or s.startswith("https://") or s.startswith("data:"):
        return s
    # Best-effort: if it's base64, wrap it as a JPEG data URL.
    try:
        base64.b64decode(s[:64] + "==", validate=False)
        return f"data:image/jpeg;base64,{s}"
    except Exception:
        return s


def create_inspection_graph(llm):
    """
    Minimal single-step graph:
    - Builds a multimodal prompt (text + optional image)
    - Calls the model once
    - Returns `report` + token `usage` when available
    """

    def _run(state: InspectState) -> InspectState:
        query = (state.get("query") or "").strip()
        image = _normalize_image(state.get("image"))

        content_parts: list[dict[str, Any]] = [{"type": "text", "text": query}]
        if image:
            content_parts.append({"type": "image_url", "image_url": {"url": image}})

        resp = llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=content_parts),
            ]
        )

        text = _extract_text(getattr(resp, "content", ""))
        usage = _extract_usage(getattr(resp, "response_metadata", None))

        merged_usage = dict(state.get("usage") or {})
        for k, v in usage.items():
            merged_usage[k] = merged_usage.get(k, 0) + v

        return {
            **state,
            "report": (text or "").strip(),
            "usage": merged_usage,
        }

    graph = StateGraph(InspectState)
    graph.add_node("inspect", _run)
    graph.add_edge(START, "inspect")
    graph.add_edge("inspect", END)
    return graph.compile()

