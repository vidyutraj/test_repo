import pandas as pd
import gurobipy as gp
from gurobipy import GRB
import os
import sys
import json
from datetime import datetime

# Load config
try:
    import config
    MIN_TURNAROUND = config.MinTurnaroundTimeMinutes
    MAX_DUTY_HOURS = config.MaxCrewDutyHours
    SLA_PENALTY = config.SlaPenalty
    DELAY_PENALTY = config.DelayPenalty
    GATEWAY_PENALTY = getattr(config, 'GatewayPenalty', 20)
    VOLUME_PENALTY = getattr(config, 'VolumePenalty', 15)
    HAZMAT_PENALTY = getattr(config, 'HazmatPenalty', 25)
except ImportError:
    print("config.py not found. Please provide config.py or constraints.json.")
    sys.exit(1)

class ConstraintManager:
    def __init__(self):
        self.DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
        self.load_data()
        self.previous_schedule = None
        self.previous_objective = None
        
    def load_data(self):
        """Load all data files"""
        self.flights = pd.read_csv(os.path.join(self.DATA_DIR, 'enhanced_flights.csv'))
        self.aircraft = pd.read_csv(os.path.join(self.DATA_DIR, 'aircraft.csv'))
        self.crew = pd.read_csv(os.path.join(self.DATA_DIR, 'crew.csv'))
        self.time_slots = pd.read_csv(os.path.join(self.DATA_DIR, 'time_slots.csv'), header=None)[0].tolist()
        
        # Load enhanced data files
        self.certification_matrix = pd.read_csv(os.path.join(self.DATA_DIR, 'aircraft_crew_certification.csv')).set_index('AircraftID')
        self.gateway_compatibility = pd.read_csv(os.path.join(self.DATA_DIR, 'gateway_aircraft_compatibility.csv')).set_index('AircraftID')
        self.aircraft_specs = pd.read_csv(os.path.join(self.DATA_DIR, 'aircraft_specifications.csv')).set_index('AircraftID')
        
        # Merge aircraft specs
        self.aircraft = self.aircraft.merge(self.aircraft_specs, on='AircraftID', how='left')
        
        # Preprocess data
        self._preprocess_data()
    
    def _preprocess_data(self):
        """Preprocess times and add priority multipliers"""
        # Helper: convert HH:MM to minutes
        parse_time = lambda t: int(t.split(":")[0]) * 60 + int(t.split(":")[1])
        
        # Preprocess times
        self.flights['ScheduledDepartureMin'] = self.flights['ScheduledDeparture'].apply(parse_time)
        self.flights['SLADeliveryTimeMin'] = self.flights['SLADeliveryTime'].apply(parse_time)
        self.aircraft['ReadyTimeMin'] = self.aircraft['ReadyTime'].apply(parse_time)
        self.crew['DutyStartMin'] = self.crew['DutyStart'].apply(parse_time)
        
        # Add cargo priority multipliers
        cargo_priorities = {
            10: 3.0, 9: 2.5, 8: 2.0, 7: 1.5, 6: 1.2,
            5: 1.0, 4: 0.8, 3: 0.6, 2: 0.4, 1: 0.2
        }
        self.flights['PriorityMultiplier'] = self.flights['CargoPriorityScore'].map(cargo_priorities)
    
    def update_crew_availability(self, crew_id, available):
        """Mark crew as available/unavailable"""
        # Update crew data
        self.crew.loc[self.crew['CrewID'] == crew_id, 'OnDuty'] = available
        
        # Save to file
        self.crew.to_csv(os.path.join(self.DATA_DIR, 'crew.csv'), index=False)
        
        # Log change
        self._log_change(f"Crew {crew_id} availability changed to {available}")
        
        # Reoptimize
        return self.reoptimize()
    
    def add_maintenance_alert(self, aircraft_id, hours):
        """Set aircraft maintenance due"""
        # Update aircraft data
        self.aircraft.loc[self.aircraft['AircraftID'] == aircraft_id, 'MaintenanceDue'] = hours
        
        # Save to file
        self.aircraft.to_csv(os.path.join(self.DATA_DIR, 'aircraft.csv'), index=False)
        
        # Log change
        self._log_change(f"Aircraft {aircraft_id} maintenance due in {hours} hours")
        
        # Reoptimize
        return self.reoptimize()
    
    def reoptimize(self):
        """Re-run optimization with current constraints"""
        # Store previous results
        if self.previous_schedule:
            old_schedule = self.previous_schedule
            old_objective = self.previous_objective
        else:
            old_schedule = None
            old_objective = None
        
        # Run optimization
        result = self._run_optimization()
        
        # Store new results
        self.previous_schedule = result['schedule']
        self.previous_objective = result['objective_value']
        
        # Compare with previous
        if old_schedule:
            changes = self._compare_schedules(old_schedule, result['schedule'])
            result['changes'] = changes
        else:
            result['changes'] = "Initial optimization"
        
        return result
    
    def _run_optimization(self):
        """Run the actual optimization"""
        # Create model
        model = gp.Model("ConstraintManagerOptimizer")
        
        # Decision variables
        departure_time = model.addVars(self.flights.index, vtype=GRB.INTEGER, name="departure_time")
        is_time = model.addVars(self.flights.index, range(len(self.time_slots)), vtype=GRB.BINARY, name="is_time")
        aircraft_used = model.addVars(self.flights.index, self.aircraft.index, vtype=GRB.BINARY, name="aircraft_used")
        crew_assigned = model.addVars(self.flights.index, self.crew.index, vtype=GRB.BINARY, name="crew_assigned")
        sla_missed = model.addVars(self.flights.index, vtype=GRB.BINARY, name="sla_missed")
        gateway_violation = model.addVars(self.flights.index, vtype=GRB.BINARY, name="gateway_violation")
        hazmat_violation = model.addVars(self.flights.index, vtype=GRB.BINARY, name="hazmat_violation")
        volume_violation = model.addVars(self.flights.index, vtype=GRB.BINARY, name="volume_violation")
        
        # Penalty variables
        minutes_delayed = model.addVars(self.flights.index, vtype=GRB.INTEGER, name="minutes_delayed")
        overtime = model.addVars(self.crew.index, vtype=GRB.INTEGER, name="overtime")
        
        # Helper function
        parse_time = lambda t: int(t.split(":")[0]) * 60 + int(t.split(":")[1])
        
        # Link is_time and departure_time
        for f_idx in self.flights.index:
            model.addConstr(gp.quicksum(is_time[f_idx, t] for t in range(len(self.time_slots))) == 1, name=f"one_time_{f_idx}")
            model.addConstr(departure_time[f_idx] == gp.quicksum(t * is_time[f_idx, t] for t in range(len(self.time_slots))), name=f"dep_time_link_{f_idx}")
        
        # Add all constraints (simplified version of your enhanced scheduler)
        # ... (This would be the full constraint set from your enhanced_scheduler_v2.py)
        # For brevity, I'm including a simplified version
        
        # Basic constraints
        for f_idx, flight in self.flights.iterrows():
            model.addConstr(aircraft_used.sum(f_idx, '*') == 1, name=f"one_aircraft_{f_idx}")
            model.addConstr(crew_assigned.sum(f_idx, '*') == 1, name=f"one_crew_{f_idx}")
            
            # Delay calculation
            scheduled = flight['ScheduledDepartureMin']
            model.addConstr(minutes_delayed[f_idx] >= (gp.quicksum(parse_time(self.time_slots[t]) * is_time[f_idx, t] for t in range(len(self.time_slots))) - scheduled), name=f"delay_calc_{f_idx}")
            model.addConstr(minutes_delayed[f_idx] >= 0, name=f"delay_nonneg_{f_idx}")
        
        # Aircraft constraints
        for a_idx, ac in self.aircraft.iterrows():
            for t in range(len(self.time_slots)):
                model.addConstr(gp.quicksum(aircraft_used[f_idx, a_idx] * is_time[f_idx, t] for f_idx in self.flights.index) <= 1, name=f"ac_no_double_{a_idx}_{t}")
            
            # Maintenance constraints
            if ac['InMaintenance'] == 'TRUE' or ac['MaintenanceDue'] <= 0:
                for f_idx in self.flights.index:
                    model.addConstr(aircraft_used[f_idx, a_idx] == 0, name=f"ac_maint_{a_idx}_{f_idx}")
        
        # Crew constraints
        for c_idx, cr in self.crew.iterrows():
            for t in range(len(self.time_slots)):
                model.addConstr(gp.quicksum(crew_assigned[f_idx, c_idx] * is_time[f_idx, t] for f_idx in self.flights.index) <= 1, name=f"crew_no_double_{c_idx}_{t}")
            
            # Only assign available crew
            if not cr['OnDuty']:
                for f_idx in self.flights.index:
                    model.addConstr(crew_assigned[f_idx, c_idx] == 0, name=f"crew_unavailable_{c_idx}_{f_idx}")
        
        # Objective function
        model.setObjective(
            gp.quicksum(DELAY_PENALTY * minutes_delayed[f_idx] * self.flights.loc[f_idx, 'PriorityMultiplier'] for f_idx in self.flights.index) +
            gp.quicksum(SLA_PENALTY * sla_missed[f_idx] * self.flights.loc[f_idx, 'PriorityMultiplier'] for f_idx in self.flights.index) +
            gp.quicksum(10 * overtime[c_idx] for c_idx in self.crew.index) +
            gp.quicksum(GATEWAY_PENALTY * gateway_violation[f_idx] for f_idx in self.flights.index) +
            gp.quicksum(HAZMAT_PENALTY * hazmat_violation[f_idx] for f_idx in self.flights.index) +
            gp.quicksum(VOLUME_PENALTY * volume_violation[f_idx] for f_idx in self.flights.index),
            GRB.MINIMIZE)
        
        # Optimize
        model.optimize()
        
        # Extract results
        schedule = self._extract_schedule(model)
        
        return {
            "objective_value": model.ObjVal,
            "schedule": schedule,
            "status": model.status
        }
    
    def _extract_schedule(self, model):
        """Extract schedule from solved model"""
        schedule = []
        for f_idx, flight in self.flights.iterrows():
            dep_slot = int(model.getVarByName(f"departure_time[{f_idx}]").x)
            dep_time = self.time_slots[dep_slot]
            
            # Find assigned aircraft and crew
            ac_idx = None
            cr_idx = None
            for a_idx in self.aircraft.index:
                if model.getVarByName(f"aircraft_used[{f_idx},{a_idx}]").x > 0.5:
                    ac_idx = a_idx
                    break
            
            for c_idx in self.crew.index:
                if model.getVarByName(f"crew_assigned[{f_idx},{c_idx}]").x > 0.5:
                    cr_idx = c_idx
                    break
            
            schedule.append({
                "flight_number": flight['FlightNumber'],
                "departure_time": dep_time,
                "aircraft": self.aircraft.loc[ac_idx, 'AircraftID'],
                "crew": self.crew.loc[cr_idx, 'CrewID'],
                "cargo_type": flight['CargoType'],
                "priority": flight['CargoPriorityScore'],
                "delay": int(model.getVarByName(f"minutes_delayed[{f_idx}]").x)
            })
        
        return schedule
    
    def get_current_schedule(self):
        """Return current schedule"""
        if self.previous_schedule:
            return {
                "schedule": self.previous_schedule,
                "objective_value": self.previous_objective
            }
        else:
            # Run initial optimization
            return self.reoptimize()
    
    def _compare_schedules(self, old_schedule, new_schedule):
        """Compare old and new schedules"""
        changes = []
        
        for old_flight, new_flight in zip(old_schedule, new_schedule):
            if old_flight['aircraft'] != new_flight['aircraft']:
                changes.append(f"Flight {old_flight['flight_number']}: Aircraft changed from {old_flight['aircraft']} to {new_flight['aircraft']}")
            
            if old_flight['crew'] != new_flight['crew']:
                changes.append(f"Flight {old_flight['flight_number']}: Crew changed from {old_flight['crew']} to {new_flight['crew']}")
            
            if old_flight['delay'] != new_flight['delay']:
                delay_diff = new_flight['delay'] - old_flight['delay']
                if delay_diff > 0:
                    changes.append(f"Flight {old_flight['flight_number']}: Delayed by {delay_diff} minutes")
                elif delay_diff < 0:
                    changes.append(f"Flight {old_flight['flight_number']}: Reduced delay by {abs(delay_diff)} minutes")
        
        return changes if changes else ["No changes detected"]
    
    def _log_change(self, change_description):
        """Log constraint changes"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {change_description}\n"
        
        # Append to log file
        with open(os.path.join(self.DATA_DIR, 'constraint_changes.log'), 'a') as f:
            f.write(log_entry) 