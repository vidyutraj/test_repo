import requests
import pandas as pd
from datetime import datetime

# Your FlightAPI API key
API_KEY = '687524ac968111227a4f0d83'

# Parameters for the request
airport_iata = 'SDF'# change to the airport you want
day_offset = 1# 0 = today, 1 = tomorrow, etc.
mode = 'arrivals'# 'departures' or 'arrivals'

# Build the URL
url = f'https://api.flightapi.io/schedule/{API_KEY}?mode={mode}&iata={airport_iata}&day={day_offset}'

# Fetch the schedule
resp = requests.get(url)
resp.raise_for_status()
data = resp.json()
print(data)

# Extract the arrivals list
arrivals = data['airport']['pluginData']['schedule'][mode]['data']

# Filter for UPS arrivals and collect fields
ups_arrivals = []
for entry in arrivals:
    flight = entry.get('flight', {})
    airline = (flight.get('airline') or {}).get('name')
    if airline == 'UPS':
        times = flight.get('time', {})
        sched = times.get('scheduled', {}).get('arrival')
        est = times.get('estimated', {}).get('arrival')
        aircraft = flight.get('aircraft') or {}
        model = aircraft.get('model') or {}
        airport = flight.get('airport') or {}
        origin = airport.get('origin') or {}
        origin_code = origin.get('code') or {}

        ups_arrivals.append({
            'flight_number': flight.get('identification', {}).get('number', {}).get('default', ''),
            'tail_number': aircraft.get('registration', ''),
            'aircraft_type': model.get('text') or model.get('code', ''),
            'origin_name': origin.get('name', ''),
            'origin_code': origin_code.get('iata', ''),
            'scheduled_arrival': datetime.fromtimestamp(sched).isoformat() if sched else '',
            'estimated_arrival': datetime.fromtimestamp(est).isoformat() if est else ''
        })

# Create a DataFrame for easy viewing
df = pd.DataFrame(ups_arrivals)
print(df)

# Optionally export to CSV
df.to_csv('ups_arrivals.csv', index=False)