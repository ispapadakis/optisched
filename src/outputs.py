import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

import pandas as pd

from src.inputs import primary_node, get_label_to_node, get_node_to_label

def time_string(total_minutes, start_time=8*60):
    """Convert Minutes to Time String Since Start of Day
   
    Args:
        total_minutes (int): Time in Minutes
        start_time (int, optional): Start of Day in Minutes. Defaults to 8*60.
       
    Returns:
        str: Time String in HH:MM format
    """
    return "{:02d}:{:02d}".format(*divmod(total_minutes + start_time, 60))

def store_result(data, manager, routing, solution, params):
    """Store Optimation Results and Save Results File
   
    Args:
        data (dict): Dictionary with keys: "label", "service_time", "time_windows", "days", "coords"
        manager (ortools.RoutingIndexManager): Index Manager
        routing (ortools.RoutingModel): Routing Model
        solution (ortools.RoutingModel): Solution
        params (dict): Dictionary with keys: "timeunits2minutes"
       
    Returns:
        tuple:
            - DataFrame with columns: "account_id", "Time In", "Time Out", "Pre Sched", "Day", "day_color"
            - List of Dropped Account Ids
            - List of Missed Appointment Account Ids
   
    Saves File with Account Stats
    """
    primary = primary_node(data)
   
    time_dimension = routing.GetDimensionOrDie("Time")
    cols = ["account_id","Time In","Time Out","Pre Sched","Day", "day_color"]
    cmap = plt.get_cmap('Set1',len(data["days"]))
   
    routes = []
    info = dict()
    intervals = solution.IntervalVarContainer()
    dropped = set(data["ndlabel"][1])
    miss_appt = set(data["ndlabel"][2])
   
    def get_stop_data(index, dropped, miss_appt, service_time, node_label):
        time_var = time_dimension.CumulVar(index)
        id = manager.IndexToNode(index)
        pid = primary[id]
        lbl = node_label[pid]
        service_time += data["nodes"]['service_time'].loc[lbl]
        dropped -= {lbl}
        pre_sched = 0
        if id > pid:
            miss_appt -= {lbl}
            if lbl in data["ndlabel"][2]:
                pre_sched = 1
        t_in  = solution.Min(time_var)*params["timeunits2minutes"]
        t_out = (solution.Max(time_var)+int(data["nodes"]['service_time'].iloc[pid]))*params["timeunits2minutes"]
        return (lbl, time_string(t_in), time_string(t_out), pre_sched, day_name, day_color), service_time

    def get_break_row():
        brk = intervals.Element(day_id)
        if brk.PerformedValue():
            tb_in = brk.StartValue()*params["timeunits2minutes"]
            tb_out = (brk.StartValue() + brk.DurationValue())*params["timeunits2minutes"]
            break_row = ("Break-Time", time_string(tb_in), time_string(tb_out), 1, day_name, day_color)
        else:
            break_row = ("Break-Skip", "20:00", "20:30", 1, day_name, None)
        return break_row

    total_time = 0
    total_service_time = 0
    node_label = get_node_to_label(data)
    for day_id in data["days"].index:
        day_name = data["days"].loc[day_id,"day_name"]
        day_color = mcolors.to_hex(cmap(day_id))
        index = routing.Start(day_id)
        day_data = []
        while not routing.IsEnd(index):
            row, total_service_time = get_stop_data(index, dropped, miss_appt, total_service_time, node_label)
            day_data.append(row)
            index = solution.Value(routing.NextVar(index))
        total_time += solution.Min(time_dimension.CumulVar(index))
        row, total_service_time = get_stop_data(index, dropped, miss_appt, total_service_time, node_label)
        day_data.append(row)
        day_data.append(get_break_row())  
        routes.append(pd.DataFrame(day_data, columns=cols))
    routes = pd.concat(routes).join(data["nodes"], on="account_id", how="left") # Return Routes as Pandas DataFrame
    routes = routes.fillna({"account_city":"-"})
    routes.sort_values(by=["Day","Time In"], inplace=True)
    dropped = list(dropped) # Return Dropped Accounts as List
    miss_appt = list(miss_appt) # Return Missed Appointments as List
    info["total_time_hours"] = total_time*params["timeunits2hour"]
    info["total_service_time_hours"] = total_service_time*params["timeunits2hour"]
    info["total_travel_time_hours"] = info["total_time_hours"] - info["total_service_time_hours"]
   
    # Account Stats (exclude starts)
    info["tot_calls"] = 0
    out = []
    labelToNode = get_label_to_node(data)
    visited = set()
    for _, row in routes.iterrows():
        client = row["account_id"]
        if "Break" in client:
            continue
        if client in data["ndlabel"][0]:
            continue
        visited.add(client)
        info["tot_calls"] += 1
        node = labelToNode[client]
        call_day = row["Day"]
        if client in data["time_windows"]:
            sched_day_id = data["time_windows"][client].day
        else:
            sched_day_id = None
        time_from_base = time_string(data['time_matrix'][0][node]*params["timeunits2minutes"],0)
        d = {
            "account_id":client,
            "call_day":call_day,
            "priority":data["nodes"]["priority"].loc[client],
            "sched_day":"None" if sched_day_id is None else data["days"].loc[sched_day_id,"day_name"],
            "time_from_base":time_from_base,
            }
        out.append(d)
    for client in dropped:
        if client in visited:
            continue
        node = labelToNode[client]
        time_from_base = time_string(data['time_matrix'][0][node]*params["timeunits2minutes"],0)
        if client in data["time_windows"]:
            sched_day_id = data["time_windows"][client].day
        else:
            sched_day_id = None
        d = {
        "account_id":client,
        "call_day":"Dropped",
        "priority":data["nodes"]["priority"].loc[client],
        "sched_day":"None" if sched_day_id is None else data["days"].loc[sched_day_id,"day_name"],
        "time_from_base":time_from_base,
        }
        out.append(d)
    statsfile = "output/{}_account_stats.csv".format(params["name"])
    pd.DataFrame(out).sort_values(
        by=["call_day","priority","sched_day","time_from_base"],
        ascending=[True,False,True,False]
        ).set_index("account_id").to_csv(statsfile)

    return routes, dropped, miss_appt, info

def print_solution(solution, data, routes, dropped, miss_appt, info):  
    """Print Solution to Console
    """
    print(routes.set_index(["Day","Time In","Time Out"])[["account_id", "account_city", "Pre Sched"]])
   
    print("\nSchedule Summary")
    print("----------------")
    print(f"Optimal Objective Value: {solution.ObjectiveValue():,d}")
    print("Total Work Time:    {total_time_hours:.1f} hours".format(**info))
    print("Total Travel Time:  {total_travel_time_hours:.1f} hours".format(**info))
    print("Total Service Time: {total_service_time_hours:.1f} hours".format(**info))
    print("Total Client Calls: {}".format(info["tot_calls"]))
   
    print("\nAppointment Stats")
    tot_appointments = len(data["ndlabel"][2])
    missed_appointments = len(miss_appt)
    print("  Total Appointments:       {}".format(tot_appointments))
    print("  Appointments Kept:        {}".format(tot_appointments - missed_appointments))
    print("  Missed Appointments:      {}".format(missed_appointments))
    print("  Rescheduled Appointments: {}".format(len(set(miss_appt) - set(dropped))))
    print("  Dropped Appointments:     {}".format(len(set(miss_appt) & set(dropped))))
