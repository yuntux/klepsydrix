from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, date
from typing import Dict, Any, List, Optional

from backend.app.core.database import get_db
from backend.app.models.school import School
from backend.app.models.discipline import Discipline
from backend.app.models.family import Family
from backend.app.models.subject import Subject
from backend.app.models.mef import Mef, MefService
from backend.app.models.trmd_budget import TrmdBudget
from backend.app.models.classroom import Classroom
from backend.app.models.teacher import Teacher
from backend.app.models.division import Division
from backend.app.models.material import Material
from backend.app.models.mission import Mission
from backend.app.models.election_method import ElectionMethod
from backend.app.models.group import Partition, ClassPart, ClassPartLink, Group
from backend.app.models.period import Period
from backend.app.models.alternation import Alternation
from backend.app.models.site import Site, SiteTravelTime
from backend.app.models.timeslot import Timeslot
from backend.app.models.preference import ResourcePreference

router = APIRouter(prefix="/api/generic")

MODEL_MAP = {
    "schools": School,
    "disciplines": Discipline,
    "families": Family,
    "subjects": Subject,
    "mefs": Mef,
    "mef_services": MefService,
    "trmd_budgets": TrmdBudget,
    "classrooms": Classroom,
    "teachers": Teacher,
    "divisions": Division,
    "materials": Material,
    "missions": Mission,
    "election_methods": ElectionMethod,
    "partitions": Partition,
    "class_parts": ClassPart,
    "class_part_links": ClassPartLink,
    "groups": Group,
    "periods": Period,
    "alternations": Alternation,
    "sites": Site,
    "site_travel_times": SiteTravelTime,
    "timeslots": Timeslot,
    "resource_preferences": ResourcePreference,
}

def get_model_or_404(resource_name: str):
    if resource_name not in MODEL_MAP:
        raise HTTPException(status_code=404, detail=f"Ressource '{resource_name}' non supportée.")
    return MODEL_MAP[resource_name]

def sqla_to_dict(obj) -> Dict[str, Any]:
    if obj is None:
        return {}
    d = {}
    for column in obj.__table__.columns:
        val = getattr(obj, column.name)
        if isinstance(val, (date, datetime)):
            d[column.name] = val.isoformat()
        else:
            d[column.name] = val
    return d

@router.get("/{resource_name}", response_model=Dict[str, Any])
def list_generic(
    resource_name: str,
    request: Request,
    school_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    db: Session = Depends(get_db)
):
    model = get_model_or_404(resource_name)
    
    # Construire le domain de filtrage
    domain = {}
    if school_id is not None and hasattr(model, "school_id"):
        domain["school_id"] = school_id
        
    for key, value in request.query_params.items():
        if key in ["skip", "limit", "school_id"]:
            continue
        if hasattr(model, key):
            try:
                column_type = model.__table__.columns[key].type.python_type
                if column_type == bool:
                    converted_val = value.lower() in ("true", "1", "yes")
                else:
                    converted_val = column_type(value)
                domain[key] = converted_val
            except Exception:
                domain[key] = value

    # Calculer le total (count) sur la base du domain
    query = db.query(model)
    for k, v in domain.items():
        query = query.filter(getattr(model, k) == v)
    total = query.count()
    
    # Lire les instances Python en appelant la méthode de classe surchargeable
    items = model.read(db, domain=domain, limit=limit, offset=skip)
    
    return {
        "total": total,
        "items": [sqla_to_dict(item) for item in items]
    }

@router.get("/{resource_name}/{item_id}", response_model=Dict[str, Any])
def get_generic(resource_name: str, item_id: int, db: Session = Depends(get_db)):
    model = get_model_or_404(resource_name)
    item = db.query(model).filter(model.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail=f"Élément {item_id} introuvable.")
    return sqla_to_dict(item)

@router.post("/{resource_name}", response_model=Dict[str, Any])
def create_generic(resource_name: str, payload: Dict[str, Any], db: Session = Depends(get_db)):
    model = get_model_or_404(resource_name)
    
    # Nettoyer le payload pour ne garder que les colonnes valides
    valid_keys = [c.name for c in model.__table__.columns if c.name != "id"]
    cleaned_payload = {}
    for k, v in payload.items():
        if k in valid_keys:
            # Conversion des dates si nécessaire
            column_type = model.__table__.columns[k].type
            if str(column_type) == "DATE" and v:
                cleaned_payload[k] = date.fromisoformat(v)
            elif str(column_type) == "DATETIME" and v:
                cleaned_payload[k] = datetime.fromisoformat(v)
            else:
                cleaned_payload[k] = v

    try:
        new_item = model.create(db, cleaned_payload)
        if new_item is None:
            return {"id": 0, "status": "purged"}
        return sqla_to_dict(new_item)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur de création : {e}")

@router.put("/{resource_name}/{item_id}", response_model=Dict[str, Any])
def update_generic(resource_name: str, item_id: int, payload: Dict[str, Any], db: Session = Depends(get_db)):
    model = get_model_or_404(resource_name)
    item = db.query(model).filter(model.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail=f"Élément {item_id} introuvable.")

    valid_keys = [c.name for c in model.__table__.columns if c.name != "id"]
    cleaned_vals = {}
    try:
        for k, v in payload.items():
            if k in valid_keys:
                column_type = model.__table__.columns[k].type
                if str(column_type) == "DATE" and v:
                    cleaned_vals[k] = date.fromisoformat(v)
                elif str(column_type) == "DATETIME" and v:
                    cleaned_vals[k] = datetime.fromisoformat(v)
                else:
                    cleaned_vals[k] = v
        
        updated_item = item.update(db, cleaned_vals)
        if updated_item is None:
            return {"id": item_id, "status": "purged"}
        return sqla_to_dict(updated_item)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur de mise à jour : {e}")

@router.delete("/{resource_name}/{item_id}")
def delete_generic(resource_name: str, item_id: int, db: Session = Depends(get_db)):
    model = get_model_or_404(resource_name)
    item = db.query(model).filter(model.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail=f"Élément {item_id} introuvable.")
    
    try:
        item.delete(db)
        return {"status": "success", "message": f"Élément {item_id} de {resource_name} supprimé avec succès."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Impossible de supprimer l'élément : {e}")

