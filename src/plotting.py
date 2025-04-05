import plotly.graph_objects as go
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import os
from math import sqrt
from src.outputs import WORKDAY_NAME

def priority_color(max_priority, colormap='OrRd', is_scaled=True, correction=0.5):
    # Color by Priority
    if is_scaled:
        cmap = plt.get_cmap(colormap, int((1+correction)*sqrt(max_priority)))
        return lambda x: mcolors.to_hex(cmap(int(sqrt(x))))
    else:
        cmap = plt.get_cmap(colormap, int((1+correction)*max_priority))
        return lambda x: mcolors.to_hex(cmap(int(x)))
    
def get_day_colors(n_days, colormap='Set1'):
    out = dict()
    cmap = plt.get_cmap(colormap, n_days)
    for day_id in range(n_days):
        out[WORKDAY_NAME[day_id]] = mcolors.to_hex(cmap(day_id))
    return out
   
def plot_region(routes, data, mapfile='weekly_schedule_map.html', output_path='output'):
    """Map Daily Routes

    Args:
        routes (pd.DataFrame): Pandas Dataframe with columns: "Day", "day_color", "latitude", "longitude", "account_id", "Time_Out"
        dropped (list): List of dropped account ids
        data (dict): Dictionary with keys: "coords", "type", "remaining"
        mapfile (str, optional): _description_. Defaults to 'weekly_schedule_map.html'.
    """
    fig = go.Figure()
   
    # Color Parameters
    max_priority = max(data["priority"])
    pcolor = priority_color(max_priority)
   
    # Drop Breaks from Routes
    routes = routes.loc[routes["account_id"].apply(lambda x: "Break" not in x)]
   
    # Show Day Schedules
    day_colors = get_day_colors(len(WORKDAY_NAME))
    start_labels = data["labels"][:data["n_starts"]]
    for day, grp in routes.groupby("Day"):

        # Pick Day Color
        day_color = day_colors[day]

        # Add the route line
        pth = grp["account_city"].tolist()
        grpacct = grp["account_id"].tolist()
        if grpacct[1] in start_labels: # do not show base to hub path
            pth.pop(0)
        if len(grpacct) >= 2 and grpacct[-2] in start_labels: # do not show hub to base path
            pth.pop()
        rprev = pth.pop(0)
        rdet = [rprev]
        for rnext in pth:
            rdet += data["paths"][rprev][rnext][1:]
            rprev = rnext
        daypath = data["latlon"].loc[rdet]
        fig.add_trace(
            go.Scattergeo(
                lat=daypath['latitude'],
                lon=daypath['longitude'],
                mode='lines',
                line=dict(width=1, color=day_color, dash = 'dot'),
                hoverinfo='none',
                showlegend=False
                )
        )
       
        # Show Visited Clients (exluding starts)
        active_client_id = [i for i in grp["node"].tolist() if i >= data["n_starts"]] 
        coord_visited = grp.loc[grp["node"].isin(active_client_id)]
        active_client_city = coord_visited["account_city"]
        fig.add_trace(
            go.Scattergeo(
                    lat=data["latlon"].loc[active_client_city,"latitude"],
                    lon=data["latlon"].loc[active_client_city,"longitude"],
                    mode='markers',
                    hoverinfo='text',
                    text=coord_visited.apply(lambda x: x["account_city"] + ":" + x["account_id"] + " - " + x["Time_Out"] + " " + x["Day"], axis=1),
                    marker=dict(
                        size=8,
                        symbol='square',
                        color=day_color,
                        line=dict(width=1,color='DarkSlateGrey')
                        ),
                    name=day
                    )
            )

    # Show Starts
    start_id = list(range(data["n_starts"]))
    starts = [data["labels"][i] for i in start_id]
    start_city = [data["account_city"][i] for i in start_id]
    latarray = data["latlon"].loc[start_city,"latitude"]
    lonarray = data["latlon"].loc[start_city,"longitude"]
    fig.add_trace(
        go.Scattergeo(
                lat=latarray,
                lon=lonarray,
                mode='markers',
                hoverinfo='text',
                text=starts,
                marker=dict(
                    size=8,
                    symbol='square',
                    color="yellow",
                    line=dict(width=1,color='DarkSlateGrey')
                    ),
                name="Start Location"
                )
        )

    # Show Dropped
    if data["dropped_node"]:

        # Sort by Priority
        dropped_priority = [data["priority"][id] for id in data["dropped_node"]] # Unordered
        ord = sorted(range(len(dropped_priority)), key=lambda k: dropped_priority[k])

        dropped_node = [data["dropped_node"][i] for i in ord]
        dropped = [data["labels"][id] for id in dropped_node]
        dropped_priority = [data["priority"][id] for id in dropped_node]
        dropped_client_city = [data["account_city"][id] for id in dropped_node]
        dropped_text = ["{} Priority:{:.1f}".format(lbl,p) for lbl,p in zip(dropped,dropped_priority)]
        fig.add_trace(
            go.Scattergeo(
                    lat=data["latlon"].loc[dropped_client_city,"latitude"],
                    lon=data["latlon"].loc[dropped_client_city,"longitude"],
                    mode='markers',
                    hoverinfo='text',
                    text=dropped_text,
                    marker=dict(
                        size=9,
                        symbol='hexagon',
                        color=[pcolor(x) for x in dropped_priority],
                        line=dict(width=1,color='DarkSlateGrey')
                        ),
                    name="Dropped"
                    )
            )
     
    # Show Remaining
    if data["inactive_client_city"]:
        fig.add_trace(
            go.Scattergeo(
                    lat=data["latlon"].loc[data["inactive_client_city"],"latitude"],
                    lon=data["latlon"].loc[data["inactive_client_city"],"longitude"],
                    mode='markers',
                    hoverinfo='text',
                    text=data["inactive_client_city"],
                    marker=dict(size=8,color="white",line=dict(width=1,color='DarkSlateGrey')),
                    name="Client Not in Scope"
                    )
            )
   
    fig.update_layout(
        geo=dict(fitbounds='locations')
        )
   
    # Add Title
    fig.update_layout(title = 'Week Routes by Day', title_x=0.5)
    fig.update_geos(resolution=50)

    fig.write_html(os.path.join(output_path,mapfile), auto_open=True)
   
    return
