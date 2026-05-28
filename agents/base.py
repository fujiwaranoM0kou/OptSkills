from __future__ import annotations

from typing import Any, Dict, Optional

from llm.llm_caller import LLMCaller
from utils.extract_json import extract_json


class BaseAgent:
    def __init__(
        self,
        llm: Optional[LLMCaller] = None,
        system_prompt: str = "",
    ) -> None:
        self.llm = llm or LLMCaller()
        self.system_prompt = system_prompt

    def call_llm(self, prompt: str) -> str:
        return self.llm.chat(user_prompt=prompt, system_prompt=self.system_prompt)

    def call_json(self, prompt: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if default is None:
            default = {}
        raw = self.call_llm(prompt)
        data = extract_json(raw, default=default)
        if not isinstance(data, dict):
            data = default
        payload = {"raw": raw, "data": data, "prompt": prompt}
        return payload
