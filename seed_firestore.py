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

"""Seed script to populate initial fog viewpoints in Firestore."""

from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-04-d19134fd9a80"
COLLECTION_NAME = "viewpoints"

INITIAL_VIEWPOINTS = [
    {
        "id": "mount-tamalpais-east-peak",
        "name": "Mount Tamalpais - East Peak & Ridgecrest",
        "region": "Marin County",
        "elevation_ft": 2571,
        "optimal_inversion_min_ft": 1200,
        "optimal_inversion_max_ft": 2200,
        "facing_direction": "South / West over Pacific & Marin Hills",
        "fog_wave_rating": "World Class",
        "description": "The premier spot in Northern California for rolling fog waves cascading over the coastal ridges. Optimal at sunset and twilight.",
        "is_favorite": True,
    },
    {
        "id": "hawk-hill-marin-headlands",
        "name": "Hawk Hill - Marin Headlands",
        "region": "Marin County",
        "elevation_ft": 920,
        "optimal_inversion_min_ft": 500,
        "optimal_inversion_max_ft": 950,
        "facing_direction": "South toward Golden Gate Bridge & SF Skyline",
        "fog_wave_rating": "Epic",
        "description": "Dramatic vantage point where fog pours through the Golden Gate strait and envelopes the bridge towers. Look for low inversion days (700-900ft).",
        "is_favorite": False,
    },
    {
        "id": "twin-peaks-san-francisco",
        "name": "Twin Peaks (Christmas Tree Point)",
        "region": "San Francisco",
        "elevation_ft": 922,
        "optimal_inversion_min_ft": 400,
        "optimal_inversion_max_ft": 850,
        "facing_direction": "East / Northeast towards Downtown San Francisco",
        "fog_wave_rating": "High",
        "description": "Watch Karl the Fog swallow Sutro Tower and sweep across the city grid towards the bay.",
        "is_favorite": False,
    },
    {
        "id": "pacifica-sweeney-ridge",
        "name": "Sweeney Ridge Trailhead",
        "region": "Pacifica / San Mateo Coast",
        "elevation_ft": 1200,
        "optimal_inversion_min_ft": 600,
        "optimal_inversion_max_ft": 1150,
        "facing_direction": "West towards Pacific Ocean",
        "fog_wave_rating": "High",
        "description": "Where Gaspar de Portola discovered SF Bay; great for capturing rolling thick coastal banks spilling over the ridge line into San Bruno.",
        "is_favorite": False,
    },
]


def seed():
    print(f"Connecting to Firestore with project '{PROJECT_ID}'...")
    db = firestore.Client(project=PROJECT_ID)
    collection = db.collection(COLLECTION_NAME)

    for item in INITIAL_VIEWPOINTS:
        doc_id = item["id"]
        doc_data = {k: v for k, v in item.items() if k != "id"}
        collection.document(doc_id).set(doc_data, merge=True)
        print(f"  ✓ Seeded viewpoint: {item['name']} ({doc_id})")

    print("\nFirestore seeding complete!")


if __name__ == "__main__":
    seed()
