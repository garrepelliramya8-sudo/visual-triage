import os
import random
from mcp.server.fastmcp import FastMCP

# Create the FastMCP server instance
mcp = FastMCP("VisualTriageProviderLocator")

# Simulated database of healthcare providers
PROVIDERS = [
    {
        "id": "hosp-1",
        "name": "Metro General Emergency Hospital",
        "specialties": ["emergency", "cardiology"],
        "zipcode": "94043",
        "address": "1200 Shoreline Blvd, Mountain View, CA 94043",
        "base_wait_time": 45,
        "rating": 4.2,
        "reviews": [
            "Staff was incredibly fast during my chest pain emergency.",
            "Long waiting time if you only have minor issues, but emergency response is top-tier.",
            "Excellent cardiologists, very thorough."
        ]
    },
    {
        "id": "clinic-2",
        "name": "Mountain View Urgent Care",
        "specialties": ["urgent_care", "family_doctor"],
        "zipcode": "94043",
        "address": "555 El Camino Real, Mountain View, CA 94043",
        "base_wait_time": 20,
        "rating": 3.8,
        "reviews": [
            "Nice clean clinic, got my stitches done quickly.",
            "Friendly doctors but they didn't accept my specific insurance.",
            "Routine visits are easy to schedule."
        ]
    },
    {
        "id": "dermo-3",
        "name": "Silicon Valley Dermatology Center",
        "specialties": ["dermatology"],
        "zipcode": "94043",
        "address": "800 Castro St, Mountain View, CA 94043",
        "base_wait_time": 15,
        "rating": 4.7,
        "reviews": [
            "Dr. Smith was amazing, identified my rash immediately.",
            "A bit expensive but well worth it for the skincare quality.",
            "Very gentle with minor skin biopsy."
        ]
    },
    {
        "id": "eye-4",
        "name": "Bay Area Ophthalmology Associates",
        "specialties": ["ophthalmology"],
        "zipcode": "94043",
        "address": "2500 Hospital Dr, Mountain View, CA 94043",
        "base_wait_time": 30,
        "rating": 4.5,
        "reviews": [
            "Great eye doctors, solved my eye redness issue in one visit.",
            "Clean clinic, state-of-the-art diagnostic machines."
        ]
    },
    {
        "id": "hosp-5",
        "name": "Beverly Hills Medical Center ER",
        "specialties": ["emergency", "cardiology"],
        "zipcode": "90210",
        "address": "8700 Beverly Blvd, Los Angeles, CA 90048",
        "base_wait_time": 60,
        "rating": 4.1,
        "reviews": [
            "Saved my life during a cardiac incident. Very professional.",
            "The emergency room was packed, but doctors were excellent once seen."
        ]
    },
    {
        "id": "dermo-6",
        "name": "Beverly Hills Skin & Laser Clinic",
        "specialties": ["dermatology"],
        "zipcode": "90210",
        "address": "9000 Wilshire Blvd, Beverly Hills, CA 90210",
        "base_wait_time": 10,
        "rating": 4.9,
        "reviews": [
            "Absolutely beautiful facility. Best dermatologists in LA.",
            "Excellent treatment of my eczema, completely cleared up."
        ]
    },
    {
        "id": "clinic-7",
        "name": "Wilshire Urgent Care Clinic",
        "specialties": ["urgent_care"],
        "zipcode": "90210",
        "address": "9900 Wilshire Blvd, Beverly Hills, CA 90210",
        "base_wait_time": 25,
        "rating": 4.0,
        "reviews": [
            "Came in for a bad cut. Stitched up in 30 minutes.",
            "Standard urgent care, decent experience."
        ]
    }
]

@mcp.tool()
def search_providers(specialty: str, zipcode: str) -> list[dict]:
    """Search for hospitals or clinics specializing in the given medical specialty in a specific ZIP code.

    Args:
        specialty: The medical specialty required (e.g. dermatology, ophthalmology, cardiology, urgent_care, emergency).
        zipcode: The 5-digit ZIP code to search within.

    Returns:
        A list of matching provider records with name, address, and specialty.
    """
    specialty_lower = specialty.lower()
    results = []
    
    # Try exact match first, fallback to containing specialty
    for provider in PROVIDERS:
        if provider["zipcode"] == zipcode:
            matches_specialty = False
            for spec in provider["specialties"]:
                if specialty_lower in spec or spec in specialty_lower:
                    matches_specialty = True
                    break
            
            if matches_specialty:
                results.append({
                    "id": provider["id"],
                    "name": provider["name"],
                    "address": provider["address"],
                    "specialties": provider["specialties"],
                    "rating": provider["rating"],
                    "distance": f"{round(random.uniform(0.5, 4.8), 1)} miles"
                })
                
    # If no provider matches in the specific ZIP, offer the closest ones from the same database
    if not results:
        for provider in PROVIDERS:
            matches_specialty = False
            for spec in provider["specialties"]:
                if specialty_lower in spec or spec in specialty_lower:
                    matches_specialty = True
                    break
            
            if matches_specialty:
                results.append({
                    "id": provider["id"],
                    "name": provider["name"],
                    "address": provider["address"],
                    "specialties": provider["specialties"],
                    "rating": provider["rating"],
                    "distance": f"{round(random.uniform(5.0, 15.0), 1)} miles (Out of ZIP area)"
                })
                
    return results

@mcp.tool()
def get_provider_reviews(provider_id: str) -> dict:
    """Retrieve detailed patient reviews and sentiment for a specific healthcare provider.

    Args:
        provider_id: The unique ID of the healthcare provider.

    Returns:
        A dictionary containing rating and reviews.
    """
    for provider in PROVIDERS:
        if provider["id"] == provider_id:
            return {
                "name": provider["name"],
                "rating": provider["rating"],
                "reviews": provider["reviews"]
            }
    return {"error": "Provider not found"}

@mcp.tool()
def get_wait_times(provider_id: str) -> dict:
    """Retrieve live estimated ER or clinic waiting times (in minutes) for a provider.

    Args:
        provider_id: The unique ID of the healthcare provider.

    Returns:
        A dictionary containing the estimated waiting time.
    """
    for provider in PROVIDERS:
        if provider["id"] == provider_id:
            # Add a slight random variance to simulate real-time live data
            variance = random.choice([-10, -5, 0, 5, 10, 15])
            live_wait = max(5, provider["base_wait_time"] + variance)
            return {
                "name": provider["name"],
                "wait_time_minutes": live_wait
            }
    return {"error": "Provider not found"}

if __name__ == "__main__":
    mcp.run()
