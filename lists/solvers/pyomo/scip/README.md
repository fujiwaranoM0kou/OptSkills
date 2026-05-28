# Pyomo Backend: scip

## Type

Pyomo `SolverFactory("scip")` interface backend.

## Minimal Usage

```python
import json
import pyomo.environ as pyo
from pyomo.opt import SolverStatus, TerminationCondition


def build_facility_mip():
    # Toy data
    facilities = [0, 1, 2]
    demand = 8
    open_cost = {0: 7, 1: 6, 2: 8}
    capacity = {0: 4, 1: 5, 2: 6}

    # Model build
    m = pyo.ConcreteModel()
    m.F = pyo.Set(initialize=facilities)
    m.y = pyo.Var(m.F, domain=pyo.Binary)
    m.ship = pyo.Var(m.F, domain=pyo.NonNegativeReals)

    m.obj = pyo.Objective(expr=sum(open_cost[f] * m.y[f] + m.ship[f] for f in m.F), sense=pyo.minimize)
    m.cap = pyo.Constraint(m.F, rule=lambda mm, f: mm.ship[f] <= capacity[f] * mm.y[f])
    m.dem = pyo.Constraint(expr=sum(m.ship[f] for f in m.F) >= demand)
    return m


def solve_with_scip():
    model = build_facility_mip()

    # Solver create + key params
    solver = pyo.SolverFactory("scip")
    solver.options["limits/time"] = 30
    solver.options["limits/gap"] = 0.0
    solver.options["parallel/maxnthreads"] = 4

    # Solve
    results = solver.solve(model, tee=False)
    status = results.solver.status
    term = results.solver.termination_condition

    # Status check + output contract
    if status == SolverStatus.ok and term in {TerminationCondition.optimal, TerminationCondition.feasible}:
        open_facilities = [int(f) for f in model.F if pyo.value(model.y[f]) > 0.5]
        payload = {
            "status": "optimal" if term == TerminationCondition.optimal else "feasible",
            "objective": float(pyo.value(model.obj)),
            "open_facilities": open_facilities,
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
    solve_with_scip()
```

## Usage Recommendations

- Use for challenging MIP workloads when SCIP is available.
- Strengthen model bounds and eliminate redundant variables.
- Use explicit runtime and gap limits for reproducible comparisons.

## Parameter Hints

- `limits/time`: total solve time limit.
- `limits/gap`: relative gap threshold.
- `parallel/maxnthreads`: thread parallelism cap.
- `presolving/maxrounds`: presolve effort control.

## Status & Output Contract

Always check `solver status / termination condition` before reading objective or variable values.

```python
if status == SolverStatus.ok and term in {TerminationCondition.optimal, TerminationCondition.feasible}:
    print(f"RESULT:{float(pyo.value(model.obj))}")
else:
    print(f"RESULT_JSON:{json.dumps({'status': 'failed', 'reason': 'infeasible_or_error', 'solver_status': str(status), 'termination_condition': str(term)})}")
```
