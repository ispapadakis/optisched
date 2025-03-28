import yaml
import os
import pandas as pd
from geopy import distance
from collections import namedtuple

def dist2time(x,speed=4.0, high_speed=10.0, high_speed_dist=10, very_high_speed=15.0, very_high_speed_dist=300):
    """Convert Distance to Time
    (Time Units are Quarter Hours)

    Args:
        x (float): Distance in Miles
        speed (float, optional): Speed in Miles Per Quarter Hour. Defaults to 5.0.
        high_speed (float, optional): Speed in Miles Per Quarter Hour for High Speed Roads. Defaults to 20.0.
        high_speed_dist (float, optional): Distance Threshold for High Speed Roads. Defaults to 20.

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

def line_distances(data,params):
    points = data["nodes"].loc[data["node_label"],params["coord_cols"]].values.tolist()
    travel_time = [
        [dist2time(dist_miles(p_from,p_to)) for p_to in points]
        for p_from in points
    ]
    return travel_time

def primary_node(data):
    """Primary Node Correspondence
   
    Args:
        data (dict): Dictionary with keys: "ndlabel", "time_windows"
    """
    N = len(data["ndlabel"][0]) + len(data["ndlabel"][1]) # n_starts + n_clients
    primary = [i for i in range(N)] + [data["time_windows"][lbl].node for lbl in data["ndlabel"][2]]
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
            "nodes", "node_label", "time_matrix", "time_windows", "days"
        """
    starts = pd.read_csv(os.path.join(data_path,"territory.csv"), index_col=0)
    acct = pd.read_csv(os.path.join(data_path,"account.csv"), index_col=0)
   
    # Select Client Accounts for Optimization
    clients = acct.loc[acct["priority"] > priority_cutoff].index.tolist()
   
    # Build Data Dictionary
    data = {}
    data["nodes"] = pd.concat(
        [
            starts[params["coord_cols"]+params["info_cols"]],
            acct[params["coord_cols"]+params["info_cols"]+params["node_cols"]]
            ]
        ).fillna(0)
    for v in params["info_cols"]:
        data["nodes"][v] = data["nodes"][v].apply(lambda x: x.title() if isinstance(x,str) else "")
       
    # Labels of nodes active in the optimizatin model
    data["ndlabel"] = [starts.index.tolist(),clients]
    node_label = get_node_to_label(data)

    # Coordinate Data
    data["latlon"] = pd.read_csv(os.path.join(data_path,"points.csv"), index_col=1)

    # Time Windows
    TimeWindow = namedtuple("TimeWindow", ["start", "end", "day", "node"])
    appt = pd.read_csv(os.path.join(data_path,"appointments.csv"), index_col=0)
    appt_client = []
    data["time_windows"] = dict()
    node = len(starts)
    for client in clients:
        if client in appt.index:
            appt_client.append(client)
            t = int(appt.loc[client,"time"])
            data["time_windows"][client] = TimeWindow(t, t, appt.loc[client,"day"], node)
        node += 1
    data["ndlabel"].append(appt_client)
 
    # Paths from Origin to Destination
    with open(os.path.join(data_path,"travel_path.yml"), 'r') as f:
        data["paths"] = yaml.safe_load(f)
  
    # Travel Time
    #travel_time = line_distances(data,params)
    with open(os.path.join(data_path,"travel_distance.yml"), 'r') as f:
        tdist = yaml.safe_load(f)
    points = data["nodes"].loc[node_label,"account_city"].tolist()
    travel_time = [
        [dist2time(tdist[lbl_from][lbl_to]) for lbl_to in points]
        for lbl_from in points
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

    data["time_matrix"] = travel_time # Order: [Starts, Active_Clients]
   
    # Days
    data["days"] = pd.read_csv(os.path.join(data_path,"days.csv"), index_col=0) # Assumes One Break Per Day
   
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
        elif k == "time_windows":
            for tk in list(v.keys())[:3]:
                print(tk, v[tk])
            print("...")
        else:
            print(v)
    #print(params["name"])
   
if __name__ == "__main__":
    main()