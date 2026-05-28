# Pyomo Backend: highs

## Type

Pyomo `SolverFactory("highs")` interface backend.

## Minimal Usage

```python
import json
import pyomo.environ as pyo
from pyomo.opt import SolverStatus, TerminationCondition


def build_knapsack_model():
    # Toy data
    items = [0, 1, 2, 3]
    profit = {0: 12, 1: 10, 2: 7, 3: 6}
    weight = {0: 5, 1: 4, 2: 3, 3: 2}
    capacity = 9

    # Model build
    m = pyo.ConcreteModel()
    m.I = pyo.Set(initialize=items)
    m.x = pyo.Var(m.I, domain=pyo.Binary)
    m.obj = pyo.Objective(expr=sum(profit[i] * m.x[i] for i in m.I), sense=pyo.maximize)
    m.cap = pyo.Constraint(expr=sum(weight[i] * m.x[i] for i in m.I) <= capacity)
    return m


def solve_with_highs():
    model = build_knapsack_model()

    # Solver create + key params
    solver = pyo.SolverFactory("highs")
    solver.options["time_limit"] = 30
    solver.options["mip_rel_gap"] = 0.0
    solver.options["threads"] = 4

    # Solve
    results = solver.solve(model, tee=False)
    status = results.solver.status
    term = results.solver.termination_condition

    # Status check + output contract
    if status == SolverStatus.ok and term in {TerminationCondition.optimal, TerminationCondition.feasible}:
        chosen = [int(i) for i in model.I if pyo.value(model.x[i]) > 0.5]
        payload = {
            "status": "optimal" if term == TerminationCondition.optimal else "feasible",
            "objective": float(pyo.value(model.obj)),
            "selected_items": chosen,
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")
    else:
        payload = {
            "status": "failed",
            "reason": "infeasible_or_error",
            "solver_status": str(status),
            "termination_condition": str(term),
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")


if __name__ == "__main__":
    solve_with_highs()
```

## Usage Recommendations

- Use as a strong open-source default for LP and MIP tasks.
- Keep variable domains and bounds explicit.
- Prefer sparse linear constraints and avoid unnecessary expression nesting.

## Parameter Hints

- `time_limit`: hard runtime cap in seconds.
- `mip_rel_gap`: relative MIP gap stopping threshold.
- `threads`: thread count for parallel search.
- `presolve`: enable or disable model presolve.

## Status & Output Contract

Always check `solver status / termination condition` before reading objective or variable values.

```python
if status == SolverStatus.ok and term in {TerminationCondition.optimal, TerminationCondition.feasible}:
    print(f"RESULT:{float(pyo.value(model.obj))}")
else:
    print(f"RESULT_JSON:{json.dumps({'status': 'failed', 'reason': 'infeasible_or_error', 'solver_status': str(status), 'termination_condition': str(term)})}")
```
