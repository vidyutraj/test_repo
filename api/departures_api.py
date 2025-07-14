import requests
import pandas as pd
from datetime import datetime
import csv

# Your FlightAPI API key
API_KEY = '6875130742e2aa2315bcda25'

# Parameters for the request
airport_iata = 'SDF'# change to the airport you want
day_offset = 1# 0 = today, 1 = tomorrow, etc.
mode = 'departures'# 'departures' or 'arrivals'

# Build the URL
url = f'https://api.flightapi.io/schedule/{API_KEY}?mode={mode}&iata={airport_iata}&day={day_offset}'

# Fetch the schedule
resp = requests.get(url)
resp.raise_for_status()
data = resp.json()

# Extract the departures list
departures = data['airport']['pluginData']['schedule'][mode]['data']

# Filter for UPS flights and collect fields
ups_flights = []
for entry in departures:
    flight = entry['flight']
    if flight.get('airline', {}).get('name') == 'UPS':
        ups_flights.append({
            'FlightNumber': flight['identification']['number']['default'],
            'TailNumber': flight['aircraft']['registration'],
            'AircraftType': flight['aircraft']['model'].get('text') or flight['aircraft']['model']['code'],
            'DestinationAirportName': flight['airport']['destination']['name'],
            'DestinationAirportCode': flight['airport']['destination']['code']['iata'],
            'ScheduledDeparture': datetime.fromtimestamp(flight['time']['scheduled']['departure']).isoformat(),
            'EstimatedDeparture': datetime.fromtimestamp(flight['time']['estimated']['departure']).isoformat()
        })

# Create a DataFrame for easy viewing
if ups_flights:
    df = pd.DataFrame(ups_flights)
    print(df)
else:
    print('No UPS flights found.')

csv_fields = [
    'FlightNumber', 'TailNumber', 'AircraftType',
    'DestinationAirportName', 'DestinationAirportCode',
    'ScheduledDeparture', 'EstimatedDeparture'
]

with open('schedule.csv', 'w', newline='') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=csv_fields)
    writer.writeheader()
    for row in ups_flights:
        writer.writerow(row)

print(f'Saved {len(ups_flights)} UPS flights to schedule.csv')