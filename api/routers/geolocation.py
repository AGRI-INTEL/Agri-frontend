"""
Geolocation API Router
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# Pydantic models for request/response
class GeocodeRequest(BaseModel):
    address: str

class ReverseGeocodeRequest(BaseModel):
    latitude: float
    longitude: float

class LocationResponse(BaseModel):
    latitude: float
    longitude: float
    display_name: str
    address: dict

class GeocodeResponse(BaseModel):
    locations: List[LocationResponse]

# Nominatim (OpenStreetMap) API base URL
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"

# Note: In production, you should use your own Nominatim instance or a commercial service
# This is just for demonstration purposes
HEADERS = {
    "User-Agent": "AgriIntel/1.0 (https://yourdomain.com)"
}

@router.post("/geocode", response_model=GeocodeResponse, tags=["Geolocation"])
async def geocode_address(request: GeocodeRequest):
    """
    Geocode an address using OpenStreetMap's Nominatim service.
    """
    try:
        async with httpx.AsyncClient() as client:
            params = {
                "q": request.address,
                "format": "json",
                "limit": 5
            }
            response = await client.get(
                f"{NOMINATIM_BASE_URL}/search",
                params=params,
                headers=HEADERS
            )
            response.raise_for_status()
            
            data = response.json()
            locations = []
            for item in data:
                locations.append(LocationResponse(
                    latitude=float(item["lat"]),
                    longitude=float(item["lon"]),
                    display_name=item["display_name"],
                    address=item.get("address", {})
                ))
            
            return GeocodeResponse(locations=locations)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Geocoding service error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/reverse-geocode", response_model=LocationResponse, tags=["Geolocation"])
async def reverse_geocode(request: ReverseGeocodeRequest):
    """
    Reverse geocode coordinates to get address information using OpenStreetMap's Nominatim service.
    """
    try:
        async with httpx.AsyncClient() as client:
            params = {
                "lat": request.latitude,
                "lon": request.longitude,
                "format": "json"
            }
            response = await client.get(
                f"{NOMINATIM_BASE_URL}/reverse",
                params=params,
                headers=HEADERS
            )
            response.raise_for_status()
            
            data = response.json()
            return LocationResponse(
                latitude=request.latitude,
                longitude=request.longitude,
                display_name=data.get("display_name", "Unknown location"),
                address=data.get("address", {})
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Reverse geocoding service error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Update the main router to include this new router
# This would be done in router.py:
# from api.routers import geolocation
# api_v1_router.include_router(geolocation.router, prefix="/geolocation", tags=["Geolocation"])