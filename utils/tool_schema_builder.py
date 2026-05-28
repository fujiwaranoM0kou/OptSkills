from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools import TOOL_REGISTRY, get_tool_info


def build_openai_tools_schema(tool_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    names = tool_names if tool_names is not None else list(TOOL_REGISTRY.keys())
    schema: List[Dict[str, Any]] = []
    for name in names:
        try:
            info = get_tool_info(name)
        except Exception:
            continue
        tool_def: Dict[str, Any] = {
            "type": "function",
            "function": {
                "name": info["name"],
                "description": info["description"],
            },
        }
        if info.get("parameters"):
            tool_def["function"]["parameters"] = info["parameters"]
        schema.append(tool_def)
    return schema

