from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .llm_config import LLMConfig


def _extract_message_content(payload: Dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as err:
        raise RuntimeError(f"Unexpected chat response payload: {payload}") from err
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: List[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                chunks.append(str(item.get("text", "")))
        return "".join(chunks)
    return str(content)


def _extract_first_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as err:
        raise RuntimeError(f"Unexpected chat response payload: {payload}") from err
    if not isinstance(message, dict):
        raise RuntimeError(f"Invalid message type in response: {type(message)}")
    return message


class LLMCaller:
    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        self.config = config or LLMConfig.from_env()

    def _apply_non_thinking_default(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        chat_template_kwargs = payload.get("chat_template_kwargs")
        if not isinstance(chat_template_kwargs, dict):
            chat_template_kwargs = {}
        chat_template_kwargs["thinking"] = False
        payload["chat_template_kwargs"] = chat_template_kwargs
        return payload

    def chat(
        self,
        user_prompt: str,
        system_prompt: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        messages: List[Dict[str, str]] = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
        }
        if self.config.top_p is not None:
            payload["top_p"] = self.config.top_p
        if self.config.extra:
            payload.update(self.config.extra)
        if extra:
            payload.update(extra)
        payload = self._apply_non_thinking_default(payload)

        response_payload = self._post_chat(payload)
        return _extract_message_content(response_payload).strip()

    def chat_messages(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if self.config.top_p is not None:
            payload["top_p"] = self.config.top_p
        if self.config.extra:
            payload.update(self.config.extra)
        if extra:
            payload.update(extra)
        payload = self._apply_non_thinking_default(payload)

        response_payload = self._post_chat(payload)
        return _extract_first_message(response_payload)

    def _post_chat(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        last_error: Optional[Exception] = None

        for attempt in range(self.config.retries):
            req = urllib.request.Request(url=url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            if self.config.api_key:
                req.add_header("Authorization", f"Bearer {self.config.api_key}")

            try:
                with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                    response_payload = json.loads(resp.read().decode("utf-8"))
                return response_payload
            except urllib.error.HTTPError as err:
                detail = err.read().decode("utf-8", errors="ignore")
                last_error = RuntimeError(f"LLM HTTP error {err.code}: {detail}")
            except urllib.error.URLError as err:
                last_error = RuntimeError(f"LLM connection error: {err}")
            except Exception as err:  # pragma: no cover - defensive
                last_error = err

            if attempt < self.config.retries - 1:
                time.sleep(1.5 * (attempt + 1))

        raise RuntimeError(f"LLM call failed after retries: {last_error}")
