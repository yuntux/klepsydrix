from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, date
from typing import Dict, Any, List, Optional
import importlib
import pkgutil
import inspect
from pydantic import BaseModel

from backend.app.core.database import get_db
from backend.app.models.base import Base
import backend.app.models as models_package

# Découverte et import dynamique de tous les modèles dans backend.app.models
for _, module_name, _ in pkgutil.iter_modules(models_package.__path__):
    importlib.import_module(f"backend.app.models.{module_name}")

router = APIRouter(prefix="/api/generic")

from backend.app.models.base import TransientModel

# Génération 100% automatique de la cartographie des modèles sur la base de leur table SQL
MODEL_MAP = {
    mapper.class_.__tablename__: mapper.class_
    for mapper in Base.registry.mappers
    if hasattr(mapper.class_, "__tablename__")
}

# Découvrir et ajouter dynamiquement tous les modèles transitoires (TransientModels)
def get_all_transient_models(cls):
    subclasses = set(cls.__subclasses__())
    return subclasses.union(
        [s for c in subclasses for s in get_all_transient_models(c)]
    )

for sub in get_all_transient_models(TransientModel):
    if getattr(sub, "__tablename__", None):
        MODEL_MAP[sub.__tablename__] = sub

def get_model_or_404(resource_name: str):
    if resource_name not in MODEL_MAP:
        raise HTTPException(status_code=404, detail=f"Ressource '{resource_name}' non supportée.")
    return MODEL_MAP[resource_name]

from pydantic import create_model

def sqla_to_dict(obj) -> Dict[str, Any]:
    if obj is None:
        return {}
    
    fields = []
    if hasattr(obj, "__table__"):
        fields = [c.name for c in obj.__table__.columns]
        
    extra_fields = list(getattr(obj, "_fields", [])) + list(getattr(obj, "_extra_fields", []))
    if extra_fields:
        # Pour un TransientModel, _fields/extra_fields est la source principale, pour les autres c'est en plus des colonnes
        from backend.app.models.base import TransientModel
        if isinstance(obj, TransientModel):
            fields = list(extra_fields)
        else:
            fields = list(set(fields + list(extra_fields)))
        
    if not fields:
        return {}
        
    d = {}
    for field in fields:
        val = getattr(obj, field, None)
        if isinstance(val, (date, datetime)):
            d[field] = val.isoformat()
        else:
            d[field] = val
        
    # Sérialiser automatiquement toutes les relations de type collection en *_ids
    if hasattr(obj, "__mapper__"):
        for rel in obj.__mapper__.relationships:
            if rel.uselist:
                # Déterminer la clé du champ virtuel
                field_name = f"{rel.key}_ids"
                if rel.key.endswith("s"):
                    field_name = f"{rel.key[:-1]}_ids"
                if rel.key.endswith("ies"):
                    field_name = f"{rel.key[:-3]}y_ids"
                
                related_objs = getattr(obj, rel.key, [])
                d[field_name] = [item.id for item in related_objs if hasattr(item, "id")]

    return d

def make_pydantic_model(model, all_optional=False):
    fields = {}
    if issubclass(model, TransientModel):
        for field in getattr(model, "_fields", []):
            fields[field] = (Optional[Any], None)
        suffix = "UpdatePayload" if all_optional else "CreatePayload"
        return create_model(f"{model.__name__}{suffix}", **fields)

    for column in model.__table__.columns:
        if column.name == "id":
            continue
        try:
            py_type = column.type.python_type
        except Exception:
            py_type = Any
        
        if all_optional or column.nullable or column.default is not None or column.server_default is not None:
            fields[column.name] = (Optional[py_type], None)
        else:
            fields[column.name] = (py_type, ...)
            
    # Inclure également les champs virtuels et extra dans le schéma Pydantic
    extra_fields = list(getattr(model, "_fields", [])) + list(getattr(model, "_extra_fields", []))
    for field in extra_fields:
        field_type = getattr(model, "_extra_field_types", {}).get(field, Any)
        fields[field] = (Optional[field_type], None)
        
    # Détecter et inclure automatiquement toutes les relations collection dans le schéma Pydantic
    from sqlalchemy.orm import Mapper
    if hasattr(model, "__mapper__") and isinstance(model.__mapper__, Mapper):
        for rel in model.__mapper__.relationships:
            if rel.uselist:
                field_name = f"{rel.key}_ids"
                if rel.key.endswith("s"):
                    field_name = f"{rel.key[:-1]}_ids"
                if rel.key.endswith("ies"):
                    field_name = f"{rel.key[:-3]}y_ids"
                
                fields[field_name] = (Optional[List[int]], None)
            
    suffix = "UpdatePayload" if all_optional else "CreatePayload"
    return create_model(f"{model.__name__}{suffix}", **fields)

def make_list_endpoint(model):
    def list_endpoint(
        request: Request,
        school_id: Optional[int] = None,
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1),
        db: Session = Depends(get_db)
    ):
        domain = {}
        if school_id is not None:
            if issubclass(model, TransientModel) and "school_id" in getattr(model, "_fields", []):
                domain["school_id"] = school_id
            elif hasattr(model, "school_id"):
                domain["school_id"] = school_id
            
        for key, value in request.query_params.items():
            if key in ["skip", "limit", "school_id"]:
                continue
            if issubclass(model, TransientModel):
                if key in getattr(model, "_fields", []):
                    domain[key] = value
            elif hasattr(model, key):
                try:
                    column_type = model.__table__.columns[key].type.python_type
                    if column_type == bool:
                        converted_val = value.lower() in ("true", "1", "yes")
                    else:
                        converted_val = column_type(value)
                    domain[key] = converted_val
                except Exception:
                    domain[key] = value

        if issubclass(model, TransientModel):
            items = model.read(db, domain=domain, limit=limit, offset=skip)
            return {
                "total": len(items),
                "items": [sqla_to_dict(item) for item in items]
            }

        query = db.query(model)
        for k, v in domain.items():
            query = query.filter(getattr(model, k) == v)
        total = query.count()
        
        items = model.read(db, domain=domain, limit=limit, offset=skip)
        return {
            "total": total,
            "items": [sqla_to_dict(item) for item in items]
        }
    return list_endpoint

def make_get_endpoint(model):
    def get_endpoint(item_id: int, db: Session = Depends(get_db)):
        if issubclass(model, TransientModel):
            # Pour un modèle virtuel, on tente de le lire via un filtre sur ID
            items = model.read(db, domain={"id": item_id})
            item = items[0] if items else None
            if not item:
                raise HTTPException(status_code=404, detail="Élément introuvable.")
            return sqla_to_dict(item)

        item = db.query(model).filter(model.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Élément introuvable.")
        return sqla_to_dict(item)
    return get_endpoint

def clean_payload(model, payload_dict: dict) -> dict:
    if issubclass(model, TransientModel):
        return payload_dict
        
    cleaned = {}
    valid_keys = [c.name for c in model.__table__.columns if c.name != "id"]
    extra_fields = getattr(model, "_fields", [])
    all_keys = valid_keys + extra_fields
    for k, v in payload_dict.items():
        if k in all_keys and v is not None:
            if k in extra_fields:
                cleaned[k] = v
                continue
            column_type = model.__table__.columns[k].type
            if str(column_type) == "DATE" and v:
                cleaned[k] = date.fromisoformat(v) if isinstance(v, str) else v
            elif str(column_type) == "DATETIME" and v:
                cleaned[k] = datetime.fromisoformat(v) if isinstance(v, str) else v
            else:
                cleaned[k] = v
    return cleaned

def make_create_endpoint(model, payload_schema):
    def create_endpoint(payload: payload_schema, db: Session = Depends(get_db)):
        if issubclass(model, TransientModel):
            raise HTTPException(status_code=405, detail="La création n'est pas supportée pour cette ressource transitoire.")

        cleaned_payload = clean_payload(model, payload.model_dump())
        try:
            new_item = model.create(db, cleaned_payload)
            if new_item is None:
                return {"id": 0, "status": "purged"}
            return sqla_to_dict(new_item)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erreur de création : {e}")
    return create_endpoint

def make_update_endpoint(model, payload_schema):
    def update_endpoint(item_id: int, payload: payload_schema, db: Session = Depends(get_db)):
        if issubclass(model, TransientModel):
            raise HTTPException(status_code=405, detail="La mise à jour n'est pas supportée pour cette ressource transitoire.")

        item = db.query(model).filter(model.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Élément introuvable.")

        cleaned_vals = clean_payload(model, payload.model_dump(exclude_unset=True))
        try:
            updated_item = item.update(db, cleaned_vals)
            if updated_item is None:
                return {"id": item_id, "status": "purged"}
            return sqla_to_dict(updated_item)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erreur de mise à jour : {e}")
    return update_endpoint

def make_delete_endpoint(model, resource_name):
    def delete_endpoint(item_id: int, db: Session = Depends(get_db)):
        if issubclass(model, TransientModel):
            raise HTTPException(status_code=405, detail="La suppression n'est pas supportée pour cette ressource transitoire.")

        item = db.query(model).filter(model.id == item_id).first()
        if not item:
            raise HTTPException(status_code=404, detail="Élément introuvable.")
        try:
            item.delete(db)
            return {"status": "success", "message": f"Élément {item_id} de {resource_name} supprimé avec succès."}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Impossible de supprimer l'élément : {e}")
    return delete_endpoint

class CallPayload(BaseModel):
    args: Optional[List[Any]] = []
    kwargs: Optional[Dict[str, Any]] = {}

def serialize_execution_result(result):
    if result is None:
        return None
    if isinstance(result, list):
        return [serialize_execution_result(item) for item in result]
    if isinstance(result, dict):
        return {k: serialize_execution_result(v) for k, v in result.items()}
    # Si c'est un modèle classique SQLAlchemy ou TransientModel
    if hasattr(result, "__table__") or isinstance(result, TransientModel):
        return sqla_to_dict(result)
    return result

def make_class_call_endpoint(model):
    def class_call_endpoint(
        method_name: str,
        payload: CallPayload,
        db: Session = Depends(get_db)
    ):
        if not hasattr(model, method_name):
            raise HTTPException(status_code=404, detail=f"Méthode '{method_name}' introuvable sur le modèle {model.__name__}.")
        
        func = getattr(model, method_name)
        if not callable(func):
            raise HTTPException(status_code=400, detail=f"L'attribut '{method_name}' n'est pas exécutable.")
            
        args = payload.args or []
        kwargs = payload.kwargs or {}
        
        try:
            sig = inspect.signature(func)
            if "db" in sig.parameters:
                kwargs["db"] = db
        except Exception:
            pass
            
        try:
            result = func(*args, **kwargs)
            db.commit()
            return serialize_execution_result(result)
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Erreur lors de l'exécution de la méthode de classe : {e}")
            
    return class_call_endpoint

def make_instance_call_endpoint(model):
    def instance_call_endpoint(
        item_id: int,
        method_name: str,
        payload: CallPayload,
        db: Session = Depends(get_db)
    ):
        if issubclass(model, TransientModel):
            items = model.read(db, domain={"id": item_id})
            instance = items[0] if items else None
        else:
            instance = db.query(model).filter(model.id == item_id).first()
            
        if not instance:
            raise HTTPException(status_code=404, detail="Instance introuvable.")
            
        if not hasattr(instance, method_name):
            raise HTTPException(status_code=404, detail=f"Méthode '{method_name}' introuvable sur l'instance.")
            
        func = getattr(instance, method_name)
        if not callable(func):
            raise HTTPException(status_code=400, detail=f"L'attribut '{method_name}' n'est pas exécutable.")
            
        args = payload.args or []
        kwargs = payload.kwargs or {}
        
        try:
            sig = inspect.signature(func)
            if "db" in sig.parameters:
                kwargs["db"] = db
        except Exception:
            pass
            
        try:
            result = func(*args, **kwargs)
            db.commit()
            return serialize_execution_result(result)
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Erreur lors de l'exécution de la méthode d'instance : {e}")
            
    return instance_call_endpoint

# Génération dynamique des routes explicites et typées au chargement pour toutes les ressources
for resource_name, model in MODEL_MAP.items():
    create_schema = make_pydantic_model(model, all_optional=False)
    update_schema = make_pydantic_model(model, all_optional=True)
    
    # 1. Lister les ressources (GET /api/generic/{resource_name})
    router.add_api_route(
        path=f"/{resource_name}",
        endpoint=make_list_endpoint(model),
        methods=["GET"],
        response_model=Dict[str, Any],
        summary=f"Lister les {resource_name}",
        tags=[resource_name]
    )
    
    # 2. Obtenir une ressource spécifique (GET /api/generic/{resource_name}/{item_id})
    router.add_api_route(
        path=f"/{resource_name}/{{item_id}}",
        endpoint=make_get_endpoint(model),
        methods=["GET"],
        response_model=Dict[str, Any],
        summary=f"Obtenir un(e) {resource_name} par ID",
        tags=[resource_name]
    )
    
    # 3. Créer une nouvelle ressource (POST /api/generic/{resource_name})
    router.add_api_route(
        path=f"/{resource_name}",
        endpoint=make_create_endpoint(model, create_schema),
        methods=["POST"],
        response_model=Dict[str, Any],
        summary=f"Créer un(e) {resource_name}",
        tags=[resource_name]
    )
    
    # 4. Mettre à jour une ressource (PATCH /api/generic/{resource_name}/{item_id})
    router.add_api_route(
        path=f"/{resource_name}/{{item_id}}",
        endpoint=make_update_endpoint(model, update_schema),
        methods=["PATCH"],
        response_model=Dict[str, Any],
        summary=f"Mettre à jour un(e) {resource_name} par ID",
        tags=[resource_name]
    )
    
    # 5. Supprimer une ressource (DELETE /api/generic/{resource_name}/{item_id})
    router.add_api_route(
        path=f"/{resource_name}/{{item_id}}",
        endpoint=make_delete_endpoint(model, resource_name),
        methods=["DELETE"],
        response_model=Dict[str, Any],
        summary=f"Supprimer un(e) {resource_name} par ID",
        tags=[resource_name]
    )

    # 6. Appel de méthode de classe dynamique (POST /api/generic/{resource_name}/call/{method_name})
    router.add_api_route(
        path=f"/{resource_name}/call/{{method_name}}",
        endpoint=make_class_call_endpoint(model),
        methods=["POST"],
        response_model=Any,
        summary=f"Appeler une méthode de classe sur {resource_name}",
        tags=[resource_name]
    )

    # 7. Appel de méthode d'instance dynamique (POST /api/generic/{resource_name}/{item_id}/call/{method_name})
    router.add_api_route(
        path=f"/{resource_name}/{{item_id}}/call/{{method_name}}",
        endpoint=make_instance_call_endpoint(model),
        methods=["POST"],
        response_model=Any,
        summary=f"Appeler une méthode d'instance sur {resource_name}",
        tags=[resource_name]
    )

