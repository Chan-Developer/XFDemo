import os
from pathlib import Path
from typing import Any

from .paths import PROJECT_DIR
from .types import Settings

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False

DEFAULT_BASE_URL = "https://llm-s81wox1ib2cco1tz.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen3-vl-plus"

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
        api_key=first_env("VLLM_API_KEY", "DASHSCOPE_API_KEY", "ALIYUN_API_KEY", "QWEN_API_KEY"),
        base_url=first_env("VLLM_API_BASE", "DASHSCOPE_BASE_URL", "ALIYUN_BASE_URL", "QWEN_BASE_URL") or DEFAULT_BASE_URL,
        model=first_env("MODEL_NAME", "DASHSCOPE_MODEL", "ALIYUN_MODEL", "QWEN_MODEL") or DEFAULT_MODEL,
        judge_api_key=first_env("DASHSCOPE_API_KEY", "ALIYUN_API_KEY", "QWEN_API_KEY", "VLLM_API_KEY"),
        judge_base_url=first_env("DASHSCOPE_BASE_URL", "ALIYUN_BASE_URL", "QWEN_BASE_URL", "VLLM_API_BASE") or DEFAULT_BASE_URL,
        judge_model=first_env("DASHSCOPE_MODEL", "ALIYUN_MODEL", "QWEN_MODEL", "MODEL_NAME") or DEFAULT_MODEL,
        temperature=env_float("TEMPERATURE", "0.1"),
        top_p=env_float("TOP_P", "0.8"),
        max_tokens=env_int("MAX_TOKENS", "768"),
        thinking_budget=env_int("THINKING_BUDGET", "4096"),
        max_output_chars=env_int("MAX_OUTPUT_CHARS", "1600"),
        max_identical_deltas=env_int("MAX_IDENTICAL_DELTAS", "3"),
        enable_thinking=env_bool("ENABLE_THINKING", "false"),
    )
