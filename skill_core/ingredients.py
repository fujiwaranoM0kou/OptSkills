from __future__ import annotations

import json
import os
from typing import Any, Dict, List

SLOTS = ("variable", "constraint", "objective")


def clean_ingredient_slots(values: Any) -> Dict[str, List[str]]:
    cleaned: Dict[str, List[str]] = {slot: [] for slot in SLOTS}
    if not isinstance(values, dict):
        return cleaned
    for slot in SLOTS:
        raw = values.get(slot, [])
        if not isinstance(raw, list):
            continue
        for item in raw:
            token = str(item).strip().lower().replace(" ", "_")
            if token and token not in cleaned[slot]:
                cleaned[slot].append(token)
    return cleaned


def load_ingredient_reference(library_dir: str) -> Dict[str, List[str]]:
    path = os.path.join(library_dir, "ingredients.json")
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {slot: [] for slot in SLOTS}
    source = payload.get("ingredients", payload)
    return clean_ingredient_slots(source)


def update_ingredient_reference(library_dir: str, values: Dict[str, List[str]]) -> None:
    current = load_ingredient_reference(library_dir)
    incoming = clean_ingredient_slots(values)
    for slot in SLOTS:
        for token in incoming[slot]:
            if token not in current[slot]:
                current[slot].append(token)
    path = os.path.join(library_dir, "ingredients.json")
    os.makedirs(library_dir, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump({"ingredients": current}, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
