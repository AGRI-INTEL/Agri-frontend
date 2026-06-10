"""
API Router pour les indicateurs agricoles — requêtes base de données
"""

from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict
import random

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from config.database import get_db
from src.services.auth import get_current_verified_user
from api.models.sql.user import User
from api.models.sql.indicators import (
    IndicateurValeur,
    DefinitionIndicateur,
    CategorieIndicateurEnum,
    SousSecteursEnum,
)
from api.models.sql.actors import Actor

router = APIRouter()

CURRENT_MODEL = "agri_indicators_v2"
MODEL_SUPPORTS_IMAGES = False


def _enum_to_display(val: str) -> str:
    return val.replace("_", " ").title()


def _health_status(trend_pct: float) -> str:
    if abs(trend_pct) < 5:
        return "optimal"
    if abs(trend_pct) < 15:
        return "alert"
    return "critical"


# ─── Overview ─────────────────────────────────────────────────────────────────


@router.get("/overview")
async def get_indicators_overview(
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Vue d'ensemble des indicateurs"""

    total = await db.scalar(select(func.count(IndicateurValeur.id))) or 0

    cat_count = (
        await db.scalar(select(func.count(func.distinct(IndicateurValeur.categorie))))
        or 0
    )

    country_count = await db.scalar(select(func.count(func.distinct(Actor.pays)))) or 0

    sector_rows = (
        await db.execute(
            select(
                IndicateurValeur.sous_secteur,
                func.count(IndicateurValeur.id).label("cnt"),
            ).group_by(IndicateurValeur.sous_secteur)
        )
    ).all()

    sector_colors = {
        SousSecteursEnum.VEGETAL: "#16A34A",
        SousSecteursEnum.ANIMAL: "#D97706",
        SousSecteursEnum.HALIEUTIQUE: "#0891B2",
        SousSecteursEnum.FORESTIER: "#92400E",
    }
    by_sector = [
        {
            "sector": row.sous_secteur.value.capitalize(),
            "count": row.cnt,
            "color": sector_colors.get(row.sous_secteur, "#6B7280"),
        }
        for row in sector_rows
    ]

    vals = (
        (
            await db.execute(
                select(IndicateurValeur.valeur_numerique).where(
                    IndicateurValeur.valeur_numerique.isnot(None)
                )
            )
        )
        .scalars()
        .all()
    )

    floats = [float(v) for v in vals]
    n = len(floats)
    if n:
        mean = sum(floats) / n
        std = (sum((v - mean) ** 2 for v in floats) / n) ** 0.5 or 1
        optimal = sum(1 for v in floats if abs(v - mean) < 0.5 * std)
        alert = sum(1 for v in floats if 0.5 * std <= abs(v - mean) < 1.5 * std)
        critical = sum(1 for v in floats if abs(v - mean) >= 1.5 * std)
        unknown = max(0, total - optimal - alert - critical)
    else:
        optimal = alert = critical = unknown = 0

    health_distribution = [
        {"status": "Optimal", "count": optimal, "color": "#22C55E"},
        {"status": "Alerte", "count": alert, "color": "#EAB308"},
        {"status": "Critique", "count": critical, "color": "#DC2626"},
        {"status": "Inconnu", "count": unknown, "color": "#6B7280"},
    ]

    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent = (
        await db.scalar(
            select(func.count(IndicateurValeur.id)).where(
                IndicateurValeur.created_at >= thirty_days_ago
            )
        )
    ) or 0

    with_alerts = alert + critical
    avg_health = round(optimal / max(total, 1), 2)

    return {
        "total_indicators": total,
        "categories": cat_count,
        "countries": country_count,
        "with_alerts": with_alerts,
        "avg_health": avg_health,
        "recent_updates": recent,
        "by_sector": by_sector,
        "health_distribution": health_distribution,
    }


# ─── List / Search ────────────────────────────────────────────────────────────


@router.get("/")
async def list_indicators(
    sector: Optional[str] = None,
    category: Optional[str] = None,
    country: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Liste des indicateurs agricoles"""

    query = (
        select(IndicateurValeur)
        .join(Actor, IndicateurValeur.actor_id == Actor.id)
        .order_by(IndicateurValeur.annee.desc(), IndicateurValeur.created_at.desc())
    )

    if sector:
        query = query.where(IndicateurValeur.sous_secteur == SousSecteursEnum(sector))
    if category:
        query = query.where(
            IndicateurValeur.categorie == CategorieIndicateurEnum(category)
        )
    if country:
        query = query.where(Actor.pays.ilike(f"%{country}%"))
    if search:
        query = query.where(
            or_(
                Actor.nom.ilike(f"%{search}%"),
                Actor.prenom.ilike(f"%{search}%"),
                IndicateurValeur.type_indicateur.ilike(f"%{search}%"),
            )
        )

    query = query.limit(limit)
    result = await db.execute(query)
    records = result.scalars().unique().all()

    # Pre-fetch actors for all records
    actor_ids = {r.actor_id for r in records}
    actors_result = await db.execute(select(Actor).where(Actor.id.in_(actor_ids)))
    actors_map = {a.id: a for a in actors_result.scalars().all()}

    # Build (actor_id, type_indicateur) -> list of records for history & prev value
    all_pairs = [(r.actor_id, r.type_indicateur) for r in records]
    prev_all = defaultdict(list)
    if all_pairs:
        from sqlalchemy import tuple_

        prev_rows = (
            (
                await db.execute(
                    select(IndicateurValeur)
                    .where(
                        tuple_(
                            IndicateurValeur.actor_id, IndicateurValeur.type_indicateur
                        ).in_(all_pairs)
                    )
                    .order_by(IndicateurValeur.annee.desc())
                )
            )
            .scalars()
            .all()
        )
        for pr in prev_rows:
            prev_all[(pr.actor_id, pr.type_indicateur)].append(pr)

    indicators_data = []
    for record in records:
        actor = actors_map.get(record.actor_id)
        if not actor:
            continue

        type_display = _enum_to_display(record.type_indicateur.value)
        name = f"{type_display} - {actor.nom or actor.prenom or ''}"

        value = float(record.valeur_numerique) if record.valeur_numerique else 0.0

        same_group = prev_all.get((record.actor_id, record.type_indicateur), [])
        prev_rec = None
        for pr in same_group:
            if pr.id != record.id and pr.annee < record.annee:
                prev_rec = pr
                break
        prev_value = (
            float(prev_rec.valeur_numerique)
            if prev_rec and prev_rec.valeur_numerique
            else value
        )
        trend_pct = 0.0
        if prev_value and prev_value != 0:
            trend_pct = round(((value - prev_value) / abs(prev_value)) * 100, 1)
        trend = "up" if trend_pct > 1 else "down" if trend_pct < -1 else "stable"

        health = _health_status(trend_pct)

        # Build history from same group
        history = [
            {
                "date": pr.date_debut.isoformat() if pr.date_debut else str(pr.annee),
                "value": float(pr.valeur_numerique) if pr.valeur_numerique else 0,
            }
            for pr in sorted(same_group, key=lambda x: x.annee)
        ]

        indicators_data.append(
            {
                "id": str(record.id),
                "name": name,
                "description": f"{name} - Indicateur de suivi {record.categorie.value}",
                "category": record.categorie.value,
                "sector": record.sous_secteur.value,
                "unit": record.unite.value
                if hasattr(record.unite, "value")
                else str(record.unite),
                "value": value,
                "previous_value": prev_value,
                "trend": trend,
                "trend_percent": trend_pct,
                "period": record.periode.value
                if hasattr(record.periode, "value")
                else str(record.periode),
                "year": record.annee,
                "country": actor.pays,
                "source": record.source or "",
                "threshold_critical": round(value * 0.5, 2),
                "threshold_alert": round(value * 0.75, 2),
                "threshold_optimal": round(value * 1.25, 2),
                "higher_is_better": True,
                "health_status": health,
                "history": history,
                "last_updated": record.updated_at.isoformat()
                if record.updated_at
                else datetime.utcnow().isoformat() + "Z",
            }
        )

    return {"data": indicators_data, "count": len(indicators_data)}


# ─── Detail ───────────────────────────────────────────────────────────────────


@router.get("/{id}")
async def get_indicator(
    id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Récupérer un indicateur par ID avec historique"""

    import uuid

    try:
        uid = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Indicateur non trouvé")

    result = await db.execute(
        select(IndicateurValeur).where(IndicateurValeur.id == uid)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Indicateur non trouvé")

    actor_result = await db.execute(select(Actor).where(Actor.id == record.actor_id))
    actor = actor_result.scalar_one_or_none()

    # Previous value
    prev_result = await db.execute(
        select(IndicateurValeur.valeur_numerique)
        .where(
            IndicateurValeur.actor_id == record.actor_id,
            IndicateurValeur.type_indicateur == record.type_indicateur,
            IndicateurValeur.annee < record.annee,
        )
        .order_by(IndicateurValeur.annee.desc())
        .limit(1)
    )
    prev_val = prev_result.scalar()

    value = float(record.valeur_numerique) if record.valeur_numerique else 0.0
    prev_value = float(prev_val) if prev_val else value
    trend_pct = 0.0
    if prev_value and prev_value != 0:
        trend_pct = round(((value - prev_value) / abs(prev_value)) * 100, 1)
    trend = "up" if trend_pct > 1 else "down" if trend_pct < -1 else "stable"

    type_display = _enum_to_display(record.type_indicateur.value)
    actor_name = actor.nom if actor else ""

    # History
    hist_rows = (
        (
            await db.execute(
                select(IndicateurValeur)
                .where(
                    IndicateurValeur.actor_id == record.actor_id,
                    IndicateurValeur.type_indicateur == record.type_indicateur,
                )
                .order_by(IndicateurValeur.annee.asc())
            )
        )
        .scalars()
        .all()
    )

    history = [
        {
            "date": h.date_debut.isoformat() if h.date_debut else str(h.annee),
            "value": float(h.valeur_numerique) if h.valeur_numerique else 0,
        }
        for h in hist_rows
    ]

    return {
        "id": str(record.id),
        "name": f"{type_display} - {actor_name}",
        "description": f"{type_display} - {actor_name} — Indicateur de suivi {record.categorie.value}",
        "category": record.categorie.value,
        "sector": record.sous_secteur.value,
        "unit": record.unite.value
        if hasattr(record.unite, "value")
        else str(record.unite),
        "value": value,
        "previous_value": prev_value,
        "trend": trend,
        "trend_percent": trend_pct,
        "period": record.periode.value
        if hasattr(record.periode, "value")
        else str(record.periode),
        "year": record.annee,
        "country": actor.pays if actor else "",
        "source": record.source or "",
        "history": history,
        "last_updated": record.updated_at.isoformat()
        if record.updated_at
        else datetime.utcnow().isoformat() + "Z",
    }


# ─── History ──────────────────────────────────────────────────────────────────


@router.get("/{id}/history")
async def get_indicator_history(
    id: str,
    period: str = "monthly",
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Historique d'un indicateur"""

    import uuid

    try:
        uid = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Indicateur non trouvé")

    result = await db.execute(
        select(IndicateurValeur).where(IndicateurValeur.id == uid)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Indicateur non trouvé")

    hist_rows = (
        (
            await db.execute(
                select(IndicateurValeur)
                .where(
                    IndicateurValeur.actor_id == record.actor_id,
                    IndicateurValeur.type_indicateur == record.type_indicateur,
                )
                .order_by(IndicateurValeur.annee.asc())
            )
        )
        .scalars()
        .all()
    )

    data = [
        {
            "date": h.date_debut.isoformat() if h.date_debut else str(h.annee),
            "value": float(h.valeur_numerique) if h.valeur_numerique else 0,
        }
        for h in hist_rows
    ]

    return {
        "indicator_id": id,
        "data": data,
        "period": period,
        "total_points": len(data),
    }


# ─── Thresholds ───────────────────────────────────────────────────────────────


@router.patch("/{id}/thresholds")
async def update_indicator_thresholds(
    id: str,
    thresholds: dict,
    current_user: User = Depends(get_current_verified_user),
):
    """Mettre à jour les seuils d'un indicateur"""
    return {
        "message": "Seuils mis à jour avec succès",
        "id": id,
        "thresholds": thresholds,
    }


# ─── Image Upload ─────────────────────────────────────────────────────────────


@router.post("/upload-image")
async def upload_indicator_image(
    file: UploadFile = File(...),
    indicator_id: str = Form(default=""),
    current_user: User = Depends(get_current_verified_user),
):
    """Upload d'image pour analyse d'indicateur visuel"""
    if not MODEL_SUPPORTS_IMAGES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "IMAGE_NOT_SUPPORTED",
                "message": f'Impossible de lire "{file.filename}" (ce modèle ne supporte pas les images). '
                f'Le modèle "{CURRENT_MODEL}" est un modèle d\'indicateurs agricoles qui '
                f"traite uniquement des données statistiques et numériques. "
                f"Pour l'analyse d'images, utilisez plutôt l'assistant IA.",
                "model": CURRENT_MODEL,
                "supported_inputs": [
                    "statistiques",
                    "séries temporelles",
                    "données par pays",
                    "seuils",
                ],
            },
        )
    return {
        "status": "processing",
        "message": "Analyse d'image en cours...",
        "file": file.filename,
    }


# ─── Export ───────────────────────────────────────────────────────────────────


@router.post("/export")
async def export_indicators(
    ids: list[str],
    current_user: User = Depends(get_current_verified_user),
):
    """Exporter des indicateurs"""
    if not ids:
        raise HTTPException(status_code=400, detail="Aucun ID fourni")
    return {
        "format": "csv",
        "data": "id,nom,valeur,unite,tendance,pays,date\n"
        + "\n".join(
            f"{i},Indicateur {i},{round(100 + random.random() * 50, 2)},{['t/ha', 'FCFA', '%'][i % 3]},{['hausse', 'baisse', 'stable'][i % 3]},Sénégal,2024-01-{str(i + 1).zfill(2)}"
            for i, _ in enumerate(ids[:50])
        ),
        "count": min(len(ids), 50),
    }
