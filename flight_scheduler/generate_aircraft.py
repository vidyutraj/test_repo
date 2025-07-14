import pandas as pd
import numpy as np
from datetime import datetime

def convert_time_to_hours(time_str):
    """Convert time string (HH:MM) to decimal hours"""
    try:
        hours, minutes = map(int, time_str.split(':'))
        return hours + minutes / 60.0
    except:
        return 0.0

def normalize_aircraft_type(ac_type):
    ac_type = str(ac_type).upper()
    if '747' in ac_type:
        return '747'
    if '767' in ac_type or '763' in ac_type:
        return '767'
    if '757' in ac_type or '752' in ac_type or '75V' in ac_type:
        return '757'
    if '737' in ac_type or 'A306' in ac_type or 'ABM' in ac_type:
        return 'A300'
    if 'MD11' in ac_type or 'M11' in ac_type:
        return 'MD11'
    return ac_type  # fallback, but should cover most cases

def generate_aircraft_csv():
    """Generate aircraft.csv with only AircraftType, CAT3, EstimatedArrival, MaintenanceDoneTime. CAT3 for arrivals is random 0/1, EstimatedArrival from estimated_arrival or scheduled_arrival for arrivals, spares keep CAT3 from reserve.csv and EstimatedArrival blank. AircraftType is normalized."""
    try:
        arrivals_df = pd.read_csv('data/arrivals.csv')
        reserve_df = pd.read_csv('data/reserve.csv')
    except FileNotFoundError as e:
        print(f"Error: Could not find input file - {e}")
        return

    # Fill EstimatedArrival: use estimated_arrival, fallback to scheduled_arrival
    estimated_arrival = arrivals_df.get('estimated_arrival', '')
    if 'scheduled_arrival' in arrivals_df.columns:
        estimated_arrival = estimated_arrival.fillna('')
        estimated_arrival = np.where(
            (estimated_arrival == '') | (estimated_arrival.isnull()),
            arrivals_df['scheduled_arrival'],
            estimated_arrival
        )

    n_arrivals = len(arrivals_df)
    arrivals_types = arrivals_df.get('aircraft_type', '').apply(normalize_aircraft_type)
    arrivals_out = pd.DataFrame({
        'AircraftType': arrivals_types,
        'CAT3': np.random.randint(0, 2, size=n_arrivals),
        'EstimatedArrival': estimated_arrival,
        'MaintenanceDoneTime': ''
    })

    reserve_types = reserve_df.get('AircraftType', '').apply(normalize_aircraft_type)
    reserve_out = pd.DataFrame({
        'AircraftType': reserve_types,
        'CAT3': reserve_df.get('CAT3', ''),
        'EstimatedArrival': '',
        'MaintenanceDoneTime': reserve_df.get('MaintenanceDoneTime', '')
    })

    aircraft_df = pd.concat([arrivals_out, reserve_out], ignore_index=True)
    output_file = 'data/aircraft.csv'
    aircraft_df.to_csv(output_file, index=False)
    print(f"Generated {output_file} with {len(aircraft_df)} aircraft")
    return aircraft_df

def determine_cat3(aircraft_type, distance):
    """Determine CAT3 capability based on aircraft type and route distance"""
    # Larger aircraft and longer routes typically have CAT3 capability
    if aircraft_type in ['747', '777', 'MD11']:
        return True
    elif aircraft_type == '767' and distance > 1000:
        return True
    elif aircraft_type == '757' and distance > 2000:
        return True
    elif aircraft_type == '737' and distance > 1500:
        return True
    else:
        return False

def validate_data():
    """Validate the generated aircraft data"""
    try:
        aircraft_df = pd.read_csv('data/aircraft.csv')
        
        print("\nData Validation:")
        print(f"Total aircraft: {len(aircraft_df)}")
        print(f"Unique tail numbers: {aircraft_df['TailNumber'].nunique()}")
        print(f"Aircraft types: {aircraft_df['AircraftType'].value_counts().to_dict()}")
        print(f"CAT3 capable: {aircraft_df['CAT3'].sum()}")
        print(f"Arriving aircraft (ArrivalTime not empty): {(aircraft_df['ArrivalTime'] != '').sum()}")
        print(f"Reserve aircraft (ArrivalTime empty): {(aircraft_df['ArrivalTime'] == '').sum()}")
        
        # Check for duplicate tail numbers
        duplicates = aircraft_df[aircraft_df['TailNumber'].duplicated()]
        if len(duplicates) > 0:
            print(f"WARNING: {len(duplicates)} duplicate tail numbers found!")
            print(duplicates['TailNumber'].tolist())
        else:
            print("✓ All tail numbers are unique")
            
    except FileNotFoundError:
        print("Error: aircraft.csv not found") 

if __name__ == "__main__":
    print("Generating aircraft.csv with only AircraftType, CAT3, EstimatedArrival, MaintenanceDoneTime...")
    generate_aircraft_csv() 