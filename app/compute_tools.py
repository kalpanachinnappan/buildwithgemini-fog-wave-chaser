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

"""Computational tools for California Fog Wave Chaser."""

from typing import Any, Dict, Optional
from app.firestore_db import get_fog_viewpoint, list_fog_viewpoints
from app.weather_tools import get_fog_wave_forecast


def calculate_fog_wave_index(
    viewpoint_id: Optional[str] = None,
    location_name: Optional[str] = None,
    manual_inversion_height_ft: Optional[int] = None,
) -> Dict[str, Any]:
    """Computes the Fog Wave Score Index (0-100%) for a viewpoint.

    Evaluates whether coastal fog will cascade below the viewpoint like ocean waves
    by calculating:
      1. Elevation Delta: Is the viewpoint safely above the marine layer ceiling?
      2. Optimal Inversion Match: Is the fog bank high enough to crest ridge saddles without socking in the peak?
      3. Atmospheric Moisture: Dew point depression and relative humidity.
      4. Wind Dynamics: Gentle offshore / NW winds (4-12 mph) that push fog over saddles.

    Args:
        viewpoint_id: Unique identifier of the viewpoint (e.g., 'mount-tamalpais-east-peak', 'hawk-hill-marin-headlands').
        location_name: Common name of the spot (used if viewpoint_id not provided, e.g. 'Mount Tamalpais').
        manual_inversion_height_ft: Optional estimated or pilot-reported inversion ceiling in feet.
            If omitted, estimated from barometric surface pressure and dew point spread.

    Returns:
        A dictionary containing the calculated score (0-100%), condition verdict,
        score breakdown, and photographic recommendation.
    """
    # 1. Resolve viewpoint from Firestore
    spot: Optional[Dict[str, Any]] = None
    if viewpoint_id:
        res = get_fog_viewpoint(viewpoint_id)
        if "error" not in res:
            spot = res

    if not spot:
        search_term = location_name or viewpoint_id or "Mount Tamalpais"
        all_spots = list_fog_viewpoints()
        for s in all_spots:
            if search_term.lower() in s.get("name", "").lower() or search_term.lower() in s.get("id", "").lower():
                spot = s
                break

    if not spot:
        # Default fallback to Mount Tamalpais
        spot = {
            "id": "mount-tamalpais-east-peak",
            "name": "Mount Tamalpais - East Peak",
            "elevation_ft": 2571,
            "optimal_inversion_min_ft": 1200,
            "optimal_inversion_max_ft": 2200,
            "facing_direction": "South / West over Pacific & Marin Hills",
        }

    elevation_ft = spot.get("elevation_ft", 2500)
    opt_min = spot.get("optimal_inversion_min_ft", 1000)
    opt_max = spot.get("optimal_inversion_max_ft", 2200)
    spot_name = spot.get("name", "Unknown Viewpoint")

    # 2. Fetch live atmospheric data
    weather = get_fog_wave_forecast(location_name=spot_name)
    humidity = weather.get("relative_humidity_percent", 50) or 50
    spread_c = weather.get("dew_point_spread_c", 5.0) or 5.0
    wind_mph = weather.get("wind_speed_mph", 5.0) or 5.0
    low_clouds = weather.get("low_cloud_cover_percent", 0) or 0

    # 3. Estimate marine layer inversion height if not manually supplied
    # In SF Bay Area, Lawrence (1995) formula / standard adiabatic approximation:
    # cloud base ~ 400 * (temp_f - dew_f), inversion top ~ base + 800-1200ft
    if manual_inversion_height_ft is not None:
        inversion_ft = manual_inversion_height_ft
    else:
        temp_f = weather.get("temperature_f", 65.0) or 65.0
        dew_f = weather.get("dew_point_f", 50.0) or 50.0
        est_cloud_base = max(300, int(400 * max(0, temp_f - dew_f)))
        inversion_ft = min(2800, est_cloud_base + 800)

    # 4. Score components (total max 100)
    # A. Inversion Height vs Viewpoint (max 40 pts)
    height_score = 0
    if inversion_ft >= elevation_ft:
        # Socked in: summit is inside or below the fog cloud
        height_score = 5
        verdict_status = "Socked In (Peak in clouds)"
    elif opt_min <= inversion_ft <= opt_max:
        # Perfect sweet spot: fog is below the peak and above the saddles
        ratio = (inversion_ft - opt_min) / max(1, (opt_max - opt_min))
        # Peak score around the middle-to-high of the optimal band
        height_score = int(35 + 5 * (1 - abs(ratio - 0.75)))
        verdict_status = "Prime Fog Wave Elevation"
    elif inversion_ft < opt_min:
        # Too low: fog is sitting flat on the ocean and not rolling over saddles
        height_score = max(5, int(25 * (inversion_ft / max(1, opt_min))))
        verdict_status = "Low Fog (Flat marine layer, little wave action)"
    else:
        # Just below peak
        height_score = 30
        verdict_status = "High Inversion (Fog cresting near summit)"

    # B. Moisture / Condensation (max 30 pts)
    moisture_score = 0
    if spread_c <= 1.5 and humidity >= 85:
        moisture_score = 30
    elif spread_c <= 3.0 and humidity >= 75:
        moisture_score = 22
    elif spread_c <= 5.0 and humidity >= 60:
        moisture_score = 15
    else:
        moisture_score = max(2, int(10 * (humidity / 100)))

    # C. Cloud Cover Density (max 15 pts)
    cloud_score = int(15 * (low_clouds / 100)) if low_clouds > 0 else (10 if humidity > 75 else 2)

    # D. Wind Dynamics (max 15 pts) - Ideal wind is 4 to 12 mph
    wind_score = 0
    if 4.0 <= wind_mph <= 12.0:
        wind_score = 15
    elif 2.0 <= wind_mph < 4.0 or 12.0 < wind_mph <= 18.0:
        wind_score = 9
    elif wind_mph > 18.0:
        wind_score = 4  # Too turbulent, tears fog apart
    else:
        wind_score = 5  # Too stagnant

    total_score = min(100, max(0, height_score + moisture_score + cloud_score + wind_score))

    if total_score >= 80:
        verdict = "🔥 EPIC CONDITIONS: Spectacular cascading fog waves highly likely!"
        photo_tip = "Bring telephoto (70-200mm) and wide angle. Shoot continuous time-lapse as fog spills over ridges."
    elif total_score >= 60:
        verdict = "✨ GOOD CONDITIONS: Solid chance of rolling fog banks along coastal saddles."
        photo_tip = "Position camera facing the coastal saddles during golden hour. Look for backlit crests."
    elif total_score >= 40:
        verdict = "🌤️ MODERATE / VARIABLE: Patchy fog or subtle rolls possible."
        photo_tip = "Check live webcams before heading out; conditions could build near sunset."
    else:
        verdict = "❌ LOW PROBABILITY: Atmosphere is too dry, too windy, or cloud deck is out of position."
        photo_tip = "Standard golden hour landscape photography recommended; fog waves unlikely today."

    return {
        "viewpoint_name": spot_name,
        "viewpoint_id": spot.get("id"),
        "viewpoint_elevation_ft": elevation_ft,
        "inversion_ceiling_ft": inversion_ft,
        "optimal_range_ft": f"{opt_min}ft - {opt_max}ft",
        "fog_wave_score_percent": total_score,
        "verdict": verdict,
        "verdict_status": verdict_status,
        "photo_tip": photo_tip,
        "metrics_breakdown": {
            "elevation_alignment_score": f"{height_score}/40",
            "moisture_score": f"{moisture_score}/30",
            "low_cloud_density_score": f"{cloud_score}/15",
            "wind_dynamics_score": f"{wind_score}/15",
            "relative_humidity": f"{humidity}%",
            "dew_point_spread": f"{spread_c}°C",
            "wind_speed": f"{wind_mph} mph",
        },
    }
