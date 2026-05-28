# Pyomo Backend: glpk

## Type

Pyomo `SolverFactory("glpk")` interface backend.

## Minimal Usage

```python
import json
import pyomo.environ as pyo
from pyomo.opt import SolverStatus, TerminationCondition


def build_small_mip():
    # Toy data
    plants = ["A", "B", "C"]
    fixed_cost = {"A": 7, "B": 5, "C": 6}
    capacity = {"A": 5, "B": 4, "C": 6}
    demand = 9

    # Model build
    m = pyo.ConcreteModel()
    m.P = pyo.Set(initialize=plants)
    m.open = pyo.Var(m.P, domain=pyo.Binary)
    m.ship = pyo.Var(m.P, domain=pyo.NonNegativeReals)

    m.obj = pyo.Objective(
        expr=sum(fixed_cost[p] * m.open[p] + m.ship[p] for p in m.P),
        sense=pyo.minimize,
    )
    m.capacity = pyo.Constraint(m.P, rule=lambda mm, p: mm.ship[p] <= capacity[p] * mm.open[p])
    m.demand = pyo.Constraint(expr=sum(m.ship[p] for p in m.P) >= demand)
    return m


def solve_with_glpk():
    model = build_small_mip()

    # Solver create + key params
    solver = pyo.SolverFactory("glpk")
    solver.options["tmlim"] = 30
    solver.options["mipgap"] = 0.0
    solver.options["cuts"] = ""

    # Solve
    results = solver.solve(model, tee=False)
    status = results.solver.status
    term = results.solver.termination_condition

    # Status check + output contract
    if status == SolverStatus.ok and term in {TerminationCondition.optimal, TerminationCondition.feasible}:
        payload = {
            "status": "optimal" if term == TerminationCondition.optimal else "feasible",
            "objective": float(pyo.value(model.obj)),
            "open_plants": [p for p in model.P if pyo.value(model.open[p]) > 0.5],
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
    solve_with_glpk()
```

## Usage Recommendations

- Use as an open-source LP/MIP baseline backend.
- Keep formulations compact and coefficient scales reasonable.
- Avoid weak big-M values that degrade branch-and-bound.

## Parameter Hints

- `tmlim`: runtime limit in seconds.
- `mipgap`: relative MIP gap stopping threshold.
- `presolve`: presolve activation flag.
- `cuts`: cut generation controls for MIP solve.

## Status & Output Contract

Always check `solver status / termination condition` before reading objective or variable values.

```python
if status == SolverStatus.ok and term in {TerminationCondition.optimal, TerminationCondition.feasible}:
    print(f"RESULT:{float(pyo.value(model.obj))}")
else:
    print(f"RESULT_JSON:{json.dumps({'status': 'failed', 'reason': 'infeasible_or_error', 'solver_status': str(status), 'termination_condition': str(term)})}")
```
