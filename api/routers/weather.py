"""Weather API endpoints — données réelles via Open-Meteo (gratuit, sans clé)"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
import httpx

from src.services.auth import get_current_verified_user
from api.models.sql.user import User

router = APIRouter()

OPEN_METEO_BASE = "https://api.open-meteo.com/v1"
ARCHIVE_BASE = "https://archive-api.open-meteo.com/v1"
GEOCODING_BASE = "https://geocoding-api.open-meteo.com/v1"

CITY_COORDS: dict[str, dict] = {
    "dakar": {"lat": 14.6928, "lon": -17.4441, "country": "Sénégal"},
    "abidjan": {"lat": 5.3600, "lon": -4.0083, "country": "Côte d'Ivoire"},
    "accra": {"lat": 5.6037, "lon": -0.1870, "country": "Ghana"},
    "lagos": {"lat": 6.5244, "lon": 3.3792, "country": "Nigeria"},
    "bamako": {"lat": 12.6392, "lon": -8.0029, "country": "Mali"},
    "niamey": {"lat": 13.5127, "lon": 2.1126, "country": "Niger"},
    "lomé": {"lat": 6.1375, "lon": 1.2123, "country": "Togo"},
    "cotonou": {"lat": 6.3703, "lon": 2.3912, "country": "Bénin"},
    "conakry": {"lat": 9.6412, "lon": -13.5784, "country": "Guinée"},
    "ouagadougou": {"lat": 12.3714, "lon": -1.5197, "country": "Burkina Faso"},
    "bissau": {"lat": 11.8636, "lon": -15.5977, "country": "Guinée-Bissau"},
    "freetown": {"lat": 8.4841, "lon": -13.2299, "country": "Sierra Leone"},
}

WMO_CODES: dict[int, dict] = {
    0: {"condition": "sunny", "label": "Ciel dégagé"},
    1: {"condition": "sunny", "label": "Principalement dégagé"},
    2: {"condition": "partly_cloudy", "label": "Partiellement nuageux"},
    3: {"condition": "cloudy", "label": "Couvert"},
    45: {"condition": "foggy", "label": "Brouillard"},
    48: {"condition": "foggy", "label": "Brouillard givrant"},
    51: {"condition": "rainy", "label": "Bruine légère"},
    53: {"condition": "rainy", "label": "Bruine modérée"},
    55: {"condition": "rainy", "label": "Bruine dense"},
    56: {"condition": "rainy", "label": "Bruine verglaçante légère"},
    57: {"condition": "rainy", "label": "Bruine verglaçante dense"},
    61: {"condition": "rainy", "label": "Pluie légère"},
    63: {"condition": "rainy", "label": "Pluie modérée"},
    65: {"condition": "rainy", "label": "Pluie forte"},
    66: {"condition": "rainy", "label": "Pluie verglaçante légère"},
    67: {"condition": "rainy", "label": "Pluie verglaçante forte"},
    71: {"condition": "rainy", "label": "Neige légère"},
    73: {"condition": "rainy", "label": "Neige modérée"},
    75: {"condition": "rainy", "label": "Neige forte"},
    77: {"condition": "rainy", "label": "Grains de neige"},
    80: {"condition": "rainy", "label": "Averses légères"},
    81: {"condition": "rainy", "label": "Averses modérées"},
    82: {"condition": "rainy", "label": "Averses fortes"},
    85: {"condition": "rainy", "label": "Averses de neige légères"},
    86: {"condition": "rainy", "label": "Averses de neige fortes"},
    95: {"condition": "stormy", "label": "Orage"},
    96: {"condition": "stormy", "label": "Orage avec grêle légère"},
    99: {"condition": "stormy", "label": "Orage avec grêle forte"},
}


def wmo_info(code: int) -> dict:
    return WMO_CODES.get(code, {"condition": "cloudy", "label": "Nuageux"})


async def geocode(city: str) -> dict:
    key = city.lower().strip()
    if key in CITY_COORDS:
        return {**CITY_COORDS[key], "name": city}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{GEOCODING_BASE}/search",
            params={"name": city, "count": 1, "language": "fr", "format": "json"},
        )
        resp.raise_for_status()
        body = resp.json()
        if not body.get("results"):
            raise HTTPException(404, f"Ville '{city}' non trouvée")
        r = body["results"][0]
        return {
            "lat": r["latitude"],
            "lon": r["longitude"],
            "name": r.get("name", city),
            "country": r.get("country", ""),
        }


async def resolve_location(city: str | None, lat: float | None, lng: float | None) -> dict:
    if city:
        loc = await geocode(city)
        return loc
    if lat is not None and lng is not None:
        return {"lat": lat, "lon": lng, "name": "Ma position", "country": ""}
    loc = await geocode("Dakar")
    return loc


async def fetch_meteo(lat: float, lon: float) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m,pressure_msl,uv_index,visibility,is_day,dew_point_2m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,sunrise,sunset,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,wind_direction_10m_dominant",
        "timezone": "auto",
        "forecast_days": 7,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{OPEN_METEO_BASE}/forecast", params=params)
        resp.raise_for_status()
        return resp.json()


async def fetch_archive(lat: float, lon: float, start: str, end: str) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "daily": "temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum,wind_speed_10m_max,relative_humidity_2m_mean,surface_pressure_mean",
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{ARCHIVE_BASE}/archive", params=params)
        resp.raise_for_status()
        return resp.json()


def detect_harmattan(temp: float, humidity: float, code: int) -> bool:
    return (
        code in (45, 48) and temp > 25 and humidity < 45
        or code not in (45, 48, 95, 96, 99) and humidity < 30 and temp > 30
    )


def enrich_condition(condition: str, description: str, temp: float, wind_speed: float) -> tuple[str, str]:
    if condition == "sunny" and temp >= 38:
        return "hot", f"Très chaud — {temp}°C"
    if wind_speed >= 39:
        return "windy", f"Vent fort — {wind_speed} km/h"
    if condition == "sunny" and temp >= 33:
        return "hot", f"Chaud — {temp}°C"
    return condition, description


def build_current_response(current: dict, daily: dict, location: dict) -> dict:
    wmo_code = current.get("weather_code", 0)
    wmo = wmo_info(wmo_code)
    temp = current.get("temperature_2m", 30)
    humidity = current.get("relative_humidity_2m", 50)
    visibility_m = current.get("visibility")
    wind_speed = current.get("wind_speed_10m", 0)

    is_harmattan = detect_harmattan(temp, humidity, wmo_code)
    condition = "harmattan" if is_harmattan else wmo["condition"]
    description = (
        "Harmattan — poussière en suspension, visibilité réduite"
        if is_harmattan else wmo["label"]
    )
    condition, description = enrich_condition(condition, description, temp, wind_speed)

    sunrise = daily.get("sunrise", [None])[0] if daily.get("sunrise") else None
    sunset = daily.get("sunset", [None])[0] if daily.get("sunset") else None

    return {
        "city": location["name"],
        "country": location.get("country", ""),
        "latitude": location["lat"],
        "longitude": location["lon"],
        "temperature": round(temp, 1),
        "feels_like": round(current.get("apparent_temperature", 0), 1),
        "condition": condition,
        "description": description,
        "humidity": humidity,
        "wind_speed": round(wind_speed, 1),
        "wind_direction": str(round(current.get("wind_direction_10m", 0))),
        "dew_point": current.get("dew_point_2m"),
        "pressure": current.get("pressure_msl"),
        "visibility": round(visibility_m / 1000, 1) if visibility_m else None,
        "uv_index": current.get("uv_index"),
        "sunrise": sunrise,
        "sunset": sunset,
        "is_day": current.get("is_day", 1) == 1,
        "weather_code": wmo_code,
        "updated_at": current.get("time", datetime.now(timezone.utc).isoformat()),
    }


def build_forecast_response(data: dict, location: dict, days: int) -> list[dict]:
    daily = data.get("daily", {})
    result: list[dict] = []
    for i in range(min(days, len(daily.get("time", [])))):
        wmo_code = daily.get("weather_code", [0])[i] if daily.get("weather_code") else 0
        wmo = wmo_info(wmo_code)
        temp = daily.get("temperature_2m_max", [30])[i] or 30
        wind = daily.get("wind_speed_10m_max", [0])[i] or 0
        humidity_val = 50

        is_harmattan = detect_harmattan(temp, humidity_val, wmo_code)
        condition = "harmattan" if is_harmattan else wmo["condition"]
        description = "Harmattan" if is_harmattan else wmo["label"]
        condition, description = enrich_condition(condition, description, temp, wind)

        result.append({
            "date": daily["time"][i],
            "temperature_min": round(daily.get("temperature_2m_min", [0])[i] or 0, 1),
            "temperature_max": round(temp, 1),
            "temperature_avg": round(
                ((daily.get("temperature_2m_max", [0])[i] or 0) + (daily.get("temperature_2m_min", [0])[i] or 0)) / 2, 1
            ),
            "condition": condition,
            "description": description,
            "humidity": humidity_val,
            "precipitation": daily.get("precipitation_sum", [0])[i],
            "precipitation_probability": daily.get("precipitation_probability_max", [0])[i],
            "wind_speed": round(wind, 1),
            "sunrise": daily.get("sunrise", [""])[i] if daily.get("sunrise") else "",
            "sunset": daily.get("sunset", [""])[i] if daily.get("sunset") else "",
            "icon": condition,
        })
    return result


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("/current")
async def get_current_weather(
    city: Optional[str] = Query(None, description="Nom de la ville"),
    lat: Optional[float] = Query(None, description="Latitude"),
    lng: Optional[float] = Query(None, description="Longitude"),
    current_user: User = Depends(get_current_verified_user),
):
    """Données météo actuelles via Open-Meteo"""
    location = await resolve_location(city, lat, lng)
    try:
        data = await fetch_meteo(location["lat"], location["lon"])
    except httpx.HTTPError as e:
        raise HTTPException(502, f"API météo indisponible: {str(e)}")

    current = data.get("current", {})
    daily = data.get("daily", {})
    return build_current_response(current, daily, location)


@router.get("/forecast")
async def get_weather_forecast(
    city: Optional[str] = Query(None, description="Nom de la ville"),
    lat: Optional[float] = Query(None, description="Latitude"),
    lng: Optional[float] = Query(None, description="Longitude"),
    days: int = Query(7, ge=1, le=14),
    current_user: User = Depends(get_current_verified_user),
):
    """Prévisions météo sur N jours via Open-Meteo"""
    location = await resolve_location(city, lat, lng)
    try:
        data = await fetch_meteo(location["lat"], location["lon"])
    except httpx.HTTPError as e:
        raise HTTPException(502, f"API météo indisponible: {str(e)}")

    forecast = build_forecast_response(data, location, days)
    return {
        "city": location["name"],
        "country": location.get("country", ""),
        "forecast": forecast,
        "days": days,
    }


@router.get("/history")
async def get_weather_history(
    city: Optional[str] = Query(None, description="Nom de la ville"),
    lat: Optional[float] = Query(None, description="Latitude"),
    lng: Optional[float] = Query(None, description="Longitude"),
    days: int = Query(7, ge=1, le=90),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    current_user: User = Depends(get_current_verified_user),
):
    """Historique météo via Open-Meteo Archive API"""
    location = await resolve_location(city, lat, lng)

    if start_date and end_date:
        start = start_date
        end = end_date
    else:
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        data = await fetch_archive(location["lat"], location["lon"], start, end)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"API historique indisponible: {str(e)}")

    daily = data.get("daily", {})
    result: list[dict] = []
    for i in range(len(daily.get("time", []))):
        result.append({
            "date": daily["time"][i],
            "temperature_max": round(daily.get("temperature_2m_max", [0])[i] or 0, 1),
            "temperature_min": round(daily.get("temperature_2m_min", [0])[i] or 0, 1),
            "temperature_avg": round(daily.get("temperature_2m_mean", [0])[i] or 0, 1),
            "precipitation_mm": daily.get("precipitation_sum", [0])[i] or 0,
            "humidity": round(daily.get("relative_humidity_2m_mean", [50])[i] or 50, 1),
            "wind_speed": round(daily.get("wind_speed_10m_max", [0])[i] or 0, 1),
            "pressure": round(daily.get("surface_pressure_mean", [1013])[i] or 1013, 1),
        })

    return {"city": location["name"], "data": result, "count": len(result)}


@router.get("/alerts")
async def get_weather_alerts(
    city: Optional[str] = Query(None, description="Nom de la ville"),
    lat: Optional[float] = Query(None, description="Latitude"),
    lng: Optional[float] = Query(None, description="Longitude"),
    current_user: User = Depends(get_current_verified_user),
):
    """Alertes météo générées à partir des conditions Open-Meteo"""
    location = await resolve_location(city, lat, lng)
    try:
        data = await fetch_meteo(location["lat"], location["lon"])
    except httpx.HTTPError as e:
        raise HTTPException(502, f"API météo indisponible: {str(e)}")

    current = data.get("current", {})
    daily = data.get("daily", {})
    alerts: list[dict] = []
    now_str = datetime.now(timezone.utc).isoformat()

    temp = current.get("temperature_2m", 25)
    humidity = current.get("relative_humidity_2m", 50)
    uv = current.get("uv_index", 0)

    if temp >= 40:
        alerts.append({
            "id": "heatwave",
            "type": "heatwave",
            "severity": "severe",
            "title": "Vague de chaleur extrême",
            "description": f"Température de {temp}°C — risques sanitaires élevés, hydratez-vous et évitez l'exposition au soleil.",
            "start_time": now_str,
            "end_time": now_str,
            "areas": [location["name"]],
        })
    elif temp >= 35:
        alerts.append({
            "id": "heatwarning",
            "type": "heatwave",
            "severity": "moderate",
            "title": "Température élevée",
            "description": f"{temp}°C attendus — restez à l'ombre et buvez de l'eau régulièrement.",
            "start_time": now_str,
            "end_time": now_str,
            "areas": [location["name"]],
        })

    if uv and uv >= 8:
        alerts.append({
            "id": "uv",
            "type": "heatwave",
            "severity": "moderate",
            "title": "Indice UV très élevé",
            "description": f"Indice UV {uv} — protection solaire indispensable.",
            "start_time": now_str,
            "end_time": now_str,
            "areas": [location["name"]],
        })

    if humidity < 25 and temp > 32:
        alerts.append({
            "id": "harmattan",
            "type": "dust",
            "severity": "moderate",
            "title": "Conditions d'harmattan",
            "description": "Air très sec avec poussière en suspension — protégez vos voies respiratoires et vos cultures.",
            "start_time": now_str,
            "end_time": now_str,
            "areas": [location["name"]],
        })

    daily_max_precip = max(daily.get("precipitation_sum", [0]) or [0])
    if daily_max_precip >= 50:
        alerts.append({
            "id": "floodrisk",
            "type": "flood",
            "severity": "severe" if daily_max_precip >= 80 else "moderate",
            "title": "Risque d'inondation",
            "description": f"Précipitations attendues: {daily_max_precip}mm — risque d'inondation, surveillez les cours d'eau.",
            "start_time": now_str,
            "end_time": now_str,
            "areas": [location["name"]],
        })

    daily_weather_codes = daily.get("weather_code", [])
    if any(code in (95, 96, 99) for code in daily_weather_codes):
        alerts.append({
            "id": "storm",
            "type": "storm",
            "severity": "severe",
            "title": "Orages violents prévus",
            "description": "Des orages avec grêle possible sont prévus — mettez à l'abri le bétail et le matériel agricole.",
            "start_time": now_str,
            "end_time": now_str,
            "areas": [location["name"]],
        })

    return alerts


@router.get("/multi")
async def get_multi_city_weather(
    cities: str = Query(..., description="Noms de villes séparés par des virgules"),
    current_user: User = Depends(get_current_verified_user),
):
    """Météo actuelle pour plusieurs villes simultanément"""
    city_list = [c.strip() for c in cities.split(",") if c.strip()]
    results: list[dict] = []

    async with httpx.AsyncClient(timeout=30) as client:
        tasks = []
        for city_name in city_list:
            try:
                loc = await geocode(city_name)
            except HTTPException:
                continue
            params = {
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,uv_index",
                "timezone": "auto",
            }
            tasks.append((city_name, loc, params))

        for city_name, loc, params in tasks:
            try:
                resp = await client.get(f"{OPEN_METEO_BASE}/forecast", params=params)
                resp.raise_for_status()
                data = resp.json()
                current = data.get("current", {})
                wmo = wmo_info(current.get("weather_code", 0))

                temp = current.get("temperature_2m", 25)
                wind_speed_val = current.get("wind_speed_10m", 0)
                humidity_val = current.get("relative_humidity_2m", 50)
                is_harmattan = detect_harmattan(temp, humidity_val, current.get("weather_code", 0))
                condition = "harmattan" if is_harmattan else wmo["condition"]
                description = "Harmattan" if is_harmattan else wmo["label"]
                condition, description = enrich_condition(condition, description, temp, wind_speed_val)

                results.append({
                    "city": loc["name"],
                    "country": loc.get("country", ""),
                    "latitude": loc["lat"],
                    "longitude": loc["lon"],
                    "temperature": round(current.get("temperature_2m", 0), 1),
                    "feels_like": round(current.get("apparent_temperature", 0), 1),
                    "condition": condition,
                    "description": description,
                    "humidity": humidity_val,
                    "wind_speed": round(wind_speed_val, 1),
                    "uv_index": current.get("uv_index"),
                    "updated_at": current.get("time", datetime.now(timezone.utc).isoformat()),
                })
            except httpx.HTTPError:
                continue

    return results
