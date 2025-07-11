# Flight Scheduler Optimization

This project uses Gurobi to solve a resource-constrained flight rescheduling problem, assigning aircraft and crew to flights while minimizing delays, SLA violations, and rule violations.

## Data Files
- `data/flights.csv`: List of flights, priorities, and original assignments
- `data/aircraft.csv`: Aircraft status and maintenance
- `data/crew.csv`: Crew status and duty hours
- `data/time_slots.csv`: Discrete time slots for scheduling
- `config.py` or `constraints.json`: Penalties and constraint parameters

## How to Run
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the scheduler:
   ```bash
   python scheduler.py
   ```

## Model Overview
- **Objective:** Minimize total penalty from delays, SLA misses, overtime, and maintenance
- **Variables:** Departure times, aircraft/crew assignments, SLA indicators
- **Constraints:** Aircraft/crew availability, maintenance, duty hours, turnaround, flight windows

Edit the data files to try different scenarios! 