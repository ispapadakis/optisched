# Description: This file contains the optimization model for the scheduling problem.

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import sys

from src.outputs import store_result, print_solution
from src.inputs import primary_node, get_node_to_label

SOLUTION_STATUS = [
    "Not Solved",
    "Success",
    "Local Optimum Not Reached",
    "Fail",
    "Fail Timeout",
    "Invalid",
    "Infeasible"
    ]

def optmodel(data, params, start_from_initial_solution=True, save_solution=False):
    """Based on ORTools Vehicles Routing Problem (VRP) with Time Windows.
    Implements:
        - Client Priority
        - Time Windows
        - Day Breaks
        - Forces Appointments on Day and Time
        - Permits Missing Appointment with Penalty
       
    Args:
        data (dict): Dictionary with keys: "time_matrix", "time_windows", "days", "node_label"
        params (dict): Dictionary
        start_from_initial_solution (bool): Read initial solution from file. Defaults to True.
        save_solution (bool): save optimal solution as future initial solution. Defualts to False.
       
    Returns:
        tuple: Tuple of DataFrames with keys: "routes", "dropped"
    """

    # Node Order : Starts, Active Clients, Client with Appointments (Repeated)
    n_starts, n_clients, n_appts = tuple(len(lst) for lst in data["ndlabel"])
   
    ### Node Correspondence
    # Node to Primary Node: includes map of Appointments to Clients
    primary = primary_node(data)
    # Node to Label
    nodeTolabel = get_node_to_label(data)
   
    # Create the routing index manager.
    manager = pywrapcp.RoutingIndexManager(
        n_starts + n_clients + n_appts, len(data["days"]), 0
    ) # The last argument is the base node index

    # Create Routing Model.
    routing = pywrapcp.RoutingModel(manager)

    # Create and register a transit callback.
    # [START transit_callback]
    def time_callback(from_index, to_index):
        """Returns the travel time + service time between the two nodes."""
        # Convert from routing variable Index to time matrix NodeIndex.
        from_node = primary[manager.IndexToNode(from_index)]
        to_node   = primary[manager.IndexToNode(to_index)]
        travel_time = data['time_matrix'][from_node][to_node]
        service_time = data["nodes"]['service_time'].iloc[from_node]
        return int(travel_time + service_time)

    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    # [END transit_callback]

    # Define cost of each arc.
    # [START arc_cost]
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
    # [END arc_cost]

    # Add Time Windows constraint.
    time = "Time"
    routing.AddDimension(
        transit_callback_index,
        params["allow_waiting_time"],      # allow waiting time
        params["max_time_units_per_day"],  # maximum time per day [this limit is tightened by day limit later]
        False,  # Don't force start cumul to zero.
        time,
    )
    time_dimension = routing.GetDimensionOrDie(time)
    time_dimension.SetGlobalSpanCostCoefficient(params["global_span_cost"])
   
    # Add time window constraints for existing appointments.
    node = n_starts + n_clients
    for lbl in data["ndlabel"][2]:
        twin = data["time_windows"][lbl]
        index = manager.NodeToIndex(node)
        time_dimension.CumulVar(index).SetRange(twin.start, twin.end)
        node += 1
    # Add time window constraints for each day start node.
    for d in data["days"].index:
        index = routing.Start(d)
        time_dimension.CumulVar(index).SetRange(
            int(data["days"].loc[d,"start_time_min"]), int(data["days"].loc[d,"start_time_max"])
        )

    # Add route-end time constraints.
    for d, day_lim in data["days"]["time_end_max"].items():
        routing.solver().Add(time_dimension.CumulVar(routing.End(d)) <= day_lim)

    # Breaks
    # [START break_constraint]
    # warning: Need a pre-travel array using the solver's index order.
    node_visit_transit = [0 for _ in range(routing.Size())]
    for index in range(routing.Size()):
        node = manager.IndexToNode(index)
        lbl = nodeTolabel[node]
        node_visit_transit[index] = int(data["nodes"]['service_time'].loc[lbl])

    break_intervals = {}
    for d in data["days"].index:
        start_min = int(data["days"].loc[d,"break_time_min"])
        start_max = int(data["days"].loc[d,"break_time_max"])
        duration = int(data["days"].loc[d,"duration"])
        break_intervals[d] = [
            routing.solver().FixedDurationIntervalVar(
                start_min,  # start min
                start_max,  # start max
                duration,  # duration
                False,  # optional: no
                f'Break for day {d}')
        ]
        time_dimension.SetBreakIntervalsOfVehicle(
            break_intervals[d],  # breaks
            d,  # day index
            node_visit_transit
            )
    # [END break_constraint]

    # Clien Priority
    node = 0
    # Starts
    for lbl in data["ndlabel"][0]:
        priority = int(data["nodes"].loc[lbl, "priority"])
        node_id = manager.NodeToIndex(node)
        routing.AddDisjunction([node_id], priority)
        node += 1
    # Primary
    for lbl in data["ndlabel"][1]:
        priority = int(data["nodes"].loc[lbl, "priority"])
        node_id = manager.NodeToIndex(node)
        routing.AddDisjunction([node_id], priority)
        node += 1
    # Appointments
    for lbl in data["ndlabel"][2]:
        priority = int(data["nodes"].loc[lbl, "priority"])
        node_id = manager.NodeToIndex(node)
        pid = manager.NodeToIndex(primary[node])
        twin = data["time_windows"][lbl]
        routing.SetAllowedVehiclesForIndex([twin.day], node_id)
        routing.AddDisjunction([node_id, pid], 2*priority, 1) # 2*priority to force max_cardinality = 1
        routing.AddDisjunction([node_id], priority + params["miss_appointment_penalty"])
        node += 1

    # Instantiate route start and end times to produce feasible times.
    for d in data["days"].index:
        routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.Start(d)))
        routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.End(d)))

    # Check if Initial Solution is Available
    initial_solution = None
    if start_from_initial_solution:
        try:
            stored_initial_solution = read_initial_solution()
            initial_solution = routing.ReadAssignmentFromRoutes(stored_initial_solution, True)
            print("Initial Solution:")
            routes, dropped, miss_appt, info = store_result(data, manager, routing, initial_solution, params)
            print_solution(initial_solution, data, routes, dropped, miss_appt, info)
            print("\nEnd Initial Solution\n")
        except FileNotFoundError:
            print("No Initial Solution")

    # Setting first solution heuristic.
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
    search_parameters.time_limit.FromSeconds(params["run_time_limit"])

    # Solve the problem.
    if initial_solution:
        solution = routing.SolveFromAssignmentWithParameters(initial_solution, search_parameters)
    else:
        solution = routing.SolveWithParameters(search_parameters)

    # Print solution on console.
    if solution:
        print("Optimization Finished: ",SOLUTION_STATUS[routing.status()])
        # Save Current Solution: Could Work as Initial Solution of Next Run
        if save_solution:
            save_solution_list(solution_list(solution, manager, routing))
        routes, dropped, miss_appt, info = store_result(data, manager, routing, solution, params)
        print_solution(solution, data, routes, dropped, miss_appt, info)
        return routes, dropped
    else:
        sys.exit("*\n*\n*   No solution found !\n*\n*")

def solution_list(solution, manager, routing):
    routes = []
    for route_number in range(routing.vehicles()):
        index = routing.Start(route_number)
        route = []
        while not routing.IsEnd(index):
            node_index = manager.IndexToNode(index)
            route.append(node_index)
            index = solution.Value(routing.NextVar(index))
        routes.append(route[1:])
    return routes

def save_solution_list(soln_list, filename="./initial_solution.txt"):
    with open(filename, 'w') as f:
        for route in soln_list:
            print(" ".join([str(i) for i in route]), file=f)

def read_initial_solution(filename="./initial_solution.txt"):
    routes = []
    with open(filename, 'r') as f:
        for ln in f.readlines():
            routes.append([int(i) for i in ln.split(" ")])
    return routes

