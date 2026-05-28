from __future__ import annotations

from typing import Any, Dict, List, Type

from tools.base import BaseTool

TOOL_REGISTRY: Dict[str, Type[BaseTool]] = {}


def register_tool(name: str | None = None):
    def decorator(cls: Type[BaseTool]) -> Type[BaseTool]:
        tool_name = name or cls.name
        if not tool_name:
            raise ValueError("Tool registration requires a name.")
        TOOL_REGISTRY[tool_name] = cls
        cls.name = tool_name
        return cls

    return decorator


def get_tool(name: str) -> Type[BaseTool]:
    if name not in TOOL_REGISTRY:
        raise ValueError(f"Tool '{name}' not found. Available: {', '.join(list_tools())}")
    return TOOL_REGISTRY[name]


def list_tools() -> List[str]:
    return list(TOOL_REGISTRY.keys())


def get_tool_info(name: str) -> Dict[str, Any]:
    tool_cls = get_tool(name)
    return {
        "name": tool_cls.name,
        "description": tool_cls.description,
        "parameters": tool_cls.parameters,
    }

