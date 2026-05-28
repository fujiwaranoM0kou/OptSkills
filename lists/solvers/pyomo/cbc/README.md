# Pyomo Backend: cbc

## Type

Pyomo `SolverFactory("cbc")` interface backend.

## Minimal Usage

```python
import json
import pyomo.environ as pyo
from pyomo.opt import SolverStatus, TerminationCondition


def build_assignment_mip():
    # Toy data
    workers = [0, 1, 2]
    jobs = [0, 1, 2]
    cost = {
        (0, 0): 8, (0, 1): 6, (0, 2): 7,
        (1, 0): 5, (1, 1): 7, (1, 2): 6,
        (2, 0): 9, (2, 1): 8, (2, 2): 5,
    }

    # Model build
    m = pyo.ConcreteModel()
    m.W = pyo.Set(initialize=workers)
    m.J = pyo.Set(initialize=jobs)
    m.x = pyo.Var(m.W, m.J, domain=pyo.Binary)

    m.obj = pyo.Objective(expr=sum(cost[w, j] * m.x[w, j] for w in m.W for j in m.J), sense=pyo.minimize)
    m.assign_job = pyo.Constraint(m.J, rule=lambda mm, j: sum(mm.x[w, j] for w in mm.W) == 1)
    m.assign_worker = pyo.Constraint(m.W, rule=lambda mm, w: sum(mm.x[w, j] for j in mm.J) <= 1)
    return m


def solve_with_cbc():
    model = build_assignment_mip()

    # Solver create + key params
    solver = pyo.SolverFactory("cbc")
    solver.options["seconds"] = 30
    solver.options["ratio"] = 0.0
    solver.options["threads"] = 4

    # Solve
    results = solver.solve(model, tee=False)
    status = results.solver.status
    term = results.solver.termination_condition

    # Status check + output contract
    if status == SolverStatus.ok and term in {TerminationCondition.optimal, TerminationCondition.feasible}:
        assignment = []
        for w in model.W:
            for j in model.J:
                if pyo.value(model.x[w, j]) > 0.5:
                    assignment.append({"worker": int(w), "job": int(j)})
        payload = {
            "status": "optimal" if term == TerminationCondition.optimal else "feasible",
            "objective": float(pyo.value(model.obj)),
            "assignment": assignment,
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
    solve_with_cbc()
```

## Usage Recommendations

- Use for MILP tasks in open-source settings.
- Tighten formulations with explicit bounds and sparse constraints.
- Keep coefficient magnitudes in a similar numeric range.

## Parameter Hints

- `seconds`: wall-clock time limit.
- `ratio`: relative MIP gap target.
- `threads`: parallel thread count.
- `logLevel`: logging verbosity.

## Status & Output Contract

Always check `solver status / termination condition` before reading objective or variable values.

```python
if status == SolverStatus.ok and term in {TerminationCondition.optimal, TerminationCondition.feasible}:
    print(f"RESULT:{float(pyo.value(model.obj))}")
else:
    print(f"RESULT_JSON:{json.dumps({'status': 'failed', 'reason': 'infeasible_or_error', 'solver_status': str(status), 'termination_condition': str(term)})}")
```
