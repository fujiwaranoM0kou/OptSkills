# OR-Tools Backends

This directory contains backend references used by OptSkill solver-pool selection.

## Scope

- `cp_model`: CP-SAT modeling for integer and Boolean optimization.
- `pywrapcp`: Routing and legacy CP search APIs.
- `pywraplp`: LP/MIP modeling through MPSolver wrappers.
- `graph`: Graph and network-flow focused algorithms.
- `algorithms`: Standalone algorithm modules (for example knapsack variants).

## Backend Selection Quick Guide

- Use `cp_model` when the model is combinatorial, logical, or scheduling-oriented.
- Use `pywraplp` when the model is algebraic LP/MIP and you want a classic solver interface.
- Use `pywrapcp` when the task is routing-centric (TSP/VRP) with neighborhood search.
- Use `graph` when the problem is explicitly a flow/network optimization problem.
- Use `algorithms` only when your task matches a built-in specialized routine.

## How These Docs Are Used

- During solver-pool selection, backend identifiers are ranked first.
- After backend selection, the matching README is injected into solving instructions.
- Backend docs should emphasize practical modeling style and parseable output behavior.

## Shared Status & Output Contract

- Always check `solver status / termination condition` (or backend-native solve status enum) before reading objective values or decision variables.
- Emit exactly one parseable final line:
  - `RESULT:<number>` for scalar objective outputs.
  - `RESULT_JSON:<json>` for structured outputs.
- On failure, emit `RESULT_JSON` with at least:
  - `status: "failed"`
  - `reason`
  - `solver_status` when available
  - `termination_condition` when available

```python
# Contract sketch
if solved_successfully:
    print(f"RESULT:{objective_value}")
else:
    print('RESULT_JSON:{"status":"failed","reason":"infeasible_or_error"}')
```
