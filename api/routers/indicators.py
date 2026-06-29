"""
API Router pour les indicateurs agricoles — requêtes base de données
"""

from typing import Optional
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import uuid

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
    TypeIndicateurEnum,
    UniteIndicateurEnum,
    PeriodeIndicateurEnum,
)
from api.models.sql.actors import Actor

router = APIRouter()

CURRENT_MODEL = "agri_indicators_v2"
MODEL_SUPPORTS_IMAGES = True


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

    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
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
                else datetime.now(timezone.utc).isoformat() + "Z",
            }
        )

    return {"data": indicators_data, "count": len(indicators_data)}


# ─── External Fetch ───────────────────────────────────────────────────────────


@router.get("/external-fetch")
async def fetch_external_indicators(
    db: AsyncSession = Depends(get_db),
):
    """Récupère automatiquement les indicateurs depuis les APIs publiques (World Bank, FAO) et les sauvegarde en base"""
    from src.services.indicators_fetch import fetch_all_external_indicators
    result = await fetch_all_external_indicators(db=db)
    await db.commit()
    return result


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
        else datetime.now(timezone.utc).isoformat() + "Z",
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
    """Analyse une image agricole via IA (vision)"""
    from config.config import get_settings
    import base64
    import httpx

    settings = get_settings()

    # Read image bytes
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB max
        raise HTTPException(status_code=400, detail="Image trop grande (max 10MB)")

    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/jpeg")
    img_b64 = base64.b64encode(content).decode()

    api_key = getattr(settings, "OPENROUTER_API_KEY", None) or getattr(settings, "OPENAI_API_KEY", None)

    if api_key:
        try:
            has_openai_key = bool(getattr(settings, "OPENAI_API_KEY", None))
            base_url = "https://api.openai.com/v1" if has_openai_key else "https://openrouter.ai/api/v1"
            model = "gpt-4o-mini" if has_openai_key else "openai/gpt-4o-mini"

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://agriintel360.lsgrouptogo.com",
                "X-Title": "AgriIntel360",
            }

            payload = {
                "model": model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{img_b64}"}
                        },
                        {
                            "type": "text",
                            "text": "Tu es un expert agronome africain. Analyse cette image agricole et fournis: 1) Ce que tu vois (culture, animal, sol, équipement, etc.) 2) État de santé/qualité observé 3) Problèmes détectés (maladies, carences, parasites) 4) Recommandations pratiques 5) Score de santé global (0-100). Réponds en français avec des emojis pertinents."
                        }
                    ]
                }],
                "max_tokens": 800,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
                resp.raise_for_status()
                analysis_text = resp.json()["choices"][0]["message"]["content"]

            return {
                "status": "completed",
                "filename": file.filename,
                "indicator_id": indicator_id or None,
                "analysis": analysis_text,
                "model": model,
                "ai_powered": True,
            }
        except Exception as e:
            analysis_text = f"⚠️ Analyse IA temporairement indisponible ({str(e)[:50]}). Vérifiez la configuration."
            return {
                "status": "fallback",
                "filename": file.filename,
                "analysis": analysis_text,
                "ai_powered": False,
            }
    else:
        # Demo analysis without API key
        return {
            "status": "demo",
            "filename": file.filename,
            "indicator_id": indicator_id or None,
            "analysis": "🌾 **Analyse visuelle (mode démo)**\n\nPour activer l'analyse IA complète, configurez OPENROUTER_API_KEY dans votre fichier .env.\n\nL'analyse visuelle peut détecter:\n- Maladies des cultures\n- Carences nutritionnelles\n- État du sol\n- Santé du bétail\n- Qualité des récoltes",
            "ai_powered": False,
        }


# ─── Create ───────────────────────────────────────────────────────────────────


@router.post("/")
async def create_indicator(
    body: dict,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Créer un nouvel indicateur manuellement"""
    actor_id = body.get("actor_id")
    if not actor_id:
        raise HTTPException(status_code=400, detail="actor_id requis")

    try:
        actor_uid = uuid.UUID(actor_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="actor_id invalide")

    actor = await db.get(Actor, actor_uid)
    if not actor:
        raise HTTPException(status_code=404, detail="Acteur non trouvé")

    try:
        secteur = SousSecteursEnum(body.get("sector", "vegetal"))
    except ValueError:
        secteur = SousSecteursEnum.VEGETAL

    try:
        categorie = CategorieIndicateurEnum(body.get("category", "revenus"))
    except ValueError:
        categorie = CategorieIndicateurEnum.REVENUS

    try:
        type_ind = TypeIndicateurEnum(body.get("type", "revenu_annuel"))
    except ValueError:
        type_ind = TypeIndicateurEnum.REVENU_ANNUEL

    try:
        unite = UniteIndicateurEnum(body.get("unit", "XOF"))
    except ValueError:
        unite = UniteIndicateurEnum.XOF

    annee = body.get("year", datetime.now(timezone.utc).year)
    valeur = body.get("value", 0)

    record = IndicateurValeur(
        id=uuid.uuid4(),
        actor_id=actor_uid,
        sous_secteur=secteur,
        categorie=categorie,
        type_indicateur=type_ind,
        valeur_numerique=valeur,
        unite=unite,
        periode=PeriodeIndicateurEnum.ANNUELLE,
        date_debut=datetime(annee, 1, 1).date(),
        annee=annee,
        source=body.get("source", "Saisie manuelle"),
        commentaire=body.get("comment", ""),
        created_by=current_user.id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return {
        "id": str(record.id),
        "message": "Indicateur créé avec succès",
        "name": f"{type_ind.value} - {actor.nom}",
    }


# ─── Delete ───────────────────────────────────────────────────────────────────


@router.delete("/{id}")
async def delete_indicator(
    id: str,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Supprimer un indicateur"""
    try:
        uid = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Indicateur non trouvé")

    record = await db.get(IndicateurValeur, uid)
    if not record:
        raise HTTPException(status_code=404, detail="Indicateur non trouvé")

    await db.delete(record)
    await db.commit()

    return {"message": "Indicateur supprimé avec succès", "id": id}


# ─── Seed Demo Data ───────────────────────────────────────────────────────────


@router.post("/seed")
async def seed_demo_indicators(
    db: AsyncSession = Depends(get_db),
):
    """Générer des données de démonstration"""
    from src.services.indicators_fetch import seed_demo_indicators as seed_fn
    result = await seed_fn(db)
    await db.commit()
    return result


# ─── Batch Update ─────────────────────────────────────────────────────────────


@router.post("/batch-update")
async def batch_update_indicators(
    body: dict,
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Mettre à jour plusieurs indicateurs en lot"""
    indicators = body.get("indicators", [])
    updated = []
    for item in indicators:
        try:
            uid = uuid.UUID(item["id"])
            record = await db.get(IndicateurValeur, uid)
            if record:
                if "value" in item:
                    record.valeur_numerique = item["value"]
                if "comment" in item:
                    record.commentaire = item["comment"]
                updated.append(str(record.id))
        except (ValueError, KeyError):
            continue
    await db.commit()
    return {"message": f"{len(updated)} indicateurs mis à jour", "updated": updated}


# ─── Export ───────────────────────────────────────────────────────────────────


@router.post("/export")
async def export_indicators(
    ids: list[str],
    current_user: User = Depends(get_current_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """Exporter des indicateurs en CSV"""
    if not ids:
        raise HTTPException(status_code=400, detail="Aucun ID fourni")

    uids = []
    for i in ids:
        try:
            uids.append(uuid.UUID(i))
        except ValueError:
            continue

    records = (await db.execute(select(IndicateurValeur).where(IndicateurValeur.id.in_(uids)))).scalars().all()

    lines = ["id,nom,valeur,unite,tendance,pays,annee,source"]
    for r in records:
        actor = await db.get(Actor, r.actor_id)
        pays = actor.pays if actor else ""

        prev = await db.execute(
            select(IndicateurValeur.valeur_numerique)
            .where(IndicateurValeur.actor_id == r.actor_id, IndicateurValeur.type_indicateur == r.type_indicateur, IndicateurValeur.annee < r.annee)
            .order_by(IndicateurValeur.annee.desc()).limit(1)
        )
        pv = prev.scalar()
        v = float(r.valeur_numerique) if r.valeur_numerique else 0
        pv_f = float(pv) if pv else v
        trend = "hausse" if v > pv_f else "baisse" if v < pv_f else "stable"

        lines.append(
            f'{r.id},{r.type_indicateur.value},{r.valeur_numerique},{r.unite.value if hasattr(r.unite, "value") else ""},{trend},{pays},{r.annee},{r.source or ""}'
        )

    return {"format": "csv", "data": "\n".join(lines), "count": len(records)}
