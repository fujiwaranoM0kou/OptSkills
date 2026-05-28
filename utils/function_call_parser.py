from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, Tuple, Union


_ANSWER_RE = re.compile(r"<answer>\s*(.*?)\s*</answer>", re.DOTALL | re.IGNORECASE)


def _is_finite_number(text: str) -> bool:
    try:
        value = float(str(text).strip())
    except (TypeError, ValueError):
        return False
    return math.isfinite(value)


def _extract_answer_payload(response: str) -> str:
    matches = [match.group(1).strip() for match in _ANSWER_RE.finditer(response)]
    if not matches:
        return ""

    # Models sometimes repeat the prompt's example, e.g. <answer>123.45</answer>,
    # before giving the real final answer. Prefer the last numeric answer tag.
    for payload in reversed(matches):
        if _is_finite_number(payload):
            return payload
    return matches[-1]


def parse_function_call_response(response: Union[str, Dict[str, Any]]) -> Tuple[str, Any]:
    if isinstance(response, dict):
        tool_calls = response.get("tool_calls", [])
        if isinstance(tool_calls, list) and tool_calls:
            first_call = tool_calls[0]
            if not isinstance(first_call, dict):
                return "error", "Invalid tool_call format."
            function_data = first_call.get("function", {})
            if not isinstance(function_data, dict):
                return "error", "Missing function block in tool_call."
            tool_name = str(function_data.get("name", "")).strip()
            arguments = function_data.get("arguments", "{}")
            if isinstance(arguments, str):
                try:
                    parameters = json.loads(arguments)
                except json.JSONDecodeError:
                    parameters = {"code": arguments}
            elif isinstance(arguments, dict):
                parameters = arguments
            else:
                parameters = {}
            if not tool_name:
                return "error", "Tool call has empty name."
            return "function_call", {
                "tool_name": tool_name,
                "parameters": parameters,
                "tool_call_id": str(first_call.get("id", "")).strip(),
            }

        content = response.get("content", "")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            content = "".join(parts)
        response = str(content)

    if isinstance(response, str):
        answer_payload = _extract_answer_payload(response)
        if answer_payload:
            return "answer", answer_payload
        return "text", response

    return "error", f"Unknown response type: {type(response)}"
