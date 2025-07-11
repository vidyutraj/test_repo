import pandas as pd
import gurobipy as gp
from gurobipy import GRB
import os
import sys

# Load config
try:
    import config
    MIN_TURNAROUND = config.MinTurnaroundTimeMinutes
    MAX_DUTY_HOURS = config.MaxCrewDutyHours
    SLA_PENALTY = config.SlaPenalty
    DELAY_PENALTY = config.DelayPenalty
    MAINT_PENALTY = config.MaintenancePenalty
except ImportError:
    print("config.py not found. Please provide config.py or constraints.json.")
    sys.exit(1)

# Data paths
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
flights = pd.read_csv(os.path.join(DATA_DIR, 'flights.csv'))
aircraft = pd.read_csv(os.path.join(DATA_DIR, 'aircraft.csv'))
crew = pd.read_csv(os.path.join(DATA_DIR, 'crew.csv'))
time_slots = pd.read_csv(os.path.join(DATA_DIR, 'time_slots.csv'), header=None)[0].tolist()

# Helper: convert HH:MM to minutes
parse_time = lambda t: int(t.split(":")[0]) * 60 + int(t.split(":")[1])

# Preprocess times
flights['ScheduledDepartureMin'] = flights['ScheduledDeparture'].apply(parse_time)
flights['SLADeliveryTimeMin'] = flights['SLADeliveryTime'].apply(parse_time)
aircraft['ReadyTimeMin'] = aircraft['ReadyTime'].apply(parse_time)
crew['DutyStartMin'] = crew['DutyStart'].apply(parse_time)

# Model
model = gp.Model("FlightScheduler")

# Decision variables
# Departure time (index in time_slots)
departure_time = model.addVars(flights.index, vtype=GRB.INTEGER, name="departure_time")
# Binary indicator for time slot assignment
is_time = model.addVars(flights.index, range(len(time_slots)), vtype=GRB.BINARY, name="is_time")
# Aircraft assignment (index of aircraft)
aircraft_used = model.addVars(flights.index, aircraft.index, vtype=GRB.BINARY, name="aircraft_used")
# Crew assignment (index of crew)
crew_assigned = model.addVars(flights.index, crew.index, vtype=GRB.BINARY, name="crew_assigned")
# SLA missed
sla_missed = model.addVars(flights.index, vtype=GRB.BINARY, name="sla_missed")

# Penalty variables
minutes_delayed = model.addVars(flights.index, vtype=GRB.INTEGER, name="minutes_delayed")
overtime = model.addVars(crew.index, vtype=GRB.INTEGER, name="overtime")

# Link is_time and departure_time
for f_idx in flights.index:
    # Each flight assigned to exactly one time slot
    model.addConstr(gp.quicksum(is_time[f_idx, t] for t in range(len(time_slots))) == 1, name=f"one_time_{f_idx}")
    # departure_time[f_idx] = sum t * is_time[f_idx, t]
    model.addConstr(departure_time[f_idx] == gp.quicksum(t * is_time[f_idx, t] for t in range(len(time_slots))), name=f"dep_time_link_{f_idx}")

# Constraints
for f_idx, flight in flights.iterrows():
    # 1. Flight must be assigned exactly one aircraft and one crew
    model.addConstr(aircraft_used.sum(f_idx, '*') == 1, name=f"one_aircraft_{f_idx}")
    model.addConstr(crew_assigned.sum(f_idx, '*') == 1, name=f"one_crew_{f_idx}")
    
    # 2. Departure time must be within time_slots (already enforced by is_time)
    model.addConstr(departure_time[f_idx] >= 0, name=f"dep_time_lb_{f_idx}")
    model.addConstr(departure_time[f_idx] <= len(time_slots) - 1, name=f"dep_time_ub_{f_idx}")
    
    # 3. Delay calculation
    scheduled = flight['ScheduledDepartureMin']
    model.addConstr(minutes_delayed[f_idx] >= (gp.quicksum(parse_time(time_slots[t]) * is_time[f_idx, t] for t in range(len(time_slots))) - scheduled), name=f"delay_calc_{f_idx}")
    model.addConstr(minutes_delayed[f_idx] >= 0, name=f"delay_nonneg_{f_idx}")
    
    # 4. SLA missed
    sla_deadline = flight['SLADeliveryTimeMin']
    # If dep time > SLA deadline, sla_missed = 1
    model.addConstr(
        gp.quicksum(parse_time(time_slots[t]) * is_time[f_idx, t] for t in range(len(time_slots))) <= sla_deadline + 10000 * sla_missed[f_idx],
        name=f"sla_miss_logic1_{f_idx}")
    model.addConstr(
        gp.quicksum(parse_time(time_slots[t]) * is_time[f_idx, t] for t in range(len(time_slots))) >= sla_deadline + 1 - 10000 * (1 - sla_missed[f_idx]),
        name=f"sla_miss_logic2_{f_idx}")

# 5. Aircraft cannot be double-booked or used if maintenance is required
for a_idx, ac in aircraft.iterrows():
    for t in range(len(time_slots)):
        # At most one flight per aircraft at a time slot
        model.addConstr(
            gp.quicksum(aircraft_used[f_idx, a_idx] * is_time[f_idx, t]
                        for f_idx in flights.index) <= 1,
            name=f"ac_no_double_{a_idx}_{t}")
    # If in maintenance OR maintenance is due (MaintenanceDue <= 0), cannot be used
    if ac['InMaintenance'] == 'TRUE' or ac['MaintenanceDue'] <= 0:
        for f_idx in flights.index:
            model.addConstr(aircraft_used[f_idx, a_idx] == 0, name=f"ac_maint_{a_idx}_{f_idx}")
    # Remove the missed maintenance penalty since it's now a hard constraint

# 6. Crew cannot be double-booked, must not exceed duty hours
for c_idx, cr in crew.iterrows():
    # Each crew can only be assigned to one flight at a time slot
    for t in range(len(time_slots)):
        model.addConstr(
            gp.quicksum(crew_assigned[f_idx, c_idx] * is_time[f_idx, t]
                        for f_idx in flights.index) <= 1,
            name=f"crew_no_double_{c_idx}_{t}")
    # Overtime calculation
    total_minutes = gp.quicksum(
        crew_assigned[f_idx, c_idx] * (flights.loc[f_idx, 'DurationMinutes'] + MIN_TURNAROUND)
        for f_idx in flights.index)
    model.addConstr(overtime[c_idx] >= total_minutes - (cr['MaxDutyHours'] * 60 - cr['HoursWorked'] * 60), name=f"crew_overtime_{c_idx}")
    model.addConstr(overtime[c_idx] >= 0, name=f"crew_overtime_nonneg_{c_idx}")

# 7. Turnaround time between flights for same aircraft
for a_idx in aircraft.index:
    assigned_flights = [f_idx for f_idx in flights.index]
    for i in range(len(assigned_flights)):
        for j in range(i+1, len(assigned_flights)):
            f1, f2 = assigned_flights[i], assigned_flights[j]
            for t1 in range(len(time_slots)):
                for t2 in range(len(time_slots)):
                    if abs(parse_time(time_slots[t1]) - parse_time(time_slots[t2])) < MIN_TURNAROUND:
                        model.addConstr(
                            aircraft_used[f1, a_idx] + aircraft_used[f2, a_idx] + is_time[f1, t1] + is_time[f2, t2] <= 3,
                            name=f"turnaround_{a_idx}_{f1}_{f2}_{t1}_{t2}")

# 8. Flight window (e.g., 2-8 AM)
FLIGHT_WINDOW_START = parse_time('02:00')
FLIGHT_WINDOW_END = parse_time('08:00')
for f_idx in flights.index:
    model.addConstr(
        gp.quicksum(parse_time(time_slots[t]) * is_time[f_idx, t] for t in range(len(time_slots))) >= FLIGHT_WINDOW_START,
        name=f"window_start_{f_idx}")
    model.addConstr(
        gp.quicksum(parse_time(time_slots[t]) * is_time[f_idx, t] for t in range(len(time_slots))) <= FLIGHT_WINDOW_END,
        name=f"window_end_{f_idx}")

# Objective
model.setObjective(
    gp.quicksum(DELAY_PENALTY * minutes_delayed[f_idx] for f_idx in flights.index) +
    gp.quicksum(SLA_PENALTY * sla_missed[f_idx] for f_idx in flights.index) +
    gp.quicksum(10 * overtime[c_idx] for c_idx in crew.index),
    GRB.MINIMIZE)

model.optimize()

# Output results
print("\n===== OPTIMIZED SCHEDULE =====")
for f_idx, flight in flights.iterrows():
    dep_slot = int(departure_time[f_idx].x)
    dep_time = time_slots[dep_slot]
    ac_idx = [a for a in aircraft.index if aircraft_used[f_idx, a].x > 0.5][0]
    cr_idx = [c for c in crew.index if crew_assigned[f_idx, c].x > 0.5][0]
    print(f"Flight {flight['FlightNumber']} departs at {dep_time}, Aircraft: {aircraft.loc[ac_idx, 'AircraftID']}, Crew: {crew.loc[cr_idx, 'CrewID']}, SLA Missed: {int(sla_missed[f_idx].x)}")

print("\n===== PENALTIES =====")
print(f"Total Objective Value: {model.ObjVal}")
for f_idx in flights.index:
    print(f"Flight {flights.loc[f_idx, 'FlightNumber']} delay: {int(minutes_delayed[f_idx].x)} min, SLA Missed: {int(sla_missed[f_idx].x)}")
for c_idx in crew.index:
    print(f"Crew {crew.loc[c_idx, 'CrewID']} overtime: {int(overtime[c_idx].x)} min") 