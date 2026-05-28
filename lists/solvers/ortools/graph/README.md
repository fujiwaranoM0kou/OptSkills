# OR-Tools Backend: graph

## Type

OR-Tools graph optimization APIs (`ortools.graph.python`).

## Minimal Usage

```python
import json
from ortools.graph.python import min_cost_flow


def solve_transport_with_min_cost_flow():
    # Toy data
    start_nodes = [0, 0, 1, 1, 2, 2]
    end_nodes = [3, 4, 3, 4, 3, 4]
    capacities = [5, 4, 3, 6, 4, 5]
    unit_costs = [2, 4, 5, 1, 3, 2]
    supplies = [5, 4, 5, -6, -8]  # nodes 0..4

    # Model build
    smcf = min_cost_flow.SimpleMinCostFlow()
    for i in range(len(start_nodes)):
        smcf.add_arc_with_capacity_and_unit_cost(
            start_nodes[i], end_nodes[i], capacities[i], unit_costs[i]
        )
    for node, supply in enumerate(supplies):
        smcf.set_node_supply(node, supply)

    # Solve
    status = smcf.solve()

    # Status check + output contract
    if status == smcf.OPTIMAL:
        arcs = []
        for i in range(smcf.num_arcs()):
            flow = smcf.flow(i)
            if flow > 0:
                arcs.append({
                    "from": smcf.tail(i),
                    "to": smcf.head(i),
                    "flow": int(flow),
                    "unit_cost": int(smcf.unit_cost(i)),
                })
        payload = {
            "status": "optimal",
            "objective": float(smcf.optimal_cost()),
            "used_arcs": arcs,
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")
    else:
        payload = {
            "status": "failed",
            "reason": "graph_solve_failed",
            "solver_status": int(status),
            "termination_condition": "min_cost_flow_status_code",
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")


if __name__ == "__main__":
    solve_transport_with_min_cost_flow()
```

## Usage Recommendations

- Use this backend when the model is truly network-flow based.
- Keep node IDs and arc definitions deterministic and documented.
- Prefer integer scaling for capacities and costs.

## Parameter Hints

- API choice: `SimpleMaxFlow` for pure max-flow, `SimpleMinCostFlow` for costed flow.
- Arc preprocessing: remove dominated or zero-capacity arcs to simplify solve.
- Supply balance: ensure total supply equals total demand.
- Integer scaling: normalize units to avoid overflow-like behavior.

## Status & Output Contract

Check `solver status / termination condition` first via backend status enum.

```python
if status == smcf.OPTIMAL:
    print(f"RESULT:{smcf.optimal_cost()}")
else:
    print('RESULT_JSON:{"status":"failed","reason":"graph_solve_failed","solver_status":%d}' % int(status))
```
