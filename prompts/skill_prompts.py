# -*- coding: utf-8 -*-

SKILL_ANALYSIS_PROMPT = """You are operation research trajectory analyst.Your goal is to generate reusable Standard Operating Procedures (SOPs) for OR skill construction. Your core task is to analyze exactly one rollout trajectory, and output reusable guidance in markdown blocks based on objective metrics.

Next, refer to the relevant keywords:
<keywords>
{keywords}
</keywords>

Next, refer to Objective Indicators
<Indicators>
{Indicators}
</Indicators>

Now, analyze the candidate data:
<trajectory>
{trajectory}
</trajectory>

Your output must be a single JSON object following this schema:
{
  "positive_sop": "### Modeling\\n- ...\\n\\n### Solving\\n- ...",
  "should_avoid": " "
}

Adhere to these output constraints:
- If `label` is "positive", `positive_sop` must be non-empty with sections "### Modeling" followed by "### Solving", containing reusable, scenario-agnostic bullet points. Set `should_avoid` to an empty string.
- If `label` is "negative", `should_avoid` must be non-empty, containing reusable, scenario-agnostic bullet points. Set `positive_sop` to an empty string.
- Do not include any text outside the JSON object.
- Keep It General: The skill should apply to similar problems, not just this one.
- Capture Executable Knowledge: When the trajectory includes effective code, extract the core logic as a reusable template. Good code templates are worth more than paragraphs of description.
- Brevity Matters: Aim for ~600 words. Focus on what's actionable."""


BUILD_SKILL_PROMPT = """You are an OR Skill Builder that writes workflow-oriented SKILL documents for long-term reuse.

Mission:
- Build one polished SKILL markdown from problem context and per-candidate analyses.
- The result must guide another model from formulation to executable solving code.
- Keep it practical, technically precise, and transferable.
- Follow the output template as a strict structural schema: do not add, remove, rename, reorder, or reformat any required section, heading level, or YAML frontmatter delimiter.

Design principles:
1. Distill lessons, do not narrate trajectory.
2. Keep workflow alternatives parallel (not sequential).
3. Use solver-aware modeling templates.
4. Make result parsing and failure handling explicit.
5. Prefer concise technical clarity over decorative prose.
6. Suitable code Usage can be placed in every step with explicit comments.
7. Keep it general,Use placeholders instead of specific values. The skill should apply to similar problems, not just this one, not just this scenario.The Skill Name,Skill description,Workflow names,Step names should all be generalized and not scenario-specific.

Hard format contract:
- Keep this section order exactly:
  frontmatter
  -> # Workflow 1 (...)
     -> ## Modeling stage
     -> ## Solving stage
  -> # Workflow 2 (...)
     -> ## Modeling stage
     -> ## Solving stage
- Do not add extra top-level sections.
- Do not output explanatory text outside the markdown.

Input:
<keywords>
{keywords}
</keywords>

<candidate_analyses_json>
{candidate_analyses}
</candidate_analyses_json>

Candidate analyses schema contract:
- Each item contains:
  - `candidate_id` (controller-provided identifier)
  - `label` (`positive` or `negative`)
  - `positive_sop` (markdown with `### Modeling` and `### Solving`)
  - `should_avoid` (markdown with `### Should Avoid`)
- Build skill content mainly from:
  - positive examples: `positive_sop`
  - negative examples: `should_avoid`
- Do not assume legacy fields such as `decision_basis`, `summary`, or nested step arrays.

Output markdown template (SKILL.md content only):
---
name: [skill_name]
description: |
  [One sentence covering both modeling and solving behavior.]
---

# Workflow 1 ([workflow_name])

## Modeling stage

### Strategy Overview
[Short paragraph.]

### Step 1 - [Model Step Name]
- [Action]
- [Action]

### Step 2 - [Model Step Name]
- [Action]
- [Action]

### Step ...

### Formulation Template
```json
{
  "sets": [],
  "parameters": [],
  "decision_variables": [],
  "objective": {
    "sense": "min",
    "expression": ""
  },
  "constraints": []
}
```

### Common Pitfalls
- [Pitfall]
- [Pitfall]

## Solving stage

### Strategy Overview
[Short paragraph.]

### Step 1 - [Solver Step Name]
- [Action]
- [Action]

### Step 2 - [Solver Step Name]
- [Action]
- [Action]

### Step ...

### Code Usage
```python
# build model from formulation
# solve with status / termination checks
```

### Common Pitfalls
- [Pitfall]
- [Pitfall]

# Workflow 2 ([workflow_name])

## Modeling stage

### Strategy Overview
[Short paragraph.]

### Step 1 - [Model Step Name]
- [Action]
- [Action]

### Step 2 - [Model Step Name]
- [Action]
- [Action]

### Step ...

### Formulation Template
```json
{
  "sets": [],
  "parameters": [],
  "decision_variables": [],
  "objective": {
    "sense": "min",
    "expression": ""
  },
  "constraints": []
}
```

### Common Pitfalls
- [Pitfall]
- [Pitfall]

## Solving stage

### Strategy Overview
[Short paragraph.]

### Step 1 - [Solver Step Name]
- [Action]
- [Action]

### Step 2 - [Solver Step Name]
- [Action]
- [Action]

### Step ...

### Code Usage
```python
# build model from formulation
# solve with status / termination checks
```

### Common Pitfalls
- [Pitfall]
- [Pitfall]

Quality bar:
- Workflows must be meaningfully different (backend/solver/API style).
- Avoid copy-paste duplication between Workflows.
- Keep placeholders generic and executable.
- Output starts with `---` and ends at markdown body."""


REFINE_SKILL_PROMPT = """You are a Skill Optimization Specialist. Your core task is to refine an existing operation research SKILL using one completed trajectory analysis and the current skill content, with the goals of improving the skill’s effectiveness, preserving its reusable workflow quality, removing redundancy, generalizing specific cases, and enhancing structure.

Your goals are to:
- improve the SKILL’s effectiveness,
- preserve and strengthen reusable workflow quality,
- remove redundancy,
- generalize only what is truly reusable,
- and maintain a stable, executable structure.

Core Execution Rules:
- Use the `<label>` as the supervision signal:
  - If `label` is `positive`: strengthen or clarify successful reusable procedures supported by the `<skill_analysis>`.
  - If `label` is `negative`: add or strengthen prerequisite checks, early warning signals, failure guards, and fallback guidance supported by the `<skill_analysis>`.
- Apply only the smallest set of edits justified by the trajectory analysis.
- Do not infer broad behavioral changes from a single narrow case.
- Preserve the SKILL’s identity: do not over-generalize it into a broader template that weakens its intended optimization problem class, solver assumptions, modeling pattern, or retrieval specificity.

Input:
<skill>
{skill}
</skill>

<skill_analysis>
{skill_analysis}
</skill_analysis>

<label>
{label}
</label>

Refinement Constraints (Strictly Follow):
1. Preserve the outer document skeleton exactly:
   - keep the full YAML frontmatter,
   - keep both opening and closing `---`,
   - keep all existing YAML keys,
   - keep key order unchanged,
   - keep the top-level section structure and heading order unchanged unless explicitly impossible to maintain validity.

2. Within existing sections, you may rewrite, compress, deduplicate, clarify, and generalize content. Prefer local edits over full rewrites.

3. Preserve all useful existing workflows. Remove only weak, vague, repetitive, or redundant wording.

4. Do not remove explicit execution checks, solver/status verification steps, or parseable output contracts. You may clarify or tighten them if supported by the trajectory.

5. Exclude scenario-specific story details from the analysis, such as names, one-time events, or incidental numeric values, unless they represent a reusable operational threshold or rule.

6. Replace overly specific examples with reusable patterns when possible. Convert hardcoded task-specific values into placeholders such as `[TARGET]`, `[QUERY]`, `[TIME_LIMIT]`, `[CAPACITY]`, or similar appropriate abstractions.

7. Preserve skill-discriminative information. Do not remove or blur details that define this SKILL’s distinctive optimization structure, including when relevant:
   - problem class,
   - decision variable pattern,
   - objective type,
   - key constraint structure,
   - solver or modeling assumptions.

8. Merge duplicate or near-duplicate content only when meaning is preserved. Consolidate overlapping explanations into clearer single statements.

9. For `positive` labels:
   - strengthen successful SOPs supported by the analysis,
   - clarify reusable step order,
   - make successful checks, thresholds, or decision criteria more explicit,
   - do not add unsupported new methods or techniques.

10. For `negative` labels:
   - prioritize prerequisite checks, early failure detection, recovery steps, and fallback guidance,
   - do not ban a method entirely unless the analysis clearly shows a general failure mode rather than a one-off execution issue,
   - do not overwrite or weaken proven successful workflows unless the analysis reveals a general flaw in them.

11. Do not introduce new solver strategies, modeling tricks, tools, or procedures unless they are clearly supported by either the existing SKILL or the trajectory.

12. Keep the content concise, actionable, and reusable. Remove verbosity that does not improve execution quality.

13. Maintain consistent formatting and scannability within the existing structure:
   - clear steps,
   - consistent bullet style,
   - concise wording,
   - no unnecessary prose expansion.

14. Perform a consistency audit across prose, formulation templates, and code examples:
   - ensure sign conventions, index ordering, objective sense, constraint direction, and variable semantics are mutually consistent,
   - if a contradiction exists, prefer the smallest edit that restores internal consistency,
   - do not preserve contradictory formulations merely to minimize edits.

Refinement Principles:
- Prefer minimal, evidence-based edits
- Generalize reusable patterns, not incidental details
- Preserve what makes the SKILL specifically useful
- Add safeguards carefully and only when justified
- Keep the SKILL executable, clear, and retrieval-distinctive

Output:
- Return only refined SKILL markdown, starting at the frontmatter (`---`).
- Do not output JSON.
- Do not output explanatory text.
- Do not wrap the answer in code fences."""


SKILL_SELECTION_PROMPT_EVAL = """You are an skill selector used for skill routing.Route the best suitable skill for the current problem.

Your task:
- Select exactly one skill from the provided candidate list.
- You must choose only from the candidate `skill_id` values provided below.
- You must rely only on the candidate skill `name` and `description`.
- Do not use hidden assumptions about the full skill content.
- Do not invent a new skill.

Problem structure signals:
<keywords>
{keywords}
</keywords>

Scenario-neutral edited problem:
<edited_problem>
{edited_problem}
</edited_problem>

Candidate skills for the current active state:
<skill_candidates_json>
{skill_candidates_json}
</skill_candidates_json>

Return JSON only in this exact schema:
{{
  "skill_id": "string",
  "reason": "string",
  "confidence": 0.0
}}

Output constraints:
- `skill_id` must exactly match one candidate `skill_id`.
- `reason` must be brief and grounded in the provided keywords / edited problem / descriptions.
- `confidence` must be a float in [0.0, 1.0].
- No markdown, no code fence, no extra keys, no extra text.
"""


SKILL_SELECTION_PROMPT = """You are a conservative Operations Research skill selector used for online self-learning skill routing.

Your task:
- Decide whether an existing reusable skill is suitable for the current problem.
- If a suitable skill exists, select exactly one skill from the provided candidate list.
- If no candidate is structurally suitable, reject retrieval.
- You must choose only from the candidate `skill_id` values provided below when `decision` is `recall`.
- You must rely only on the candidate skill `name` and `description`.
- Do not use hidden assumptions about the full skill content.
- Do not invent a new skill.

Reject when:
- the candidate belongs to a different canonical optimization family,
- the current problem and candidate are not the same canonical optimization type,
- the core modeling structure, decision-variable pattern, objective, or constraint mechanism does not match,
- the match is based only on superficial keyword overlap,
- candidate descriptions are too generic to justify reuse,
- or you are uncertain that the selected skill is reusable for this problem.

Recall only when:
- the current problem and selected candidate strictly and clearly describe the same canonical optimization type,
- and the candidate description covers the current problem's core variable semantics, constraint mechanism, and objective semantics.

Strict decision policy:
- Trust your own structural judgment even when all candidates look imperfect.
- Do not force a recall just because a candidate is the closest available option.
- Do not recall a skill that would require adapting its canonical formulation to a different problem type.
- Reusable means directly applicable at the canonical type level, not merely adaptable.
- Be careful with problems that look similar at the surface level; similar keywords do not by themselves mean the same canonical optimization type.
- If the exact canonical type is not represented by any candidate description, choose `reject`.

Problem structure signals:
<keywords>
{keywords}
</keywords>

Scenario-neutral edited problem:
<edited_problem>
{edited_problem}
</edited_problem>

Candidate skills for the current active state:
<skill_candidates_json>
{skill_candidates_json}
</skill_candidates_json>

Return JSON only in this exact schema:
{{
  "decision": "recall",
  "skill_id": "string",
  "reason": "string",
  "confidence": 0.0
}}

Output constraints:
- `decision` must be exactly `recall` or `reject`.
- If `decision` is `recall`, `skill_id` must exactly match one candidate `skill_id`.
- If `decision` is `reject`, `skill_id` must be an empty string.
- `reason` must be brief and grounded in the provided keywords / edited problem / descriptions.
- `confidence` must be a float in [0.0, 1.0].
- No markdown, no code fence, no extra keys, no extra text.
"""


SKILL_SELECTION_PROMPT_JUDGE = """You are a strict Operations Research skill applicability judge.

Your task:
- Decide whether the selected reusable skill can be directly applied to the current problem.
- You are not selecting the closest skill.
- You are judging one already-selected skill and must reject it if it is only superficially related or merely adaptable.

Directly applicable means:
- the current problem and selected skill have the same canonical optimization type or subtype,
- the decision-variable semantics match,
- the core constraint mechanism matches,
- the objective semantics match,
- and the skill can be reused without changing its canonical formulation family.

Reject when:
- the selected skill belongs to a broader, narrower, or adjacent optimization family but not the same canonical type,
- using the skill would require adding/removing essential formulation components,
- the match relies on shared surface words such as route, assignment, cover, capacity, schedule, graph, pairwise, or sequence,
- the selected skill is only a useful inspiration or starting point,
- the selected skill description does not explicitly cover the current problem's key subtype,
- or you are uncertain.

Problem structure signals:
<keywords>
{keywords}
</keywords>

Scenario-neutral edited problem:
<edited_problem>
{edited_problem}
</edited_problem>

Selected skill:
<selected_skill_json>
{selected_skill_json}
</selected_skill_json>

Selector rationale:
<selector_reason>
{selector_reason}
</selector_reason>

Return JSON only in this exact schema:
{{
  "applicable": false,
  "reason": "string",
  "confidence": 0.0
}}

Output constraints:
- `applicable` must be a boolean.
- `reason` must be brief and grounded in the problem and selected skill description.
- `confidence` must be a float in [0.0, 1.0].
- No markdown, no code fence, no extra keys, no extra text.
"""
