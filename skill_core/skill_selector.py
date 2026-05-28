from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from llm.llm_caller import LLMCaller
from prompts.skill_prompts import SKILL_SELECTION_PROMPT, SKILL_SELECTION_PROMPT_EVAL, SKILL_SELECTION_PROMPT_JUDGE
from skill_core.skill_manager import SkillManager
from utils.extract_json import extract_json


class SkillSelector:
    def __init__(self, llm: LLMCaller, manager: SkillManager) -> None:
        self.llm = llm
        self.manager = manager

    def _candidates(self) -> List[Dict[str, str]]:
        return [
            {"skill_id": record.skill_id, "name": record.name, "description": record.description}
            for record in self.manager.list_skills()
            if record.path
        ]

    def _bundle(self, data: Dict[str, Any], candidates: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        skill_id = str(data.get("skill_id", "")).strip()
        valid = {item["skill_id"] for item in candidates}
        if not skill_id or skill_id not in valid:
            return None
        record = self.manager.get_skill_record(skill_id)
        if record is None:
            return None
        content = self.manager.get_skill_content(record.path)
        if not content.strip():
            return None
        return {"selection": data, "skill_record": record.as_dict(), "skill_content": content}

    def select_eval(self, ingredients: Dict[str, List[str]], edited_problem: str) -> Dict[str, Any]:
        candidates = self._candidates()
        if not candidates:
            raise RuntimeError("Evaluation requires a non-empty skill library.")
        prompt = SKILL_SELECTION_PROMPT_EVAL.format(
            keywords=json.dumps(ingredients, ensure_ascii=False, indent=2),
            edited_problem=str(edited_problem).strip(),
            skill_candidates_json=json.dumps(candidates, ensure_ascii=False, indent=2),
        )
        raw = self.llm.chat(user_prompt=prompt, system_prompt="You are a precise OR skill selector.")
        data = extract_json(raw, default={})
        bundle = self._bundle(data if isinstance(data, dict) else {}, candidates)
        if bundle is None:
            raise RuntimeError("Skill selector returned an invalid skill_id.")
        bundle["selection"]["raw"] = raw
        return bundle

    def select_learning(self, ingredients: Dict[str, List[str]], edited_problem: str) -> Optional[Dict[str, Any]]:
        candidates = self._candidates()
        if not candidates:
            return None
        prompt = SKILL_SELECTION_PROMPT.format(
            keywords=json.dumps(ingredients, ensure_ascii=False, indent=2),
            edited_problem=str(edited_problem).strip(),
            skill_candidates_json=json.dumps(candidates, ensure_ascii=False, indent=2),
        )
        try:
            raw = self.llm.chat(user_prompt=prompt, system_prompt="You are a conservative OR skill selector.")
            data = extract_json(raw, default={})
        except Exception:
            return None
        if not isinstance(data, dict) or str(data.get("decision", "")).strip().lower() != "recall":
            return None
        bundle = self._bundle(data, candidates)
        if bundle is None:
            return None
        selected = {
            "skill_id": bundle["skill_record"]["skill_id"],
            "name": bundle["skill_record"]["name"],
            "description": bundle["skill_record"]["description"],
        }
        judge_prompt = SKILL_SELECTION_PROMPT_JUDGE.format(
            keywords=json.dumps(ingredients, ensure_ascii=False, indent=2),
            edited_problem=str(edited_problem).strip(),
            selected_skill_json=json.dumps(selected, ensure_ascii=False, indent=2),
            selector_reason=str(data.get("reason", "")),
        )
        try:
            judge_raw = self.llm.chat(user_prompt=judge_prompt, system_prompt="You are a strict OR skill applicability judge.")
            judgment = extract_json(judge_raw, default={})
        except Exception:
            return None
        if not isinstance(judgment, dict) or not bool(judgment.get("applicable", False)):
            return None
        data["raw"] = raw
        data["judge"] = judgment
        return bundle
