# OptiSched - Optimize Weekly Client Calls

## Trade Off Travel Time and Meeting Importance

Using [Google OR-Tools Vehicle Routing](https://developers.google.com/optimization/routing)

**Purpose**:

Schedule weekly client calls to a) maximize the priority of in-schedule clients, while b) minimizing total travel time.

**Features**:

- Weekly optimization horizon is favored by users
- If it makes sense, keep prescheduled appointments
- Add Breaks in Work Day in a Flexible Way
- Accommodate Hotel Stays to Service Remote Areas
- Option to begin from Initial Solution

**Input**:

- Configuration Parameters 
    - Key Goal Setting Features: Penalty for Travel Time, Penalty for missing Pre-scheduled appointments (Note: client priority is included with client data)
    - Optimization Parameters (e.g. max processing time)
    - Modularization Parameters: to easily move to another sales region or time scale
- Client Data: Contains Client Location and Priority
- Territory Data: Contains info about base, hubs for overnight stay, whether to go to hub by air
- Workday Data: Desired duration, break time parameters
- Prescheduled Appointments: Appointments to meet if possible on a preset day and time (** Users are likely to use this feature to guide optimization to desired state**)
- Distances between locations
- Mapping Info
    - Key Points: Lat / Lon
    - Paths to Travel when driving (schedule has enough slack to permit deviations during implementation)

**Output**:

- [Weekly Schedule](output/optisched_RegionGR.txt)
- [Map of Daily Routes](http://htmlpreview.github.io/?https://github.com/ispapadakis/optisched/blob/main/output/RegionGR_map.html)
- [Optimal Plan Stats by Client](output/RegionGR_account_stats.csv)

## Sensitivity Analysis

### Scenario 1: Lower Penalty for Missing Appointments

Result: A) Less Travel Time and B) Not Missing Client with Prior Appointment (by rescheduling)

- [Weekly Schedule](output/optisched_RegionGR_S1.txt)
- [Map of Daily Routes](http://htmlpreview.github.io/?https://github.com/ispapadakis/optisched/blob/main/output/RegionGR_S1_map.html)
- [Optimal Plan Stats by Client](output/RegionGR_S1_account_stats.csv)