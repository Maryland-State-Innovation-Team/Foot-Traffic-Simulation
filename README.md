# Foot Traffic Simulation for Baltimore City

This repository simulates and visualizes detailed hourly foot traffic patterns in Baltimore City using U.S. Census data, LODES job flows, and OpenStreetMap (OSM) road and transit networks.

## Features
- Downloads and caches American Community Survey (ACS) and LODES data for Baltimore City
- Extracts and processes OSM road and transit data
- Simulates hourly foot traffic by census tract, commute mode, and time window
- Visualizes results as an animated heatmap GIF

## Installation

1. **Clone the repository:**
	```powershell
	git clone https://github.com/Maryland-State-Innovation-Team/Foot-Traffic-Simulation.git
	cd Foot-Traffic-Simulation
	```

2. **Install Python dependencies:**
	- It is recommended to use a virtual environment (e.g., `venv` or `conda`).
	- Install required packages:
	  ```powershell
	  pip install -r requirements.txt
	  ```

## Required API Keys

This project requires a U.S. Census API key to download ACS data.

1. **Obtain a Census API key:**
	- Register for free at: https://api.census.gov/data/key_signup.html

2. **Configure your API key:**
	- Open `simulate.py` and replace the placeholder:
	  ```python
	  CENSUS_API_KEY = "YOUR_CENSUS_API_KEY"
	  ```
	  with your actual API key string.

## Usage

Run the simulation and generate the animation:

```powershell
python simulate.py
```

The script will:
- Download and cache all required datasets (ACS, LODES, OSM) on first run
- Simulate hourly foot traffic for Baltimore City
- Save the results as a GeoJSON file in the `cache/` directory
- Generate an animated GIF (`foot_traffic_animation_detailed.gif`) visualizing hourly foot traffic

If cached data exists, the script will use it to speed up subsequent runs.

## Methodology Overview

1. **Data Acquisition:**
	- **ACS Data:** Downloads detailed commute mode and time-of-departure data by census tract for Baltimore City using the Census API.
	- **LODES Data:** Downloads job origin-destination (J2J) flows for Maryland, filtered to jobs within Baltimore City.
	- **OSM Data:** Downloads and caches the road network and transit features for Baltimore City using OSMnx.

2. **Simulation Logic:**
	- For each census tract, simulates workers by commute mode and time window, assigning home and work locations to road segments.
	- Uses LODES data to probabilistically assign work tracts for each home tract.
	- Simulates hourly presence on the road network, including time at home, work, and commuting, for each synthetic worker.
	- Aggregates foot traffic counts per road segment for each hour of the day.

3. **Visualization:**
	- Generates hourly heatmaps of foot traffic on the road network.
	- Creates an animated GIF showing the evolution of foot traffic over a 24-hour period.

## Output Files

- `cache/acs_detailed_commute_data.csv` — Cached ACS commute data
- `cache/lodes_od_md.csv.gz` — Cached LODES job flow data
- `cache/baltimore_roads.graphml` — Cached OSM road network
- `cache/baltimore_transit_expanded.geojson` — Cached OSM transit features
- `cache/foot_traffic_detailed.geojson` — Simulated hourly foot traffic (GeoJSON)
- `foot_traffic_animation_detailed.gif` — Animated heatmap of hourly foot traffic

## Notes

- The simulation is stochastic; results may vary between runs.
- The script is designed for Baltimore City but can be adapted to other locations by changing configuration variables in `simulate.py`.
- For large-scale runs, ensure sufficient memory and disk space for caching data.

## License

See [LICENSE](LICENSE) for details.
