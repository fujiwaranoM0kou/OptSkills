from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


def _slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_]+", "_", str(text).strip().lower())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "skill"


@dataclass
class SkillRecord:
    skill_id: str
    name: str
    description: str
    path: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "path": self.path,
        }


class SkillManager:
    def __init__(self, library_dir: str, index_path: Optional[str] = None) -> None:
        self.library_dir = os.path.abspath(library_dir)
        self.index_path = index_path or os.path.join(self.library_dir, "index.json")
        self._lock = threading.RLock()
        self._ensure_index()

    def _ensure_index(self) -> None:
        os.makedirs(self.library_dir, exist_ok=True)
        if not os.path.exists(self.index_path):
            self._save_index({"version": "1.0", "skills": []})

    def _load_index(self) -> Dict[str, Any]:
        try:
            with open(self.index_path, "r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError):
            payload = {"version": "1.0", "skills": []}
        payload["skills"] = payload.get("skills", []) if isinstance(payload.get("skills"), list) else []
        return payload

    def _save_index(self, payload: Dict[str, Any]) -> None:
        cleaned = {"version": str(payload.get("version", "1.0")), "skills": []}
        for item in payload.get("skills", []):
            if isinstance(item, dict):
                cleaned["skills"].append(
                    {
                        "skill_id": str(item.get("skill_id", "")).strip(),
                        "name": str(item.get("name", "")).strip(),
                        "description": str(item.get("description", "")).strip(),
                        "path": str(item.get("path", "")).strip(),
                    }
                )
        os.makedirs(self.library_dir, exist_ok=True)
        tmp = f"{self.index_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(cleaned, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, self.index_path)

    def normalize_index(self) -> None:
        with self._lock:
            self._save_index(self._load_index())

    def list_skills(self) -> List[SkillRecord]:
        with self._lock:
            items = self._load_index().get("skills", [])
        return [
            SkillRecord(
                skill_id=str(item.get("skill_id", "")).strip(),
                name=str(item.get("name", "")).strip(),
                description=str(item.get("description", "")).strip(),
                path=str(item.get("path", "")).strip(),
            )
            for item in items
            if isinstance(item, dict) and str(item.get("skill_id", "")).strip()
        ]

    def get_skill_record(self, skill_id: str) -> Optional[SkillRecord]:
        return next((item for item in self.list_skills() if item.skill_id == str(skill_id).strip()), None)

    def get_skill_content(self, relative_path: str) -> str:
        path = os.path.join(self.library_dir, str(relative_path).strip())
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    @staticmethod
    def _write_skill(path: str, content: str) -> None:
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(str(content).strip() + "\n")
        os.replace(tmp, path)

    def create_skill(self, *, content: str, name: str = "", description: str = "", skill_id: Optional[str] = None) -> SkillRecord:
        with self._lock:
            payload = self._load_index()
            skills = payload["skills"]
            existing = {str(item.get("skill_id", "")).strip() for item in skills if isinstance(item, dict)}
            base = _slug(skill_id or name or "skill_auto")
            final_id = base
            idx = 2
            while final_id in existing:
                final_id = f"{base}_{idx}"
                idx += 1
            record = SkillRecord(final_id, str(name).strip() or final_id, str(description).strip(), f"{final_id}.md")
            self._write_skill(os.path.join(self.library_dir, record.path), content)
            skills.append(record.as_dict())
            self._save_index(payload)
            return record

    def update_skill(self, skill_id: str, *, content: Optional[str] = None, name: Optional[str] = None, description: Optional[str] = None, **_: Any) -> Optional[SkillRecord]:
        with self._lock:
            payload = self._load_index()
            for item in payload["skills"]:
                if isinstance(item, dict) and str(item.get("skill_id", "")).strip() == str(skill_id).strip():
                    if content is not None:
                        self._write_skill(os.path.join(self.library_dir, str(item["path"])), content)
                    if name is not None:
                        item["name"] = str(name).strip()
                    if description is not None:
                        item["description"] = str(description).strip()
                    self._save_index(payload)
                    return self.get_skill_record(str(skill_id).strip())
        return None
