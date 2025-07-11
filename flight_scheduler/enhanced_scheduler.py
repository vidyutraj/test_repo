import pandas as pd
import gurobipy as gp
from gurobipy import GRB
import os
import sys
import numpy as np

# Load config
try:
    import config
    MIN_TURNAROUND = config.MinTurnaroundTimeMinutes
    MAX_DUTY_HOURS = config.MaxCrewDutyHours
    SLA_PENALTY = config.SlaPenalty
    DELAY_PENALTY = config.DelayPenalty
    FUEL_PENALTY = getattr(config, 'FuelPenalty', 5)  # Default fuel penalty
    GATEWAY_PENALTY = getattr(config, 'GatewayPenalty', 20)  # Default gateway penalty
    VOLUME_PENALTY = getattr(config, 'VolumePenalty', 15)  # Default volume penalty
except ImportError:
    print("config.py not found. Please provide config.py or constraints.json.")
    sys.exit(1)

# Data paths
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
flights = pd.read_csv(os.path.join(DATA_DIR, 'flights.csv'))
aircraft = pd.read_csv(os.path.join(DATA_DIR, 'aircraft.csv'))
crew = pd.read_csv(os.path.join(DATA_DIR, 'crew.csv'))
time_slots = pd.read_csv(os.path.join(DATA_DIR, 'time_slots.csv'), header=None)[0].tolist()

# Enhanced data structures
# Aircraft-Crew Certification Matrix (which crews can fly which aircraft)
certification_matrix = pd.DataFrame({
    'AircraftID': ['A101', 'A102', 'A103', 'A104', 'A105', 'A106'],
    'C01': [1, 1, 0, 1, 0, 1],
    'C02': [1, 0, 1, 1, 1, 0],
    'C03': [0, 1, 1, 0, 1, 1],
    'C04': [1, 1, 1, 1, 0, 1],
    'C05': [0, 1, 1, 1, 1, 0],
    'C06': [1, 0, 1, 0, 1, 1],
    'C07': [1, 1, 0, 1, 1, 1],
    'C08': [0, 1, 1, 1, 0, 1]
}).set_index('AircraftID')

# Gateway-Aircraft Compatibility Matrix
gateways = ['SDF', 'ORD', 'JFK', 'ATL', 'LAX', 'DFW']
gateway_compatibility = pd.DataFrame({
    'AircraftID': ['A101', 'A102', 'A103', 'A104', 'A105', 'A106'],
    'SDF': [1, 1, 1, 1, 1, 1],
    'ORD': [1, 1, 1, 1, 1, 1],
    'JFK': [1, 1, 1, 1, 0, 1],  # A105 too large for JFK
    'ATL': [1, 1, 1, 1, 1, 1],
    'LAX': [1, 1, 1, 1, 1, 1],
    'DFW': [1, 1, 1, 1, 1, 1]
}).set_index('AircraftID')

# Cargo priority multipliers (higher = more important)
cargo_priorities = {
    10: 3.0,  # Medical/emergency
    9: 2.5,   # Next-day air
    8: 2.0,   # Priority
    7: 1.5,   # High priority
    6: 1.2,   # Medium-high
    5: 1.0,   # Standard
    4: 0.8,   # Medium-low
    3: 0.6,   # Low priority
    2: 0.4,   # Economy
    1: 0.2    # Ground
}

# Helper: convert HH:MM to minutes
parse_time = lambda t: int(t.split(":")[0]) * 60 + int(t.split(":")[1])

# Preprocess times
flights['ScheduledDepartureMin'] = flights['ScheduledDeparture'].apply(parse_time)
flights['SLADeliveryTimeMin'] = flights['SLADeliveryTime'].apply(parse_time)
aircraft['ReadyTimeMin'] = aircraft['ReadyTime'].apply(parse_time)
crew['DutyStartMin'] = crew['DutyStart'].apply(parse_time)

# Add cargo priority multipliers to flights
flights['PriorityMultiplier'] = flights['CargoPriorityScore'].map(cargo_priorities)

# Model
model = gp.Model("EnhancedFlightScheduler")

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
# Gateway compatibility violation
gateway_violation = model.addVars(flights.index, vtype=GRB.BINARY, name="gateway_violation")

# Penalty variables
minutes_delayed = model.addVars(flights.index, vtype=GRB.INTEGER, name="minutes_delayed")
overtime = model.addVars(crew.index, vtype=GRB.INTEGER, name="overtime")
fuel_cost = model.addVars(flights.index, vtype=GRB.INTEGER, name="fuel_cost")

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
    
    # 2. Departure time must be within time_slots
    model.addConstr(departure_time[f_idx] >= 0, name=f"dep_time_lb_{f_idx}")
    model.addConstr(departure_time[f_idx] <= len(time_slots) - 1, name=f"dep_time_ub_{f_idx}")
    
    # 3. Delay calculation
    scheduled = flight['ScheduledDepartureMin']
    model.addConstr(minutes_delayed[f_idx] >= (gp.quicksum(parse_time(time_slots[t]) * is_time[f_idx, t] for t in range(len(time_slots))) - scheduled), name=f"delay_calc_{f_idx}")
    model.addConstr(minutes_delayed[f_idx] >= 0, name=f"delay_nonneg_{f_idx}")
    
    # 4. SLA missed
    sla_deadline = flight['SLADeliveryTimeMin']
    model.addConstr(
        gp.quicksum(parse_time(time_slots[t]) * is_time[f_idx, t] for t in range(len(time_slots))) <= sla_deadline + 10000 * sla_missed[f_idx],
        name=f"sla_miss_logic1_{f_idx}")
    model.addConstr(
        gp.quicksum(parse_time(time_slots[t]) * is_time[f_idx, t] for t in range(len(time_slots))) >= sla_deadline + 1 - 10000 * (1 - sla_missed[f_idx]),
        name=f"sla_miss_logic2_{f_idx}")
    
    # 5. Aircraft-Crew Certification
    for a_idx, ac in aircraft.iterrows():
        for c_idx, cr in crew.iterrows():
            if certification_matrix.loc[ac['AircraftID'], cr['CrewID']] == 0:
                model.addConstr(aircraft_used[f_idx, a_idx] + crew_assigned[f_idx, c_idx] <= 1, name=f"cert_{f_idx}_{a_idx}_{c_idx}")
    
    # 6. Gateway-Aircraft Compatibility
    origin = flight['Origin']
    for a_idx, ac in aircraft.iterrows():
        if gateway_compatibility.loc[ac['AircraftID'], origin] == 0:
            model.addConstr(aircraft_used[f_idx, a_idx] <= gateway_violation[f_idx], name=f"gateway_origin_{f_idx}_{a_idx}")
    
    destination = flight['Destination']
    for a_idx, ac in aircraft.iterrows():
        if gateway_compatibility.loc[ac['AircraftID'], destination] == 0:
            model.addConstr(aircraft_used[f_idx, a_idx] <= gateway_violation[f_idx], name=f"gateway_dest_{f_idx}_{a_idx}")

# 7. Aircraft cannot be double-booked or used if maintenance is required
for a_idx, ac in aircraft.iterrows():
    for t in range(len(time_slots)):
        # At most one flight per aircraft at a time slot
        model.addConstr(
            gp.quicksum(aircraft_used[f_idx, a_idx] * is_time[f_idx, t]
                        for f_idx in flights.index) <= 1,
            name=f"ac_no_double_{a_idx}_{t}")
    # If in maintenance OR maintenance is due, cannot be used
    if ac['InMaintenance'] == 'TRUE' or ac['MaintenanceDue'] <= 0:
        for f_idx in flights.index:
            model.addConstr(aircraft_used[f_idx, a_idx] == 0, name=f"ac_maint_{a_idx}_{f_idx}")

# 8. Crew cannot be double-booked, must not exceed duty hours
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

# 9. Turnaround time between flights for same aircraft
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

# 10. Flight window (e.g., 2-8 AM)
FLIGHT_WINDOW_START = parse_time('02:00')
FLIGHT_WINDOW_END = parse_time('08:00')
for f_idx in flights.index:
    model.addConstr(
        gp.quicksum(parse_time(time_slots[t]) * is_time[f_idx, t] for t in range(len(time_slots))) >= FLIGHT_WINDOW_START,
        name=f"window_start_{f_idx}")
    model.addConstr(
        gp.quicksum(parse_time(time_slots[t]) * is_time[f_idx, t] for t in range(len(time_slots))) <= FLIGHT_WINDOW_END,
        name=f"window_end_{f_idx}")

# 11. Fuel cost calculation (simplified - based on distance and aircraft type)
for f_idx, flight in flights.iterrows():
    # Base fuel cost for the flight
    base_fuel = flight['DurationMinutes'] * 2  # $2 per minute of flight
    model.addConstr(fuel_cost[f_idx] >= base_fuel, name=f"fuel_base_{f_idx}")
    # Additional fuel cost for delays (more fuel needed for longer flights)
    model.addConstr(fuel_cost[f_idx] >= base_fuel + minutes_delayed[f_idx], name=f"fuel_delay_{f_idx}")

# Enhanced Objective Function
model.setObjective(
    gp.quicksum(DELAY_PENALTY * minutes_delayed[f_idx] * flights.loc[f_idx, 'PriorityMultiplier'] for f_idx in flights.index) +
    gp.quicksum(SLA_PENALTY * sla_missed[f_idx] * flights.loc[f_idx, 'PriorityMultiplier'] for f_idx in flights.index) +
    gp.quicksum(10 * overtime[c_idx] for c_idx in crew.index) +
    gp.quicksum(FUEL_PENALTY * fuel_cost[f_idx] for f_idx in flights.index) +
    gp.quicksum(GATEWAY_PENALTY * gateway_violation[f_idx] for f_idx in flights.index),
    GRB.MINIMIZE)

model.optimize()

# Enhanced Output Results
print("\n===== ENHANCED OPTIMIZED SCHEDULE =====")
for f_idx, flight in flights.iterrows():
    dep_slot = int(departure_time[f_idx].x)
    dep_time = time_slots[dep_slot]
    ac_idx = [a for a in aircraft.index if aircraft_used[f_idx, a].x > 0.5][0]
    cr_idx = [c for c in crew.index if crew_assigned[f_idx, c].x > 0.5][0]
    ac_id = aircraft.loc[ac_idx, 'AircraftID']
    cr_id = crew.loc[cr_idx, 'CrewID']
    sla_miss = int(sla_missed[f_idx].x)
    gw_viol = int(gateway_violation[f_idx].x)
    priority = flight['CargoPriorityScore']
    
    print(f"Flight {flight['FlightNumber']} (Priority {priority}) departs at {dep_time}")
    print(f"  Aircraft: {ac_id}, Crew: {cr_id}")
    print(f"  SLA Missed: {sla_miss}, Gateway Violation: {gw_viol}")

print("\n===== ENHANCED PENALTIES =====")
print(f"Total Objective Value: {model.ObjVal}")

print("\nFlight Details:")
for f_idx in flights.index:
    flight = flights.loc[f_idx]
    delay = int(minutes_delayed[f_idx].x)
    sla_miss = int(sla_missed[f_idx].x)
    fuel = int(fuel_cost[f_idx].x)
    gw_viol = int(gateway_violation[f_idx].x)
    priority = flight['CargoPriorityScore']
    
    print(f"Flight {flight['FlightNumber']} (Priority {priority}):")
    print(f"  Delay: {delay} min, SLA Missed: {sla_miss}")
    print(f"  Fuel Cost: ${fuel}, Gateway Violation: {gw_viol}")

print("\nCrew Overtime:")
for c_idx in crew.index:
    ot = int(overtime[c_idx].x)
    if ot > 0:
        print(f"Crew {crew.loc[c_idx, 'CrewID']} overtime: {ot} min")

print("\nResource Utilization:")
available_aircraft = len([a for a_idx, a in aircraft.iterrows() if a['InMaintenance'] != 'TRUE' and a['MaintenanceDue'] > 0])
used_aircraft = sum(1 for a_idx in aircraft.index for f_idx in flights.index if aircraft_used[f_idx, a_idx].x > 0.5)
print(f"Aircraft: {used_aircraft}/{available_aircraft} available aircraft used")

available_crew = len(crew)
used_crew = sum(1 for c_idx in crew.index for f_idx in flights.index if crew_assigned[f_idx, c_idx].x > 0.5)
print(f"Crew: {used_crew}/{available_crew} crew members used") 