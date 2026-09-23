# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Weather and marine layer tools for California Fog Wave Chaser."""

import json
from typing import Any, Dict, Optional
import urllib.parse
import urllib.request

# Default coastal coordinates for known hot spots
KNOWN_COORDINATES = {
    "mount-tamalpais": (37.9235, -122.5965),
    "mount tamalpais": (37.9235, -122.5965),
    "mt tam": (37.9235, -122.5965),
    "hawk-hill": (37.8282, -122.4996),
    "hawk hill": (37.8282, -122.4996),
    "marin headlands": (37.8282, -122.4996),
    "twin peaks": (37.7544, -122.4477),
    "twin-peaks": (37.7544, -122.4477),
    "pacifica": (37.6138, -122.4869),
    "sweeney ridge": (37.6138, -122.4869),
    "san francisco": (37.7749, -122.4194),
    "sf": (37.7749, -122.4194),
}


def get_fog_wave_forecast(
    location_name: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> Dict[str, Any]:
    """Fetches real-time coastal weather and atmospheric conditions to predict fog waves.

    Retrieves temperature, dew point depression, relative humidity, low-level cloud cover,
    wind speed, and wind direction for California coastal photography viewpoints.

    Args:
        location_name: Name of the spot or area (e.g., 'Mount Tamalpais', 'Hawk Hill', 'Twin Peaks', 'Pacifica').
        latitude: Latitude coordinate if known (overrides location_name if both lat & lon provided).
        longitude: Longitude coordinate if known (overrides location_name if both lat & lon provided).

    Returns:
        A dictionary containing real-time weather metrics, estimated cloud/fog conditions, and a preliminary assessment.
    """
    target_lat = latitude
    target_lon = longitude
    resolved_name = location_name or "Custom Coordinates"

    if (target_lat is None or target_lon is None) and location_name:
        loc_key = location_name.lower().strip()
        for k, coords in KNOWN_COORDINATES.items():
            if k in loc_key:
                target_lat, target_lon = coords
                resolved_name = location_name
                break

    # Fallback to Mt. Tamalpais if no valid location could be resolved
    if target_lat is None or target_lon is None:
        target_lat, target_lon = KNOWN_COORDINATES["mount-tamalpais"]
        resolved_name = location_name or "Mount Tamalpais"

    params = {
        "latitude": target_lat,
        "longitude": target_lon,
        "current": (
            "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,"
            "surface_pressure,wind_speed_10m,wind_direction_10m,cloud_cover,cloud_cover_low"
        ),
        "hourly": "temperature_2m,relative_humidity_2m,cloud_cover_low,wind_speed_10m",
        "forecast_days": 1,
        "timezone": "America/Los_Angeles",
    }

    url = f"https://api.open-meteo.com/v1/forecast?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "FogWaveChaserAgent/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        current = data.get("current", {})
        temp_c = current.get("temperature_2m")
        dew_c = current.get("dew_point_2m")
        humidity = current.get("relative_humidity_2m")
        wind_speed_kmh = current.get("wind_speed_10m")
        wind_dir = current.get("wind_direction_10m")
        low_clouds = current.get("cloud_cover_low")

        temp_f = round(temp_c * 9 / 5 + 32, 1) if temp_c is not None else None
        dew_f = round(dew_c * 9 / 5 + 32, 1) if dew_c is not None else None
        wind_mph = round(wind_speed_kmh * 0.621371, 1) if wind_speed_kmh is not None else None

        # Dew point spread: smaller spread (< 2.5°C / 4.5°F) indicates condensation/fog formation
        spread_c = round(temp_c - dew_c, 1) if (temp_c is not None and dew_c is not None) else None

        # Fog assessment
        if spread_c is not None and spread_c <= 2.5 and humidity >= 85:
            fog_presence = "Dense marine layer / fog present or forming"
        elif spread_c is not None and spread_c <= 4.0 and humidity >= 70:
            fog_presence = "Moderate moisture / patchy fog potential"
        else:
            fog_presence = "Dry / clear conditions, low fog probability"

        return {
            "location": resolved_name,
            "coordinates": {"latitude": target_lat, "longitude": target_lon},
            "timestamp": current.get("time"),
            "temperature_f": temp_f,
            "dew_point_f": dew_f,
            "dew_point_spread_c": spread_c,
            "relative_humidity_percent": humidity,
            "wind_speed_mph": wind_mph,
            "wind_direction_degrees": wind_dir,
            "low_cloud_cover_percent": low_clouds,
            "fog_status": fog_presence,
        }

    except Exception as e:
        return {
            "error": f"Failed to retrieve weather forecast for {resolved_name}: {str(e)}",
            "location": resolved_name,
        }


def get_golden_hour_times(
    location_name: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    date: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetches exact golden hour, blue hour, sunrise, and sunset times for fog photography.

    Calls the free public SunriseSunset.io API to get optimal lighting windows, solar azimuth,
    and twilight timings for planning fog wave photoshoots.

    Args:
        location_name: Name of the spot or area (e.g., 'Mount Tamalpais', 'Hawk Hill', 'Twin Peaks', 'Pacifica').
        latitude: Latitude coordinate (optional if location_name is provided).
        longitude: Longitude coordinate (optional if location_name is provided).
        date: Optional date in YYYY-MM-DD format (defaults to current date).

    Returns:
        A dictionary with golden hour morning/evening windows, blue hour windows, sunrise/sunset, and solar angles.
    """
    target_lat = latitude
    target_lon = longitude
    resolved_name = location_name or "Custom Location"

    if (target_lat is None or target_lon is None) and location_name:
        loc_key = location_name.lower().strip()
        for k, coords in KNOWN_COORDINATES.items():
            if k in loc_key:
                target_lat, target_lon = coords
                resolved_name = location_name
                break

    if target_lat is None or target_lon is None:
        target_lat, target_lon = KNOWN_COORDINATES["mount-tamalpais"]
        resolved_name = location_name or "Mount Tamalpais"

    params = {
        "lat": target_lat,
        "lng": target_lon,
        "timezone": "America/Los_Angeles",
    }
    if date:
        params["date"] = date

    url = f"https://api.sunrisesunset.io/json?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "FogWaveChaserAgent/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if data.get("status") != "OK":
            return {"error": f"API returned status {data.get('status')}", "location": resolved_name}

        results = data.get("results", {})
        return {
            "location": resolved_name,
            "coordinates": {"latitude": target_lat, "longitude": target_lon},
            "date": results.get("date"),
            "sunrise": results.get("sunrise"),
            "sunset": results.get("sunset"),
            "dawn": results.get("dawn"),
            "dusk": results.get("dusk"),
            "golden_hour_morning": results.get("golden_hour_morning"),
            "golden_hour_evening": results.get("golden_hour_evening"),
            "blue_hour_morning": results.get("blue_hour_morning"),
            "blue_hour_evening": results.get("blue_hour_evening"),
            "sun_azimuth": results.get("sun_azimuth"),
            "sunset_azimuth": results.get("sunset_azimuth"),
        }
    except Exception as e:
        return {
            "error": f"Failed to retrieve golden hour times for {resolved_name}: {str(e)}",
            "location": resolved_name,
        }

