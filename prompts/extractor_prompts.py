# -*- coding: utf-8 -*-

EXTRACTOR_PROMPT = """
You are an optimization-structure extractor.
Your goal is to ignore surface semantics and recover the underlying optimization structure.
Different stories may describe the same mathematical problem class. You must normalize them into the same structural representation whenever the variables, constraints, and objective are essentially the same.

You must do two things on the same problem:
1) extract scenario-agnostic optimization keywords into three slots;
2) minimally edit the problem text into a scenario-neutral version.

Task A: Keyword extraction
- Extract high-signal structural keywords and place them into:
  - `variable`
  - `constraint`
  - `objective`
- The goal is not only mathematical correctness, but also discriminative power: the extracted keywords should help distinguish different canonical optimization classes even when their algebraic forms are similar.
- The extracted keywords should capture the structural signature of the problem: the decision roles of variables, the coupling mechanisms in constraints, and the operational intent of the objective.
- Prefer canonical optimization roles, mechanisms, and structural motifs over generic algebraic descriptions.
- Prefer structurally discriminative keywords that best characterize the problem class, rather than the most generic mathematical-form label.
- Preserve distinctions between problem classes even when they share similar variable types, linear constraints, or objective form.
- If a keyword is needed, use lowercase snake_case and keep it scenario-agnostic.
- Use generic keywords such as variable type, linear equality/inequality, or lower/upper bound only when they add meaningful structural information or when no more specific structural keyword applies.
- Do not include a generic algebraic keyword when it is already implied by a more specific structural keyword, unless the generic keyword adds distinct information.
- For the `objective` slot, prefer keywords describing optimization intent, cost structure, or performance criterion over keywords describing only algebraic form.
- Do not output narrative entities unless they represent canonical optimization structure.
- Avoid redundant near-synonyms, overly broad labels, or multiple generic keywords when a more specific structural keyword better captures the optimization pattern.

Task B: Minimal scenario-neutral edit
- Produce `edited_problem` by preserving the original problem structure as much as possible.
- Keep mathematical meaning, quantities, equations/inequalities, and logical relations unchanged.
- Replace scenario-specific nouns/entities with generic placeholders where needed (for example: `entity_A`, `resource_i`, `task_j`).
- Do NOT simplify the optimization structure.
- Do NOT reorder, delete, or add constraints/objectives.
- Do not delete information.
- Do not summarize.
- Edit all scenario-specific background narratives, even if they carry no mathematical content.
- Keep this as a minimal edit not a paraphrase rewrite.

Confidence
- Return a confidence score in [0,1] for keyword extraction quality.
  - 0.8-1.0: Keywords are structurally accurate, scenario-agnostic, and clearly discriminative for the problem class;
  - 0.5-0.7: Most keywords are relevant, but some are generic or a few important structural distinctions are underspecified;
  - 0.2-0.4: Some keywords are relevant but require more inference, or important discriminative structure is missing;
  - 0.0-0.1: Few or no clear keywords can be extracted.

Problem description to analyze:
<problem_description>
{problem_description}
</problem_description>

Output JSON only:
{{
  "keywords": {{
    "variable": ["string"],
    "constraint": ["string"],
    "objective": ["string"]
  }},
  "edited_problem": "string",
  "confidence": 0.0
}}

Output constraints:
- Include all three keyword slots (`variable`, `constraint`, `objective`), each as an array (can be empty).
- `edited_problem` must be non-empty plain text.
- No extra keys.
- The confidence score is a float between 0.0 and 1.0.
- Return only JSON, no markdown/code fence/explanation.
"""

EXTRACTOR_PROMPT_EVAL = """
You are an optimization-structure extractor.
Your goal is to ignore surface semantics and recover the underlying optimization structure.
Different stories may describe the same mathematical problem class. You must normalize them into the same structural representation whenever the variables, constraints, and objective are essentially the same.

You must do two things on the same problem:
1) extract scenario-agnostic optimization keywords into three slots;
2) minimally edit the problem text into a scenario-neutral version.

Task A: Keyword extraction
- Extract high-signal structural keywords and place them into:
  - `variable`
  - `constraint`
  - `objective`
- The goal is not only mathematical correctness, but also discriminative power: the extracted keywords should help distinguish different canonical optimization classes even when their algebraic forms are similar.
- The extracted keywords should capture the structural signature of the problem: the decision roles of variables, the coupling mechanisms in constraints, and the operational intent of the objective.
- Prefer canonical optimization roles, mechanisms, and structural motifs over generic algebraic descriptions.
- Prefer structurally discriminative keywords that best characterize the problem class, rather than the most generic mathematical-form label.
- Preserve distinctions between problem classes even when they share similar variable types, linear constraints, or objective form.
- If a keyword is needed, use lowercase snake_case and keep it scenario-agnostic.
- Use generic keywords such as variable type, linear equality/inequality, or lower/upper bound only when they add meaningful structural information or when no more specific structural keyword applies.
- Do not include a generic algebraic keyword when it is already implied by a more specific structural keyword, unless the generic keyword adds distinct information.
- For the `objective` slot, prefer keywords describing optimization intent, cost structure, or performance criterion over keywords describing only algebraic form.
- Do not output narrative entities unless they represent canonical optimization structure.
- Avoid redundant near-synonyms, overly broad labels, or multiple generic keywords when a more specific structural keyword better captures the optimization pattern.

Keyword list reference for inference:
<keywords_list>
{keywords_list}
</keywords_list>

When extracting keywords, prioritize canonical tokens from this list when they are semantically appropriate to the problem. Do not force a token from the list if none is a good fit.

Task B: Minimal scenario-neutral edit
- Produce `edited_problem` by preserving the original problem structure as much as possible.
- Keep mathematical meaning, quantities, equations/inequalities, and logical relations unchanged.
- Replace scenario-specific nouns/entities with generic placeholders where needed (for example: `entity_A`, `resource_i`, `task_j`).
- Do NOT simplify the optimization structure.
- Do NOT reorder, delete, or add constraints/objectives.
- Do not delete information.
- Do not summarize.
- Edit all scenario-specific background narratives, even if they carry no mathematical content.
- Keep this as a minimal edit not a paraphrase rewrite.

Confidence
- Return a confidence score in [0,1] for keyword extraction quality.
  - 0.8-1.0: Keywords are structurally accurate, scenario-agnostic, and clearly discriminative for the problem class;
  - 0.5-0.7: Most keywords are relevant, but some are generic or a few important structural distinctions are underspecified;
  - 0.2-0.4: Some keywords are relevant but require more inference, or important discriminative structure is missing;
  - 0.0-0.1: Few or no clear keywords can be extracted.

Problem description to analyze:
<problem_description>
{problem_description}
</problem_description>

Output JSON only:
{{
  "keywords": {{
    "variable": ["string"],
    "constraint": ["string"],
    "objective": ["string"]
  }},
  "edited_problem": "string",
  "confidence": 0.0
}}

Output constraints:
- Include all three keyword slots (`variable`, `constraint`, `objective`), each as an array (can be empty).
- `edited_problem` must be non-empty plain text.
- No extra keys.
- The confidence score is a float between 0.0 and 1.0.
- Return only JSON, no markdown/code fence/explanation.
"""
