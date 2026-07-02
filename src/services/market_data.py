"""
Market price aggregation service with ESOKO, FAO GIEWS, and mFarm stubs
"""

import logging
import statistics
from datetime import datetime, timezone
from typing import Optional

from config.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

ESOKO_BASE = "https://api.esoko.com/v2"
FAO_GIEWS_BASE = "https://giews-api.fao.org/api/v1"
MFARM_BASE = "https://api.mfarm.co.ke/v1"

ALERT_THRESHOLDS: dict[str, dict[str, float]] = {
    "mais": {"min": 150, "max": 500, "drop_pct": 15, "surge_pct": 25},
    "arachide": {"min": 300, "max": 900, "drop_pct": 12, "surge_pct": 20},
    "manioc": {"min": 100, "max": 350, "drop_pct": 15, "surge_pct": 25},
    "cacao": {"min": 1500, "max": 4000, "drop_pct": 10, "surge_pct": 20},
    "coton": {"min": 400, "max": 1200, "drop_pct": 10, "surge_pct": 18},
    "sorgho": {"min": 120, "max": 400, "drop_pct": 15, "surge_pct": 25},
    "mil": {"min": 120, "max": 380, "drop_pct": 15, "surge_pct": 25},
    "riz": {"min": 300, "max": 800, "drop_pct": 12, "surge_pct": 20},
}


class MarketDataService:

    async def fetch_prices(
        self, crop: Optional[str] = None, country: Optional[str] = None
    ) -> list[dict]:
        all_prices = []

        try:
            esoko = await self._fetch_esoko(crop, country)
            all_prices.extend(esoko)
        except Exception as e:
            logger.warning("ESOKO fetch failed: %s", e)

        try:
            fao = await self._fetch_fao_giews(crop, country)
            all_prices.extend(fao)
        except Exception as e:
            logger.warning("FAO GIEWS fetch failed: %s", e)

        try:
            mfarm = await self._fetch_mfarm(crop, country)
            all_prices.extend(mfarm)
        except Exception as e:
            logger.warning("mFarm fetch failed: %s", e)

        return all_prices

    def aggregate_prices(self, prices: list[dict]) -> dict:
        if not prices:
            return {"total": 0, "aggregations": {}}

        grouped: dict[str, list[float]] = {}
        source_groups: dict[str, set[str]] = {}
        for p in prices:
            key = f"{p.get('crop', 'unknown')}_{p.get('country', 'unknown')}"
            val = p.get("price")
            if val is not None:
                grouped.setdefault(key, []).append(val)
                source_groups.setdefault(key, set()).add(p.get("source", "unknown"))

        aggregations = []
        all_prices_list = []
        for key, values in grouped.items():
            crop_name, country_name = key.split("_", 1)
            agg = {
                "crop": crop_name,
                "country": country_name,
                "avg": round(statistics.mean(values), 2),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "count": len(values),
                "median": round(statistics.median(values), 2),
                "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
                "sources": list(source_groups.get(key, [])),
            }
            aggregations.append(agg)
            all_prices_list.extend(values)

        return {
            "total": len(prices),
            "aggregations": aggregations,
            "overall_avg": round(statistics.mean(all_prices_list), 2) if all_prices_list else 0.0,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_price_alert_thresholds(self, crop: str) -> dict:
        crop_key = crop.lower().strip()
        thresholds = ALERT_THRESHOLDS.get(crop_key, {"min": 100, "max": 1000, "drop_pct": 15, "surge_pct": 20})
        return {
            "crop": crop_key,
            "thresholds": thresholds,
        }

    async def _fetch_esoko(
        self, crop: Optional[str] = None, country: Optional[str] = None
    ) -> list[dict]:
        api_key = getattr(settings, "ESOKO_API_KEY", None)
        if not api_key:
            logger.debug("ESOKO_API_KEY not configured — skipping")
            return []
        try:
            import httpx

            params: dict[str, str] = {}
            if crop:
                params["commodity"] = crop
            if country:
                params["country"] = country

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{ESOKO_BASE}/prices",
                    headers={"Authorization": f"Bearer {api_key}"},
                    params=params,
                )
                if response.status_code == 200:
                    data = response.json()
                    results = []
                    for item in data if isinstance(data, list) else data.get("data", []):
                        results.append(
                            {
                                "source": "ESOKO",
                                "crop": item.get("commodity", crop or "unknown"),
                                "country": item.get("country", country or "unknown"),
                                "market": item.get("market", ""),
                                "price": item.get("price"),
                                "currency": item.get("currency", "XOF"),
                                "unit": item.get("unit", "kg"),
                                "date": item.get("date", datetime.now(timezone.utc).isoformat()),
                            }
                        )
                    return results
                logger.warning("ESOKO API returned %s: %s", response.status_code, response.text[:200])
                return []
        except Exception as e:
            logger.warning("ESOKO fetch exception: %s", e)
            return []

    async def _fetch_fao_giews(
        self, crop: Optional[str] = None, country: Optional[str] = None
    ) -> list[dict]:
        api_key = getattr(settings, "FAO_API_KEY", None)
        if not api_key:
            logger.debug("FAO_API_KEY not configured — skipping")
            return []
        try:
            import httpx

            params: dict[str, str] = {}
            if crop:
                params["crop"] = crop
            if country:
                params["area"] = country

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{FAO_GIEWS_BASE}/prices",
                    headers={"X-API-Key": api_key} if api_key else {},
                    params=params,
                )
                if response.status_code == 200:
                    data = response.json()
                    results = []
                    for item in data if isinstance(data, list) else data.get("data", []):
                        results.append(
                            {
                                "source": "FAO GIEWS",
                                "crop": item.get("crop", crop or "unknown"),
                                "country": item.get("area", country or "unknown"),
                                "market": item.get("market", ""),
                                "price": item.get("price_usd"),
                                "currency": "USD",
                                "unit": item.get("unit", "tonne"),
                                "date": item.get("date", datetime.now(timezone.utc).isoformat()),
                            }
                        )
                    return results
                logger.warning("FAO GIEWS API returned %s: %s", response.status_code, response.text[:200])
                return []
        except Exception as e:
            logger.warning("FAO GIEWS fetch exception: %s", e)
            return []

    async def _fetch_mfarm(
        self, crop: Optional[str] = None, country: Optional[str] = None
    ) -> list[dict]:
        api_key = getattr(settings, "MFARM_API_KEY", None)
        if not api_key:
            logger.debug("MFARM_API_KEY not configured — skipping")
            return []
        try:
            import httpx

            params: dict[str, str] = {}
            if crop:
                params["product"] = crop
            if country:
                params["region"] = country

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    f"{MFARM_BASE}/prices",
                    headers={"Authorization": f"Bearer {api_key}"},
                    params=params,
                )
                if response.status_code == 200:
                    data = response.json()
                    results = []
                    for item in data if isinstance(data, list) else data.get("data", []):
                        results.append(
                            {
                                "source": "mFarm",
                                "crop": item.get("product", crop or "unknown"),
                                "country": item.get("region", country or "unknown"),
                                "market": item.get("market", ""),
                                "price": item.get("price"),
                                "currency": item.get("currency", "KES"),
                                "unit": item.get("unit", "kg"),
                                "date": item.get("date", datetime.now(timezone.utc).isoformat()),
                            }
                        )
                    return results
                logger.warning("mFarm API returned %s: %s", response.status_code, response.text[:200])
                return []
        except Exception as e:
            logger.warning("mFarm fetch exception: %s", e)
            return []


market_data_service = MarketDataService()
