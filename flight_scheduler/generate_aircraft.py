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

def generate_aircraft_csv():
    """Generate aircraft.csv from arrivals.csv and reserve.csv"""
    
    # Read the input files
    try:
        arrivals_df = pd.read_csv('data/arrivals.csv')
        reserve_df = pd.read_csv('data/reserve.csv')
    except FileNotFoundError as e:
        print(f"Error: Could not find input file - {e}")
        return
    
    # Process arriving aircraft
    arriving_aircraft = []
    
    for _, row in arrivals_df.iterrows():
        # Convert arrival time to decimal hours
        arrival_hours = convert_time_to_hours(row['ArrivalTime'])
        
        # Determine CAT3 based on aircraft type and route
        cat3 = determine_cat3(row['AircraftType'], row['Distance'])
        
        arriving_aircraft.append({
            'AircraftType': row['AircraftType'],
            'TailNumber': row['TailNumber'],
            'CAT3': cat3,
            'MaintenanceHours': 0,  # Arriving aircraft are ready for use
            'ArrivalHours': arrival_hours
        })
    
    # Process reserve aircraft
    reserve_aircraft = []
    
    for _, row in reserve_df.iterrows():
        reserve_aircraft.append({
            'AircraftType': row['AircraftType'],
            'TailNumber': row['TailNumber'],
            'CAT3': row['CAT3'],
            'MaintenanceHours': row['HoursMaintenance'],
            'ArrivalHours': 0  # Reserve aircraft are already in Louisville
        })
    
    # Combine both datasets
    all_aircraft = arriving_aircraft + reserve_aircraft
    
    # Create DataFrame and save to CSV
    aircraft_df = pd.DataFrame(all_aircraft)
    
    # Sort by arrival hours (arriving aircraft first, then reserve)
    aircraft_df = aircraft_df.sort_values(['ArrivalHours', 'TailNumber'])
    
    # Save to CSV
    output_file = 'data/aircraft.csv'
    aircraft_df.to_csv(output_file, index=False)
    
    print(f"Generated {output_file} with {len(aircraft_df)} aircraft")
    print(f"- {len(arriving_aircraft)} arriving aircraft")
    print(f"- {len(reserve_aircraft)} reserve aircraft")
    
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
        print(f"Arriving aircraft (ArrivalHours > 0): {(aircraft_df['ArrivalHours'] > 0).sum()}")
        print(f"Reserve aircraft (ArrivalHours = 0): {(aircraft_df['ArrivalHours'] == 0).sum()}")
        
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
    print("Generating aircraft.csv from arrivals.csv and reserve.csv...")
    
    # Generate the aircraft CSV
    aircraft_df = generate_aircraft_csv()
    
    if aircraft_df is not None:
        # Validate the generated data
        validate_data()
        
        print("\nSample of generated data:")
        print(aircraft_df.head(10))
    else:
        print("Failed to generate aircraft.csv") 