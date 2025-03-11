import plotly.graph_objects as go
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import os
from math import sqrt

def priority_color(max_priority, colormap='OrRd', is_scaled=True, correction=0.5):
    # Color by Priority
    if is_scaled:
        cmap = plt.get_cmap(colormap, int((1+correction)*sqrt(max_priority)))
        return lambda x: mcolors.to_hex(cmap(int(sqrt(x))))
    else:
        cmap = plt.get_cmap(colormap, int((1+correction)*max_priority))
        return lambda x: mcolors.to_hex(cmap(int(x)))
   
def plot_region(routes, dropped, data, mapfile='weekly_schedule_map.html', output_path='output'):
    """Map Daily Routes

    Args:
        routes (pd.DataFrame): Pandas Dataframe with columns: "Day", "day_color", "latitude", "longitude", "account_id", "Time Out"
        dropped (list): List of dropped account ids
        data (dict): Dictionary with keys: "coords", "type", "remaining"
        mapfile (str, optional): _description_. Defaults to 'weekly_schedule_map.html'.
    """
    fig = go.Figure()
   
    max_priority = data["nodes"]["priority"].max()
    pcolor = priority_color(max_priority)
   
    # Drop Breaks from Routes
    routes = routes.loc[routes["account_id"].apply(lambda x: "Break" not in x)]
   
    # Show Day Schedules
    for (day, day_color), grp in routes.groupby(["Day","day_color"]):
        # Add the route line
        fig.add_trace(
            go.Scattergeo(
                lat=grp['latitude'],
                lon=grp['longitude'],
                mode='lines',
                line=dict(width=2, color=day_color, dash = 'dot'),
                hoverinfo='none',
                #marker= dict(size=10, color=day_color, symbol= "arrow-bar-up", angleref="previous"),
                showlegend=False
                )
        )
       
        # Show Visited Clients (exluding starts)
        active_clients = data["ndlabel"][1]
        coord_visited = grp.loc[grp["account_id"].isin(active_clients)]
        assert len(coord_visited) == len(set(coord_visited.account_id))
        fig.add_trace(
            go.Scattergeo(
                    lat=coord_visited['latitude'],
                    lon=coord_visited['longitude'],
                    mode='markers',
                    hoverinfo='text',
                    text=coord_visited.apply(lambda x: x["account_id"] + " - " + x["Time Out"] + " " + x["Day"], axis=1),
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
    starts = data["ndlabel"][0]
    fig.add_trace(
        go.Scattergeo(
                lat=data["nodes"].loc[starts, 'latitude'],
                lon=data["nodes"].loc[starts, 'longitude'],
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
    if dropped:
        coord_dropped = data["nodes"].loc[dropped]
        coord_dropped.sort_values(by="priority", ascending=True, inplace=True)
        fig.add_trace(
            go.Scattergeo(
                    lat=coord_dropped['latitude'],
                    lon=coord_dropped['longitude'],
                    mode='markers',
                    hoverinfo='text',
                    text=coord_dropped.reset_index().apply(lambda x: "{} Priority:{:.1f}".format(x["account_id"],x["priority"]), axis=1),
                    marker=dict(
                        size=9,
                        symbol='hexagon',
                        color=coord_dropped["priority"].apply(pcolor),
                        line=dict(width=1,color='DarkSlateGrey')
                        ),
                    name="Dropped"
                    )
            )
     
    # Show Remaining
    nodes_remaining = set(data["nodes"].index) - set(starts) - set(active_clients)
    if nodes_remaining:
        coord_remaining = data["nodes"].loc[list(nodes_remaining)]
        fig.add_trace(
            go.Scattergeo(
                    lat=coord_remaining['latitude'],
                    lon=coord_remaining['longitude'],
                    mode='markers',
                    hoverinfo='text',
                    text=coord_remaining.account_city,
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
