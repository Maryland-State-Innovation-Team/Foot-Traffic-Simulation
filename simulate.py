import os
import cenpy
import pandas as pd
import geopandas as gpd
import numpy as np
import osmnx as ox
import networkx as nx
import matplotlib.pyplot as plt
import contextily as cx
from matplotlib.animation import FuncAnimation
import imageio
from shapely.geometry import Point

# --- Configuration ---
CENSUS_API_KEY = "YOUR_CENSUS_API_KEY"
CITY_NAME = "Baltimore, Maryland"
STATE_FIPS = '24' # Maryland
COUNTY_FIPS = '510' # Baltimore City
YEAR = 2023
LODES_YEAR = 2022

# --- Caching Directories ---
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# --- Data File Paths ---
ACS_DATA_FILE = os.path.join(CACHE_DIR, "acs_detailed_commute_data.csv")
LODES_FILE = os.path.join(CACHE_DIR, "lodes_od_md.csv.gz")
BALTIMORE_ROADS_FILE = os.path.join(CACHE_DIR, "baltimore_roads.graphml")
BALTIMORE_TRANSIT_FILE = os.path.join(CACHE_DIR, "baltimore_transit_expanded.geojson")
FOOT_TRAFFIC_CACHE = os.path.join(CACHE_DIR, "foot_traffic_detailed.geojson")
ANIMATION_FILE = "foot_traffic_animation_detailed.gif"


# --- Helper Functions ---

def get_acs_data(variables, file_path):
    """Downloads and caches detailed ACS data."""
    if os.path.exists(file_path):
        print(f"Loading cached ACS data from {file_path}...")
        return pd.read_csv(file_path, dtype={'GEOID': str})
    else:
        if CENSUS_API_KEY == "YOUR_CENSUS_API_KEY":
            raise ValueError("Please replace 'YOUR_CENSUS_API_KEY' with your actual Census API key.")
        print("Downloading detailed ACS data...")
        conn = cenpy.remote.APIConnection(f"ACSDT5Y{YEAR}")
        g_filter = {'state': STATE_FIPS, 'county': COUNTY_FIPS}
        data = conn.query(variables, geo_unit='tract', geo_filter=g_filter)
        data['GEOID'] = data['state'] + data['county'] + data['tract']
        data.to_csv(file_path, index=False)
        return data

def get_lodes_data(file_path):
    """Downloads and caches LODES data for the entire state."""
    if os.path.exists(file_path):
        print(f"Loading cached LODES data from {file_path}...")
        return pd.read_csv(file_path)
    else:
        print("Downloading LODES data...")
        url = f"https://lehd.ces.census.gov/data/lodes/LODES8/md/od/md_od_main_JT01_{LODES_YEAR}.csv.gz"
        data = pd.read_csv(url, dtype={'w_geocode': str, 'h_geocode': str})
        # Filter for jobs within Baltimore City
        data = data[data['w_geocode'].str.startswith(f"{STATE_FIPS}{COUNTY_FIPS}")]
        data.to_csv(file_path, index=False, compression='gzip')
        return data

def get_osm_data(roads_file, transit_file):
    """Downloads and caches OpenStreetMap data with expanded transit tags."""
    if os.path.exists(roads_file):
        print("Loading cached roads data...")
        roads = ox.load_graphml(roads_file)
    else:
        print("Downloading roads data...")
        roads = ox.graph_from_place(CITY_NAME, network_type='drive')
        ox.save_graphml(roads, roads_file)

    if os.path.exists(transit_file):
        print("Loading cached transit data...")
        transit = gpd.read_file(transit_file)
    else:
        print("Downloading expanded transit data...")
        tags = {
            "railway": "station",
            "public_transport": ["platform", "stop_position", "station"],
            "highway": "bus_stop",
            "amenity": "bus_station"
        }
        transit = ox.features_from_place(CITY_NAME, tags)
        transit.to_file(transit_file, driver='GeoJSON')
    return roads, transit

def define_acs_variables():
    """Defines the ACS variables and maps them to commute modes and times."""
    variables = {'B08006_017E': ('wfh', None)} # Work from home
    
    time_windows = {
        '12:00 a.m. to 4:59 a.m.': (0, 5), '5:00 a.m. to 5:29 a.m.': (5, 5.5),
        '5:30 a.m. to 5:59 a.m.': (5.5, 6), '6:00 a.m. to 6:29 a.m.': (6, 6.5),
        '6:30 a.m. to 6:59 a.m.': (6.5, 7), '7:00 a.m. to 7:29 a.m.': (7, 7.5),
        '7:30 a.m. to 7:59 a.m.': (7.5, 8), '8:00 a.m. to 8:29 a.m.': (8, 8.5),
        '8:30 a.m. to 8:59 a.m.': (8.5, 9), '9:00 a.m. to 9:59 a.m.': (9, 10),
        '10:00 a.m. to 10:59 a.m.': (10, 11), '11:00 a.m. to 11:59 a.m.': (11, 12),
        '12:00 p.m. to 3:59 p.m.': (12, 16), '4:00 p.m. to 11:59 p.m.': (16, 24)
    }
    
    modes = {
        'drive': range(17, 31),    # Drove alone
        'carpool': range(32, 46),  # Carpooled
        'transit': range(47, 61),  # Public transit
        'walk': range(62, 76),     # Walked
        'other': range(77, 91)     # Other means (incl. bicycle)
    }

    time_keys = list(time_windows.keys())
    for mode, r in modes.items():
        for i, var_num in enumerate(r):
            variables[f'B08132_{var_num:03}E'] = (mode, time_windows[time_keys[i]])
            
    return variables


# --- Main Simulation ---
def run_simulation():
    """Main function to run the detailed foot traffic simulation."""

    # --- 1. Data Acquisition and Preparation ---
    variable_map = define_acs_variables()
    acs_data = get_acs_data(list(variable_map.keys()), ACS_DATA_FILE)
    
    lodes_data = get_lodes_data(LODES_FILE)
    roads, transit = get_osm_data(BALTIMORE_ROADS_FILE, BALTIMORE_TRANSIT_FILE)
    
    nodes, edges = ox.graph_to_gdfs(roads)
    edges['foot_traffic'] = 0
    hourly_foot_traffic = {hour: edges.copy() for hour in range(24)}

    # --- 2. Simulation Logic ---
    print("Running detailed simulation...")
    
    # Get Baltimore census tracts geometry
    tracts_geo = cenpy.products.Decennial2020().from_place(CITY_NAME, level='tract', variables=['GEOID'])
    tracts_geo = tracts_geo.to_crs(edges.crs)

    for _, home_tract in acs_data.iterrows():
        home_tract_geoid = home_tract['GEOID']
        print(f"Simulating tract {home_tract_geoid}...")
        
        try:
            home_tract_geom = tracts_geo[tracts_geo['GEOID'] == home_tract_geoid].iloc[0].geometry
            roads_in_home_tract = edges[edges.intersects(home_tract_geom)]
            if roads_in_home_tract.empty:
                continue
        except IndexError:
            continue # Skip if tract geometry not found

        # J2J data for this specific home tract
        od_pairs = lodes_data[lodes_data['h_geocode'] == home_tract_geoid]

        for var, (mode, time_window) in variable_map.items():
            num_workers = int(home_tract[var])
            if num_workers <= 0:
                continue

            for _ in range(num_workers):
                # --- Assign Home ---
                home_edge = roads_in_home_tract.sample(1).iloc[0]
                
                # --- Sleep Schedule ---
                sleep_duration = np.random.uniform(5, 9)
                
                # --- Work from Home ---
                if mode == 'wfh':
                    work_start_hour = np.random.normal(9, 1) # Assume 9am start
                    sleep_start_hour = (work_start_hour - sleep_duration - 1 + 24) % 24
                    for hour in range(24):
                        if not (sleep_start_hour <= hour < (sleep_start_hour + sleep_duration) % 24):
                            hourly_foot_traffic[hour].loc[home_edge.name, 'foot_traffic'] += 1
                    continue # End simulation for this worker
                
                # --- Assign Work Location (based on J2J data) ---
                if od_pairs.empty:
                    continue # No destination data for this tract
                
                work_tract_geoid = od_pairs.sample(1, weights='S000').iloc[0]['w_geocode']
                try:
                    work_tract_geom = tracts_geo[tracts_geo['GEOID'] == work_tract_geoid].iloc[0].geometry
                    roads_in_work_tract = edges[edges.intersects(work_tract_geom)]
                    if roads_in_work_tract.empty:
                        continue
                    work_edge = roads_in_work_tract.sample(1).iloc[0]
                except (IndexError, ValueError):
                    continue

                # --- Assign Departure Time ---
                departure_hour = np.random.normal(loc=np.mean(time_window), scale=0.5)
                arrival_hour = departure_hour + np.random.uniform(0.25, 1.5) # Commute duration
                return_departure = arrival_hour + 8 # 8-hour workday
                return_arrival = return_departure + (arrival_hour - departure_hour)

                # --- Sleep Schedule ---
                sleep_start_hour = (departure_hour - sleep_duration - 1 + 24) % 24

                # --- Simulate 24h path ---
                for hour in range(24):
                    is_sleeping = (sleep_start_hour <= hour < (sleep_start_hour + sleep_duration)) or \
                                  ((sleep_start_hour + sleep_duration) > 24 and hour < (sleep_start_hour + sleep_duration) % 24)
                    
                    if is_sleeping:
                        continue
                    
                    if hour < departure_hour or hour >= return_arrival: # At home
                        hourly_foot_traffic[hour].loc[home_edge.name, 'foot_traffic'] += 1
                    elif arrival_hour <= hour < return_departure: # At work
                        hourly_foot_traffic[hour].loc[work_edge.name, 'foot_traffic'] += 1
                    elif departure_hour <= hour < arrival_hour: # Commuting to work
                        if mode in ['walk', 'other']:
                            try:
                                path = ox.shortest_path(roads, home_edge['u'], work_edge['v'], weight='length')
                                path_edges = ox.utils_graph.get_route_edge_attributes(roads, path)
                                for edge in path_edges:
                                    hourly_foot_traffic[hour].loc[(edge['u'], edge['v'], edge['key']), 'foot_traffic'] += 1
                            except nx.NetworkXNoPath:
                                hourly_foot_traffic[hour].loc[home_edge.name, 'foot_traffic'] += 1 # Default to home
                        elif mode == 'transit':
                            # Simplified: foot traffic to/from nearest transit
                            home_node = ox.nearest_nodes(roads, home_edge.geometry.centroid.x, home_edge.geometry.centroid.y)
                            work_node = ox.nearest_nodes(roads, work_edge.geometry.centroid.x, work_edge.geometry.centroid.y)
                            hourly_foot_traffic[hour].loc[home_edge.name, 'foot_traffic'] += 1
                            hourly_foot_traffic[hour].loc[work_edge.name, 'foot_traffic'] += 1


    # --- 3. Cache Foot Traffic Data ---
    print("Caching foot traffic data...")
    all_hours_list = []
    for hour, gdf in hourly_foot_traffic.items():
        gdf['hour'] = hour
        all_hours_list.append(gdf[gdf['foot_traffic'] > 0]) # Cache only edges with traffic
    
    all_hours_gdf = pd.concat(all_hours_list)
    all_hours_gdf.to_file(FOOT_TRAFFIC_CACHE, driver='GeoJSON')
    return all_hours_gdf

# --- Visualization ---
def create_animation(foot_traffic_data):
    """Creates an animated heatmap of foot traffic."""
    print("Creating animation...")
    if foot_traffic_data.empty:
        print("Foot traffic data is empty. Cannot create animation.")
        return

    filenames = []
    vmax = foot_traffic_data['foot_traffic'].quantile(0.99) # Clip for better visualization
    
    for hour in range(24):
        fig, ax = plt.subplots(figsize=(12, 12))
        hour_data = foot_traffic_data[foot_traffic_data['hour'] == hour]
        
        if hour_data.empty: continue

        hour_data.plot(ax=ax, linewidth=np.clip(hour_data['foot_traffic'] / vmax * 5, 0.1, 5),
                     edgecolor='purple', alpha=0.7)

        ax.set_title(f"Foot Traffic in Baltimore - {hour:02d}:00", fontsize=16)
        ax.set_xticks([])
        ax.set_yticks([])
        cx.add_basemap(ax, crs=hour_data.crs.to_string(), source=cx.providers.CartoDB.Positron)
        plt.tight_layout()

        filename = f"{CACHE_DIR}/frame_{hour:02d}.png"
        plt.savefig(filename, dpi=100)
        plt.close()
        filenames.append(filename)

    print("Building GIF...")
    with imageio.get_writer(ANIMATION_FILE, mode='I', duration=0.5) as writer:
        for filename in filenames:
            image = imageio.imread(filename)
            writer.append_data(image)

    for filename in filenames:
        os.remove(filename)

    print(f"Animation saved to {ANIMATION_FILE}")

# --- Main Execution ---
if __name__ == "__main__":
    if not os.path.exists(FOOT_TRAFFIC_CACHE):
        foot_traffic_data = run_simulation()
    else:
        print("Loading cached foot traffic data...")
        foot_traffic_data = gpd.read_file(FOOT_TRAFFIC_CACHE)

    if 'foot_traffic_data' in locals() and not foot_traffic_data.empty:
        create_animation(foot_traffic_data)
    else:
        print("Could not generate or load foot traffic data. Animation not created.")