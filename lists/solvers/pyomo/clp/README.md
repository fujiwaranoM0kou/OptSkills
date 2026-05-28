# Pyomo Backend: clp

## Type

Pyomo `SolverFactory("clp")` interface backend.

## Minimal Usage

```python
import json
import pyomo.environ as pyo
from pyomo.opt import SolverStatus, TerminationCondition


def build_lp_model():
    # Toy data
    products = ["p1", "p2"]
    profit = {"p1": 5, "p2": 4}
    labor = {"p1": 3, "p2": 2}
    material = {"p1": 2, "p2": 4}
    labor_cap = 18
    material_cap = 16

    # Model build
    m = pyo.ConcreteModel()
    m.P = pyo.Set(initialize=products)
    m.x = pyo.Var(m.P, domain=pyo.NonNegativeReals)

    m.obj = pyo.Objective(expr=sum(profit[p] * m.x[p] for p in m.P), sense=pyo.maximize)
    m.labor = pyo.Constraint(expr=sum(labor[p] * m.x[p] for p in m.P) <= labor_cap)
    m.material = pyo.Constraint(expr=sum(material[p] * m.x[p] for p in m.P) <= material_cap)
    return m


def solve_with_clp():
    model = build_lp_model()

    # Solver create + key params
    solver = pyo.SolverFactory("clp")
    solver.options["sec"] = 30
    solver.options["primalTolerance"] = 1e-7
    solver.options["dualTolerance"] = 1e-7

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
            "reason": "lp_not_solved",
            "solver_status": str(status),
            "termination_condition": str(term),
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")


if __name__ == "__main__":
    solve_with_clp()
```

## Usage Recommendations

- Use for continuous LP models.
- Switch to integer-capable backend if integrality is required.
- Keep constraints strictly linear and well-scaled.

## Parameter Hints

- `sec`: wall-clock time limit.
- `presolve`: enable or disable presolve reductions.
- `primalTolerance`: primal feasibility tolerance.
- `dualTolerance`: dual feasibility tolerance.

## Status & Output Contract

Always check `solver status / termination condition` before reading objective or variable values.

```python
if status == SolverStatus.ok and term in {TerminationCondition.optimal, TerminationCondition.feasible}:
    print(f"RESULT:{float(pyo.value(model.obj))}")
else:
    print(f"RESULT_JSON:{json.dumps({'status': 'failed', 'reason': 'lp_not_solved', 'solver_status': str(status), 'termination_condition': str(term)})}")
```
