from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .env_loader import load_project_dotenv


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_optional_json(name: str) -> Dict[str, Any]:
    value = os.getenv(name, "").strip()
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout: int = 180
    temperature: float = 0.0
    max_tokens: int = 8192
    top_p: Optional[float] = None
    retries: int = 3
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls, prefix: str = "OPTSKILL") -> "LLMConfig":
        load_project_dotenv()
        base_url = (
            os.getenv(f"{prefix}_BASE_URL")
            or os.getenv("DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com/v1"
        )
        api_key = (
            os.getenv(f"{prefix}_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or ""
        ).strip()
        if not api_key:
            raise RuntimeError(
                f"Missing API key: set {prefix}_API_KEY, DEEPSEEK_API_KEY, or OPENAI_API_KEY."
            )
        model = (
            os.getenv(f"{prefix}_MODEL")
            or os.getenv("DEEPSEEK_MODEL")
            or "deepseek-chat"
        )
        timeout = _env_int(f"{prefix}_TIMEOUT", 180)
        temperature = _env_float(f"{prefix}_TEMPERATURE", 0.0)
        max_tokens = _env_int(f"{prefix}_MAX_TOKENS", 8192)
        retries = _env_int(f"{prefix}_RETRIES", 3)
        top_p_raw = os.getenv(f"{prefix}_TOP_P")
        top_p = None
        if top_p_raw and top_p_raw.strip():
            try:
                top_p = float(top_p_raw)
            except ValueError:
                top_p = None
        extra = _env_optional_json(f"{prefix}_EXTRA_JSON")
        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=timeout,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            retries=retries,
            extra=extra,
        )
