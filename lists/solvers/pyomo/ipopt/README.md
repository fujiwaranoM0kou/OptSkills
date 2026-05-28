# Pyomo Backend: ipopt

## Type

Pyomo `SolverFactory("ipopt")` interface backend.

## Minimal Usage

```python
import json
import pyomo.environ as pyo
from pyomo.opt import SolverStatus, TerminationCondition


def build_nlp_model():
    # Toy data
    target_x = 2.0
    target_y = 1.5

    # Model build
    m = pyo.ConcreteModel()
    m.x = pyo.Var(bounds=(0.0, 4.0), initialize=0.5)
    m.y = pyo.Var(bounds=(0.0, 4.0), initialize=0.5)

    # Smooth nonlinear objective
    m.obj = pyo.Objective(expr=(m.x - target_x) ** 2 + (m.y - target_y) ** 2, sense=pyo.minimize)

    # Smooth nonlinear constraints
    m.c1 = pyo.Constraint(expr=m.x ** 2 + 0.5 * m.y <= 3.5)
    m.c2 = pyo.Constraint(expr=m.x + m.y >= 1.2)
    return m


def solve_with_ipopt():
    model = build_nlp_model()

    # Solver create + key params
    solver = pyo.SolverFactory("ipopt")
    solver.options["tol"] = 1e-7
    solver.options["max_iter"] = 500
    solver.options["acceptable_tol"] = 1e-5
    solver.options["print_level"] = 0

    # Solve
    results = solver.solve(model, tee=False)
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
            "status": "optimal_or_local",
            "objective": float(pyo.value(model.obj)),
            "x": float(pyo.value(model.x)),
            "y": float(pyo.value(model.y)),
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")
    else:
        payload = {
            "status": "failed",
            "reason": "nlp_not_converged",
            "solver_status": str(status),
            "termination_condition": str(term),
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")


if __name__ == "__main__":
    solve_with_ipopt()
```

## Usage Recommendations

- Use for smooth continuous NLP formulations.
- Provide meaningful variable initialization for stable convergence.
- Keep nonlinear constraints differentiable and well-scaled.

## Parameter Hints

- `tol`: KKT convergence tolerance.
- `max_iter`: maximum NLP iterations.
- `acceptable_tol`: practical early-stop tolerance.
- `print_level`: solver logging verbosity.

## Status & Output Contract

Always check `solver status / termination condition` before reading objective or variable values.

```python
ok_terms = {TerminationCondition.optimal, TerminationCondition.locallyOptimal, TerminationCondition.feasible}
if status == SolverStatus.ok and term in ok_terms:
    print(f"RESULT:{float(pyo.value(model.obj))}")
else:
    print(f"RESULT_JSON:{json.dumps({'status': 'failed', 'reason': 'nlp_not_converged', 'solver_status': str(status), 'termination_condition': str(term)})}")
```
