from __future__ import annotations

import json
import math
import re
import time
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent
from agents.function_call_tool_handler import FunctionCallToolHandler
from prompts.function_call_agent_prompts import (
    FC_AGENT_SYSTEM_PROMPT_TEMPLATE,
    FC_AGENT_USER_PROMPT,
)
from prompts.function_call_agent_miplib_nl_prompts import (
    MIPLIB_NL_FC_AGENT_SYSTEM_PROMPT_TEMPLATE,
    MIPLIB_NL_FC_AGENT_USER_PROMPT,
)
from utils.extract_json import extract_json
from utils.function_call_parser import parse_function_call_response
from utils.runtime_logger import RuntimeLogger
from utils.tool_schema_builder import build_openai_tools_schema


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: List[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                chunks.append(str(item.get("text", "")))
        return "".join(chunks).strip()
    if content is None:
        return ""
    return str(content).strip()


class FunctionCallAgent(BaseAgent):
    def __init__(
        self,
        max_turns: int = 8,
        logger: Optional[RuntimeLogger] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(system_prompt=FC_AGENT_SYSTEM_PROMPT_TEMPLATE, **kwargs)
        self.max_turns = max_turns
        self.logger = logger
        self.tool_handler = FunctionCallToolHandler(llm=self.llm, logger=self.logger)

    def _log(
        self,
        event: str,
        message: str = "",
        *,
        sample_id: str = "",
        data: Optional[Dict[str, Any]] = None,
        level: str = "INFO",
    ) -> None:
        if self.logger is None:
            return
        self.logger.log(
            component="function_call_agent",
            event=event,
            message=message,
            sample_id=sample_id,
            data=data or {},
            level=level,
        )

    def _build_initial_messages(
        self,
        problem_description: str,
        ingredients: Any,
        skill: str,
        problem_context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        ingredients_text = json.dumps(ingredients, ensure_ascii=False, indent=2)
        context = problem_context if isinstance(problem_context, dict) else {}
        if str(context.get("bench", "")).strip().lower() == "miplib_nl":
            system_template = MIPLIB_NL_FC_AGENT_SYSTEM_PROMPT_TEMPLATE
            abstract_problem = str(context.get("abstract_problem", "")).strip() or problem_description
            parameters_json = json.dumps(context.get("parameters", {}), ensure_ascii=False, indent=2)
            files_json = json.dumps(context.get("files", []), ensure_ascii=False, indent=2)
            user_prompt = MIPLIB_NL_FC_AGENT_USER_PROMPT.format(
                abstract_problem=abstract_problem,
                parameters_json=parameters_json,
                files_json=files_json,
            )
        else:
            system_template = self.system_prompt
            user_prompt = FC_AGENT_USER_PROMPT.format(
                problem_description=problem_description,
            )
        system_prompt = (
            system_template
            .replace("{keywords}", ingredients_text)
            .replace("{skill}", skill.strip())
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _to_assistant_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "role": "assistant",
            "content": _content_to_text(message.get("content", "")),
        }
        tool_calls = message.get("tool_calls", [])
        normalized_calls = self._normalize_tool_calls(tool_calls)
        if normalized_calls:
            out["tool_calls"] = normalized_calls
        return out

    def _normalize_tool_calls(self, tool_calls: Any) -> List[Dict[str, Any]]:
        if not isinstance(tool_calls, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for idx, call in enumerate(tool_calls, start=1):
            if not isinstance(call, dict):
                continue
            function_block = call.get("function", {})
            if not isinstance(function_block, dict):
                continue
            name = str(function_block.get("name", "")).strip()
            if not name:
                continue
            raw_arguments = function_block.get("arguments", {})
            arguments_obj: Dict[str, Any]
            if isinstance(raw_arguments, dict):
                arguments_obj = raw_arguments
            elif isinstance(raw_arguments, str):
                raw_text = raw_arguments.strip()
                if not raw_text:
                    arguments_obj = {}
                else:
                    try:
                        parsed = json.loads(raw_text)
                        arguments_obj = parsed if isinstance(parsed, dict) else {"code": raw_text}
                    except json.JSONDecodeError:
                        # Keep malformed argument strings executable by mapping them to code.
                        arguments_obj = {"code": raw_text}
            else:
                arguments_obj = {}

            normalized.append(
                {
                    "id": str(call.get("id", "")).strip() or f"call_{idx}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(arguments_obj, ensure_ascii=False),
                    },
                }
            )
        return normalized

    def _print_message(self, turn_idx: int, message: Dict[str, Any]) -> None:
        role = str(message.get("role", "unknown"))
        try:
            payload = json.dumps(message, ensure_ascii=False)
        except TypeError:
            payload = str(message)
        line = f"[FunctionCallAgent][Turn {turn_idx}][{role}] {payload}"
        try:
            print(line)
        except UnicodeEncodeError:
            safe_line = line.encode("ascii", errors="backslashreplace").decode("ascii")
            print(safe_line)

    def _extract_formulation(self, text: str) -> Optional[Dict[str, Any]]:
        if not text or not text.strip():
            return None
        match = re.search(r"<formulation>\s*(.*?)\s*</formulation>", text, re.DOTALL | re.IGNORECASE)
        if not match:
            return None
        formulation_raw = match.group(1).strip()
        parsed = extract_json(formulation_raw, default={})
        if isinstance(parsed, dict) and parsed:
            return parsed
        return None

    def _approx_message_chars(self, message: Dict[str, Any]) -> int:
        if not isinstance(message, dict):
            return 0
        total = 0
        total += len(str(message.get("role", "")))
        total += len(_content_to_text(message.get("content", "")))
        tool_calls = message.get("tool_calls", [])
        if isinstance(tool_calls, list):
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                function_block = call.get("function", {})
                if isinstance(function_block, dict):
                    total += len(str(function_block.get("name", "")))
                    total += len(str(function_block.get("arguments", "")))
        return total

    def _approx_messages_chars(self, messages: List[Dict[str, Any]]) -> int:
        total = 0
        for message in messages:
            if isinstance(message, dict):
                total += self._approx_message_chars(message)
        return total

    def _parse_numeric_answer(self, text: str) -> Optional[float]:
        payload = str(text).strip()
        if not payload:
            return None
        try:
            value = float(payload)
        except ValueError:
            return None
        if not math.isfinite(value):
            return None
        return value

    def _extract_tmp_result(self, text: str) -> Optional[float]:
        if not text or not str(text).strip():
            return None
        matches = re.findall(r"<tmp>\s*(.*?)\s*</tmp>", str(text), flags=re.DOTALL | re.IGNORECASE)
        for payload in reversed(matches):
            value = self._parse_numeric_answer(payload)
            if value is not None:
                return value
        return None

    def run(
        self,
        problem_description: str,
        ingredients: Any,
        skill: str = "",
        timeout: int = 60,
        max_turns: Optional[int] = None,
        verbose: bool = False,
        sample_id: str = "",
        problem_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        turn_limit = max_turns if max_turns is not None else self.max_turns
        self._log("fc_run_start", message="function call run start", sample_id=sample_id, data={"turn_limit": turn_limit})
        tools_schema = build_openai_tools_schema(["run_code"])
        base_messages = self._build_initial_messages(
            problem_description=problem_description,
            ingredients=ingredients,
            skill=skill,
            problem_context=problem_context,
        )
        archive_messages: List[Dict[str, Any]] = list(base_messages)
        prev_assistant_msg: Optional[Dict[str, Any]] = None
        prev_tool_msg: Optional[Dict[str, Any]] = None
        prev_user_feedback_msg: Optional[Dict[str, Any]] = None
        self._log(
            "fc_context_init",
            sample_id=sample_id,
            data={
                "message_count": len(base_messages),
                "context_chars": self._approx_messages_chars(base_messages),
                "problem_chars": len(str(problem_description or "")),
                "skill_chars": len(str(skill or "")),
                "tools_count": len(tools_schema),
            },
        )

        latest_formulation: Dict[str, Any] = {}
        latest_result: Any = None
        final_payload: Dict[str, Any] = {}
        final_raw = ""
        attempts: List[Dict[str, Any]] = []
        loop_trace: List[Dict[str, Any]] = []

        for turn_idx in range(1, turn_limit + 1):
            request_messages: List[Dict[str, Any]] = list(base_messages)
            if isinstance(prev_user_feedback_msg, dict):
                request_messages.append(prev_user_feedback_msg)
            if isinstance(prev_assistant_msg, dict):
                request_messages.append(prev_assistant_msg)
            if isinstance(prev_tool_msg, dict):
                request_messages.append(prev_tool_msg)
            self._log("fc_turn_start", sample_id=sample_id, data={"turn": turn_idx})
            llm_t0 = time.perf_counter()
            self._log(
                "fc_llm_request_start",
                sample_id=sample_id,
                data={
                    "turn": turn_idx,
                    "request_message_count": len(request_messages),
                    "request_context_chars": self._approx_messages_chars(request_messages),
                    "archive_message_count": len(archive_messages),
                    "tools_count": len(tools_schema),
                },
            )
            try:
                assistant = self.llm.chat_messages(
                    messages=request_messages,
                    tools=tools_schema,
                    tool_choice="auto",
                    extra={
                        "chat_template_kwargs": {
                            "thinking": False
                        }
                    },
                )
            except Exception as err:
                elapsed_ms = round((time.perf_counter() - llm_t0) * 1000.0, 2)
                self._log(
                    "fc_llm_request_error",
                    message="llm chat_messages failed",
                    sample_id=sample_id,
                    data={
                        "turn": turn_idx,
                        "latency_ms": elapsed_ms,
                        "error": str(err),
                    },
                    level="ERROR",
                )
                raise
            elapsed_ms = round((time.perf_counter() - llm_t0) * 1000.0, 2)
            assistant_tool_calls = assistant.get("tool_calls", []) if isinstance(assistant, dict) else []
            if not isinstance(assistant_tool_calls, list):
                assistant_tool_calls = []
            self._log(
                "fc_llm_request_done",
                sample_id=sample_id,
                data={
                    "turn": turn_idx,
                    "latency_ms": elapsed_ms,
                    "assistant_content_chars": len(
                        _content_to_text(assistant.get("content", "")) if isinstance(assistant, dict) else ""
                    ),
                    "assistant_tool_calls": len(assistant_tool_calls),
                    "request_message_count": len(request_messages),
                    "archive_message_count": len(archive_messages),
                },
            )
            assistant_msg = self._to_assistant_message(assistant)
            archive_messages.append(assistant_msg)
            if verbose:
                self._print_message(turn_idx=turn_idx, message=assistant_msg)
            action, data = parse_function_call_response(assistant)
            self._log(
                "fc_turn_decision",
                sample_id=sample_id,
                data={"turn": turn_idx, "action": action},
            )

            if action == "function_call" and isinstance(data, dict):
                tool_name = str(data.get("tool_name", "")).strip()
                parameters = data.get("parameters", {})
                if not isinstance(parameters, dict):
                    parameters = {}
                tool_call_id = str(data.get("tool_call_id", "")).strip()
                code_chars = len(str(parameters.get("code", "")))
                self._log(
                    "fc_tool_call_start",
                    message=f"tool={tool_name}",
                    sample_id=sample_id,
                    data={
                        "turn": turn_idx,
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "code_chars": code_chars,
                    },
                )
                tool_t0 = time.perf_counter()
                execution = self.tool_handler.execute_tool_call(
                    tool_name=tool_name,
                    parameters=parameters,
                    tool_call_id=tool_call_id,
                    config={"timeout": timeout},
                    sample_id=sample_id,
                )
                tool_elapsed_ms = round((time.perf_counter() - tool_t0) * 1000.0, 2)
                tool_feedback = execution["feedback_message"]
                archive_messages.append(tool_feedback)
                if verbose:
                    self._print_message(turn_idx=turn_idx, message=tool_feedback)
                run_result = execution.get("tool_result", {})
                execution_meta = execution.get("execution_meta", {})
                if not isinstance(execution_meta, dict):
                    execution_meta = {}
                code = str(parameters.get("code", "")).strip()
                attempt = {
                    "attempt": len(attempts) + 1,
                    "tool_call_id": tool_call_id or f"call_{len(attempts) + 1}",
                    "assistant_content": assistant_msg.get("content", ""),
                    "code": code,
                    "run_result": run_result if isinstance(run_result, dict) else {},
                }
                attempts.append(attempt)
                if isinstance(run_result, dict) and run_result.get("returncode") == 0:
                    parsed_result = run_result.get("result")
                    if parsed_result is not None:
                        latest_result = parsed_result
                self._log(
                    "fc_tool_call",
                    message=f"tool={tool_name}",
                    sample_id=sample_id,
                    data={
                        "turn": turn_idx,
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "latency_ms": tool_elapsed_ms,
                        "returncode": run_result.get("returncode") if isinstance(run_result, dict) else None,
                        "result": run_result.get("result") if isinstance(run_result, dict) else None,
                        "tool_duration_s": run_result.get("duration_s") if isinstance(run_result, dict) else None,
                        "timeout": run_result.get("timeout") if isinstance(run_result, dict) else None,
                        "handler_exec_latency_ms": execution_meta.get("exec_latency_ms"),
                        "handler_summary_latency_ms": execution_meta.get("summary_latency_ms"),
                        "handler_total_latency_ms": execution_meta.get("total_latency_ms"),
                        "summary_applied": execution_meta.get("summary_applied"),
                        "stdout_summary_applied": run_result.get("stdout_summary_applied") if isinstance(run_result, dict) else None,
                        "stderr_summary_applied": run_result.get("stderr_summary_applied") if isinstance(run_result, dict) else None,
                    },
                )
                prev_assistant_msg = assistant_msg
                prev_tool_msg = tool_feedback
                prev_user_feedback_msg = None
                loop_trace.append(
                    {
                        "turn": turn_idx,
                        "phase": "agent_loop",
                        "assistant_content": assistant_msg.get("content", ""),
                        "tool_called": True,
                        "tool_name": tool_name,
                        "tool_result": run_result,
                    }
                )
                continue

            if action in {"text", "answer"}:
                text = data if isinstance(data, str) else assistant_msg.get("content", "")
                tmp_result = self._extract_tmp_result(text)
                if tmp_result is not None:
                    latest_result = tmp_result
                    self._log(
                        "fc_tmp_result",
                        message="temporary numeric result recorded",
                        sample_id=sample_id,
                        data={"turn": turn_idx, "tmp_result": tmp_result},
                    )
                if action == "answer":
                    numeric_answer = self._parse_numeric_answer(text)
                    if numeric_answer is not None:
                        final_raw = f"<answer>{text.strip()}</answer>"
                        final_payload = {
                            "formulation": latest_formulation if isinstance(latest_formulation, dict) else {},
                            "final_result": numeric_answer,
                        }
                        latest_result = numeric_answer
                        self._log(
                            "fc_answer",
                            message="numeric answer accepted",
                            sample_id=sample_id,
                            data={"turn": turn_idx, "answer": numeric_answer},
                        )
                        loop_trace.append(
                            {
                                "turn": turn_idx,
                                "phase": "agent_loop",
                                "assistant_content": assistant_msg.get("content", ""),
                                "tool_called": False,
                                "parsed": final_payload,
                            }
                        )
                        break
                    feedback = {
                        "role": "user",
                        "content": "Invalid <answer> format. Provide numeric-only output, e.g., <answer>123.45</answer>.",
                    }
                    archive_messages.append(feedback)
                    if verbose:
                        self._print_message(turn_idx=turn_idx, message=feedback)
                    prev_assistant_msg = assistant_msg
                    prev_tool_msg = None
                    prev_user_feedback_msg = feedback
                    loop_trace.append(
                        {
                            "turn": turn_idx,
                            "phase": "agent_loop",
                            "assistant_content": assistant_msg.get("content", ""),
                            "tool_called": False,
                            "parsed": {},
                            "feedback": feedback["content"],
                        }
                    )
                    continue

                formulation = self._extract_formulation(text)
                if formulation is not None:
                    latest_formulation = formulation
                    self._log("fc_formulation", message="formulation parsed", sample_id=sample_id, data={"turn": turn_idx})
                    prev_assistant_msg = assistant_msg
                    prev_tool_msg = None
                    prev_user_feedback_msg = None
                    loop_trace.append(
                        {
                            "turn": turn_idx,
                            "phase": "agent_loop",
                            "assistant_content": assistant_msg.get("content", ""),
                            "tool_called": False,
                            "parsed": {"formulation": formulation},
                        }
                    )
                    continue

            loop_trace.append(
                {
                    "turn": turn_idx,
                    "phase": "agent_loop",
                    "assistant_content": assistant_msg.get("content", ""),
                    "tool_called": False,
                    "parsed": {},
                }
            )
            prev_assistant_msg = assistant_msg
            prev_tool_msg = None
            prev_user_feedback_msg = None

        candidates: List[Dict[str, Any]] = []
        for item in attempts:
            rr = item.get("run_result", {})
            candidates.append(
                {
                    "candidate_id": f"candidate_{item.get('attempt', len(candidates) + 1)}",
                    "solver_id": "function_call_agent",
                    "family": "function_call_agent",
                    "prompt": "",
                    "raw": item.get("assistant_content", ""),
                    "code": item.get("code", ""),
                    "run_result": rr if isinstance(rr, dict) else {},
                }
            )

        if not final_payload:
            final_payload = {
                "formulation": latest_formulation if isinstance(latest_formulation, dict) else {},
                "final_result": latest_result,
            }

        if not final_raw and final_payload:
            final_raw = json.dumps(final_payload, ensure_ascii=False)

        self._log(
            "fc_run_done",
            message="function call run done",
            sample_id=sample_id,
            data={"attempts": len(attempts), "final_result": final_payload.get("final_result")},
        )

        return {
            "messages": archive_messages,
            "attempts": attempts,
            "candidates": candidates,
            "final_raw": final_raw,
            "final_payload": final_payload,
            "phase_trace": loop_trace,
            "loop_trace": loop_trace,
        }
