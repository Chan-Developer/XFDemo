from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from openai import OpenAI

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False


DEFAULT_BASE_URL = "https://llm-s81wox1ib2cco1tz.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3-vl-plus"
PROJECT_DIR = Path(__file__).resolve().parents[2]
REFERENCE_IMAGE = PROJECT_DIR / "agent_reference" / "2806.png"

INTERNAL_LABELS = [
    "室内消火栓手轮缺失",
    "室内消火栓栓口方向错误",
    "室内消火栓无消防水带",
    "室内消火栓无消防水枪",
    "室内消火栓消防接口缺失",
    "消防软管卷盘供水管道折弯严重",
    "室内消火栓无箱体",
    "室内消火栓箱锈蚀",
    "室内消火栓箱门缺失",
]

APPEARANCE_LABELS = [
    "室内消火栓箱明显部位未采用耐久性文字或图形标注操作说明",
    "室内消火栓箱门上未标注“消火栓”和英文“FIRE HYDRANT”字样",
    "室内消火栓箱体无铭牌",
    "室内消火栓箱门标识模糊",
    "室内消火栓箱体铭牌模糊",
    "室内消火栓箱门为玻璃门",
    "室内消火栓箱体或箱门被物品遮挡",
]

AUTO_PROMPT = f"""你是消防巡检助手。根据单张图片完成室内消火栓巡检。
先自动判断本图主要检查范围：
- 箱门开启，箱内阀门、手轮、栓口、水带、水枪、接口、软管卷盘等内部器材清晰可见时，按“内部组件”判断。
- 箱门关闭，或主要看到箱门/箱体正面、文字标识、英文 FIRE HYDRANT、操作说明、铭牌、材质、遮挡时，按“箱体外观”判断。
- 一张图里如果内部和外观都清楚，优先输出证据最充分、最影响安全巡检的一侧；不要把不可见项目硬判为异常。

内部组件可选隐患标签：{"；".join(INTERNAL_LABELS)}。
箱体外观可选隐患标签：{"；".join(APPEARANCE_LABELS)}。

判定规则：
1. 只依据图片中清晰可见的内容。
2. 被遮挡、反光、画面外或看不清的部件，可以说明“当前画面无法判断”，但不要直接判成异常。
3. 隐患标签只能从列表选择，不要创造新标签。
4. 不输出思维链，只输出可核验的短依据。

输出格式固定为：
检查范围：内部组件/箱体外观
结论：合规/不合规/无法判断
可见依据：一句话说明直接可见事实。
隐患标签：多个隐患用“；”分隔；无隐患写“无”。
"""

INTERNAL_JUDGE_PROMPT = f"""你是消防设施复核专家。现在有两张图：
- 第一张是标准参考图，展示开门状态下室内消火栓箱内部完整组件，可作为组件完整性和位置关系参考。
- 第二张是用户上传的待检图。

你的任务是复核“首轮模型输出”是否被图片证据支持，并在必要时矫正。重点检查：箱体、箱门、手轮、栓口方向、消防水带、消防水枪、消防接口、消防软管卷盘供水管道、锈蚀或缺失状态。

可选内部隐患标签：{"；".join(INTERNAL_LABELS)}。

专业复核规则：
1. 只保留用户图中清晰可见、证据充分的隐患；看不清、被遮挡、画面外、反光导致无法确认的项目不能判为缺失。
2. 参考图用于识别“完整组件应长什么样”和相对位置，不要求用户图和参考图完全一致。
3. 如果首轮模型把合规部件误报为缺失，要删除该标签。
4. 如果用户图中有首轮漏掉且清晰可见的内部隐患，要补充。
5. 输出最终给前端看的结论，不要输出推理过程，不要提“首轮模型错了/误判/漏判”，不要引用法规条文编号。

首轮模型输出：
{{raw_report}}

请按固定格式输出：
检查范围：内部组件
结论：合规/不合规/无法判断
可见依据：用1-2句话说明最终判定依据。
隐患标签：多个隐患用“；”分隔；无隐患写“无”。
复核说明：说明保留、删除或补充了哪些关键判断；没有修正则写“首轮结果与图像证据一致”。
"""

APPEARANCE_JUDGE_PROMPT = f"""你是消防设施外观复核专家。请复核用户上传图片中的室内消火栓箱体外观判定。

可选外观隐患标签：{"；".join(APPEARANCE_LABELS)}。

专业复核规则：
1. 只保留图片中清晰可见、证据充分的外观隐患。
2. 操作说明、“消火栓 / FIRE HYDRANT”、铭牌、箱门材质、遮挡需要分别核对；不能因为其中一个缺失就自动推断其他也缺失。
3. 文字模糊和文字缺失要区分：能看到有文字但读不清是“模糊”，完全没有对应文字才是“未标注/无铭牌”。
4. 如果画面角度、裁切、遮挡导致无法确认，不要直接判为异常。
5. 输出最终给前端看的结论，不要输出推理过程，不要提“首轮模型错了/误判/漏判”，不要引用法规条文编号。

首轮模型输出：
{{raw_report}}

请按固定格式输出：
检查范围：箱体外观
结论：合规/不合规/无法判断
可见依据：用1-2句话说明最终判定依据。
隐患标签：多个隐患用“；”分隔；无隐患写“无”。
复核说明：说明保留、删除或补充了哪些关键判断；没有修正则写“首轮结果与图像证据一致”。
"""

WHITESPACE_RE = re.compile(r"\s+")
THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


class InspectionState(TypedDict, total=False):
    query: str
    image: str | None
    task: str
    messages: list[dict[str, Any]]
    report: str
    raw_report: str
    usage: dict[str, int]


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    base_url: str
    model: str
    temperature: float
    top_p: float
    max_tokens: int
    thinking_budget: int
    max_output_chars: int
    max_identical_deltas: int
    enable_thinking: bool


@dataclass(frozen=True)
class ModelResult:
    content: str
    usage: dict[str, int]


@dataclass(frozen=True)
class ModelDelta:
    content: str = ""
    reasoning_content: str = ""
    usage: dict[str, int] | None = None


def load_env() -> None:
    for env_file in (Path.cwd() / ".env", PROJECT_DIR / ".env", PROJECT_DIR / "deploy" / ".env"):
        if env_file.exists():
            load_dotenv(env_file, override=False)
    load_dotenv(override=False)


def first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def env_int(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)


def env_float(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def env_bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y", "on"}


def get_settings() -> Settings:
    load_env()
    return Settings(
        api_key=first_env("DASHSCOPE_API_KEY", "ALIYUN_API_KEY", "QWEN_API_KEY", "VLLM_API_KEY"),
        base_url=first_env("DASHSCOPE_BASE_URL", "ALIYUN_BASE_URL", "QWEN_BASE_URL", "VLLM_API_BASE") or DEFAULT_BASE_URL,
        model=first_env("DASHSCOPE_MODEL", "ALIYUN_MODEL", "QWEN_MODEL", "MODEL_NAME") or DEFAULT_MODEL,
        temperature=env_float("TEMPERATURE", "0.1"),
        top_p=env_float("TOP_P", "0.8"),
        max_tokens=env_int("MAX_TOKENS", "768"),
        thinking_budget=env_int("THINKING_BUDGET", "4096"),
        max_output_chars=env_int("MAX_OUTPUT_CHARS", "1600"),
        max_identical_deltas=env_int("MAX_IDENTICAL_DELTAS", "3"),
        enable_thinking=env_bool("ENABLE_THINKING", "false"),
    )


class QwenClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.api_key:
            raise RuntimeError("缺少 API Key，请在 .env 中配置 DASHSCOPE_API_KEY")
        self.settings = settings
        self.client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)

    def _params(self, messages: list[dict[str, Any]], stream: bool) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "stream": stream,
            "temperature": self.settings.temperature,
            "top_p": self.settings.top_p,
            "max_tokens": self.settings.max_tokens,
        }
        if any(key in self.settings.base_url for key in ("dashscope", "aliyun", "maas.aliyuncs")):
            params["extra_body"] = {
                "enable_thinking": self.settings.enable_thinking,
                "thinking_budget": self.settings.thinking_budget,
            }
        return params

    def invoke(self, messages: list[dict[str, Any]]) -> ModelResult:
        completion = self.client.chat.completions.create(**self._params(messages, stream=False))
        message = completion.choices[0].message if completion.choices else None
        return ModelResult(
            content=(getattr(message, "content", "") if message else "") or "",
            usage=extract_usage(getattr(completion, "usage", None)),
        )

    def stream(self, messages: list[dict[str, Any]]):
        for chunk in self.client.chat.completions.create(**self._params(messages, stream=True)):
            usage = extract_usage(getattr(chunk, "usage", None))
            if not getattr(chunk, "choices", None):
                if usage:
                    yield ModelDelta(usage=usage)
                continue
            delta = chunk.choices[0].delta
            yield ModelDelta(
                content=getattr(delta, "content", None) or "",
                reasoning_content=getattr(delta, "reasoning_content", None) or "",
                usage=usage,
            )


def extract_usage(usage: Any) -> dict[str, int]:
    if not usage:
        return {}
    fields = ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens")
    if isinstance(usage, dict):
        return {key: usage[key] for key in fields if isinstance(usage.get(key), int)}
    return {key: value for key in fields if isinstance(value := getattr(usage, key, None), int)}


def normalize_image(image: str | None) -> str | None:
    if not image:
        return None
    value = image.strip()
    if not value:
        return None
    if value.startswith(("http://", "https://", "data:")):
        return value
    return f"data:image/jpeg;base64,{value}"


def file_to_data_url(path: Path) -> str | None:
    if not path.exists():
        return None
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def detect_task(query: str, explicit_task: str | None = None, report: str | None = None) -> str:
    task = (explicit_task or "").strip().lower()
    if task in {"internal", "internal_components", "内部", "内部组件"}:
        return "internal_components"
    if task in {"appearance", "外观", "箱体外观"}:
        return "appearance"
    text = f"{query or ''}\n{report or ''}"
    if any(word in text for word in ("检查范围：内部", "内部组件", "检查内部", "箱内", "水带", "水枪", "手轮", "栓口", "接口", "卷盘")):
        return "internal_components"
    if any(word in text for word in ("检查范围：箱体外观", "外观", "检查外观", "箱门标识", "FIRE HYDRANT", "铭牌", "操作说明", "玻璃门")):
        return "appearance"
    return "auto"


def build_messages(query: str, image: str | None, task: str) -> list[dict[str, Any]]:
    content_parts: list[dict[str, Any]] = [{"type": "text", "text": f"{AUTO_PROMPT}\n用户问题：{query}"}]
    if image:
        content_parts.insert(0, {"type": "image_url", "image_url": {"url": image}})
    return [{"role": "user", "content": content_parts}]


def build_judge_messages(query: str, image: str, raw_report: str, task: str) -> list[dict[str, Any]]:
    task = "internal_components" if task == "internal_components" else "appearance"
    prompt_template = INTERNAL_JUDGE_PROMPT if task == "internal_components" else APPEARANCE_JUDGE_PROMPT
    prompt = prompt_template.format(raw_report=raw_report)
    parts: list[dict[str, Any]] = []
    if task == "internal_components":
        reference_url = file_to_data_url(REFERENCE_IMAGE)
        if reference_url:
            parts.extend([
                {"type": "text", "text": "标准参考图：开门状态下的完整室内消火栓内部组件。"},
                {"type": "image_url", "image_url": {"url": reference_url}},
            ])
    parts.extend([
        {"type": "text", "text": "用户待检图："},
        {"type": "image_url", "image_url": {"url": image}},
        {"type": "text", "text": f"用户问题：{query}\n\n{prompt}"},
    ])
    return [{"role": "user", "content": parts}]



def sanitize_final_report(text: str) -> str:
    candidate = (text or "").strip()
    if not candidate:
        return candidate
    allowed_labels = INTERNAL_LABELS + APPEARANCE_LABELS
    cleaned_lines: list[str] = []
    for raw_line in candidate.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("隐患标签："):
            value = line.split("：", 1)[1].strip().strip("。")
            if value in {"", "无", "无隐患", "无隐患标签"}:
                line = "隐患标签：无"
            else:
                matched = [label for label in allowed_labels if label in value]
                line = "隐患标签：" + ("；".join(dict.fromkeys(matched)) if matched else "无")
        if line.startswith("复核说明：") and any(word in line for word in ("首轮", "模型", "误判", "漏判")):
            line = "复核说明：已根据参考图和用户图完成二次复核，最终结果以图像可见证据为准。"
        line = re.sub(r"《[^》]+》[^；。]*", "", line)
        line = re.sub(r"GB\s*\d+[\d.-]*[^；。]*", "", line, flags=re.IGNORECASE)
        line = line.replace("首轮结果与图像证据一致", "二次复核结果与图像证据一致")
        cleaned_lines.append(line.strip())
    return "\n".join(cleaned_lines)

def prepare_input(state: InspectionState) -> InspectionState:
    query = (state.get("query") or "").strip()
    if not query:
        raise ValueError("Query is required")
    image = normalize_image(state.get("image"))
    task = detect_task(query=query, explicit_task=state.get("task"))
    return {"query": query, "image": image, "task": task, "messages": build_messages(query=query, image=image, task=task)}


class InspectionAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = QwenClient(settings)

    def prepare(self, data: dict[str, Any]) -> InspectionState:
        return prepare_input({
            "query": (data or {}).get("query", ""),
            "image": (data or {}).get("image"),
            "task": (data or {}).get("task", ""),
        })

    def invoke(self, data: dict[str, Any]) -> InspectionState:
        prepared = self.prepare(data)
        first = self.model.invoke(prepared["messages"])
        raw_report = trim_output(strip_reasoning(first.content), self.settings.max_output_chars)
        final_report = raw_report
        usage = dict(first.usage)

        image = prepared.get("image")
        if image:
            judge_task = detect_task(prepared.get("query", ""), prepared.get("task"), raw_report)
            if judge_task == "auto":
                judge_task = "internal_components" if "内部" in raw_report else "appearance"
            judge_messages = build_judge_messages(prepared.get("query", ""), image, raw_report, judge_task)
            reviewed = self.model.invoke(judge_messages)
            reviewed_text = trim_output(strip_reasoning(reviewed.content), self.settings.max_output_chars)
            if reviewed_text:
                final_report = sanitize_final_report(reviewed_text)
            usage = merge_usage(usage, reviewed.usage)

        return {**prepared, "raw_report": raw_report, "report": sanitize_final_report(final_report), "usage": usage}

    def stream_checked(self, data: dict[str, Any]) -> InspectionState:
        return self.invoke(data)

    def stream(self, messages: list[dict[str, Any]]):
        return self.model.stream(messages)


def merge_usage(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    merged = dict(left or {})
    for key, value in (right or {}).items():
        if isinstance(value, int):
            merged[key] = merged.get(key, 0) + value
    return merged


_agent_cache: tuple[Settings, InspectionAgent] | None = None


def get_agent() -> InspectionAgent:
    global _agent_cache
    settings = get_settings()
    if _agent_cache and _agent_cache[0] == settings:
        return _agent_cache[1]
    agent = InspectionAgent(settings)
    _agent_cache = (settings, agent)
    return agent


def normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub("", text or "")


def has_repeated_tail(text: str) -> bool:
    compact = normalize_text(text)
    if len(compact) < 72:
        return False
    max_unit = min(80, len(compact) // 3)
    for unit_len in range(max_unit, 15, -1):
        unit = compact[-unit_len:]
        if unit and compact.endswith(unit * 3):
            return True
    return False


def strip_reasoning(text: str) -> str:
    return THINK_BLOCK_RE.sub("", text or "").strip()


def trim_output(text: str, max_chars: int) -> str:
    candidate = (text or "").strip()
    if not candidate:
        return candidate
    changed = True
    while changed:
        changed = False
        max_unit = min(80, len(candidate) // 3)
        for unit_len in range(max_unit, 15, -1):
            unit = candidate[-unit_len:]
            if unit and candidate.endswith(unit * 3):
                candidate = candidate[: -(2 * unit_len)].rstrip()
                changed = True
                break
    if len(candidate) > max_chars:
        candidate = candidate[:max_chars].rstrip()
    return candidate


def ndjson(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


class _SimpleCompiledGraph:
    def __init__(self, func: Any) -> None:
        self.func = func

    def invoke(self, state: InspectionState) -> InspectionState:
        return self.func(state)


def create_prepare_graph():
    return _SimpleCompiledGraph(prepare_input)


def create_inspection_graph(model: Any):
    def invoke_plain(state: InspectionState) -> InspectionState:
        prepared = prepare_input(state)
        response = model.invoke(prepared["messages"])
        return {**prepared, "report": trim_output(strip_reasoning(response.content), 1200), "usage": response.usage}
    return _SimpleCompiledGraph(invoke_plain)
