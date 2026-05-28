# OR-Tools Backend: cp_model

## Type

OR-Tools CP-SAT API backend (`ortools.sat.python.cp_model`).

## Minimal Usage

```python
import json
from ortools.sat.python import cp_model


def solve_small_knapsack():
    # Toy data
    values = [20, 14, 8, 9]
    weights = [6, 4, 3, 2]
    capacity = 9

    # Model build
    model = cp_model.CpModel()
    x = [model.NewBoolVar(f"x_{i}") for i in range(len(values))]
    model.Add(sum(weights[i] * x[i] for i in range(len(values))) <= capacity)
    model.Maximize(sum(values[i] * x[i] for i in range(len(values))))

    # Solver create + key params
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = 42
    solver.parameters.relative_gap_limit = 0.0

    # Solve
    status = solver.Solve(model)

    # Status check + output contract
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        chosen = [i for i in range(len(values)) if solver.Value(x[i]) == 1]
        payload = {
            "status": "optimal" if status == cp_model.OPTIMAL else "feasible",
            "objective": float(solver.ObjectiveValue()),
            "chosen_items": chosen,
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")
    else:
        payload = {
            "status": "failed",
            "reason": "no_feasible_solution",
            "solver_status": int(status),
            "termination_condition": "cp_sat_status_code",
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")


if __name__ == "__main__":
    solve_small_knapsack()
```

## Usage Recommendations

- Prefer integer and Boolean variables; CP-SAT is not a continuous NLP solver.
- Encode logic with native constraints (`OnlyEnforceIf`, implications) instead of weak big-M when possible.
- Set a time limit in all experiments for predictable runtime.

## Parameter Hints

- `max_time_in_seconds`: hard runtime cap.
- `num_search_workers`: parallel search workers for larger instances.
- `relative_gap_limit`: acceptable relative optimality gap.
- `random_seed`: reproducibility across repeated runs.

## Status & Output Contract

Check `solver status / termination condition` first. For `cp_model`, status enum is the canonical gate before reading objective and variable values.

```python
if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    print(f"RESULT:{solver.ObjectiveValue()}")
else:
    print('RESULT_JSON:{"status":"failed","reason":"no_feasible_solution","solver_status":%d}' % int(status))
```
