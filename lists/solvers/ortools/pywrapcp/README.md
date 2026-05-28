# OR-Tools Backend: pywrapcp

## Type

OR-Tools Constraint Solver and Routing bindings (`ortools.constraint_solver.pywrapcp`).

## Minimal Usage

```python
import json
import math
from ortools.constraint_solver import pywrapcp, routing_enums_pb2


def build_euclidean_distance_matrix(coords):
    n = len(coords)
    matrix = [[0 for _ in range(n)] for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            dx = coords[i][0] - coords[j][0]
            dy = coords[i][1] - coords[j][1]
            matrix[i][j] = int(round(math.sqrt(dx * dx + dy * dy)))
    return matrix


def solve_tsp_routing(coords, time_limit_seconds=20):
    # Toy data -> routing input
    distance_matrix = build_euclidean_distance_matrix(coords)
    n = len(distance_matrix)

    # Model build
    manager = pywrapcp.RoutingIndexManager(n, 1, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return distance_matrix[from_node][to_node]

    transit_id = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_id)

    # Solver create + key params
    search_params = pywrapcp.DefaultRoutingSearchParameters()
    search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_params.time_limit.seconds = time_limit_seconds
    search_params.solution_limit = 1

    # Solve
    solution = routing.SolveWithParameters(search_params)

    # Status check + output contract
    if solution is None:
        payload = {
            "status": "failed",
            "reason": "no_solution",
            "solver_status": int(routing.status()),
            "termination_condition": "routing_no_solution",
        }
        print(f"RESULT_JSON:{json.dumps(payload)}")
        return

    route = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        route.append(manager.IndexToNode(index))
        index = solution.Value(routing.NextVar(index))
    route.append(manager.IndexToNode(index))

    payload = {
        "status": "feasible_or_optimal",
        "objective": float(solution.ObjectiveValue()),
        "route": route,
        "wall_time_seconds": routing.solver().WallTime() / 1000.0,
        "solver_status": int(routing.status()),
    }
    print(f"RESULT_JSON:{json.dumps(payload)}")


if __name__ == "__main__":
    coordinates = [
        (0, 0),
        (2, 4),
        (5, 1),
        (8, 3),
        (6, 7),
        (3, 6),
        (1, 8),
    ]
    solve_tsp_routing(coordinates, time_limit_seconds=20)
```

## Usage Recommendations

- Prefer this backend for routing-style problems (TSP/VRP family).
- Keep manager indices and original node ids clearly separated.
- Add dimensions (time/capacity) incrementally and validate each addition.
- Use deterministic runtime controls when comparing against other backends.

## Parameter Hints

- `first_solution_strategy`: initial route construction policy.
- `local_search_metaheuristic`: route improvement strategy.
- `time_limit.seconds`: hard wall-clock budget.
- `solution_limit`: limit accepted solutions for fast return.

## Status & Output Contract

Check `solver status / termination condition` through `solution is None` and backend status code before reading objective/route values.

```python
if solution is None:
    print('RESULT_JSON:{"status":"failed","reason":"no_solution","solver_status":0}')
else:
    print(f"RESULT:{float(solution.ObjectiveValue())}")
```

Never print placeholder numeric objectives when no route exists.
