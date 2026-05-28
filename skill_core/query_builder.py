from __future__ import annotations

from typing import Dict, List

SLOTS = ("variable", "constraint", "objective")


def normalize_ingredients(values: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        token = str(value).strip().lower().replace(" ", "_")
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def normalize_ingredient_slots(values: Dict[str, List[str]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {slot: [] for slot in SLOTS}
    if not isinstance(values, dict):
        return out
    for slot in SLOTS:
        raw = values.get(slot, [])
        if not isinstance(raw, list):
            raw = []
        out[slot] = normalize_ingredients([str(v) for v in raw])
    return out


def _slot_text(values: List[str]) -> str:
    if not values:
        return ""
    return ", ".join(values)


def build_ingredients_only_query(ingredient_slots: Dict[str, List[str]]) -> str:
    normalized = normalize_ingredient_slots(ingredient_slots)
    objective_text = _slot_text(normalized.get("objective", []))
    variable_text = _slot_text(normalized.get("variable", []))
    constraint_text = _slot_text(normalized.get("constraint", []))
    return (
        "[Objective Keywords]\n"
        f"{objective_text}\n\n"
        "[Variable Keywords]\n"
        f"{variable_text}\n\n"
        "[Constraint Keywords]\n"
        f"{constraint_text}"
    )
