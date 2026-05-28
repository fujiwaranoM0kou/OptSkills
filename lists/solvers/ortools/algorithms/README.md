# OR-Tools Backend: algorithms

## Type

OR-Tools specialized algorithm modules (`ortools.algorithms.python`).

## Minimal Usage

```python
import json
from ortools.algorithms.python import knapsack_solver


def solve_knapsack_module():
    # Toy data
    profits = [24, 13, 23, 15, 16]
    weights = [[12, 7, 11, 8, 9]]
    capacities = [26]

    # Solver create
    solver = knapsack_solver.KnapsackSolver(
        knapsack_solver.SolverType.KNAPSACK_MULTIDIMENSION_BRANCH_AND_BOUND_SOLVER,
        "knapsack_demo",
    )

    # Solve (module-specific API)
    try:
        objective = solver.solve(profits, weights, capacities)
    except Exception as exc:
        payload = {
            "status": "failed",
            "reason": "algorithm_exception",
            "solver_status": str(exc),
            "termination_condition": "exception",
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")
        return

    # Status-like validation + output contract
    if objective is None:
        payload = {
            "status": "failed",
            "reason": "no_result",
            "solver_status": "none_objective",
            "termination_condition": "module_return_none",
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")
        return

    selected = [
        i for i in range(len(profits)) if solver.best_solution_contains(i)
    ]
    payload = {
        "status": "optimal_or_best_found",
        "objective": float(objective),
        "selected_items": selected,
    }
    print(f"RESULT_JSON:{json.dumps(payload)}")


if __name__ == "__main__":
    solve_knapsack_module()
```

## Usage Recommendations

- Use this backend only when the problem maps directly to a supported algorithm module.
- Keep all input arrays index-aligned and integer-scaled.
- Validate return values explicitly because some modules expose limited status APIs.

## Parameter Hints

- `SolverType`: choose algorithm variant based on dimensionality and size.
- Input scaling: convert floating data to integers before solve.
- Pre-filtering: remove dominated candidates when possible.
- Runtime guard: wrap `solve(...)` in exception handling for robust pipelines.

## Status & Output Contract

When module APIs do not expose full status enums, validate module return semantics as the `solver status / termination condition` gate before output.

```python
if objective is None:
    print('RESULT_JSON:{"status":"failed","reason":"no_result"}')
else:
    print(f"RESULT:{float(objective)}")
```

