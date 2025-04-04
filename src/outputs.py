import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

import pandas as pd

from src.inputs import primary_node, get_label_to_node, get_node_to_label

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

def get_default_labels(n_starts, n_clients, n_appts):
    out = ["Start_{:02d}".format(i) for i in range(n_starts)]
    out = out + ["Client{:02d}".format(i) for i in range(n_clients)]
    out = out + ["Appt__{:02d}".format(i) for i in range(n_appts)]
    return out

def print_sched_sequence(label, appt_start_node, seqs):
    print("\nSchedule Plan:\n")
    for day_id, seq_ in enumerate(seqs):
        print(WORKDAY_NAME[day_id])
        print("-"*len(WORKDAY_NAME[day_id]))
        for id in [0]+seq_+[0]:
            lbl = label[id]
            if id >= appt_start_node:
                print(lbl+" (Prior Appt)")
            else:
                print(lbl)
        print()

def store_result(data, params, seqs, tstarts, brks):
    """Store Optimation Results and Save Results File
   
    Args:
        data (dict): Dictionary with keys: "label", "service_time", "time_windows", "days", "coords"
        params (dict): Dictionary with keys: "timeunits2minutes"
        seqs (list): Nodes Visited by Day
        tstarts (list): Time to start Visit to each Node by Day
        brks (list): Break start and Break End by Day
       
    Returns:
        tuple:
            - DataFrame with columns: "account_id", "Time In", "Time Out", "Pre Sched", "Day", "day_color"
            - List of Dropped Account Ids
            - List of Missed Appointment Account Ids
            - Solution Info Dict
   
    Saves File with Account Stats
    """
    n_days = len(data["day_lims"])
    primary = primary_node(**data)
   
    cols = ["account_id","Time In","Time Out","Pre Sched","Day", "day_color"]
    cmap = plt.get_cmap('Set1', n_days)
   
    node_label = get_node_to_label(data)
    routes = []
    info = dict()
    dropped = set(data["ndlabel"][1])
    miss_appt = set(data["ndlabel"][2])
   
    def get_stop_data(id, ts, dropped, miss_appt, service_time):
        pid = primary[id]
        lbl = node_label[pid]
        service_time += data["nodes"]['service_time'].loc[lbl]
        dropped -= {lbl}
        pre_sched = 0
        if id > pid:
            miss_appt -= {lbl}
            if lbl in data["ndlabel"][2]:
                pre_sched = 1
        t_in  = ts*params["timeunits2minutes"]
        t_out = (ts+int(data["nodes"]['service_time'].iloc[pid]))*params["timeunits2minutes"]
        return (lbl, time_string(t_in), time_string(t_out), pre_sched, day_name, day_color), service_time

    def get_break_row(brk):
        if brk:
            ts, te = brk
            tb_in = ts*params["timeunits2minutes"]
            tb_out = te*params["timeunits2minutes"]
            break_row = ("Break-Time", time_string(tb_in), time_string(tb_out), 1, day_name, day_color)
        else:
            break_row = ("Break-Skip", "20:00", "20:30", 1, day_name, None)
        return break_row

    total_time = 0
    total_service_time = 0
    for day_id in range(n_days):
        day_name = WORKDAY_NAME[day_id]
        day_color = mcolors.to_hex(cmap(day_id))
        seq_ = seqs[day_id]
        tstart = tstarts[day_id]
        brk = brks[day_id]
        day_data = []
        for id, ts in zip(seq_,tstart):
            row, total_service_time = get_stop_data(id, ts, dropped, miss_appt, total_service_time)
            day_data.append(row)
        total_time += ts # Time of Day's Route End (Note: ts == te for Base)
        day_data.append(get_break_row(brk))
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
        if client in data["time_windows_old"]:
            sched_day_id = data["time_windows_old"][client].day
        else:
            sched_day_id = None
        time_from_base = time_string(data['time_matrix'][0][node]*params["timeunits2minutes"],0)
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

    return routes, dropped, miss_appt, info

def print_solution(data, routes, dropped, miss_appt, info):  
    """Print Solution to Console
    """
    print(routes.set_index(["Day","Time In","Time Out"])[["account_id", "account_city", "Pre Sched"]])
   
    print("\nSchedule Summary")
    print("----------------")
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
