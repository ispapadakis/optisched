import pandas as pd
import sys

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
   
    ### Initialize Collectors
    routes = []
    info = dict()
    primary_nodes = list(range(data["n_starts"],data["n_starts"]+data["n_clients"])) # store for later
    dropped_node = set(primary_nodes)
    miss_appt_node = set([twin.node for twin in data["time_windows"]])

    ### Row Operations

    def get_stop_data(id, ts):
        nonlocal dropped_node, miss_appt_node, total_service_time
        pid = data["primary"][id]
        lbl = data["labels"][id]
        priority = data["priority"][pid]
        account_city = data["account_city"][pid]
        total_service_time += data["service_time"][pid]
        dropped_node -= {pid}
        pre_sched = 0
        if id > pid:
            miss_appt_node -= {pid}
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

    ### Initialize Account Stats
    time_from_base = lambda i: time_string(data['time_matrix'][0][i]*params["timeunits2minutes"],0)
    acctstats = [None] * data["n_starts"]
    acctstats += [
        {
            "account_id":data["labels"][node], 
            "call_day":"Dropped", 
            "priority":data["priority"][node], 
            "sched_day":"None", 
            "time_from_base":time_from_base(node)
        } 
        for node in primary_nodes
        ]
    for twin in data["time_windows"]:
        acctstats[twin.node]["sched_day"] = WORKDAY_NAME[twin.day]

    ### Traverse Routes to Collect Route Data and Account Stats
    total_time = 0
    total_service_time = 0
    info["tot_calls"] = 0
    for day_id in range(n_days):
        day_name = WORKDAY_NAME[day_id]
        seq_ = seqs[day_id]
        tstart = tstarts[day_id]
        brk = brks[day_id]
        day_data = []
        for node, ts in zip(seq_,tstart):
            if node >= data["n_starts"]:
                info["tot_calls"] += 1
                pnode = data["primary"][node]
                acctstats[pnode]["call_day"] = day_name
            day_data.append(get_stop_data(node, ts))
        total_time += ts # Time of Day's Route End (Note: ts == te for Base)
        day_data.append(get_break_row(brk))
        routes.append(pd.DataFrame(day_data, columns=RouteRow._fields))
    routes = pd.concat(routes) # Return Routes as Pandas DataFrame
    routes.sort_values(by=["Day","Time_In"], inplace=True)
    info["total_time_hours"] = total_time*params["timeunits2hour"]
    info["total_service_time_hours"] = total_service_time*params["timeunits2hour"]
    info["total_travel_time_hours"] = info["total_time_hours"] - info["total_service_time_hours"]
   
    # Save Account Stats
    statsfile = "output/{}_account_stats.csv".format(params["name"])
    pd.DataFrame(acctstats[data["n_starts"]:]).sort_values(
        by=["call_day","priority","sched_day","time_from_base"],
        ascending=[True,False,True,False]
        ).set_index("account_id").to_csv(statsfile)
    
    # Calculate Model Stats
    info["tot_appointments"] = data["n_appts"]
    info["missed_appointments"] = len(miss_appt_node)
    info["kept_appointments"] = info["tot_appointments"] - info["missed_appointments"]
    info["rescheduled_appointments"] = len(miss_appt_node - dropped_node)
    info["dropped_appointments"] = len(miss_appt_node & dropped_node)

    # Store for Plotting
    data["dropped_node"] = list(dropped_node) # Store Dropped Primary Nodes as List

    return routes, info

def print_solution(routes, info, send_to_file=False):  
    """Print the solution summary to the specified output.
    Args:
        routes (pd.DataFrame): DataFrame with route information
        info (dict): Dictionary with solution information
        send_to_file (bool): Flag to send output to file or stdout
    """
    # Select output destination
    if send_to_file:
        fout = open(get_report_filename(**info), "w")
    else:
        fout = sys.stdout

    print(routes.set_index(["Day","Time_In","Time_Out"])[["account_id", "account_city", "Pre_Sched"]])
   
    print("\nSchedule Summary", file=fout)
    print("----------------", file=fout)
    print("Total Work Time:    {total_time_hours:.1f} hours".format(**info), file=fout)
    print("Total Travel Time:  {total_travel_time_hours:.1f} hours".format(**info), file=fout)
    print("Total Service Time: {total_service_time_hours:.1f} hours".format(**info), file=fout)
    print("Total Client Calls: {}".format(info["tot_calls"]), file=fout)
   
    print("\nAppointment Stats", file=fout)
    print("  Total Appointments:       {tot_appointments:d}".format(**info), file=fout)
    print("  Appointments Kept:        {kept_appointments:d}".format(**info), file=fout)
    print("  Missed Appointments:      {missed_appointments:d}".format(**info), file=fout)
    print("  Rescheduled Appointments: {rescheduled_appointments:d}".format(**info), file=fout)
    print("  Dropped Appointments:     {dropped_appointments:d}".format(**info), file=fout)

def get_report_filename(name, **kwargs):
    """Get Report Filename
   
    Args:
        name (str): Name of the file
        kwargs: Additional arguments
   
    Returns:
        str: Filename with Path
    """
    return "output/optisched_{}.txt".format(name)
