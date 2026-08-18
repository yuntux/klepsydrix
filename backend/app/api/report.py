"""
Endpoint générique d'impression (voir architecture.md §22) — UNE route paramétrée par le nom du
rapport, pas une route par document. Ajouter un PDF ne demande donc jamais de toucher au routage :
seulement une entrée dans `reports/REGISTRY` et un gabarit.

Reprend la forme d'Odoo (`/report/pdf/<reportname>/<docids>`), à un écart près : pas d'équivalent
de `/report/download`. Odoo en a besoin parce que le navigateur navigue directement vers l'URL ;
ici c'est impossible — `resolve_database` exige l'en-tête `X-Klepsydrix-Database`, qu'un
`window.open()` ou un `<a href>` ne peut pas porter. Le frontend télécharge donc via `apiFetch()`
puis un blob (voir services/api.ts::downloadReport), ce qui a l'avantage de garder TOUTES les
requêtes sur le chemin unique qui gère le jeton d'écriture et les redirections d'authentification.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.reports import REGISTRY, get_report
from backend.app.reports.base import render_html, render_pdf

router = APIRouter(prefix="/api/report")


@router.get("/registry", summary="Lister les rapports disponibles")
def list_reports():
    """Sert à l'IHM (et au débogage) pour connaître les rapports sans les coder en dur côté client."""
    return [
        {
            "name": report.name,
            "label": report.label,
            "resource": report.model.__tablename__,
            "paperformat": report.paperformat,
        }
        for report in REGISTRY.values()
    ]


@router.get("/{report_name}", summary="Générer un rapport (PDF par défaut)")
def generate_report(
    report_name: str,
    ids: str = Query("", description="Identifiants séparés par des virgules. Vide = tout ce qui est accessible."),
    format: str = Query("pdf", pattern="^(pdf|html)$"),
    db: Session = Depends(get_db),
):
    """
    `format=html` n'est pas un gadget : c'est ce qui permet d'itérer sur un gabarit dans le
    navigateur sans regénérer un PDF à chaque fois, et c'est sur ce rendu que portent les tests de
    contenu. Emprunt direct à `/report/html/` d'Odoo.

    Aucun contrôle de droits explicite ici : `get_values` lit via `read()`/`browse()`, donc le
    moteur de droits et son domaine s'appliquent déjà (voir architecture.md §18.B). `ids` vide est
    une RECHERCHE (filtrage silencieux) ; `ids` fourni est une DÉSIGNATION, et `browse()` lève
    alors `AccessDeniedError` — traduite en 403 par le gestionnaire global — plutôt que de
    produire un document amputé d'apparence complète (§18.I).
    """
    report = get_report(report_name)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Rapport « {report_name} » inconnu.")

    try:
        parsed_ids = [int(value) for value in ids.split(",") if value.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Le paramètre « ids » doit être une liste d'entiers séparés par des virgules.")

    if format == "html":
        return Response(content=render_html(report, db, parsed_ids, {}), media_type="text/html")

    pdf = render_pdf(report, db, parsed_ids, {})
    return Response(
        content=pdf,
        media_type="application/pdf",
        # Le nom de fichier est calculé côté serveur (équivalent de `print_report_name` d'Odoo) et
        # jamais reconstruit côté client. Volontairement sans accent : évite d'avoir à recourir à
        # l'encodage RFC 5987 (filename*=UTF-8'') pour un gain nul.
        headers={"Content-Disposition": f'attachment; filename="{report.filename(db, parsed_ids)}"'},
    )
