import pandas as pd

from src.inputs import get_label_to_node
from collections import namedtuple

WORKDAY_NAME = ["1.Monday", "2.Tuesday", "3.Wednesday", "4.Thursday", "5.Friday"]

def time_string(total_minutes, start_time=8*60):
    """Convert Minutes to Time String Since Start of Day
   
    Args:
        total_minutes (int): Time in Minutes
        start_time (int, optional): Start of Day in Minutes. Defaults to 8*60.
       
    Returns:
        str: Time String in HH:MM format
    """
    return "{:02d}:{:02d}".format(*divmod(total_minutes + start_time, 60))

def store_result(data, params, seqs, tstarts, brks):
    """Store Optimation Results and Save Results File
   
    Args:
        data (dict): Dictionary with keys: "label", "service_time", "time_windows", "days", "coords"
        params (dict): Dictionary with keys: "timeunits2minutes"
        seqs (list): Nodes Visited by Day
        tstarts (list): Time to start Visit to each Node by Day
        brks (list): Break start and Break End by Day
       
    Returns:
        pd.DataFrame: with "account_id", "Time_In", "Time_Out", "Pre Sched", "Day", "priority", "account_city"
        dict: Solution Info
   
    Saves File with Account Stats
    """
    n_days = len(data["day_lims"])
   
    RouteRow = namedtuple(
        "RouteRow", 
        [
            "account_id", "node", "Time_In", "Time_Out", "Pre_Sched", 
            "Day", "priority", "account_city"
            ]
        )
   
    routes = []
    info = dict()
    dropped = set(data["ndlabel"][1])
    n_primary = data["n_starts"]+data["n_clients"]
    dropped_id = set(range(data["n_starts"],n_primary))
    miss_appt = set(data["ndlabel"][2])
    miss_appt_id = set([twin.node for twin in data["time_windows"]])
   
    def get_stop_data(id, ts, dropped, miss_appt):
        nonlocal dropped_id, miss_appt_id, total_service_time
        pid = data["primary"][id]
        lbl = data["labels"][id]
        priority = data["priority"][pid]
        account_city = data["account_city"][pid]
        total_service_time += data["service_time"][pid]
        dropped -= {lbl}
        dropped_id -= {pid}
        pre_sched = 0
        if id > pid:
            miss_appt -= {lbl}
            miss_appt_id -= {pid}
            pre_sched = 1
        t_in  = ts*params["timeunits2minutes"]
        t_out = (ts+int(data['service_time'][pid]))*params["timeunits2minutes"]
        row = RouteRow(
            lbl, id, time_string(t_in), time_string(t_out), pre_sched, day_name, 
            priority, account_city
            )
        return row

    def get_break_row(brk):
        if brk:
            ts, te = brk
            tb_in = ts*params["timeunits2minutes"]
            tb_out = te*params["timeunits2minutes"]
            break_row = ("Break-Time", -1, time_string(tb_in), time_string(tb_out), 1, day_name, None, "-")
        else:
            break_row = ("Break-Skip", -1, "20:00", "20:30", 1, day_name, None, "-")
        return break_row

    total_time = 0
    total_service_time = 0
    for day_id in range(n_days):
        day_name = WORKDAY_NAME[day_id]
        seq_ = seqs[day_id]
        tstart = tstarts[day_id]
        brk = brks[day_id]
        day_data = []
        for id, ts in zip(seq_,tstart):
            row = get_stop_data(id, ts, dropped, miss_appt)
            day_data.append(row)
        total_time += ts # Time of Day's Route End (Note: ts == te for Base)
        day_data.append(get_break_row(brk))
        routes.append(pd.DataFrame(day_data, columns=RouteRow._fields))
    routes = pd.concat(routes) # Return Routes as Pandas DataFrame
    routes.sort_values(by=["Day","Time_In"], inplace=True)
    info["total_time_hours"] = total_time*params["timeunits2hour"]
    info["total_service_time_hours"] = total_service_time*params["timeunits2hour"]
    info["total_travel_time_hours"] = info["total_time_hours"] - info["total_service_time_hours"]
    print(dropped_id)
    print(miss_appt_id)
   
    # Account Stats (exclude starts)
    info["tot_calls"] = 0
    out = []
    labelToNode = get_label_to_node(data)
    visited = set()
    for _, row in routes.iterrows():
        client = row["account_id"]
        node = int(row["node"])
        pnode = data["primary"][node]
        if "Break" in client:
            continue
        if client in data["ndlabel"][0]:
            continue
        visited.add(client)
        info["tot_calls"] += 1
        call_day = row["Day"]
        if client in data["time_windows_old"]:
            sched_day_id = data["time_windows_old"][client].day
        else:
            sched_day_id = None
        time_from_base = time_string(data['time_matrix'][0][pnode]*params["timeunits2minutes"],0)
        d = {
            "account_id":client,
            "call_day":call_day,
            "priority":data["nodes"]["priority"].loc[client],
            "sched_day":"None" if sched_day_id is None else WORKDAY_NAME[sched_day_id],
            "time_from_base":time_from_base,
            }
        out.append(d)
    for client in dropped:
        if client in visited:
            continue
        node = labelToNode[client]
        time_from_base = time_string(data['time_matrix'][0][node]*params["timeunits2minutes"],0)
        if client in data["time_windows_old"]:
            sched_day_id = data["time_windows_old"][client].day
        else:
            sched_day_id = None
        d = {
        "account_id":client,
        "call_day":"Dropped",
        "priority":data["nodes"]["priority"].loc[client],
        "sched_day":"None" if sched_day_id is None else WORKDAY_NAME[sched_day_id],
        "time_from_base":time_from_base,
        }
        out.append(d)
    statsfile = "output/{}_account_stats.csv".format(params["name"])
    pd.DataFrame(out).sort_values(
        by=["call_day","priority","sched_day","time_from_base"],
        ascending=[True,False,True,False]
        ).set_index("account_id").to_csv(statsfile)
    
    # Calculate Stats
    info["tot_appointments"] = data["n_appts"]
    info["missed_appointments"] = len(miss_appt_id)
    info["kept_appointments"] = info["tot_appointments"] - info["missed_appointments"]
    info["rescheduled_appointments"] = len(miss_appt_id - dropped_id)
    info["dropped_appointments"] = len(miss_appt_id & dropped_id)

    # Store for Plotting
    data["dropped"] = list(dropped) # Store Dropped Accounts as List
    data["dropped_id"] = list(dropped_id) # Store Dropped Ids as List
    data["miss_appt_id"] = list(miss_appt_id) # Store Ids with Missed Appointments as List

    return routes, info

def print_solution(routes, info):  
    """Print Solution to Console
    """
    print(routes.set_index(["Day","Time_In","Time_Out"])[["account_id", "account_city", "Pre_Sched"]])
   
    print("\nSchedule Summary")
    print("----------------")
    print("Total Work Time:    {total_time_hours:.1f} hours".format(**info))
    print("Total Travel Time:  {total_travel_time_hours:.1f} hours".format(**info))
    print("Total Service Time: {total_service_time_hours:.1f} hours".format(**info))
    print("Total Client Calls: {}".format(info["tot_calls"]))
   
    print("\nAppointment Stats")
    print("  Total Appointments:       {tot_appointments:d}".format(**info))
    print("  Appointments Kept:        {kept_appointments:d}".format(**info))
    print("  Missed Appointments:      {missed_appointments:d}".format(**info))
    print("  Rescheduled Appointments: {rescheduled_appointments:d}".format(**info))
    print("  Dropped Appointments:     {dropped_appointments:d}".format(**info))
