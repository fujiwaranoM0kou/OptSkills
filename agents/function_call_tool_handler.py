from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, Optional

from llm.llm_caller import LLMCaller
from tools import get_tool
from utils.runtime_logger import RuntimeLogger


class FunctionCallToolHandler:
    def __init__(
        self,
        llm: Optional[LLMCaller] = None,
        logger: Optional[RuntimeLogger] = None,
    ) -> None:
        self.llm = llm
        self.logger = logger
        self.summary_enabled = self._env_bool("OPTSKILL_TOOL_SUMMARY_ENABLED", True)
        self.summary_threshold_tokens = self._env_int("OPTSKILL_TOOL_SUMMARY_THRESHOLD_TOKENS", 1200)
        self.summary_max_tokens = self._env_int("OPTSKILL_TOOL_SUMMARY_MAX_TOKENS", 512)
        self.summary_input_max_chars = self._env_int("OPTSKILL_TOOL_SUMMARY_INPUT_MAX_CHARS", 24000)
        self.output_hard_cap_chars = self._env_int("OPTSKILL_TOOL_OUTPUT_HARD_CAP_CHARS", 12000)
        self.artifact_dir = self._resolve_artifact_dir()
        self.run_code_cwd = ""

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
            component="tool_handler",
            event=event,
            message=message,
            sample_id=sample_id,
            data=data or {},
            level=level,
        )

    def _env_bool(self, key: str, default: bool) -> bool:
        value = os.getenv(key, "").strip().lower()
        if not value:
            return default
        return value not in {"0", "false", "no", "off"}

    def _env_int(self, key: str, default: int) -> int:
        value = os.getenv(key, "").strip()
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    def _resolve_artifact_dir(self) -> str:
        configured = os.getenv("OPTSKILL_TOOL_ARTIFACT_DIR", "").strip()
        if configured:
            if os.path.isabs(configured):
                return configured
            return os.path.abspath(configured)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, "outputs", "standalone", "runtime_logs", "tool_outputs")

    def _resolve_run_code_cwd(self, sample_id: str = "") -> str:
        configured = os.getenv("OPTSKILL_RUN_CODE_CWD", "").strip()
        if configured:
            cwd = configured if os.path.isabs(configured) else os.path.abspath(configured)
            os.makedirs(cwd, exist_ok=True)
            return cwd

        if self.run_code_cwd:
            return self.run_code_cwd

        base = os.getenv("OPTSKILL_RUN_CODE_CWD_BASE", "").strip()
        if not base:
            base = os.path.join(self.artifact_dir, "workspaces")
        if not os.path.isabs(base):
            base = os.path.abspath(base)

        label = sample_id.strip() or "sample"
        safe_label = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in label)[:80]
        self.run_code_cwd = os.path.join(base, f"{safe_label}_{uuid.uuid4().hex[:8]}")
        os.makedirs(self.run_code_cwd, exist_ok=True)
        return self.run_code_cwd

    def _estimate_tokens(self, text: Any) -> int:
        return max(0, len(str(text or "")) // 4)

    def _get_summary_llm(self) -> Optional[LLMCaller]:
        if self.llm is None:
            try:
                self.llm = LLMCaller()
            except Exception:
                return None
        return self.llm

    def _summarize_stream(
        self,
        stream_name: str,
        stream_text: str,
        returncode: Any,
        timeout: Any,
        duration_s: Any,
        result_value: Any,
    ) -> str:
        llm = self._get_summary_llm()
        if llm is None:
            raise RuntimeError("LLM summary caller is unavailable")

        system_prompt = (
            "You summarize optimization code execution logs.\n"
            "Keep critical debugging signals and solver outcomes.\n"
            "Output plain text only."
        )
        user_prompt = (
            f"Summarize the {stream_name} log from a run_code tool execution.\n"
            "Requirements:\n"
            "- Preserve error type and the final traceback clue if present.\n"
            "- Preserve solver status / termination condition if present.\n"
            "- Preserve RESULT / RESULT_JSON related values if present.\n"
            "- Keep key warnings.\n"
            "- Keep concise and structured with short labeled lines.\n\n"
            f"run metadata: returncode={returncode}, timeout={timeout}, duration_s={duration_s}, result={result_value}\n\n"
            f"{stream_name} log:\n"
            f"{stream_text}"
        )
        summary = llm.chat(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.0,
            max_tokens=self.summary_max_tokens,
        ).strip()
        return summary if summary else stream_text

    def _save_raw_output_artifact(
        self,
        tool_name: str,
        result: Dict[str, Any],
        stdout_tokens: int,
        stderr_tokens: int,
        threshold_tokens: int,
    ) -> str:
        os.makedirs(self.artifact_dir, exist_ok=True)
        file_name = f"{tool_name}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}.json"
        path = os.path.join(self.artifact_dir, file_name)
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "tool_name": tool_name,
            "summary_threshold_tokens": threshold_tokens,
            "stdout_tokens": stdout_tokens,
            "stderr_tokens": stderr_tokens,
            "returncode": result.get("returncode"),
            "timeout": result.get("timeout"),
            "duration_s": result.get("duration_s"),
            "result": result.get("result"),
            "stdout_raw": str(result.get("stdout", "")),
            "stderr_raw": str(result.get("stderr", "")),
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return path

    def _important_log_lines(self, text: str, max_lines: int = 40) -> str:
        patterns = (
            "RESULT:",
            "RESULT_JSON:",
            "objective",
            "status",
            "termination",
            "optimal",
            "feasible",
            "infeasible",
            "timeout",
            "error",
            "traceback",
            "exception",
        )
        picked = []
        for line in str(text or "").splitlines():
            lowered = line.lower()
            if any(pattern.lower() in lowered for pattern in patterns):
                picked.append(line)
                if len(picked) >= max_lines:
                    break
        return "\n".join(picked)

    def _compact_stream_for_context(self, stream_name: str, stream_text: str, max_chars: int) -> str:
        text = str(stream_text or "")
        max_chars = max(1000, int(max_chars))
        if len(text) <= max_chars:
            return text

        important = self._important_log_lines(text)
        marker = (
            f"[{stream_name} truncated for LLM context: original_chars={len(text)}. "
            "Raw output was saved to raw_output_path when available.]\n"
        )
        budget = max_chars - len(marker) - len(important) - 200
        budget = max(800, budget)
        head_len = max(400, budget // 2)
        tail_len = max(400, budget - head_len)
        chunks = [marker]
        if important:
            chunks.append("[important lines]\n")
            chunks.append(important[: max(0, max_chars // 3)])
            chunks.append("\n[/important lines]\n")
        chunks.append("[head]\n")
        chunks.append(text[:head_len])
        chunks.append("\n[... omitted ...]\n[tail]\n")
        chunks.append(text[-tail_len:])
        return "".join(chunks)

    def _compact_stream_for_summary(self, stream_name: str, stream_text: str) -> str:
        return self._compact_stream_for_context(
            stream_name=stream_name,
            stream_text=stream_text,
            max_chars=self.summary_input_max_chars,
        )

    def _cap_stream_fields_for_context(self, out: Dict[str, Any]) -> Dict[str, Any]:
        hard_cap = max(1000, int(self.output_hard_cap_chars))
        for key in ("stdout", "stderr"):
            value = str(out.get(key, ""))
            if len(value) <= hard_cap:
                continue
            out[key] = self._compact_stream_for_context(
                stream_name=key,
                stream_text=value,
                max_chars=hard_cap,
            )
            out[f"{key}_summary_applied"] = True
            out[f"{key}_summary_method"] = "deterministic_truncation"
        return out

    def _apply_run_code_output_summary(
        self,
        tool_name: str,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        if tool_name != "run_code" or not isinstance(result, dict):
            return result

        stdout = str(result.get("stdout", ""))
        stderr = str(result.get("stderr", ""))
        stdout_tokens = self._estimate_tokens(stdout)
        stderr_tokens = self._estimate_tokens(stderr)
        threshold = max(1, int(self.summary_threshold_tokens))

        out = dict(result)
        out["stdout_tokens"] = stdout_tokens
        out["stderr_tokens"] = stderr_tokens
        out["stdout_summary_applied"] = False
        out["stderr_summary_applied"] = False
        out["raw_output_path"] = ""
        out["output_summary_model"] = ""

        if not self.summary_enabled:
            return self._cap_stream_fields_for_context(out)

        need_stdout = stdout_tokens > threshold
        need_stderr = stderr_tokens > threshold
        if not (need_stdout or need_stderr):
            return self._cap_stream_fields_for_context(out)

        summary_error: Dict[str, str] = {}
        try:
            raw_output_path = self._save_raw_output_artifact(
                tool_name=tool_name,
                result=result,
                stdout_tokens=stdout_tokens,
                stderr_tokens=stderr_tokens,
                threshold_tokens=threshold,
            )
            out["raw_output_path"] = raw_output_path
        except Exception as err:
            out["raw_output_path"] = ""
            summary_error["artifact"] = str(err)

        llm = self._get_summary_llm()
        if llm is not None:
            try:
                out["output_summary_model"] = str(getattr(llm, "config", None).model)
            except Exception:
                out["output_summary_model"] = ""

        if need_stdout:
            try:
                stdout_for_summary = self._compact_stream_for_summary("stdout", stdout)
                out["stdout"] = self._summarize_stream(
                    stream_name="stdout",
                    stream_text=stdout_for_summary,
                    returncode=result.get("returncode"),
                    timeout=result.get("timeout"),
                    duration_s=result.get("duration_s"),
                    result_value=result.get("result"),
                )
                out["stdout_summary_applied"] = True
                out["stdout_summary_method"] = "llm"
            except Exception as err:
                summary_error["stdout"] = str(err)
                out["stdout"] = self._compact_stream_for_context(
                    stream_name="stdout",
                    stream_text=stdout,
                    max_chars=self.output_hard_cap_chars,
                )
                out["stdout_summary_applied"] = True
                out["stdout_summary_method"] = "deterministic_truncation_after_summary_error"

        if need_stderr:
            try:
                stderr_for_summary = self._compact_stream_for_summary("stderr", stderr)
                out["stderr"] = self._summarize_stream(
                    stream_name="stderr",
                    stream_text=stderr_for_summary,
                    returncode=result.get("returncode"),
                    timeout=result.get("timeout"),
                    duration_s=result.get("duration_s"),
                    result_value=result.get("result"),
                )
                out["stderr_summary_applied"] = True
                out["stderr_summary_method"] = "llm"
            except Exception as err:
                summary_error["stderr"] = str(err)
                out["stderr"] = self._compact_stream_for_context(
                    stream_name="stderr",
                    stream_text=stderr,
                    max_chars=self.output_hard_cap_chars,
                )
                out["stderr_summary_applied"] = True
                out["stderr_summary_method"] = "deterministic_truncation_after_summary_error"

        if summary_error:
            out["summary_error"] = summary_error
        return self._cap_stream_fields_for_context(out)

    def get_or_create_tool(self, tool_name: str, config: Dict[str, Any] | None = None) -> Any:
        # Create a fresh tool instance per call so runtime config is always applied.
        tool_cls = get_tool(tool_name)
        return tool_cls(config=config or {})

    def execute_tool_call(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        tool_call_id: str = "",
        config: Dict[str, Any] | None = None,
        sample_id: str = "",
    ) -> Dict[str, Any]:
        total_t0 = time.perf_counter()
        try:
            self._log(
                event="tool_call_start",
                message=f"tool={tool_name}",
                sample_id=sample_id,
                data={
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id or "call_0",
                },
            )
            tool_config = dict(config or {})
            if (
                tool_name == "run_code"
                and "cwd" not in tool_config
                and self._env_bool("OPTSKILL_RUN_CODE_ISOLATE_CWD", True)
            ):
                tool_config["cwd"] = self._resolve_run_code_cwd(sample_id=sample_id)
            tool = self.get_or_create_tool(tool_name=tool_name, config=tool_config)
            exec_t0 = time.perf_counter()
            result = tool.call(parameters)
            exec_latency_ms = round((time.perf_counter() - exec_t0) * 1000.0, 2)
            self._log(
                event="tool_exec_done",
                message=f"tool={tool_name}",
                sample_id=sample_id,
                data={
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id or "call_0",
                    "exec_latency_ms": exec_latency_ms,
                },
            )
            if not isinstance(result, dict):
                result = {"result": result}
            summary_t0 = time.perf_counter()
            result = self._apply_run_code_output_summary(tool_name=tool_name, result=result)
            summary_latency_ms = round((time.perf_counter() - summary_t0) * 1000.0, 2)
            total_latency_ms = round((time.perf_counter() - total_t0) * 1000.0, 2)
            summary_applied = bool(result.get("stdout_summary_applied")) or bool(result.get("stderr_summary_applied"))
            self._log(
                event="tool_call_done",
                message=f"tool={tool_name}",
                sample_id=sample_id,
                data={
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id or "call_0",
                    "exec_latency_ms": exec_latency_ms,
                    "summary_latency_ms": summary_latency_ms,
                    "total_latency_ms": total_latency_ms,
                    "summary_applied": summary_applied,
                    "returncode": result.get("returncode"),
                    "timeout": result.get("timeout"),
                },
            )
            return {
                "error": False,
                "tool_result": result,
                "execution_meta": {
                    "exec_latency_ms": exec_latency_ms,
                    "summary_latency_ms": summary_latency_ms,
                    "total_latency_ms": total_latency_ms,
                    "summary_applied": summary_applied,
                },
                "feedback_message": {
                    "role": "tool",
                    "tool_call_id": tool_call_id or "call_0",
                    "content": json.dumps(result, ensure_ascii=False),
                },
            }
        except Exception as err:
            error_payload = {
                "error": str(err),
                "returncode": -1,
                "stdout": "",
                "stderr": str(err),
                "result": None,
            }
            total_latency_ms = round((time.perf_counter() - total_t0) * 1000.0, 2)
            self._log(
                event="tool_call_error",
                message=f"tool={tool_name}",
                sample_id=sample_id,
                data={
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id or "call_0",
                    "total_latency_ms": total_latency_ms,
                    "error": str(err),
                },
                level="ERROR",
            )
            return {
                "error": True,
                "tool_result": error_payload,
                "execution_meta": {
                    "exec_latency_ms": None,
                    "summary_latency_ms": None,
                    "total_latency_ms": total_latency_ms,
                    "summary_applied": False,
                },
                "feedback_message": {
                    "role": "tool",
                    "tool_call_id": tool_call_id or "call_0",
                    "content": json.dumps(error_payload, ensure_ascii=False),
                },
            }
