"""
Agricultural calendar service for West African crops
"""

import logging
from typing import Any

from config.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

MONTHS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

WEST_AFRICAN_SEASONS = {
    "TG": {"wet": [4, 5, 6, 7, 8, 9, 10], "dry": [11, 12, 1, 2, 3]},
    "SN": {"wet": [6, 7, 8, 9, 10], "dry": [11, 12, 1, 2, 3, 4, 5]},
    "GH": {"wet": [4, 5, 6, 7, 8, 9, 10], "dry": [11, 12, 1, 2, 3]},
    "NG": {"wet": [4, 5, 6, 7, 8, 9, 10], "dry": [11, 12, 1, 2, 3]},
    "CI": {"wet": [4, 5, 6, 7, 8, 9, 10], "dry": [11, 12, 1, 2, 3]},
    "BF": {"wet": [5, 6, 7, 8, 9], "dry": [10, 11, 12, 1, 2, 3, 4]},
    "ML": {"wet": [6, 7, 8, 9], "dry": [10, 11, 12, 1, 2, 3, 4, 5]},
    "BJ": {"wet": [4, 5, 6, 7, 8, 9, 10], "dry": [11, 12, 1, 2, 3]},
    "NE": {"wet": [6, 7, 8, 9], "dry": [10, 11, 12, 1, 2, 3, 4, 5]},
    "GN": {"wet": [4, 5, 6, 7, 8, 9, 10], "dry": [11, 12, 1, 2, 3]},
    "CM": {"wet": [4, 5, 6, 7, 8, 9, 10], "dry": [11, 12, 1, 2, 3]},
}

CROP_CALENDARS: dict[str, list[dict[str, Any]]] = {
    "mais": [
        {"event": "preparation_sol", "start_month": 3, "end_month": 4, "description": "Labour et fertilisation de base", "priority": "high"},
        {"event": "semis", "start_month": 4, "end_month": 6, "description": "Semis en poquets, 2-3 graines par trou", "priority": "high"},
        {"event": "entretien", "start_month": 5, "end_month": 8, "description": "Sarclage, buttage et apport d'urée", "priority": "medium"},
        {"event": "traitement", "start_month": 6, "end_month": 8, "description": "Traitement contre foreurs et chenilles", "priority": "medium"},
        {"event": "recolte", "start_month": 8, "end_month": 10, "description": "Récolte des épis à maturité", "priority": "high"},
    ],
    "arachide": [
        {"event": "preparation_sol", "start_month": 4, "end_month": 5, "description": "Défrichage et labour léger", "priority": "high"},
        {"event": "semis", "start_month": 5, "end_month": 7, "description": "Semis à 2-3 cm de profondeur", "priority": "high"},
        {"event": "entretien", "start_month": 6, "end_month": 8, "description": "Sarclage et buttage", "priority": "medium"},
        {"event": "traitement", "start_month": 7, "end_month": 8, "description": "Traitement contre rosette et cercosporiose", "priority": "medium"},
        {"event": "recolte", "start_month": 9, "end_month": 11, "description": "Arrachage et séchage des gousses", "priority": "high"},
    ],
    "manioc": [
        {"event": "preparation_sol", "start_month": 2, "end_month": 4, "description": "Défrichage et buttage", "priority": "high"},
        {"event": "semis", "start_month": 3, "end_month": 6, "description": "Bouturage des tiges", "priority": "high"},
        {"event": "entretien", "start_month": 4, "end_month": 10, "description": "Sarclage régulier", "priority": "medium"},
        {"event": "traitement", "start_month": 5, "end_month": 9, "description": "Traitement contre cochenilles et acariens", "priority": "medium"},
        {"event": "recolte", "start_month": 12, "end_month": 2, "description": "Récolte 9-18 mois après plantation", "priority": "high"},
    ],
    "cacao": [
        {"event": "preparation_sol", "start_month": 1, "end_month": 3, "description": "Nettoyage des plantations et élagage", "priority": "high"},
        {"event": "semis", "start_month": 4, "end_month": 6, "description": "Plantation des jeunes plants ombragés", "priority": "high"},
        {"event": "entretien", "start_month": 1, "end_month": 12, "description": "Entretien permanent des cabosses", "priority": "medium"},
        {"event": "traitement", "start_month": 3, "end_month": 11, "description": "Traitement contre pourriture brune et mirides", "priority": "high"},
        {"event": "recolte", "start_month": 9, "end_month": 3, "description": "Récolte principale des cabosses mûres", "priority": "high"},
    ],
    "coton": [
        {"event": "preparation_sol", "start_month": 4, "end_month": 5, "description": "Labour profond et fertilisation", "priority": "high"},
        {"event": "semis", "start_month": 5, "end_month": 7, "description": "Semis en lignes espacées", "priority": "high"},
        {"event": "entretien", "start_month": 6, "end_month": 9, "description": "Sarclage, démariage et apport d'engrais", "priority": "medium"},
        {"event": "traitement", "start_month": 6, "end_month": 10, "description": "Traitement phytosanitaire hebdomadaire", "priority": "high"},
        {"event": "recolte", "start_month": 10, "end_month": 12, "description": "Cueillette manuelle des capsules ouvertes", "priority": "high"},
    ],
    "sorgho": [
        {"event": "preparation_sol", "start_month": 4, "end_month": 5, "description": "Labour et enfouissement des résidus", "priority": "high"},
        {"event": "semis", "start_month": 5, "end_month": 7, "description": "Semis en poquets après les premières pluies", "priority": "high"},
        {"event": "entretien", "start_month": 6, "end_month": 9, "description": "Sarclage et démariage", "priority": "medium"},
        {"event": "traitement", "start_month": 7, "end_month": 9, "description": "Traitement contre les oiseaux et chenilles", "priority": "medium"},
        {"event": "recolte", "start_month": 10, "end_month": 12, "description": "Coupe des panicules à maturité", "priority": "high"},
    ],
    "mil": [
        {"event": "preparation_sol", "start_month": 4, "end_month": 5, "description": "Labour superficiel", "priority": "high"},
        {"event": "semis", "start_month": 5, "end_month": 7, "description": "Semis en poquets après les pluies", "priority": "high"},
        {"event": "entretien", "start_month": 6, "end_month": 9, "description": "Sarclage manuel", "priority": "medium"},
        {"event": "traitement", "start_month": 7, "end_month": 9, "description": "Protection contre les oiseaux", "priority": "medium"},
        {"event": "recolte", "start_month": 10, "end_month": 12, "description": "Coupe des chandelles", "priority": "high"},
    ],
    "riz": [
        {"event": "preparation_sol", "start_month": 3, "end_month": 5, "description": "Pépinière et préparation de la rizière", "priority": "high"},
        {"event": "semis", "start_month": 5, "end_month": 7, "description": "Repiquage en rizière inondée", "priority": "high"},
        {"event": "entretien", "start_month": 6, "end_month": 9, "description": "Gestion de l'eau et sarclage", "priority": "medium"},
        {"event": "traitement", "start_month": 7, "end_month": 10, "description": "Traitement contre pyriculariose et insectes", "priority": "high"},
        {"event": "recolte", "start_month": 10, "end_month": 12, "description": "Coupe des panicules et battage", "priority": "high"},
    ],
}


class AgriculturalCalendarService:

    def get_calendar(self, crop: str, country: str, year: int) -> dict:
        crop_key = crop.lower().strip()
        country_key = country.upper().strip()

        events = CROP_CALENDARS.get(crop_key, [])
        season = WEST_AFRICAN_SEASONS.get(country_key, {"wet": [5, 6, 7, 8, 9], "dry": [10, 11, 12, 1, 2, 3, 4]})

        calendar_months = []
        for month_idx in range(12):
            month_name = MONTHS[month_idx]
            month_events = []
            for evt in events:
                if self._month_in_range(month_idx + 1, evt["start_month"], evt["end_month"]):
                    month_events.append(
                        {
                            "event": evt["event"],
                            "description": evt["description"],
                            "priority": evt["priority"],
                        }
                    )
            season_type = "wet" if (month_idx + 1) in season["wet"] else "dry"
            calendar_months.append(
                {
                    "month": month_idx + 1,
                    "month_name": month_name,
                    "season": season_type,
                    "events": month_events,
                }
            )

        return {
            "crop": crop_key,
            "country": country_key,
            "year": year,
            "calendar": calendar_months,
        }

    def get_seasonal_forecast(self, country: str, month: int) -> dict:
        country_key = country.upper().strip()
        season = WEST_AFRICAN_SEASONS.get(country_key, {"wet": [5, 6, 7, 8, 9], "dry": [10, 11, 12, 1, 2, 3, 4]})

        is_wet = month in season["wet"]
        current_season = "wet" if is_wet else "dry"

        next_month = (month % 12) + 1
        upcoming_season = "wet" if next_month in season["wet"] else "dry"

        recommendations = []
        if is_wet:
            recommendations.extend([
                "Préparer les semis et le labour",
                "Vérifier les systèmes de drainage",
                "Surveiller les risques d'inondation",
            ])
        else:
            recommendations.extend([
                "Planifier l'irrigation",
                "Surveiller le stress hydrique des cultures",
                "Préparer les stock de fourrage",
            ])

        return {
            "country": country_key,
            "month": month,
            "month_name": MONTHS[month - 1],
            "current_season": current_season,
            "upcoming_season": upcoming_season,
            "is_wet_season": is_wet,
            "recommendations": recommendations,
        }

    def _month_in_range(self, month: int, start: int, end: int) -> bool:
        if start <= end:
            return start <= month <= end
        return month >= start or month <= end


calendar_service = AgriculturalCalendarService()
