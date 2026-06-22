"""
Service pour récupérer automatiquement les indicateurs agricoles depuis des APIs publiques
World Bank Data API - gratuit, sans clé API
"""
import httpx
from typing import List, Dict, Any
from datetime import datetime, timezone

WORLD_BANK_BASE = "https://api.worldbank.org/v2"
FAOSTAT_BASE = "https://fenixservices.fao.org/faostat/api/v1"

# Indicateurs World Bank
WB_INDICATORS = {
    "AG.LND.AGRI.ZS": "Terres agricoles (% superficie)",
    "AG.YLD.CREL.KG": "Rendement céréales (kg/ha)",
    "AG.PRD.FOOD.XD": "Indice production alimentaire",
    "NV.AGR.TOTL.ZS": "Valeur ajoutée agriculture (% PIB)",
    "SL.AGR.EMPL.ZS": "Emploi agricole (% total)",
    "AG.LND.IRIG.AG.ZS": "Terres irriguées (% ag.)",
    "AG.CON.FERT.ZS": "Consommation engrais (kg/ha)",
}

TRACKED_COUNTRIES = ["TG", "SN", "GH", "NG", "CI", "BF", "ML", "CM", "GN", "BJ"]

COUNTRY_NAMES = {
    "TG": "Togo", "SN": "Sénégal", "GH": "Ghana", "NG": "Nigeria",
    "CI": "Côte d'Ivoire", "BF": "Burkina Faso", "ML": "Mali",
    "CM": "Cameroun", "GN": "Guinée", "BJ": "Bénin",
}


async def fetch_world_bank_indicator(country: str, indicator: str, client: httpx.AsyncClient) -> List[Dict]:
    """Fetch a single indicator for a country from World Bank API"""
    url = f"{WORLD_BANK_BASE}/country/{country}/indicator/{indicator}"
    params = {"format": "json", "per_page": "5", "mrv": "5", "date": "2018:2024"}
    try:
        r = await client.get(url, params=params, timeout=10.0)
        r.raise_for_status()
        data = r.json()
        if len(data) < 2 or not data[1]:
            return []
        results = []
        for item in data[1]:
            if item.get("value") is not None:
                results.append({
                    "country_code": country,
                    "country_name": COUNTRY_NAMES.get(country, country),
                    "indicator_code": indicator,
                    "indicator_name": WB_INDICATORS.get(indicator, indicator),
                    "year": item.get("date", ""),
                    "value": float(item["value"]),
                    "source": "World Bank",
                    "unit": _get_unit(indicator),
                })
        return results
    except Exception:
        return []


def _get_unit(indicator: str) -> str:
    units = {
        "AG.LND.AGRI.ZS": "%",
        "AG.YLD.CREL.KG": "kg/ha",
        "AG.PRD.FOOD.XD": "indice",
        "NV.AGR.TOTL.ZS": "% PIB",
        "SL.AGR.EMPL.ZS": "%",
        "AG.LND.IRIG.AG.ZS": "%",
        "AG.CON.FERT.ZS": "kg/ha",
    }
    return units.get(indicator, "")


async def fetch_all_external_indicators() -> Dict[str, Any]:
    """Fetch all agricultural indicators for tracked countries"""
    import asyncio

    results = []
    errors = []
    async with httpx.AsyncClient() as client:
        tasks = []
        for country in TRACKED_COUNTRIES:
            for indicator in WB_INDICATORS:
                tasks.append(fetch_world_bank_indicator(country, indicator, client))

        batches = [tasks[i:i+20] for i in range(0, len(tasks), 20)]
        for batch in batches:
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            for br in batch_results:
                if isinstance(br, list):
                    results.extend(br)
                elif isinstance(br, Exception):
                    errors.append(str(br))

    return {
        "success": True,
        "count": len(results),
        "data": results,
        "errors": errors,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sources": ["World Bank Data API"],
    }
