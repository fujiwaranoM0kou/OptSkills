from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List


def _read_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    yield value


def _question(row: Dict[str, Any]) -> str:
    for key in ("input", "abstract_problem", "question", "problem_description"):
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def _answer(row: Dict[str, Any]) -> str:
    for key in ("answer", "optimal_value", "ground_truth", "label"):
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def _sample_key(row: Dict[str, Any], index: int) -> str:
    for key in ("sample_key", "id", "instance_id", "name", "index"):
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return str(index)


def _miplib_files(payload: Any, instance_dir: str) -> List[Dict[str, str]]:
    items = payload.items() if isinstance(payload, dict) else enumerate(payload or [])
    files: List[Dict[str, str]] = []
    for key, item in items:
        data = item if isinstance(item, dict) else {"path": str(item)}
        relative = str(data.get("path", data.get("file", key))).strip()
        if not relative:
            continue
        files.append({"path": os.path.abspath(os.path.join(instance_dir, relative))})
    return files


def _read_miplib(root: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(root)):
        instance_dir = os.path.join(root, name)
        path = os.path.join(instance_dir, "instance.json")
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8-sig") as handle:
            row = json.load(handle)
        question = str(row.get("abstract_problem", "")).strip()
        if not question:
            continue
        entries.append(
            {
                "idx": len(entries) + 1,
                "row": row,
                "sample_key": name,
                "sample_id": f"sample_{name}",
                "question": question,
                "answer": str(row.get("optimal_value", "")).strip(),
                "fc_problem_context": {
                    "bench": "miplib_nl",
                    "abstract_problem": question,
                    "parameters": row.get("parameters", {}) if isinstance(row.get("parameters"), dict) else {},
                    "files": _miplib_files(row.get("files", []), instance_dir),
                },
            }
        )
    return entries


def load_entries(question: str, answer: str, data: str, miplib_nl_bench: bool) -> List[Dict[str, Any]]:
    if str(question).strip():
        return [{"idx": 1, "row": {}, "sample_key": "single", "sample_id": "sample", "question": question, "answer": answer}]
    if not data:
        raise SystemExit("Provide --data or --question.")
    path = os.path.abspath(data)
    if miplib_nl_bench:
        return _read_miplib(path)
    entries: List[Dict[str, Any]] = []
    for idx, row in enumerate(_read_jsonl(path), start=1):
        q = _question(row)
        if not q:
            continue
        key = _sample_key(row, idx)
        entries.append({"idx": idx, "row": row, "sample_key": key, "sample_id": f"sample_{key}", "question": q, "answer": _answer(row)})
    return entries


def select_entries(entries: List[Dict[str, Any]], keys: List[str]) -> List[Dict[str, Any]]:
    by_key = {str(item["sample_key"]): item for item in entries}
    return [by_key[key] for key in keys if key in by_key]
