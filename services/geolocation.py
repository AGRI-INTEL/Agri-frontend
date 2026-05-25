"""
Geolocation Service
Handles geolocation calculations and nearby place lookups
"""

import math
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class GeolocationService:
    """Service for handling geolocation operations"""

    EARTH_RADIUS_KM = 6371.0

    def calculate_distance(
        self, point1: Tuple[float, float], point2: Tuple[float, float]
    ) -> float:
        """
        Calculate the great-circle distance between two points using the Haversine formula.

        Args:
            point1: (latitude, longitude) in decimal degrees
            point2: (latitude, longitude) in decimal degrees

        Returns:
            Distance in kilometres
        """
        try:
            lat1, lon1 = math.radians(point1[0]), math.radians(point1[1])
            lat2, lon2 = math.radians(point2[0]), math.radians(point2[1])

            dlat = lat2 - lat1
            dlon = lon2 - lon1

            a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
            c = 2 * math.asin(math.sqrt(a))

            return round(self.EARTH_RADIUS_KM * c, 3)
        except Exception as e:
            logger.error(f"Error calculating distance: {e}")
            raise ValueError(f"Distance calculation error: {e}") from e

    def get_bounding_box(
        self, center: Tuple[float, float], radius_km: float
    ) -> Dict[str, float]:
        """
        Return a lat/lon bounding box around a centre point.

        Args:
            center: (latitude, longitude)
            radius_km: search radius in kilometres

        Returns:
            dict with min_lat, max_lat, min_lon, max_lon
        """
        lat, lon = center
        delta_lat = math.degrees(radius_km / self.EARTH_RADIUS_KM)
        delta_lon = math.degrees(
            radius_km / (self.EARTH_RADIUS_KM * math.cos(math.radians(lat)))
        )
        return {
            "min_lat": lat - delta_lat,
            "max_lat": lat + delta_lat,
            "min_lon": lon - delta_lon,
            "max_lon": lon + delta_lon,
        }

    def filter_by_radius(
        self,
        center: Tuple[float, float],
        places: List[Dict],
        radius_km: float,
        lat_key: str = "latitude",
        lon_key: str = "longitude",
    ) -> List[Dict]:
        """
        Filter a list of places to those within *radius_km* of *center*.
        Adds a ``distance_km`` key to each matching place.

        Args:
            center: (latitude, longitude) reference point
            places: list of dicts that each contain lat/lon keys
            radius_km: maximum distance
            lat_key: key name for latitude in each place dict
            lon_key: key name for longitude in each place dict

        Returns:
            Sorted list of places within the radius (nearest first)
        """
        results = []
        for place in places:
            try:
                dist = self.calculate_distance(
                    center, (place[lat_key], place[lon_key])
                )
                if dist <= radius_km:
                    results.append({**place, "distance_km": dist})
            except Exception:
                continue
        return sorted(results, key=lambda p: p["distance_km"])

    def get_sample_places(
        self, latitude: float, longitude: float, radius_km: float = 10.0
    ) -> List[Dict]:
        """
        Return sample nearby agricultural points of interest for demonstration.

        Args:
            latitude: reference latitude
            longitude: reference longitude
            radius_km: search radius (default 10 km)

        Returns:
            List of nearby places with distance_km
        """
        candidates = [
            {
                "name": "Centre Agricole Régional",
                "latitude": latitude + 0.005,
                "longitude": longitude + 0.005,
                "type": "agricultural_center",
                "description": "Centre de formation et d'appui aux agriculteurs",
            },
            {
                "name": "Station Météorologique",
                "latitude": latitude - 0.003,
                "longitude": longitude + 0.007,
                "type": "weather_station",
                "description": "Station de mesure météorologique automatique",
            },
            {
                "name": "Marché Local",
                "latitude": latitude + 0.012,
                "longitude": longitude - 0.008,
                "type": "market",
                "description": "Marché hebdomadaire de produits agricoles",
            },
            {
                "name": "Coopérative Agricole",
                "latitude": latitude - 0.020,
                "longitude": longitude + 0.015,
                "type": "cooperative",
                "description": "Coopérative de producteurs locaux",
            },
            {
                "name": "Entrepôt de Stockage",
                "latitude": latitude + 0.030,
                "longitude": longitude + 0.025,
                "type": "storage",
                "description": "Entrepôt frigorifique pour conservation des récoltes",
            },
        ]
        return self.filter_by_radius((latitude, longitude), candidates, radius_km)

    def geocode_african_city(self, city_name: str) -> Optional[Dict]:
        """
        Return approximate coordinates for major West-African cities.
        Useful as a fallback when the Nominatim API is unavailable.

        Args:
            city_name: city name (case-insensitive)

        Returns:
            dict with latitude, longitude, country or None
        """
        cities: Dict[str, Dict] = {
            "lomé": {"latitude": 6.1375, "longitude": 1.2123, "country": "Togo"},
            "accra": {"latitude": 5.5600, "longitude": -0.2057, "country": "Ghana"},
            "abidjan": {"latitude": 5.3600, "longitude": -4.0083, "country": "Côte d'Ivoire"},
            "dakar": {"latitude": 14.6928, "longitude": -17.4467, "country": "Sénégal"},
            "lagos": {"latitude": 6.5244, "longitude": 3.3792, "country": "Nigeria"},
            "abuja": {"latitude": 9.0765, "longitude": 7.3986, "country": "Nigeria"},
            "ouagadougou": {"latitude": 12.3647, "longitude": -1.5353, "country": "Burkina Faso"},
            "bamako": {"latitude": 12.6392, "longitude": -8.0029, "country": "Mali"},
            "niamey": {"latitude": 13.5137, "longitude": 2.1098, "country": "Niger"},
            "cotonou": {"latitude": 6.3654, "longitude": 2.4183, "country": "Bénin"},
            "conakry": {"latitude": 9.6412, "longitude": -13.5784, "country": "Guinée"},
            "freetown": {"latitude": 8.4897, "longitude": -13.2344, "country": "Sierra Leone"},
            "monrovia": {"latitude": 6.2907, "longitude": -10.7605, "country": "Libéria"},
            "yamoussoukro": {"latitude": 6.8276, "longitude": -5.2893, "country": "Côte d'Ivoire"},
            "kumasi": {"latitude": 6.6885, "longitude": -1.6244, "country": "Ghana"},
            "kano": {"latitude": 12.0022, "longitude": 8.5920, "country": "Nigeria"},
            "ibadan": {"latitude": 7.3775, "longitude": 3.9470, "country": "Nigeria"},
        }
        return cities.get(city_name.lower().strip())


# Global singleton
geolocation_service = GeolocationService()
