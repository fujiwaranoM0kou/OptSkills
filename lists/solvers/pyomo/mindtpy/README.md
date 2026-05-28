# Pyomo Backend: mindtpy

## Type

Pyomo `SolverFactory("mindtpy")` decomposition backend.

## Minimal Usage

```python
import json
import pyomo.environ as pyo
from pyomo.opt import SolverStatus, TerminationCondition


def build_convex_minlp():
    # Toy data
    m = pyo.ConcreteModel()
    m.x = pyo.Var(bounds=(0.0, 6.0), initialize=1.0)
    m.y = pyo.Var(domain=pyo.Binary)

    # Convex MINLP-style objective
    m.obj = pyo.Objective(expr=(m.x - 4.0) ** 2 + 3.0 * m.y, sense=pyo.minimize)

    # Linking constraints
    m.c1 = pyo.Constraint(expr=m.x >= 1.0 + m.y)
    m.c2 = pyo.Constraint(expr=m.x <= 5.0)
    return m


def solve_with_mindtpy():
    model = build_convex_minlp()

    # Solver create + key params
    solver = pyo.SolverFactory("mindtpy")

    # Solve with explicit subsolvers
    results = solver.solve(
        model,
        strategy="OA",
        mip_solver="cbc",
        nlp_solver="ipopt",
        time_limit=120,
        tee=False,
    )
    status = results.solver.status
    term = results.solver.termination_condition

    # Status check + output contract
    ok_terms = {
        TerminationCondition.optimal,
        TerminationCondition.locallyOptimal,
        TerminationCondition.feasible,
    }
    if status == SolverStatus.ok and term in ok_terms:
        payload = {
            "status": "optimal_or_feasible",
            "objective": float(pyo.value(model.obj)),
            "x": float(pyo.value(model.x)),
            "y": int(round(pyo.value(model.y))),
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")
    else:
        payload = {
            "status": "failed",
            "reason": "decomposition_failed",
            "solver_status": str(status),
            "termination_condition": str(term),
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")


if __name__ == "__main__":
    solve_with_mindtpy()
```

## Usage Recommendations

- Use for MINLP decomposition workflows requiring explicit MIP and NLP subsolvers.
- Verify subsolver availability before launching experiments.
- Keep MINLP model well-bounded to improve OA or ECP iteration quality.

## Parameter Hints

- `strategy`: decomposition strategy (`OA`, `ECP`, `GOA`).
- `mip_solver`: MILP subsolver selection.
- `nlp_solver`: NLP subsolver selection.
- `time_limit`: total decomposition runtime cap.

## Status & Output Contract

Always check `solver status / termination condition` before reading objective or variable values.

```python
ok_terms = {TerminationCondition.optimal, TerminationCondition.locallyOptimal, TerminationCondition.feasible}
if status == SolverStatus.ok and term in ok_terms:
    print(f"RESULT:{float(pyo.value(model.obj))}")
else:
    print(f"RESULT_JSON:{json.dumps({'status': 'failed', 'reason': 'decomposition_failed', 'solver_status': str(status), 'termination_condition': str(term)})}")
```
