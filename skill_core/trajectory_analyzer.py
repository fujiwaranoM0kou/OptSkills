from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from llm.llm_caller import LLMCaller
from prompts.skill_prompts import SKILL_ANALYSIS_PROMPT
from utils.extract_json import extract_json


class TrajectoryAnalyzer:
    def __init__(self, llm: LLMCaller, workers: int = 1) -> None:
        self.llm = llm
        self.workers = max(1, int(workers))

    @staticmethod
    def _to_numeric(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _round_2dp_half_up(value: Any) -> Optional[str]:
        try:
            quantized = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError, TypeError):
            return None
        return format(quantized, "f")

    def attach_objective_metrics(self, candidates: List[Dict[str, Any]], ground_truth: str) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []
        ground_truth_text = str(ground_truth).strip()
        gt_numeric = self._to_numeric(ground_truth_text) if ground_truth_text else None
        for item in candidates:
            if not isinstance(item, dict):
                continue
            candidate = dict(item)
            run_result = candidate.get("run_result", {})
            if not isinstance(run_result, dict):
                run_result = {}
            result_value = run_result.get("result")
            success = run_result.get("returncode") == 0 and result_value is not None
            runtime_s = self._to_numeric(candidate.get("runtime_s"))
            if runtime_s is None:
                runtime_s = self._to_numeric(run_result.get("duration_s"))
            if runtime_s is None:
                runtime_s = 0.0
            raw_calls = candidate.get("num_tool_calls")
            num_tool_calls = int(raw_calls) if isinstance(raw_calls, int) else 1
            if num_tool_calls < 0:
                num_tool_calls = 0
            pred_numeric = self._to_numeric(result_value) if ground_truth_text else None
            abs_gap = round(abs(pred_numeric - gt_numeric), 10) if pred_numeric is not None and gt_numeric is not None else None
            candidate["objective_metrics"] = {
                "runtime_s": round(runtime_s, 3),
                "success": bool(success),
                "num_tool_calls": num_tool_calls,
                "abs_gap": abs_gap,
                "prediction_2dp": self._round_2dp_half_up(pred_numeric) if pred_numeric is not None else None,
                "ground_truth_2dp": self._round_2dp_half_up(gt_numeric) if gt_numeric is not None else None,
            }
            enriched.append(candidate)
        return enriched

    def _objective_label(self, candidate: Dict[str, Any]) -> Optional[str]:
        metrics = candidate.get("objective_metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        if not bool(metrics.get("success")):
            return "negative"
        pred_2dp = str(metrics.get("prediction_2dp", "") or "").strip()
        gt_2dp = str(metrics.get("ground_truth_2dp", "") or "").strip()
        if pred_2dp and gt_2dp:
            return "positive" if pred_2dp == gt_2dp else "negative"
        abs_gap = self._to_numeric(metrics.get("abs_gap"))
        if abs_gap is None:
            return None
        return "positive" if abs_gap <= 0.005 else "negative"

    def default_label(self, candidate: Dict[str, Any]) -> str:
        label = self._objective_label(candidate)
        if label in {"positive", "negative"}:
            return label
        metrics = candidate.get("objective_metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        return "positive" if bool(metrics.get("success")) else "negative"

    @staticmethod
    def _to_str_list(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _to_bullets(self, lines: List[str]) -> List[str]:
        out: List[str] = []
        for line in lines:
            text = str(line).strip()
            if not text:
                continue
            out.append(text if text.startswith(("-", "*", "1.", "2.", "3.")) else f"- {text}")
        return out

    def _compose_stage_markdown(self, modeling_lines: List[str], solving_lines: List[str]) -> str:
        modeling = self._to_bullets(modeling_lines) or ["- Keep variable definitions, domains, and key constraints explicit."]
        solving = self._to_bullets(solving_lines) or ["- Check solver status before reading values and emit parseable RESULT output."]
        return "### Modeling\n" + "\n".join(modeling) + "\n\n### Solving\n" + "\n".join(solving)

    def _coerce_markdown(self, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            return "\n".join(self._to_bullets([str(item) for item in value if str(item).strip()])).strip()
        return ""

    def _legacy_positive_sop_to_markdown(self, parsed: Dict[str, Any]) -> str:
        legacy = parsed.get("positive_sop", {})
        if not isinstance(legacy, dict):
            return ""
        modeling_lines: List[str] = []
        solving_lines: List[str] = []
        modeling_lines.extend([f"Modeling step: {x}" for x in self._to_str_list(legacy.get("modeling_steps", []))])
        modeling_lines.extend([f"Intermediate expression/format: {x}" for x in self._to_str_list(legacy.get("intermediate_expressions_and_formats", []))])
        modeling_lines.extend([f"Modeling pitfall: {x}" for x in self._to_str_list(legacy.get("modeling_common_pitfalls", []))])
        solving_lines.extend([f"Solving step: {x}" for x in self._to_str_list(legacy.get("solving_steps", []))])
        solving_lines.extend([f"Code usage/flow: {x}" for x in self._to_str_list(legacy.get("solver_code_usage_and_flow", []))])
        solving_lines.extend([f"Solving pitfall: {x}" for x in self._to_str_list(legacy.get("solving_common_pitfalls", []))])
        return self._compose_stage_markdown(modeling_lines, solving_lines) if modeling_lines or solving_lines else ""

    def _legacy_should_avoid_to_markdown(self, parsed: Dict[str, Any]) -> str:
        legacy = parsed.get("should_avoid", {})
        if not isinstance(legacy, dict):
            return ""
        modeling_lines = [f"Avoid: {x}" for x in self._to_str_list(legacy.get("modeling", []))]
        solving_lines = [f"Avoid: {x}" for x in self._to_str_list(legacy.get("solving", []))]
        return self._compose_stage_markdown(modeling_lines, solving_lines) if modeling_lines or solving_lines else ""

    def _normalize_stage_markdown(self, markdown: str, default_modeling: List[str], default_solving: List[str]) -> str:
        text = str(markdown).strip()
        if not text:
            return self._compose_stage_markdown(default_modeling, default_solving)
        lowered = text.lower()
        if "### modeling" in lowered and "### solving" in lowered:
            return text
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return self._compose_stage_markdown(lines or default_modeling, default_solving)

    @staticmethod
    def _strip_system_messages(messages: Any) -> List[Dict[str, Any]]:
        if not isinstance(messages, list):
            return []
        return [item for item in messages if isinstance(item, dict) and str(item.get("role", "")).strip().lower() != "system"]

    def _sanitize_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = copy.deepcopy(candidate) if isinstance(candidate, dict) else {}
        function_agent = sanitized.get("function_agent", {})
        if isinstance(function_agent, dict):
            function_agent["messages"] = self._strip_system_messages(function_agent.get("messages", []))
            sanitized["function_agent"] = function_agent
        if "history" in sanitized:
            sanitized["history"] = self._strip_system_messages(sanitized.get("history", []))
        if "messages" in sanitized:
            sanitized["messages"] = self._strip_system_messages(sanitized.get("messages", []))
        return sanitized

    def analyze_candidate(self, ingredients: Dict[str, List[str]], candidate: Dict[str, Any]) -> Dict[str, Any]:
        metrics = candidate.get("objective_metrics", {})
        if not isinstance(metrics, dict):
            metrics = {}
        label = self._objective_label(candidate) or self.default_label(candidate)
        indicators = {
            "label": label,
            "success": bool(metrics.get("success")),
            "runtime_s": metrics.get("runtime_s"),
            "num_tool_calls": metrics.get("num_tool_calls"),
        }
        prompt = (
            SKILL_ANALYSIS_PROMPT.replace("{keywords}", json.dumps(ingredients, ensure_ascii=False, indent=2))
            .replace("{Indicators}", json.dumps(indicators, ensure_ascii=False, indent=2))
            .replace("{trajectory}", json.dumps(self._sanitize_candidate(candidate), ensure_ascii=False, indent=2))
        )
        parsed = extract_json(self.llm.chat(prompt), default={})
        parsed = parsed if isinstance(parsed, dict) else {}
        positive_sop = self._coerce_markdown(parsed.get("positive_sop", "")) or self._coerce_markdown(parsed.get("positive_sop_md", "")) or self._legacy_positive_sop_to_markdown(parsed)
        should_avoid = self._coerce_markdown(parsed.get("should_avoid", "")) or self._coerce_markdown(parsed.get("should_avoid_md", "")) or self._legacy_should_avoid_to_markdown(parsed)
        if label == "positive":
            positive_sop = self._normalize_stage_markdown(
                positive_sop,
                [
                    "Use explicit sets/parameters/decision variables and keep assumptions machine-checkable.",
                    "Preserve valid expression forms for the chosen solver workflow.",
                ],
                [
                    "Build code directly from formulation fields and keep solver configuration aligned with the selected backend.",
                    "Check status/termination before reading solution values and emit parseable RESULT output.",
                ],
            )
            should_avoid = ""
        else:
            should_avoid = self._normalize_stage_markdown(
                should_avoid,
                [
                    "Do not omit critical constraints or silently change variable domains.",
                    "Do not introduce unsupported nonlinear terms for the selected workflow.",
                ],
                [
                    "Do not trust non-zero return codes or infeasible/unknown statuses.",
                    "Do not output pseudo numeric answers when execution fails.",
                ],
            )
            positive_sop = ""
        return {
            "candidate_id": str(candidate.get("candidate_id", "")).strip(),
            "label": label,
            "positive_sop": positive_sop,
            "should_avoid": should_avoid,
        }

    def analyze_candidates(self, ingredients: Dict[str, List[str]], candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        indexed: List[Tuple[int, Dict[str, Any]]] = [(idx, item) for idx, item in enumerate(candidates) if isinstance(item, dict)]
        if not indexed:
            return []
        max_workers = min(len(indexed), self.workers)
        if max_workers <= 1:
            return [self.analyze_candidate(ingredients, item) for _, item in indexed]
        output: Dict[int, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(self.analyze_candidate, ingredients, item): idx for idx, item in indexed}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    output[idx] = future.result()
                except Exception as exc:
                    raise RuntimeError(f"skill_analysis failed for candidate index {idx}: {exc}") from exc
        return [output[idx] for idx, _ in indexed]
