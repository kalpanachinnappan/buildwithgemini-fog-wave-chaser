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

"""Firestore client and tools for California Fog Wave Chaser."""

from typing import Any, Dict, List, Optional
from google.cloud import firestore

# Hardcoded project ID as required to avoid project number issues on Agent Platform
PROJECT_ID = "qwiklabs-gcp-04-d19134fd9a80"
COLLECTION_NAME = "viewpoints"


def get_firestore_client() -> firestore.Client:
    """Returns a Firestore client initialized with the hardcoded project ID."""
    return firestore.Client(project=PROJECT_ID)


def list_fog_viewpoints(region: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves fog viewpoints and photography spots from Firestore.

    Args:
        region: Optional region to filter viewpoints by (e.g., "Marin County", "San Francisco", "Pacifica", "Big Sur").

    Returns:
        A list of viewpoint records with details including elevation, optimal marine layer range, facing direction, and notes.
    """
    db = get_firestore_client()
    collection_ref = db.collection(COLLECTION_NAME)

    if region:
        query = collection_ref.where("region", "==", region)
        docs = query.stream()
    else:
        docs = collection_ref.stream()

    viewpoints = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        viewpoints.append(data)

    return viewpoints


def get_fog_viewpoint(viewpoint_id: str) -> Dict[str, Any]:
    """Gets detailed information for a specific fog viewpoint by its ID.

    Args:
        viewpoint_id: Unique identifier for the viewpoint (e.g., 'mount-tamalpais-east-peak', 'hawk-hill').

    Returns:
        Dictionary containing viewpoint details, or an error message if not found.
    """
    db = get_firestore_client()
    doc_ref = db.collection(COLLECTION_NAME).document(viewpoint_id)
    doc = doc_ref.get()

    if not doc.exists:
        return {"error": f"Viewpoint '{viewpoint_id}' not found in Firestore."}

    data = doc.to_dict()
    data["id"] = doc.id
    return data


def save_fog_viewpoint(
    name: str,
    viewpoint_id: Optional[str] = None,
    region: str = "Bay Area",
    elevation_ft: int = 1000,
    optimal_inversion_min_ft: int = 600,
    optimal_inversion_max_ft: int = 1500,
    facing_direction: str = "West",
    fog_wave_rating: str = "Recommended",
    description: str = "Scenic coastal fog photography spot.",
    is_favorite: bool = False,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> Dict[str, Any]:
    """Adds or updates a fog wave viewpoint in the Firestore database.

    Args:
        name: Name of the spot (e.g. 'Mount Tamalpais - East Peak' or 'Grizzly Peak').
        viewpoint_id: Optional unique slug/ID. If not provided, it is automatically derived from the name.
        region: Geographic region (e.g., 'East Bay', 'Marin County', 'San Francisco', 'San Mateo Coast').
        elevation_ft: Elevation in feet above sea level.
        optimal_inversion_min_ft: Minimum marine layer height in feet for fog waves.
        optimal_inversion_max_ft: Maximum marine layer height in feet before the peak is socked in.
        facing_direction: Dominant camera facing direction (e.g. 'West', 'Southwest').
        fog_wave_rating: Rating or description of fog wave frequency/quality (e.g. 'World Class', 'Epic', 'High', 'Moderate', 'Recommended').
        description: Tips, parking/hiking information, and composition notes.
        is_favorite: Whether this spot is marked as a user favorite.
        latitude: Optional latitude coordinate for map pin (e.g., 37.882).
        longitude: Optional longitude coordinate for map pin (e.g., -122.235).

    Returns:
        Confirmation status and the saved document ID.
    """
    import re
    if not viewpoint_id:
        viewpoint_id = re.sub(r'[^a-zA-Z0-9]+', '-', name.lower()).strip('-')

    db = get_firestore_client()
    doc_ref = db.collection(COLLECTION_NAME).document(viewpoint_id)


    data = {
        "name": name,
        "region": region,
        "elevation_ft": elevation_ft,
        "optimal_inversion_min_ft": optimal_inversion_min_ft,
        "optimal_inversion_max_ft": optimal_inversion_max_ft,
        "facing_direction": facing_direction,
        "fog_wave_rating": fog_wave_rating,
        "description": description,
        "is_favorite": is_favorite,
    }
    if latitude is not None:
        data["latitude"] = float(latitude)
    if longitude is not None:
        data["longitude"] = float(longitude)

    doc_ref.set(data, merge=True)
    return {"status": "success", "message": f"Viewpoint '{name}' ({viewpoint_id}) saved successfully.", "data": data}

