from __future__ import annotations

import json
from typing import Any, Dict, Union

from tools.base import BaseTool
from tools.tool_registry import register_tool
from utils.run_code import run_python_code


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@register_tool("run_code")
class RunCodeTool(BaseTool):
    name = "run_code"
    description = "Execute Python code and return stdout/stderr/returncode/result."
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Executable Python code.",
            },
            "timeout": {
                "type": "integer",
                "description": "Execution timeout in seconds.",
                "default": 60,
            },
        },
        "required": ["code"],
    }

    def call(self, params: Union[str, Dict[str, Any]], **kwargs: Any) -> Dict[str, Any]:
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {"code": params}
        if not isinstance(params, dict):
            params = {}

        code = str(params.get("code", "")).strip()
        if not code:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": "Missing required parameter: code",
                "result": None,
                "timeout": False,
                "duration_s": 0.0,
            }

        timeout_default = _safe_int(self.config.get("timeout", 60), 60)
        requested_timeout = _safe_int(params.get("timeout", timeout_default), timeout_default)
        timeout = min(max(1, requested_timeout), max(1, timeout_default))
        cwd = self.config.get("cwd")
        python_bin = self.config.get("python_bin")
        return run_python_code(code=code, timeout=timeout, cwd=cwd, python_bin=python_bin)
