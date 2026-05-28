from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from llm.llm_caller import LLMCaller
from prompts.skill_prompts import (
    BUILD_SKILL_PROMPT,
    REFINE_SKILL_PROMPT,
)
from skill_core.skill_manager import SkillManager
from utils.skill_syntax import repair_skill_frontmatter


def _strip_fence(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _extract_frontmatter_name(text: str) -> str:
    match = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
    if not match:
        return ""
    return match.group(1).strip().strip("'\"")


def _extract_frontmatter_description(text: str) -> str:
    match = re.search(r"^description:\s*\|\s*\n(.*?)(?:\n[a-zA-Z_]+:|\n---|\Z)", text, re.DOTALL | re.MULTILINE)
    if not match:
        return ""
    lines = [line.strip() for line in match.group(1).splitlines() if line.strip()]
    return " ".join(lines)


class SkillBuilder:
    def __init__(
        self,
        llm: Optional[LLMCaller] = None,
        manager: Optional[SkillManager] = None,
    ) -> None:
        self.llm = llm or LLMCaller()
        if manager is None:
            raise ValueError("SkillBuilder requires an explicit SkillManager.")
        self.manager = manager

    def _build_raw_skill(
        self,
        category: str,
        ingredients: Dict[str, List[str]],
        candidate_analyses: List[Dict[str, Any]],
    ) -> str:
        prompt = (
            BUILD_SKILL_PROMPT.replace("{keywords}", json.dumps(ingredients, ensure_ascii=False, indent=2))
            .replace("{candidate_analyses}", json.dumps(candidate_analyses, ensure_ascii=False, indent=2))
        )
        output = self.llm.chat(prompt)
        return _strip_fence(output)

    def build_raw_skill(
        self,
        category: str,
        ingredients: Dict[str, List[str]],
        candidate_analyses: List[Dict[str, Any]],
    ) -> str:
        return self._build_raw_skill(
            category=category,
            ingredients=ingredients,
            candidate_analyses=candidate_analyses,
        )

    def store_skill_content(
        self,
        category: str,
        candidate_analyses: List[Dict[str, Any]],
        skill_content: str,
    ) -> Dict[str, object]:
        final_skill = repair_skill_frontmatter(skill_content)
        if not final_skill:
            raise RuntimeError("store_skill_content received empty skill content")
        name = _extract_frontmatter_name(final_skill) or f"skill_{category}"
        description = _extract_frontmatter_description(final_skill)
        record = self.manager.create_skill(
            content=final_skill,
            name=name,
            description=description,
        )
        return {
            "record": record.as_dict(),
            "candidate_analyses": candidate_analyses,
        }

    def refine_existing_skill(
        self,
        skill_id: str,
        skill_content: str,
        skill_analysis: Dict[str, Any],
        label: str,
    ) -> Dict[str, Any]:
        sid = str(skill_id).strip()
        if not sid:
            raise RuntimeError("skill_id is required for refine_existing_skill")
        normalized_label = str(label).strip().lower()
        if normalized_label not in {"positive", "negative"}:
            raise RuntimeError(f"Invalid refine label: {label}")

        analysis_payload = skill_analysis if isinstance(skill_analysis, dict) else {}
        analysis_text = json.dumps(analysis_payload, ensure_ascii=False, indent=2)
        prompt = (
            REFINE_SKILL_PROMPT.replace("{skill}", str(skill_content))
            .replace("{skill_analysis}", analysis_text)
            .replace("{label}", normalized_label)
        )
        raw = self.llm.chat(prompt)
        refined_skill = repair_skill_frontmatter(_strip_fence(raw))
        if not refined_skill:
            refined_skill = str(skill_content).strip()

        updated_record = self.manager.update_skill(
            skill_id=sid,
            content=refined_skill,
            name=_extract_frontmatter_name(refined_skill) or None,
            description=_extract_frontmatter_description(refined_skill) or None,
        )
        if updated_record is None:
            raise RuntimeError(f"Skill not found for refine_existing_skill: {sid}")
        return {
            "record": updated_record.as_dict(),
            "label": normalized_label,
            "skill_analysis": analysis_payload,
        }

    def build_and_store(
        self,
        category: str,
        ingredients: Dict[str, List[str]],
        candidate_analyses: List[Dict[str, Any]],
    ) -> Dict[str, object]:
        raw_skill = self.build_raw_skill(
            category=category,
            ingredients=ingredients,
            candidate_analyses=candidate_analyses,
        )
        return self.store_skill_content(
            category=category,
            candidate_analyses=candidate_analyses,
            skill_content=raw_skill,
        )
