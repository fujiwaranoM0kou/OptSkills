# -*- coding: utf-8 -*-
SOLVER_POOL_SELECTION_PROMPT = """You are selecting python solver library and backend combinations for optimization tasks.

Task:
- Choose top-k candidates from the provided solver catalog.
- Use problem description + structured keyword slots.
- Prefer backends that are likely to be available and stable.
- Catalog only contains framework/backend identifiers; detailed docs are loaded after selection.

Selection principles:
1. Infer problem family from objective/constraint keywords.
2. Prefer robust and standard backends when uncertain.
3. Keep diversity across frameworks/backends when possible.
4. Do not invent solver IDs; choose only from catalog.

Input:
<problem_description>
{problem_description}
</problem_description>

<keywords>
{keywords}
</keywords>

<top_k>
{top_k}
</top_k>

<solver_catalog_json>
{solver_catalog}
</solver_catalog_json>

Return JSON only:
{{
  "selected": [
    {{
      "solver_id": "string",
      "reason": "short reason"
    }}
  ]
}}"""


