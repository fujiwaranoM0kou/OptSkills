from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Union


JsonType = Union[Dict[str, Any], List[Any]]


def strip_markdown_fence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned.startswith("```"):
        return cleaned
    cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _try_load_json(snippet: str) -> Optional[JsonType]:
    try:
        loaded = json.loads(snippet)
        if isinstance(loaded, (dict, list)):
            return loaded
    except json.JSONDecodeError:
        pass
    snippet = re.sub(r",\s*([}\]])", r"\1", snippet)
    try:
        loaded = json.loads(snippet)
        if isinstance(loaded, (dict, list)):
            return loaded
    except json.JSONDecodeError:
        return None
    return None


def _extract_balanced_block(text: str, open_char: str, close_char: str) -> Optional[str]:
    start = text.find(open_char)
    if start < 0:
        return None
    depth = 0
    for idx in range(start, len(text)):
        ch = text[idx]
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def extract_json(text: str, default: Optional[JsonType] = None) -> JsonType:
    if default is None:
        default = {}
    if not text or not text.strip():
        return default

    cleaned = strip_markdown_fence(text)
    direct = _try_load_json(cleaned)
    if direct is not None:
        return direct

    object_block = _extract_balanced_block(cleaned, "{", "}")
    if object_block:
        loaded = _try_load_json(object_block)
        if loaded is not None:
            return loaded

    array_block = _extract_balanced_block(cleaned, "[", "]")
    if array_block:
        loaded = _try_load_json(array_block)
        if loaded is not None:
            return loaded

    return default
