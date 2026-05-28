from __future__ import annotations

import copy
import json
import math
import time
from typing import Any, Dict, List, Optional

from agents.function_call_agent import FunctionCallAgent
from agents.solver_pools_rollout import SolverPoolsRolloutAgent
from llm.embedding_caller import EmbeddingCaller
from llm.llm_caller import LLMCaller
from prompts.extractor_prompts import EXTRACTOR_PROMPT, EXTRACTOR_PROMPT_EVAL
from skill_core.cluster_builder import ClusterBuilder
from skill_core.ingredients import clean_ingredient_slots, load_ingredient_reference, update_ingredient_reference
from skill_core.query_builder import build_ingredients_only_query
from skill_core.skill_builder import SkillBuilder
from skill_core.skill_manager import SkillManager
from skill_core.skill_selector import SkillSelector
from skill_core.trajectory_analyzer import TrajectoryAnalyzer
from utils.extract_json import extract_json
from utils.runtime_logger import RuntimeLogger

ROLLOUT_MODEL_SKILL = """# Modeling Skill
Build a base optimization formulation JSON with exactly five fields:
```json
{
  "sets": [],
  "parameters": [],
  "decision_variables": [],
  "objective": {},
  "constraints": []
}
```

Rules:
- Keep symbols explicit and index-safe.
- Keep assumptions explicit.
- Avoid hidden constants.
- Prefer linear structure unless keywords clearly indicate nonlinear/combinatorial structure.
"""


class AgentLoop:
    def __init__(
        self,
        *,
        skill_library_dir: str,
        archetype_fusion_alpha: float = 0.55,
        agent_max_turns: int = 12,
        analysis_workers: int = 1,
        builder_workers: int = 1,
        logger: Optional[RuntimeLogger] = None,
        llm: Optional[LLMCaller] = None,
    ) -> None:
        self.llm = llm or LLMCaller()
        self.logger = logger
        self.agent_max_turns = max(1, int(agent_max_turns))
        self.archetype_fusion_alpha = float(archetype_fusion_alpha)
        if not (0.0 <= self.archetype_fusion_alpha <= 1.0):
            raise ValueError("archetype_fusion_alpha must be in [0, 1].")
        self.embedding_caller: Optional[EmbeddingCaller] = None
        self.manager = SkillManager(skill_library_dir)
        self.builder = SkillBuilder(llm=self.llm, manager=self.manager)
        self.analyzer = TrajectoryAnalyzer(self.llm, analysis_workers)
        self.selector = SkillSelector(self.llm, self.manager)
        self.cluster_builder = ClusterBuilder(self.builder, self.analyzer, builder_workers)
        self.solver_pool_rollout = SolverPoolsRolloutAgent(llm=self.llm, logger=logger)

    def _log(self, event: str, message: str = "", sample_id: str = "", data: Optional[Dict[str, Any]] = None) -> None:
        if self.logger is not None:
            self.logger.log(component="agent_loop", event=event, message=message, sample_id=sample_id, data=data or {})

    def extract(self, problem_description: str, use_eval_prompt: bool = False) -> Dict[str, Any]:
        if use_eval_prompt:
            prompt = EXTRACTOR_PROMPT_EVAL.format(
                problem_description=problem_description,
                keywords_list=json.dumps(load_ingredient_reference(self.manager.library_dir), ensure_ascii=False, indent=2),
            )
        else:
            prompt = EXTRACTOR_PROMPT.format(problem_description=problem_description)
        raw = self.llm.chat(user_prompt=prompt, system_prompt="You are a precise OR keyword extractor.")
        data = extract_json(raw, default={})
        return {"raw": raw, "data": data if isinstance(data, dict) else {}}

    @staticmethod
    def _normalize(vector: List[float]) -> List[float]:
        if not vector:
            raise ValueError("empty embedding vector")
        norm = math.sqrt(sum(float(value) ** 2 for value in vector))
        return [float(value) / norm for value in vector] if norm > 0.0 else [float(value) for value in vector]

    def build_query_embedding(self, problem_text: str, ingredient_slots: Dict[str, List[str]]) -> Dict[str, Any]:
        if self.embedding_caller is None:
            self.embedding_caller = EmbeddingCaller()
        ingredient_text = build_ingredients_only_query(ingredient_slots)
        vectors = self.embedding_caller.embed_texts([ingredient_text, problem_text])
        if not isinstance(vectors, list) or len(vectors) != 2:
            raise RuntimeError("embedding caller must return two vectors for fused query embedding")
        if len(vectors[0]) != len(vectors[1]):
            raise ValueError(
                f"embedding dimension mismatch for fusion: ingredients={len(vectors[0])} problem={len(vectors[1])}"
            )
        alpha = self.archetype_fusion_alpha
        fused = self._normalize([alpha * a + (1.0 - alpha) * b for a, b in zip(vectors[0], vectors[1])])
        return {
            "query_embedding": fused,
            "query_text_ingredients": ingredient_text,
            "query_text_problem": problem_text,
        }

    def _rollout_skill(self, choice: Dict[str, Any]) -> str:
        framework = str(choice.get("framework", "")).strip()
        backend = str(choice.get("backend", "")).strip()
        backend_doc = str(choice.get("backend_doc", "")).strip()
        return (
            f"{ROLLOUT_MODEL_SKILL}\n\n"
            "# Solving stage\n"
            f"- Framework: {framework}\n"
            f"- Backend: {backend}\n"
            "- Backend reference markdown:\n"
            f"{backend_doc}\n"
            "- Always check solve status before reading objective value.\n"
            "- Output parseable `RESULT:<number>` or `RESULT_JSON:<json>`."
        )

    def _run_rollout_candidate(self, problem_description: str, ingredients: Dict[str, List[str]], choice: Dict[str, Any], timeout: int, sample_id: str, context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        start = time.perf_counter()
        result = FunctionCallAgent(llm=self.llm, max_turns=self.agent_max_turns, logger=self.logger).run(
            problem_description=problem_description,
            ingredients=ingredients,
            skill=self._rollout_skill(choice),
            timeout=timeout,
            sample_id=sample_id,
            problem_context=context,
        )
        attempts = result.get("attempts", []) if isinstance(result.get("attempts"), list) else []
        successful = next(
            (item for item in attempts if isinstance(item.get("run_result"), dict) and item["run_result"].get("returncode") == 0 and item["run_result"].get("result") is not None),
            {},
        )
        run_result = dict(successful.get("run_result", {})) if isinstance(successful, dict) else {}
        final = result.get("final_payload", {}) if isinstance(result.get("final_payload"), dict) else {}
        if final.get("final_result") is not None:
            run_result["result"] = final["final_result"]
        return {
            "candidate_id": f"candidate_{choice.get('candidate_rank', 1)}",
            "solver_id": str(choice.get("solver_id", "")),
            "family": "keyword_slots",
            "prompt": "",
            "raw": str(result.get("final_raw", "")),
            "code": str(successful.get("code", "")) if isinstance(successful, dict) else "",
            "run_result": run_result,
            "runtime_s": round(time.perf_counter() - start, 3),
            "num_tool_calls": len(attempts),
            "function_agent": result,
            "formulation": final.get("formulation", {}),
            "ingredient_slots": ingredients,
        }

    def _run_solver_pool_rollout(self, problem_description: str, ingredients: Dict[str, List[str]], top_k: int, timeout: int, sample_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.solver_pool_rollout.rollout(
            problem_description=problem_description,
            ingredient_slots=ingredients,
            top_k=top_k,
            sample_id=sample_id,
            run_candidate=lambda choice: self._run_rollout_candidate(problem_description, ingredients, choice, timeout, sample_id, context),
        )

    def cluster_collect(self, problem_description: str, ground_truth: str = "", top_k: int = 3, timeout: int = 120, sample_id: str = "") -> Dict[str, Any]:
        extractor = self.extract(problem_description)
        ingredients = clean_ingredient_slots(extractor.get("data", {}).get("keywords", {}))
        edited = str(extractor.get("data", {}).get("edited_problem", "")).strip() or problem_description
        embedding = self.build_query_embedding(edited, ingredients)
        rollout = self._run_solver_pool_rollout(problem_description, ingredients, top_k, timeout, sample_id)
        candidates = self.analyzer.attach_objective_metrics(rollout.get("candidates", []), ground_truth)
        rollout["candidates"] = candidates
        return {
            "path": "cluster_rollout",
            "extractor": extractor,
            "ingredient_slots": ingredients,
            "edited_problem_description": edited,
            "query_embedding": embedding["query_embedding"],
            "query_text_ingredients": embedding["query_text_ingredients"],
            "query_text_problem": embedding["query_text_problem"],
            "rollout": rollout,
            "eligible": any(self.analyzer.default_label(item) == "positive" for item in candidates),
        }

    def cluster_build(self, collected_samples: List[Dict[str, Any]], dbscan_eps: float, dbscan_min_samples: int) -> Dict[str, Any]:
        return self.cluster_builder.build(collected_samples, dbscan_eps, dbscan_min_samples)

    def _execute_skill(self, problem_description: str, ingredients: Dict[str, List[str]], selection: Dict[str, Any], timeout: int, sample_id: str, context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        start = time.perf_counter()
        output = FunctionCallAgent(llm=self.llm, max_turns=self.agent_max_turns, logger=self.logger).run(
            problem_description=problem_description,
            ingredients=ingredients,
            skill=selection["skill_content"],
            timeout=timeout,
            sample_id=sample_id,
            problem_context=context,
        )
        final = output.get("final_payload", {}) if isinstance(output.get("final_payload"), dict) else {}
        attempts = output.get("attempts", []) if isinstance(output.get("attempts"), list) else []
        prediction = final.get("final_result")
        raw_candidates = output.get("candidates", []) if isinstance(output.get("candidates"), list) else []
        candidate = next(
            (
                copy.deepcopy(item)
                for item in raw_candidates
                if isinstance(item, dict)
                and isinstance(item.get("run_result"), dict)
                and prediction is not None
                and item["run_result"].get("result") == prediction
            ),
            {},
        )
        candidate.update(
            {
                "candidate_id": str(candidate.get("candidate_id", "")).strip() or f"selected_{selection['skill_record']['skill_id']}",
                "skill_id": selection["skill_record"]["skill_id"],
                "run_result": {
                    **(candidate.get("run_result", {}) if isinstance(candidate.get("run_result"), dict) else {}),
                    "result": prediction,
                    "returncode": 0 if prediction is not None else None,
                },
                "runtime_s": round(time.perf_counter() - start, 3),
                "num_tool_calls": len(attempts),
                "function_agent": {
                    "messages": output.get("messages", []),
                    "final_payload": final,
                    "final_raw": output.get("final_raw", ""),
                },
                "formulation": final.get("formulation", {}),
            }
        )
        return {"function_agent": output, "candidate": candidate, "prediction": prediction}

    def run(self, *, problem_description: str, ground_truth: str = "", top_k: int = 3, timeout: int = 120, enable_self_learn: bool = False, sample_id: str = "", use_eval_extractor_prompt: bool = False, fc_problem_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        extractor = self.extract(problem_description, use_eval_prompt=use_eval_extractor_prompt)
        ingredients = clean_ingredient_slots(extractor.get("data", {}).get("keywords", {}))
        edited = str(extractor.get("data", {}).get("edited_problem", "")).strip() or problem_description
        if not enable_self_learn:
            selection = self.selector.select_eval(ingredients, edited)
            result = self._execute_skill(problem_description, ingredients, selection, timeout, sample_id, fc_problem_context)
            result["candidate"] = self.analyzer.attach_objective_metrics([result["candidate"]], ground_truth)[0]
            return {"path": "eval", "extractor": extractor, "skill_selection": selection["selection"], **result}

        update_ingredient_reference(self.manager.library_dir, ingredients)
        selection = self.selector.select_learning(ingredients, edited)
        if selection is not None:
            result = self._execute_skill(problem_description, ingredients, selection, timeout, sample_id, fc_problem_context)
            enriched = self.analyzer.attach_objective_metrics([result["candidate"]], ground_truth)
            candidate = enriched[0]
            result["candidate"] = candidate
            refine: Dict[str, Any] = {"attempted": False, "updated": False, "label": "", "reason": ""}
            if not str(ground_truth).strip():
                refine["reason"] = "missing_ground_truth"
            else:
                label = self.analyzer.default_label(candidate)
                analysis = self.analyzer.analyze_candidate(ingredients, candidate)
                refine = self.builder.refine_existing_skill(
                    selection["skill_record"]["skill_id"],
                    selection["skill_content"],
                    analysis,
                    label,
                )
                refine.update({"attempted": True, "updated": True, "label": label, "analysis": analysis})
            return {"path": "learning_recall", "extractor": extractor, "skill_selection": selection["selection"], "skill_refine": refine, **result}

        rollout = self._run_solver_pool_rollout(problem_description, ingredients, top_k, timeout, sample_id, fc_problem_context)
        enriched = self.analyzer.attach_objective_metrics(rollout.get("candidates", []), ground_truth)
        rollout["candidates"] = enriched
        positives = [item for item in enriched if self.analyzer.default_label(item) == "positive"]
        build: Dict[str, Any] = {"updated": False}
        if positives:
            analyses = self.analyzer.analyze_candidates(ingredients, enriched)
            build = self.builder.build_and_store("learning", ingredients, analyses)
            build["updated"] = True
        prediction = positives[0].get("run_result", {}).get("result") if positives else None
        return {"path": "learning_novelty", "extractor": extractor, "rollout": rollout, "skill_build": build, "prediction": prediction}
