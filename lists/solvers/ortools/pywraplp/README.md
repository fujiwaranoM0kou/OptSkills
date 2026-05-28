# OR-Tools Backend: pywraplp

## Type

OR-Tools MPSolver bindings (`ortools.linear_solver.pywraplp`).

## Minimal Usage

```python
import json
from ortools.linear_solver import pywraplp


def solve_small_mip():
    # Solver create + key params
    solver = pywraplp.Solver.CreateSolver("SCIP")
    if solver is None:
        print('RESULT_JSON:{"status":"failed","reason":"backend_unavailable","solver_status":"CreateSolver(None)"}')
        return

    solver.SetTimeLimit(30000)
    solver.SetNumThreads(4)

    # Toy data + model build
    profit = [10, 6, 4, 7]
    weight = [4, 2, 1, 3]
    capacity = 5

    x = [solver.IntVar(0, 1, f"x_{i}") for i in range(len(profit))]
    solver.Add(sum(weight[i] * x[i] for i in range(len(weight))) <= capacity)

    objective = solver.Objective()
    for i in range(len(profit)):
        objective.SetCoefficient(x[i], profit[i])
    objective.SetMaximization()

    # Solve
    status = solver.Solve()

    # Status check + output contract
    if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        chosen = [i for i in range(len(profit)) if x[i].solution_value() > 0.5]
        payload = {
            "status": "optimal" if status == pywraplp.Solver.OPTIMAL else "feasible",
            "objective": float(objective.Value()),
            "chosen_items": chosen,
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")
    else:
        payload = {
            "status": "failed",
            "reason": "infeasible_or_error",
            "solver_status": int(status),
            "termination_condition": "mpsolver_status_code",
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")


if __name__ == "__main__":
    solve_small_mip()
```

## Usage Recommendations

- Choose backend string explicitly (`GLOP`, `CBC`, `SCIP`) and keep it aligned with LP vs MIP needs.
- Define tight variable bounds and domains to reduce degeneracy.
- Keep linear expressions simple and avoid accidental nonlinear constructs.

## Parameter Hints

- `CreateSolver("...")`: backend selection (`GLOP` for LP, `CBC/SCIP` for MIP).
- `SetTimeLimit(ms)`: hard runtime limit.
- `SetNumThreads(n)`: control thread count when backend supports it.
- `MPSolverParameters.RELATIVE_MIP_GAP`: stop condition for near-optimal MIP solutions.

## Status & Output Contract

Check `solver status / termination condition` before reading objective and variable values.

```python
if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
    print(f"RESULT:{objective.Value()}")
else:
    print('RESULT_JSON:{"status":"failed","reason":"infeasible_or_error","solver_status":%d}' % int(status))
```
