# Pyomo Backend: gurobi

## Type

Pyomo `SolverFactory("gurobi")` interface backend.

## Minimal Usage

```python
import json
import pyomo.environ as pyo
from pyomo.opt import SolverStatus, TerminationCondition


def build_transport_lp():
    # Toy data
    plants = ["A", "B"]
    markets = ["X", "Y", "Z"]
    supply = {"A": 7, "B": 8}
    demand = {"X": 3, "Y": 5, "Z": 7}
    cost = {
        ("A", "X"): 2, ("A", "Y"): 4, ("A", "Z"): 5,
        ("B", "X"): 3, ("B", "Y"): 1, ("B", "Z"): 2,
    }

    # Model build
    m = pyo.ConcreteModel()
    m.P = pyo.Set(initialize=plants)
    m.M = pyo.Set(initialize=markets)
    m.x = pyo.Var(m.P, m.M, domain=pyo.NonNegativeReals)

    m.obj = pyo.Objective(expr=sum(cost[p, q] * m.x[p, q] for p in m.P for q in m.M), sense=pyo.minimize)
    m.sup = pyo.Constraint(m.P, rule=lambda mm, p: sum(mm.x[p, q] for q in mm.M) <= supply[p])
    m.dem = pyo.Constraint(m.M, rule=lambda mm, q: sum(mm.x[p, q] for p in mm.P) >= demand[q])
    return m


def solve_with_gurobi():
    model = build_transport_lp()

    # Solver create + key params
    solver = pyo.SolverFactory("gurobi")
    solver.options["TimeLimit"] = 30
    solver.options["MIPGap"] = 0.0
    solver.options["Threads"] = 4
    solver.options["Seed"] = 42

    # Solve
    results = solver.solve(model, tee=False)
    status = results.solver.status
    term = results.solver.termination_condition

    # Status check + output contract
    if status == SolverStatus.ok and term in {TerminationCondition.optimal, TerminationCondition.feasible}:
        print(f"RESULT:{float(pyo.value(model.obj))}")
    else:
        payload = {
            "status": "failed",
            "reason": "infeasible_or_error",
            "solver_status": str(status),
            "termination_condition": str(term),
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")


if __name__ == "__main__":
    solve_with_gurobi()
```

## Usage Recommendations

- Use for medium/large LP-MIP workloads when license and runtime are configured.
- Set key parameters explicitly to ensure fair backend comparisons.
- Keep data scaling stable to avoid numerical warnings.

## Parameter Hints

- `TimeLimit`: wall-clock runtime limit.
- `MIPGap`: relative optimality gap threshold.
- `Threads`: thread count for parallel search.
- `Seed`: deterministic random seed for reproducibility.

## Status & Output Contract

Always check `solver status / termination condition` before reading objective or variable values.

```python
if status == SolverStatus.ok and term in {TerminationCondition.optimal, TerminationCondition.feasible}:
    print(f"RESULT:{float(pyo.value(model.obj))}")
else:
    print(f"RESULT_JSON:{json.dumps({'status': 'failed', 'reason': 'infeasible_or_error', 'solver_status': str(status), 'termination_condition': str(term)})}")
```
