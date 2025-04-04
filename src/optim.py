""" Optimize Weekly Schedule of Traveling Salesperson
    using ORTools
    Trade off Addressing Needs of Clients with Highest Priority vs Minimizing Travel Time
    with:
        - Day Preferences: Start/End Time and Breaks
        - Soft Constraint on Prior Appointments
        - Ability to Begin with Initial Solution
"""

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import sys

SOLUTION_STATUS = [
    "Not Solved",
    "Success",
    "Local Optimum Not Reached",
    "Fail",
    "Fail Timeout",
    "Invalid",
    "Infeasible"
    ]

TIME_DIM_NAME = "Time"

def optmodel(
        n_starts, 
        n_clients, 
        n_appts,
        primary,
        priority,
        service_time,
        time_windows,
        time_matrix,
        break_data,
        day_lims,
        allow_waiting_time=4,
        max_time_units_per_day=52,
        global_span_cost=1,
        miss_appointment_penalty=1,
        run_time_limit=2,
        labels = None,
        start_from_initial_solution=True, 
        save_solution=False, 
        verbose=True,
        **kwargs
        ):
    """Based on ORTools Vehicles Routing Problem (VRP) with Time Windows.
    Implements:
        - Client Priority
        - Time Windows
        - Day Breaks
        - Forces Appointments on Day and Time
        - Permits Missing Appointment with Penalty
        - Accepts Initial Solution
       
    Args:
        n_starts (int): Number of Start Locations (Base, Hotels)
        n_clients (int): Number of Client Locations
        n_appts (int): Number of Clients with Appointments (Subset of All Client Locations)
        primary (list): List of node indices in order of optimization
        priority (list): List of client priorities
        service_time (list): List of service times for each node
        time_windows (list): List of time windows for each node
        time_matrix (list): List of travel times between nodes
        break_data (list): List of breaks for each node
        day_lims (list): List of day limits for each node
        labels (list, optional): List of node labels. Defaults to None.
        allow_waiting_time (int, optional): See Routing Manual. Defaults to 4.
        max_time_units_per_day (int, optional): See Routing Manual. Defaults to 52.
        global_span_cost (int, optional): See Routing Manual. Defaults to 1.
        miss_appointment_penalty (int, optional): See Routing Manual. Defaults to 1.
        run_time_limit (int, optional): See Routing Manual. Defaults to 2.
        start_from_initial_solution (bool, optional): Read initial solution from file. Defaults to True.
        save_solution (bool, optional): save optimal solution as future initial solution. Defaults to False.
        verbose (bool, optional): show raw results. Defaults to True.
       
    Returns:
        seqs (list): List of routes
        tstarts (list): List of start times for each route
        brks (list): List of breaks for each route
    """

    if labels is None:
        labels = get_default_labels(n_starts, n_clients, n_appts)

    # Infer Number of Days: day_lims is not optional
    n_days = len(day_lims)
   
    # Create the routing index manager.
    manager = pywrapcp.RoutingIndexManager(
        n_starts + n_clients + n_appts, n_days, 0
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
        travel_time = time_matrix[from_node][to_node]
        return int(service_time[from_node] + travel_time) # Service From Node Then Travel

    transit_callback_index = routing.RegisterTransitCallback(time_callback)
    # [END transit_callback]

    # Define cost of each arc.
    # [START arc_cost]
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
    # [END arc_cost]

    #[START time window constraints]
    # Used for Appointments, Day Limits and Breaks

    # Add Time Dimension.
    routing.AddDimension(
        transit_callback_index,
        allow_waiting_time,      # allow waiting time
        max_time_units_per_day,  # maximum time per day [this limit is tightened by day limit later]
        False,  # Don't force start cumul to zero.
        TIME_DIM_NAME,
    )
    time_dimension = routing.GetDimensionOrDie(TIME_DIM_NAME)
    time_dimension.SetGlobalSpanCostCoefficient(global_span_cost)
   
    # Add time window constraints for existing appointments.
    node = n_starts + n_clients
    for twin in time_windows:
        index = manager.NodeToIndex(node)
        time_dimension.CumulVar(index).SetRange(twin.start, twin.end)
        node += 1

    # Add time window constraints for each day.
    for d, dlim in enumerate(day_lims):
        # Day Start Limits
        time_dimension.CumulVar(routing.Start(d)).SetRange(dlim.start_time_min, dlim.start_time_max)
        # Day End Limits
        routing.solver().Add(time_dimension.CumulVar(routing.End(d)) <= dlim.time_end_max)

    # Add time window constraints for day breaks.
    # warning: Need a pre-travel array using the solver's index order.
    # use: service_time data.
    node_visit_transit = [
        service_time[primary[manager.IndexToNode(index)]]
        for index in range(routing.Size())
        ]
    # Create break intervals
    for d, bdat in enumerate(break_data):
        # Breaks are defined as [start_min, start_max, duration, break_option, label]
        time_dimension.SetBreakIntervalsOfVehicle(
            [routing.solver().FixedDurationIntervalVar(*bdat)],  # breaks
            d,  # day index
            node_visit_transit
            )
    # [END time window constraints]

    # Clien Priority
    node = 0
    # Starts and Active Clients
    for _ in range(n_starts+ n_clients):
        node_id = manager.NodeToIndex(node)
        routing.AddDisjunction([node_id], priority[node])
        node += 1
    # Appointments
    for a, twin in enumerate(time_windows):
        node_id = manager.NodeToIndex(node)
        pid = manager.NodeToIndex(twin.node) # Index of corresponding active client
        routing.SetAllowedVehiclesForIndex([twin.day], node_id)
        routing.AddDisjunction([node_id, pid], 2*priority[twin.node], 1) # 2*priority to force max_cardinality = 1
        routing.AddDisjunction([node_id], priority[twin.node] + miss_appointment_penalty)
        node += 1

    # Instantiate route start and end times to produce feasible times.
    for d in range(n_days):
        routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.Start(d)))
        routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.End(d)))

    # Setting first solution heuristic.
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.TABU_SEARCH # Only option deviating from local minima
        )
    search_parameters.time_limit.FromSeconds(run_time_limit)
    # When an initial solution is given for search, the model will be closed with
    # the default search parameters unless it is explicitly closed with the custom
    # search parameters.
    routing.CloseModelWithParameters(search_parameters)

    # Check if Initial Solution is Available
    initial_solution = None
    if start_from_initial_solution:
        try:
            stored_initial_seqs = read_initial_solution()
            initial_solution = routing.ReadAssignmentFromRoutes(stored_initial_seqs, True)
        except FileNotFoundError:
            print("No Initial Solution")

    # Solve the problem.
    if initial_solution:
        if verbose:
            print("Initial Solution:")
            print_sched_sequence(labels, n_starts + n_clients, stored_initial_seqs)
            print("\nEnd Initial Solution\n")
        solution = routing.SolveFromAssignmentWithParameters(initial_solution, search_parameters)
    else:
        solution = routing.SolveWithParameters(search_parameters)

    # Print solution on console.
    if solution:
        print("Optimization Finished: ",SOLUTION_STATUS[routing.status()])
        print(f"Optimal Objective Value: {solution.ObjectiveValue():,d}")
        seqs, tstarts, brks = read_solution(solution, manager, routing)
        # Save Current Solution: Could Work as Initial Solution of Next Run
        if save_solution:
            save_solution_sequence(seqs)
        if verbose:
            print("\nOptimal Solution:")
            optimal_seqs = [seq_[1:-1] for seq_ in seqs]
            print_sched_sequence(labels, n_starts + n_clients, optimal_seqs)
            print("\nEnd Optimal Solution\n")
        if initial_solution and are_seqs_identical(stored_initial_seqs,optimal_seqs):
            print("WARNING: Optimal Identical to Initial\n")  
        return seqs, tstarts, brks
    else:
        sys.exit("*\n*\n*   No solution found !\n*\n*")

def are_seqs_identical(seq0, seq1):
    test = True
    for s0, s1 in zip(seq0,seq1):
        test &= len(s0) == len(s1)
        test &= all(x0==x1 for x0,x1 in zip(s0,s1))
        if not test:
            break
    return test

def read_solution(solution, manager, routing):
    routes = []
    breaks = []
    time_starts = []
    time_dimension = routing.GetDimensionOrDie(TIME_DIM_NAME)
    intervals = solution.IntervalVarContainer()
    for route_number in range(routing.vehicles()):
        brk = intervals.Element(route_number)
        index = routing.Start(route_number)
        route = []
        time_start = []
        while True:
            node_index = manager.IndexToNode(index)
            route.append(node_index)
            time_start.append(solution.Min(time_dimension.CumulVar(index)))
            if routing.IsEnd(index):
                break
            else:
                index = solution.Value(routing.NextVar(index))
        routes.append(route)
        time_starts.append(time_start)
        breaks.append(
            (brk.StartValue(), brk.StartValue() + brk.DurationValue()) if brk.PerformedValue() else None
            )
    return routes, time_starts, breaks

def save_solution_sequence(soln_list, filename="./initial_solution.txt"):
    with open(filename, 'w') as f:
        for route in soln_list:
            print(" ".join([str(i) for i in route[1:-1]]), file=f)

def read_initial_solution(filename="./initial_solution.txt"):
    routes = []
    with open(filename, 'r') as f:
        for ln in f.readlines():
            routes.append([int(i) for i in ln.split(" ")])
    return routes

def get_default_labels(n_starts, n_clients, n_appts):
    out = ["Start_{:02d}".format(i) for i in range(n_starts)]
    out = out + ["Client{:02d}".format(i) for i in range(n_clients)]
    out = out + ["Appt__{:02d}".format(i) for i in range(n_appts)]
    return out

def print_sched_sequence(label, appt_start_node, seqs):
    print("\nSchedule Plan:\n")
    for day_id, seq_ in enumerate(seqs):
        print("Day {}".format(day_id+1))
        print("-----")
        for id in [0]+seq_+[0]:
            lbl = label[id]
            if id >= appt_start_node:
                print(lbl+" (Prior Appt)")
            else:
                print(lbl)
        print()