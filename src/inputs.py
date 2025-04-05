import yaml
import os
import pandas as pd
from geopy import distance
from collections import namedtuple
from itertools import chain

def dist2time(x, speed=4.0, high_speed=10.0, high_speed_dist=10, very_high_speed=15.0, very_high_speed_dist=300):
    """Convert Distance to Time
    (Time Units are Quarter Hours)

    Args:
        x (float): Distance in Miles
        speed (float, optional): Speed in Miles Per Quarter Hour. Defaults to 4.0.
        high_speed (float, optional): Speed in Miles Per Quarter Hour for High Speed Roads. Defaults to 10.0.
        high_speed_dist (float, optional): Distance Threshold for High Speed Roads. Defaults to 10.
        very_high_speed (float, optional): Speed in Miles Per Quarter Hour for Air Travel. Defaults to 15.0.
        very_high_speed_dist (float, optional): Distance Threshold for Air Travel. Defaults to 300.

    Returns:
        int: Travel Time in Quarter Hours
       
    Example:
    >>> dist2time(10)
    3
    >>> dist2time(30)
    6
    """
    if x < 1e-6:
        return 0
    if x > very_high_speed_dist: # by plane
        return int(x/very_high_speed)+1
    elif x > high_speed_dist: # by highway
        return int(x/high_speed)+1
    else: # by backroads
        return int(x/speed)+1

def dist_miles(point0,point1):
    """Geodesic Distance Between Two Points in Miles

    Args:
        point0 (tuple(float)): (lat,lon)
        point1 (tuple(float)): (lat,lon)

    Returns:
        float: Distance in Miles
       
    Example:
    >>> dist_miles((40.7128, -74.0060), (34.0522, -118.2437))
    2444.0
    """
    return distance.distance(point0,point1).miles

def primary_node(n_starts,n_clients,time_windows,**kwargs):
    """Primary Node Correspondence
   
    Args:
        data (dict): Dictionary with keys: "ndlabel", "time_windows"
    """
    N = n_starts + n_clients
    primary = [i for i in range(N)] + [twin.node for twin in time_windows]
    return primary

def get_node_to_label(data):
    """Node to Label Correspondence
   
    Args:
        data (dict): Dictionary with keys: "ndlabel"
    """
    nodeTolabel = []
    for lst in data["ndlabel"]:
        nodeTolabel += lst
    return nodeTolabel

def get_label_to_node(data):
    """Label to Primary Node Correspondence
   
    Args:
        data (dict): Dictionary with keys: "ndlabel"
    """
    node = 0
    labelToNode = {}
    # Appt Nodes are not Repeated
    for lst in data["ndlabel"][:2]:
        for lbl in lst:
            labelToNode[lbl] = node
            node += 1
    return labelToNode

def create_data_model(params, data_path, priority_cutoff=5):
    """Data Model for Weekly Scheduling with Breaks
   
    Args:
        params (dict): Dictionary with keys: "base_index", "coord_cols", "segment_weight", "window_max_time", "base_min_start"
        data_path (str): Path to Data Files
       
    Returns:
        dict: Dictionary with keys:
            "nodes", "time_matrix", "time_windows", "day_lims", "break_data", "paths", "latlon", "n_clients", "n_starts", 
            "inactive_clients", "n_appts", "primary", "labels", "ndlabel"
        """
    # Build Data Dictionary
    data = {}

    # Read Starting Location Data
    starts = pd.read_csv(os.path.join(data_path,"territory.csv"), index_col=0)
    data["n_starts"] = len(starts)

    # Read Account Data
    acct = pd.read_csv(os.path.join(data_path,"account.csv"), index_col=0)
   
    # Select Client Accounts for Optimization (Low-Priority Clients Are Not Included)
    clients = []
    data["inactive_client_city"] = []
    for lbl in acct.index:
        if acct.loc[lbl, "priority"] > priority_cutoff:
            clients.append(lbl)
        else:
            data["inactive_client_city"].append(acct.loc[lbl, "account_city"])
    data["n_clients"] = len(clients)

    # Read Appointment Data: Form Time Windows
    TimeWindow = namedtuple("TimeWindow", ["start", "end", "day", "node"])
    appt = pd.read_csv(os.path.join(data_path,"appointments.csv"), index_col=0)
    appt_client = []
    primary = [i for i in range(len(starts)+len(clients))]
    data["time_windows"] = []
    primnode = len(starts)
    for client in clients:
        if client in appt.index:
            appt_client.append(client)
            primary.append(primnode)
            t = int(appt.loc[client,"time"]) # Assumes client is unique - One Appointment per client
            data["time_windows"].append(TimeWindow(t, t, appt.loc[client,"day"], primnode))
        primnode += 1
    data["n_appts"] = len(data["time_windows"])
    data["primary"] = primary
       
    # Labels of nodes active in the optimization model in order
    # Node Order: Starts, Active Clients, Active Clients with Appointments (Repeated)
    data["ndlabel"] = [starts.index.tolist(),clients,appt_client]
    data["labels"] = list(chain(*data["ndlabel"]))

    # Calculate Primary Node Properties (Numbers Need to be of Type int)
    data["priority"] = [0] * data["n_starts"] + [int(acct.loc[lbl,"priority"]) for lbl in clients]
    data["service_time"] = [0] * data["n_starts"] + [int(acct.loc[lbl,"service_time"]) for lbl in clients]
    data["account_city"] = [starts.loc[lbl,"account_city"] for lbl in starts.index] 
    data["account_city"] += [acct.loc[lbl,"account_city"] for lbl in clients]

    # Paths from Origin to Destination
    with open(os.path.join(data_path,"travel_path.yml"), 'r') as f:
        data["paths"] = yaml.safe_load(f)
  
    ### Travel Time
    # Calculate Travel Time Matrix
    with open(os.path.join(data_path,"travel_distance.yml"), 'r') as f:
        tdist = yaml.safe_load(f)
    travel_time = [
        [dist2time(tdist[city_from][city_to]) for city_to in data["account_city"]]
        for city_from in data["account_city"]
    ]
    # Implement Hub Shortcuts
    base_city = starts["account_city"][0]
    for node, lbl in enumerate(starts.index[1:],1):
        hub_city = starts["account_city"][node]
        travel_time[node][0] = starts.loc[lbl,"dist_to_base"]
        travel_time[0][node] = starts.loc[lbl,"dist_from_base"]
        if starts.loc[lbl,"by_air"]:
            data["paths"][base_city][hub_city] = [base_city,hub_city]
            data["paths"][hub_city][base_city] = [hub_city,base_city]
    # Store Travel Time Matrix
    data["time_matrix"] = travel_time # Order: [Starts, Active_Clients]
   
    # Read Day Data: Start/End Time and Break Preferences
    day_data = pd.read_csv(os.path.join(data_path,"days.csv"), index_col=0) # Assumes One Break Per Day

    # Inputs to Optimization Model: Break Data and Day Limits
    BreakRow = namedtuple("BreakRow", ["start_min", "start_max", "duration", "break_option", "label"])
    DayLims = namedtuple("DayLims", ["start_time_min", "start_time_max", "time_end_max"])
    data["break_data"] = []
    data["day_lims"] = []
    for day_id, row in day_data.iterrows():
        break_label = 'Break for {}'.format(row["day_name"])
        # Set Break Option to False: Break is not optional
        data["break_data"].append(
            BreakRow(int(row["break_time_min"]),int(row["break_time_max"]),int(row["duration"]),False,break_label)
            )
        data["day_lims"].append(
            DayLims(int(row["start_time_min"]), int(row["start_time_max"]), int(row["time_end_max"]))
            )

    # Read Coordinate Data: Used for Plotting Maps
    data["latlon"] = pd.read_csv(os.path.join(data_path,"points.csv"), index_col=1)

    return data

def get_model_data(config_path="config", data_path="Data"):
   
    # Load Example Parameters
    with open(os.path.join(config_path,"region_gr.yml"))as f:
        params = yaml.load(f, Loader=yaml.FullLoader)
       
    # Data Path
    model_data_path = os.path.join(data_path,params["path"])
       
    # Instantiate the data problem.
    data = create_data_model(params, model_data_path)
   
    return data, params

def main():
    data, params = get_model_data()
    for k, v in data.items():
        print(k, type(v))
        if k == "time_matrix":
            for row in v[:8]:
                print(row[:8])
            print("...")
        elif k == "paths":
            print("...")
        elif type(v) is list:
            for tk in v[:3]:
                print(tk)
            print("...")
        else:
            print(v)
    #print(params["name"])
   
if __name__ == "__main__":
    main()