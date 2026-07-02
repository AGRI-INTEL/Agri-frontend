"""
NDVI satellite data service with NASA POWER API, Sentinel Hub, and simulated fallback
"""

import logging
import math
from datetime import date, datetime, timezone
from typing import Optional

from config.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

NASA_POWER_BASE = "https://power.larc.nasa.gov/api/temporal/monthly/point"
SENTINEL_HUB_BASE = "https://services.sentinel-hub.com/api/v1"


class SatelliteService:

    async def get_ndvi(
        self, lat: float, lng: float, date_str: Optional[str] = None
    ) -> dict:
        target_date = date_str or date.today().isoformat()
        try:
            result = await self._fetch_nasa_power(lat, lng, target_date)
            if result and result.get("ndvi") is not None:
                return result
        except Exception as e:
            logger.warning("NASA POWER fetch failed for (%s, %s): %s", lat, lng, e)

        try:
            result = await self._fetch_sentinel_hub(lat, lng, target_date)
            if result and result.get("ndvi") is not None:
                return result
        except Exception as e:
            logger.warning("Sentinel Hub fetch failed for (%s, %s): %s", lat, lng, e)

        return self._simulate_ndvi(lat, lng, target_date)

    async def get_ndvi_timeseries(
        self, lat: float, lng: float, start_date: str, end_date: str
    ) -> list[dict]:
        results = []

        try:
            nasa_results = await self._fetch_nasa_power_timeseries(
                lat, lng, start_date, end_date
            )
            if nasa_results:
                return nasa_results
        except Exception as e:
            logger.warning(
                "NASA POWER timeseries fetch failed for (%s, %s): %s", lat, lng, e
            )

        try:
            sentinel_results = await self._fetch_sentinel_hub_timeseries(
                lat, lng, start_date, end_date
            )
            if sentinel_results:
                return sentinel_results
        except Exception as e:
            logger.warning(
                "Sentinel Hub timeseries fetch failed for (%s, %s): %s", lat, lng, e
            )

        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        current = start
        while current <= end:
            mid = current.isoformat()
            results.append(self._simulate_ndvi(lat, lng, mid))
            current = date(current.year, current.month + 1, 1) if current.month < 12 else date(current.year + 1, 1, 1)

        return results

    async def _fetch_nasa_power(
        self, lat: float, lng: float, date_str: str
    ) -> Optional[dict]:
        target_date = date.fromisoformat(date_str)
        params = {
            "parameters": "NDVI",
            "community": "AG",
            "format": "JSON",
            "start": str(target_date.year),
            "end": str(target_date.year),
            "latitude": lat,
            "longitude": lng,
        }
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(NASA_POWER_BASE, params=params)
                response.raise_for_status()
                data = response.json()
                properties = data.get("properties", {}).get("parameter", {})
                ndvi_values = properties.get("NDVI", {})
                if ndvi_values:
                    monthly_key = f"{target_date.year}{target_date.month:02d}"
                    values = []
                    for k, v in ndvi_values.items():
                        if k.startswith(str(target_date.year)):
                            values.append(v)
                    ndvi = sum(values) / len(values) if values else None
                    if ndvi is not None:
                        return {
                            "ndvi": round(ndvi, 4),
                            "date": date_str,
                            "vegetation_health": self._classify_ndvi(ndvi),
                            "cloud_cover": None,
                            "source": "NASA POWER",
                        }
        except Exception as e:
            logger.debug("NASA POWER single-point error: %s", e)
        return None

    async def _fetch_nasa_power_timeseries(
        self, lat: float, lng: float, start_date: str, end_date: str
    ) -> Optional[list[dict]]:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        params = {
            "parameters": "NDVI",
            "community": "AG",
            "format": "JSON",
            "start": str(start.year),
            "end": str(end.year),
            "latitude": lat,
            "longitude": lng,
        }
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(NASA_POWER_BASE, params=params)
                response.raise_for_status()
                data = response.json()
                properties = data.get("properties", {}).get("parameter", {})
                ndvi_values = properties.get("NDVI", {})
                if not ndvi_values:
                    return None

                results = []
                current = start
                while current <= end:
                    key = f"{current.year}{current.month:02d}"
                    val = ndvi_values.get(key)
                    if val is not None:
                        results.append(
                            {
                                "ndvi": round(val, 4),
                                "date": current.isoformat(),
                                "vegetation_health": self._classify_ndvi(val),
                                "cloud_cover": None,
                                "source": "NASA POWER",
                            }
                        )
                    current = (
                        date(current.year, current.month + 1, 1)
                        if current.month < 12
                        else date(current.year + 1, 1, 1)
                    )
                return results
        except Exception as e:
            logger.debug("NASA POWER timeseries error: %s", e)
        return None

    async def _fetch_sentinel_hub(
        self, lat: float, lng: float, date_str: str
    ) -> Optional[dict]:
        api_key = getattr(settings, "SENTINEL_HUB_API_KEY", None)
        if not api_key:
            return None
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                evalscript = """
                //VERSION=3
                function setup() {
                    return {
                        input: ["B04", "B08"],
                        output: { bands: 1, sampleType: "FLOAT32" }
                    };
                }
                function evaluatePixel(sample) {
                    let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
                    return [ndvi];
                }
                """
                payload = {
                    "input": {
                        "bounds": {
                            "geometry": {
                                "type": "Point",
                                "coordinates": [lng, lat],
                            }
                        },
                        "data": [
                            {
                                "type": "S2L2A",
                                "dataFilter": {
                                    "timeRange": {
                                        "from": f"{date_str}T00:00:00Z",
                                        "to": f"{date_str}T23:59:59Z",
                                    },
                                    "maxCloudCoverage": 30,
                                },
                            }
                        ],
                    },
                    "evalscript": evalscript,
                    "output": {"width": 1, "height": 1},
                }
                response = await client.post(
                    f"{SENTINEL_HUB_BASE}/process",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
                if response.status_code == 200:
                    data = response.json()
                    ndvi = data.get("data", {}).get("ndvi", None)
                    if ndvi is not None:
                        return {
                            "ndvi": round(ndvi, 4),
                            "date": date_str,
                            "vegetation_health": self._classify_ndvi(ndvi),
                            "cloud_cover": None,
                            "source": "Sentinel Hub",
                        }
        except Exception as e:
            logger.debug("Sentinel Hub single-point error: %s", e)
        return None

    async def _fetch_sentinel_hub_timeseries(
        self, lat: float, lng: float, start_date: str, end_date: str
    ) -> Optional[list[dict]]:
        api_key = getattr(settings, "SENTINEL_HUB_API_KEY", None)
        if not api_key:
            return None
        try:
            import httpx

            evalscript = """
            //VERSION=3
            function setup() {
                return {
                    input: ["B04", "B08"],
                    output: { bands: 1, sampleType: "FLOAT32" }
                };
            }
            function evaluatePixel(sample) {
                let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
                return [ndvi];
            }
            """
            payload = {
                "input": {
                    "bounds": {
                        "geometry": {
                            "type": "Point",
                            "coordinates": [lng, lat],
                        }
                    },
                    "data": [
                        {
                            "type": "S2L2A",
                            "dataFilter": {
                                "timeRange": {
                                    "from": f"{start_date}T00:00:00Z",
                                    "to": f"{end_date}T23:59:59Z",
                                },
                                "maxCloudCoverage": 30,
                            },
                        }
                    ],
                },
                "evalscript": evalscript,
                "output": {"width": 1, "height": 1},
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{SENTINEL_HUB_BASE}/process",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
                if response.status_code == 200:
                    data = response.json()
                    ndvi = data.get("data", {}).get("ndvi", None)
                    if ndvi is not None:
                        return [
                            {
                                "ndvi": round(ndvi, 4),
                                "date": start_date,
                                "vegetation_health": self._classify_ndvi(ndvi),
                                "cloud_cover": None,
                                "source": "Sentinel Hub",
                            }
                        ]
        except Exception as e:
            logger.debug("Sentinel Hub timeseries error: %s", e)
        return None

    def _simulate_ndvi(self, lat: float, lng: float, date_str: str) -> dict:
        try:
            target_date = date.fromisoformat(date_str)
        except (ValueError, TypeError):
            target_date = date.today()

        day_of_year = target_date.timetuple().tm_yday
        latitude_rad = math.radians(lat)

        hemisphere_factor = 1.0 if lat >= 0 else -1.0
        seasonal_offset = math.sin(
            2 * math.pi * (day_of_year - 80 + hemisphere_factor * 40) / 365
        )
        ndvi = 0.5 + 0.35 * seasonal_offset + 0.05 * math.sin(latitude_rad)

        ndvi = max(0.1, min(0.9, ndvi))
        ndvi = round(ndvi, 4)

        cloud_cover = round(max(0, min(100, 30 - 20 * seasonal_offset + 10 * (hash(str(lat) + str(lng) + str(day_of_year)) % 20 - 10) / 20)), 1)

        return {
            "ndvi": ndvi,
            "date": target_date.isoformat(),
            "vegetation_health": self._classify_ndvi(ndvi),
            "cloud_cover": cloud_cover,
            "source": "simulated",
        }

    def _classify_ndvi(self, ndvi: float) -> str:
        if ndvi < 0.2:
            return "poor"
        if ndvi < 0.4:
            return "fair"
        if ndvi < 0.6:
            return "good"
        return "excellent"


satellite_service = SatelliteService()
