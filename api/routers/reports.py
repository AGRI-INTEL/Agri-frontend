"""
Reports & Export API endpoints
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from config.database import get_db
from src.services.auth import get_current_active_user
from api.models.sql.user import User
from api.models.sql.reports import Report

logger = logging.getLogger(__name__)
router = APIRouter()


REPORT_TYPES = ["production", "market", "alert", "community"]


@router.post("/generate")
async def generate_report(
    body: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a report (production/market/alert/community) in PDF/CSV/Excel"""
    report_type = body.get("type", "").lower().strip()
    report_format = body.get("format", "csv").lower().strip()
    parameters = body.get("parameters", {})

    if report_type not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail=f"Type de rapport invalide. Types supportés: {', '.join(REPORT_TYPES)}")
    if report_format not in ("pdf", "csv", "excel"):
        raise HTTPException(status_code=400, detail="Format invalide. Formats supportés: pdf, csv, excel")

    title = body.get("title", f"Rapport {report_type} - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")

    try:
        import io
        import csv

        if report_format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Rapport", report_type, "Généré le", datetime.now(timezone.utc).isoformat()])
            writer.writerow([])
            for key, value in parameters.items():
                writer.writerow([key, value])
            content = output.getvalue()
            output.close()

            file_ref = Report(
                user_id=current_user.id,
                title=title,
                report_type=report_type,
                format=report_format,
                status="completed",
                parameters=parameters,
                file_size=f"{len(content)} bytes",
            )
            db.add(file_ref)
            await db.commit()
            await db.refresh(file_ref)

            return Response(
                content=content,
                media_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="{title}.csv"',
                    "Report-ID": str(file_ref.id),
                },
            )

        elif report_format == "excel":
            try:
                import pandas
                df = pandas.DataFrame([parameters]) if parameters else pandas.DataFrame({"info": ["Aucune donnée"]})
                output = io.BytesIO()
                with pandas.ExcelWriter(output, engine="openpyxl") as writer:
                    df.to_excel(writer, sheet_name="Rapport", index=False)
                content = output.getvalue()
                output.close()

                file_ref = Report(
                    user_id=current_user.id,
                    title=title,
                    report_type=report_type,
                    format=report_format,
                    status="completed",
                    parameters=parameters,
                    file_size=f"{len(content)} bytes",
                )
                db.add(file_ref)
                await db.commit()
                await db.refresh(file_ref)

                return Response(
                    content=content,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={
                        "Content-Disposition": f'attachment; filename="{title}.xlsx"',
                        "Report-ID": str(file_ref.id),
                    },
                )
            except ImportError:
                raise HTTPException(status_code=400, detail="Le format Excel nécessite la bibliothèque openpyxl")

        elif report_format == "pdf":
            content = f"<html><body><h1>{title}</h1><p>Type: {report_type}</p><p>Généré le: {datetime.now(timezone.utc).isoformat()}</p><pre>{parameters}</pre></body></html>"
            try:
                from weasyprint import HTML
                pdf_bytes = HTML(string=content).write_pdf()
            except ImportError:
                raise HTTPException(status_code=400, detail="Le format PDF nécessite la bibliothèque weasyprint")

            file_ref = Report(
                user_id=current_user.id,
                title=title,
                report_type=report_type,
                format=report_format,
                status="completed",
                parameters=parameters,
                file_size=f"{len(pdf_bytes)} bytes",
            )
            db.add(file_ref)
            await db.commit()
            await db.refresh(file_ref)

            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f'attachment; filename="{title}.pdf"',
                    "Report-ID": str(file_ref.id),
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Report generation error: %s", e)
        raise HTTPException(status_code=500, detail=f"Erreur lors de la génération du rapport: {str(e)}")


@router.get("/history")
async def get_report_history(
    report_type: Optional[str] = Query(None),
    format: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """List previously generated reports for the user"""
    try:
        query = select(Report).where(Report.user_id == current_user.id)

        if report_type:
            query = query.where(Report.report_type == report_type)
        if format:
            query = query.where(Report.format == format)

        total_q = await db.execute(select(func.count()).select_from(query.subquery()))
        total = total_q.scalar() or 0

        query = query.order_by(desc(Report.created_at)).offset((page - 1) * per_page).limit(per_page)
        result = await db.execute(query)
        reports = result.scalars().all()

        return {
            "reports": [
                {
                    "id": str(r.id),
                    "title": r.title,
                    "type": r.report_type,
                    "format": r.format,
                    "status": r.status,
                    "file_size": r.file_size,
                    "parameters": r.parameters,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in reports
            ],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
        }
    except Exception as e:
        logger.error("Report history error: %s", e)
        return {"reports": [], "total": 0, "page": page, "per_page": per_page, "pages": 0}


@router.get("/download/{report_id}")
async def download_report(
    report_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Download a specific report file"""
    try:
        uid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")

    result = await db.execute(select(Report).where(Report.id == uid, Report.user_id == current_user.id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")

    return {
        "id": str(report.id),
        "title": report.title,
        "type": report.report_type,
        "format": report.format,
        "status": report.status,
        "file_size": report.file_size,
        "parameters": report.parameters,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "message": "Le fichier n'est plus disponible sur le serveur. Veuillez regénérer le rapport.",
    }


@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a report"""
    try:
        uid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")

    result = await db.execute(select(Report).where(Report.id == uid, Report.user_id == current_user.id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")

    await db.delete(report)
    await db.commit()
    return {"message": "Rapport supprimé avec succès", "id": report_id}
