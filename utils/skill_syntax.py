from __future__ import annotations

import re


def repair_skill_frontmatter(content: str) -> str:
    text = str(content).strip()
    text = re.sub(r"^```(?:markdown|md)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    if not text.startswith("---"):
        text = "---\n" + text
    lines = text.splitlines()
    closing = next((idx for idx in range(1, len(lines)) if lines[idx].strip() == "---"), None)
    if closing is None:
        insert_at = 1
        while insert_at < len(lines) and (
            lines[insert_at].startswith("name:")
            or lines[insert_at].startswith("description:")
            or lines[insert_at].startswith("  ")
            or not lines[insert_at].strip()
        ):
            insert_at += 1
        lines.insert(insert_at, "---")
    return "\n".join(lines).strip() + "\n"
