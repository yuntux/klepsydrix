from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Union
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

from backend.app.models.base import TransientModel, UnsupportedOperationError, AccessDeniedError
from backend.app.core.exclusive_mode import ExclusiveModeActiveError

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

from pydantic import create_model, Field

def sqla_to_dict(obj) -> Dict[str, Any]:
    if obj is None:
        return {}
    
    fields = []
    if hasattr(obj, "__table__"):
        # info={"private": True} (voir base.py) : jamais sérialisé par l'API générique, quel que
        # soit l'appelant — réservé aux colonnes qui ne doivent JAMAIS transiter par une réponse
        # HTTP générique (ex: UserIdentityProvider.password_hash), pas seulement en lecture par
        # défaut comme readOnly.
        fields = [c.name for c in obj.__table__.columns if not (c.info or {}).get("private")]

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

def make_pydantic_model(model, all_optional=False, include_id=False):
    fields = {}
    if issubclass(model, TransientModel):
        if include_id:
            fields["id"] = (int, ...)
        field_info = getattr(model, "_field_info", {})
        for field in getattr(model, "_fields", []):
            info = field_info.get(field, {})
            field_kwargs = {}
            if info:
                if "label" in info:
                    field_kwargs["title"] = info["label"]
                json_schema_extra = {k: v for k, v in info.items() if k not in ("label", "type")}
                if "type" in info:
                    json_schema_extra["ui_type"] = info["type"]
                if json_schema_extra:
                    field_kwargs["json_schema_extra"] = json_schema_extra
            fields[field] = (Optional[Any], Field(None, **field_kwargs) if field_kwargs else None)
        suffix = "_ReadPayload" if include_id else ("_UpdatePayload" if all_optional else "_CreatePayload")
        base_name = getattr(model, "__tablename__", model.__name__)
        return create_model(f"{base_name}{suffix}", **fields)

    if include_id:
        fields["id"] = (int, ...)

    for column in model.__table__.columns:
        if column.name == "id":
            continue
        if (column.info or {}).get("private"):
            # Jamais exposée par l'API générique — ni lue (voir sqla_to_dict) ni acceptée en
            # entrée ici : un champ "private" n'existe tout simplement pas pour /api/generic/*.
            continue
        try:
            py_type = column.type.python_type
        except Exception:
            py_type = Any
            
        field_kwargs = {}
        json_schema_extra = {}
        if hasattr(column, "info") and column.info:
            if "label" in column.info:
                field_kwargs["title"] = column.info["label"]
            json_schema_extra = {k: (v() if callable(v) else v) for k, v in column.info.items() if k not in ("label", "type")}
            if "type" in column.info:
                json_schema_extra["ui_type"] = column.info["type"]

        # Nullabilité RÉELLE de la colonne SQL (distincte du wrapping Optional[...] ci-dessous,
        # qui ne reflète que "peut être omis d'un payload partiel" dès qu'une colonne a un default
        # — voir clean_payload : un champ non-nullable ne doit jamais offrir de bouton "effacer"
        # côté frontend, sans quoi le clic est un no-op silencieux).
        json_schema_extra["nullable"] = column.nullable

        # Détection automatique de la ressource liée via la clé étrangère SQL
        if hasattr(column, "foreign_keys") and column.foreign_keys:
            fk_list = list(column.foreign_keys)
            if fk_list:
                target_table = fk_list[0].column.table.name
                json_schema_extra["resource"] = target_table
                
        if json_schema_extra:
            field_kwargs["json_schema_extra"] = json_schema_extra
        
        pydantic_default = None
        if column.default is not None and hasattr(column.default, "arg") and not callable(column.default.arg):
            pydantic_default = column.default.arg
        elif all_optional or column.nullable or column.server_default is not None:
            pydantic_default = None

        if pydantic_default is None and not all_optional and not column.nullable and column.default is None and column.server_default is None:
            fields[column.name] = (py_type, Field(..., **field_kwargs))
        else:
            fields[column.name] = (Optional[py_type], Field(pydantic_default, **field_kwargs))
            
    # Inclure également les champs virtuels et extra dans le schéma Pydantic
    extra_fields = list(getattr(model, "_fields", [])) + list(getattr(model, "_extra_fields", []))
    for field in extra_fields:
        field_type = getattr(model, "_extra_field_types", {}).get(field, Any)
        field_kwargs = {}
        descriptor = getattr(model, field, None)
        info = getattr(descriptor, "info", None)
        if info:
            if "label" in info:
                field_kwargs["title"] = info["label"]
            json_schema_extra = {k: (v() if callable(v) else v) for k, v in info.items() if k not in ("label", "type")}
            if "type" in info:
                json_schema_extra["ui_type"] = info["type"]
            if json_schema_extra:
                field_kwargs["json_schema_extra"] = json_schema_extra
        fields[field] = (Optional[field_type], Field(None, **field_kwargs))
        
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
                
                target_table = rel.mapper.class_.__tablename__
                title = rel.info.get("label", field_name.replace("_", " ").title())
                rel_schema_extra = {"resource": target_table, "ui_type": "multiselect"}
                if rel.secondary is None:
                    # Relation 1-à-N "possédée" (pas un many-to-many via table d'association) :
                    # expose le nom de la FK de retour côté enfant, pour permettre au frontend
                    # d'ouvrir une popin CRUD générique filtrée sur ce champ (GenericListModal)
                    # sans aucune configuration ui.json dédiée. Absent pour un vrai m2m (ex:
                    # teacher_ids) où les enregistrements pointés existent indépendamment du
                    # parent et ne doivent pas être créés/supprimés depuis cette popin.
                    for local_col, remote_col in rel.local_remote_pairs:
                        if remote_col.table is rel.mapper.class_.__table__:
                            rel_schema_extra["parentField"] = rel.mapper.get_property_by_column(remote_col).key
                            break
                for k, v in rel.info.items():
                    if k not in ("label", "type"):
                        rel_schema_extra[k] = v() if callable(v) else v
                # Une relation possédée (parentField présent, voir ci-dessus) accepte aussi des
                # "commandes" façon Odoo one2many — un dict {id?, **champs} par ligne plutôt qu'un
                # simple id — voir CRUDMixin._apply_owned_collection_commands (base.py,
                # architecture.md section 15.J). Un vrai many-to-many (secondary is not None, ex:
                # teacher_ids) reste strictement une liste d'ids : ses enregistrements existent
                # indépendamment du parent, ce mécanisme de commandes n'a pas de sens pour lui.
                item_type = Union[int, Dict[str, Any]] if rel.secondary is None else int
                fields[field_name] = (Optional[List[item_type]], Field(None, title=title, json_schema_extra=rel_schema_extra))
            
    suffix = "_ReadPayload" if include_id else ("_UpdatePayload" if all_optional else "_CreatePayload")
    base_name = getattr(model, "__tablename__", model.__name__)
    return create_model(f"{base_name}{suffix}", **fields)

def make_list_endpoint(model):
    def list_endpoint(
        request: Request,
        school_id: Optional[int] = None,
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1),
        db: Session = Depends(get_db)
    ):
        # Un champ est "filtrable" s'il correspond à un attribut de classe réel (colonne, related_field,
        # relation...) ou à un champ déclaré par un TransientModel (_fields) — une seule condition
        # valable pour les deux types de modèle, pas besoin de savoir lequel on a en face.
        def is_filterable(key: str) -> bool:
            return hasattr(model, key) or key in getattr(model, "_fields", [])

        domain = {}
        if school_id is not None and is_filterable("school_id"):
            domain["school_id"] = school_id

        # Filtre par liste d'IDs explicite (ex: "ids=12,45,78") — nécessaire pour tout consommateur
        # qui veut filtrer sur un champ dérivé non-SQL (related_field, ex: division_id/mef_id sur
        # Service : une simple property Python, pas une colonne filtrable en SQL) : plutôt que
        # filtrer côté serveur sur ce champ, on calcule les IDs pertinents côté client puis on
        # filtre ici sur `id`, une vraie colonne, toujours filtrable. Voir GenericListModal (prop
        # `ids`) et GenericPivot, architecture.md section 15.L. Passer une liste comme valeur du
        # domaine "id" est reconnu génériquement par CRUDMixin._apply_domain comme un IN(...).
        ids_param = request.query_params.get("ids")
        if ids_param:
            try:
                domain["id"] = [int(v) for v in ids_param.split(",") if v.strip() != ""]
            except ValueError:
                raise HTTPException(status_code=400, detail="Le paramètre 'ids' doit être une liste d'entiers séparés par des virgules.")

        for key, value in request.query_params.items():
            if key in ["skip", "limit", "school_id", "ids"] or not is_filterable(key):
                continue
            # Cast du type Python de l'attribut (ex: "true" -> bool, "3" -> int) quand SQLAlchemy
            # sait en exposer un — vraie colonne SQL, mais aussi hybrid_property avec .expression
            # (ex: Timeslot.active, voir timeslot.py) : les deux exposent .type.python_type de la
            # même façon au niveau classe. Sinon (related_field, champ TransientModel...), qui
            # n'ont pas de .type, l'exception retombe sur la valeur brute.
            try:
                column_type = getattr(model, key).type.python_type
                domain[key] = (value.lower() in ("true", "1", "yes")) if column_type == bool else column_type(value)
            except Exception:
                domain[key] = value

        total = model.count(db, domain)
        items = model.read(db, domain=domain, limit=limit, offset=skip)
        return {
            "total": total,
            "items": [sqla_to_dict(item) for item in items]
        }
    return list_endpoint

def make_get_endpoint(model):
    def get_endpoint(item_id: int, db: Session = Depends(get_db)):
        items = model.read(db, domain={"id": item_id})
        item = items[0] if items else None
        if not item:
            raise HTTPException(status_code=404, detail="Élément introuvable.")
        return sqla_to_dict(item)
    return get_endpoint

def make_display_name_endpoint(model):
    def display_name_endpoint(item_id: int, db: Session = Depends(get_db)):
        from backend.app.core.access_control import get_display_name_unchecked
        name = get_display_name_unchecked(db, model, item_id)
        if name is None:
            raise HTTPException(status_code=404, detail="Élément introuvable.")
        return {"id": item_id, "display_name": name}
    return display_name_endpoint

def make_create_endpoint(model, payload_schema):
    def create_endpoint(payload: payload_schema, db: Session = Depends(get_db)):
        cleaned_payload = model.clean_payload(payload.model_dump())
        try:
            new_item = model.create(db, cleaned_payload)
            if new_item is None:
                from fastapi.responses import JSONResponse
                return JSONResponse(content={"id": 0, "status": "purged"})
            db.refresh(new_item)
            return sqla_to_dict(new_item)
        except UnsupportedOperationError as e:
            raise HTTPException(status_code=405, detail=str(e))
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except ExclusiveModeActiveError as e:
            raise HTTPException(status_code=423, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erreur de création : {e}")
    return create_endpoint

def make_update_endpoint(model, payload_schema):
    def update_endpoint(item_id: int, payload: payload_schema, db: Session = Depends(get_db)):
        items = model.read(db, domain={"id": item_id})
        item = items[0] if items else None
        if not item:
            raise HTTPException(status_code=404, detail="Élément introuvable.")

        cleaned_vals = model.clean_payload(payload.model_dump(exclude_unset=True), allow_null=True)
        try:
            updated_item = item.update(db, cleaned_vals)
            if updated_item is None:
                return {"id": item_id, "status": "purged"}
            # db.refresh() DISCARDE tout changement d'attribut non flushé (remplacé par l'état
            # actuellement en base) : un modèle qui, comme Course.update(), continue à modifier
            # self APRÈS le dernier flush interne à CRUDMixin.update() (ex: recompute_status(),
            # appelée après le flush de la ligne 476/486 de base.py) verrait ces changements
            # silencieusement perdus par le refresh ci-dessous sans ce flush préalable.
            db.flush()
            db.refresh(updated_item)
            return sqla_to_dict(updated_item)
        except UnsupportedOperationError as e:
            raise HTTPException(status_code=405, detail=str(e))
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except ExclusiveModeActiveError as e:
            raise HTTPException(status_code=423, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    return update_endpoint

def make_onchange_endpoint(model):
    from pydantic import BaseModel
    
    class OnchangePayload(BaseModel):
        values: dict
        field_changed: str
        
    def onchange_endpoint(payload: OnchangePayload, db: Session = Depends(get_db)):
        try:
            # L'instance de brouillon reste en mémoire (voir process_onchange) : db ne sert qu'aux
            # méthodes @onchange qui déclarent un paramètre `db` pour résoudre une relation en
            # lecture seule (ex: address_city_id -> RefCity.country_id).
            diff = model.process_onchange(db, payload.values, payload.field_changed)
            return {"status": "success", "diff": diff}
        except Exception as e:
            return {"status": "error", "message": str(e), "diff": {}}
    
    return onchange_endpoint

def make_defaults_endpoint(model):
    from pydantic import BaseModel

    class DefaultsPayload(BaseModel):
        context: dict = {}

    def defaults_endpoint(payload: DefaultsPayload, db: Session = Depends(get_db)):
        # 1. Défauts statiques déjà connus du schéma (column.default), même logique que
        # make_pydantic_model — pour que le frontend n'ait pas à dupliquer field.default.
        defaults = {}
        if hasattr(model, "__table__"):
            for column in model.__table__.columns:
                if column.default is not None and hasattr(column.default, "arg") and not callable(column.default.arg):
                    defaults[column.name] = column.default.arg
        # 2. Défauts calculés dynamiquement par le modèle à partir du contexte (voir
        # CRUDMixin.default_get, pendant de default_get() côté Odoo).
        try:
            dynamic_defaults = model.default_get(db, payload.context)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        defaults.update(dynamic_defaults or {})
        return defaults

    return defaults_endpoint

def make_delete_endpoint(model, resource_name: str):
    def delete_endpoint(item_id: int, db: Session = Depends(get_db)):
        items = model.read(db, domain={"id": item_id})
        item = items[0] if items else None
        if not item:
            raise HTTPException(status_code=404, detail="Élément introuvable.")
        try:
            item.delete(db)
            return {"status": "success", "message": f"Élément {item_id} de {resource_name} supprimé avec succès."}
        except UnsupportedOperationError as e:
            raise HTTPException(status_code=405, detail=str(e))
        except AccessDeniedError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except ExclusiveModeActiveError as e:
            raise HTTPException(status_code=423, detail=str(e))
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

def _check_rpc_access(model, method_name: str, func, db: Session):
    """
    Garde-fou RPC (voir architecture.md, moteur de droits, base.py::requires_access) : une méthode
    appelée via /call/{method_name} n'appelle pas systématiquement create()/update()/delete() (déjà
    protégées) — un calcul, un export, le déclenchement du solveur y échapperaient sinon totalement.
    Refus par défaut pour toute méthode non décorée @requires_access. Mode système
    (db.klepsydrix_user_id absent) : toujours autorisé, comme le reste du moteur de droits.
    """
    user_id = getattr(db, "klepsydrix_user_id", None)
    if user_id is None:
        return
    required_operation = getattr(func, "_requires_access", None)
    if required_operation is None:
        raise HTTPException(status_code=403, detail=f"Méthode '{method_name}' non autorisée en appel distant (non décorée @requires_access).")
    from backend.app.core.access_control import access_rows_for
    from backend.app.models.user import User
    user = db.get(User, user_id)
    if not access_rows_for(db, model, user, required_operation):
        raise HTTPException(status_code=403, detail=f"Droit « {required_operation} » refusé sur {model.__tablename__}.")


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

        _check_rpc_access(model, method_name, func, db)

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
            return serialize_execution_result(result)
        except ExclusiveModeActiveError as e:
            raise HTTPException(status_code=423, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Erreur lors de l'exécution de la méthode de classe : {e}")

    return class_call_endpoint

def make_instance_call_endpoint(model):
    def instance_call_endpoint(
        item_id: int,
        method_name: str,
        payload: CallPayload,
        db: Session = Depends(get_db)
    ):
        items = model.read(db, domain={"id": item_id})
        instance = items[0] if items else None

        if not instance:
            raise HTTPException(status_code=404, detail="Instance introuvable.")
            
        if not hasattr(instance, method_name):
            raise HTTPException(status_code=404, detail=f"Méthode '{method_name}' introuvable sur l'instance.")
            
        func = getattr(instance, method_name)
        if not callable(func):
            raise HTTPException(status_code=400, detail=f"L'attribut '{method_name}' n'est pas exécutable.")

        _check_rpc_access(model, method_name, func, db)

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
        except ExclusiveModeActiveError as e:
            db.rollback()
            raise HTTPException(status_code=423, detail=str(e))
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Erreur lors de l'exécution de la méthode d'instance : {e}")

    return instance_call_endpoint

def make_actions_endpoint(model):
    def actions_endpoint():
        return getattr(model, "__actions__", [])
    return actions_endpoint

# Génération dynamique des routes explicites et typées au chargement pour toutes les ressources
for resource_name, model in MODEL_MAP.items():
    create_schema = make_pydantic_model(model, all_optional=False)
    update_schema = make_pydantic_model(model, all_optional=True)
    read_schema = make_pydantic_model(model, include_id=True)
    base_name = getattr(model, "__tablename__", model.__name__)
    list_schema = create_model(
        f"{base_name}_ListResponse",
        total=(int, ...),
        items=(List[read_schema], ...)
    )
    
    # 1. Lister les ressources (GET /api/generic/{resource_name})
    router.add_api_route(
        path=f"/{resource_name}",
        endpoint=make_list_endpoint(model),
        methods=["GET"],
        response_model=list_schema,
        summary=f"Lister les {resource_name}",
        tags=[resource_name]
    )
    # 1.5. Obtenir les actions génériques du modèle (GET /api/generic/{resource_name}/actions)
    router.add_api_route(
        path=f"/{resource_name}/actions",
        endpoint=make_actions_endpoint(model),
        methods=["GET"],
        response_model=List[Dict[str, Any]],
        summary=f"Obtenir les actions métier sur {resource_name}",
        tags=[resource_name]
    )
    
    # 2. Obtenir une ressource spécifique (GET /api/generic/{resource_name}/{item_id})
    router.add_api_route(
        path=f"/{resource_name}/{{item_id}}",
        endpoint=make_get_endpoint(model),
        methods=["GET"],
        response_model=read_schema,
        summary=f"Obtenir un(e) {resource_name} par ID",
        tags=[resource_name]
    )

    # 2bis. Libellé seul d'une ressource, en lecture privilégiée (voir architecture.md,
    # "display_name d'une relation non lisible" — moteur de droits) — pour résoudre le libellé
    # d'une relation que l'utilisateur courant ne peut pas lire dans son intégralité.
    router.add_api_route(
        path=f"/{resource_name}/{{item_id}}/display_name",
        endpoint=make_display_name_endpoint(model),
        methods=["GET"],
        response_model=Dict[str, Any],
        summary=f"Obtenir le libellé (display_name) d'un(e) {resource_name} par ID, sans contrôle de droit",
        tags=[resource_name]
    )

    # 3. Créer une nouvelle ressource (POST /api/generic/{resource_name})
    router.add_api_route(
        path=f"/{resource_name}",
        endpoint=make_create_endpoint(model, create_schema),
        methods=["POST"],
        response_model=read_schema,
        summary=f"Créer un(e) {resource_name}",
        tags=[resource_name]
    )
    
    # 4. Mettre à jour une ressource (PATCH /api/generic/{resource_name}/{item_id})
    router.add_api_route(
        path=f"/{resource_name}/{{item_id}}",
        endpoint=make_update_endpoint(model, update_schema),
        methods=["PATCH"],
        response_model=read_schema,
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

    # 6. Onchange de formulaire (POST /api/generic/{resource_name}/onchange)
    router.add_api_route(
        path=f"/{resource_name}/onchange",
        endpoint=make_onchange_endpoint(model),
        methods=["POST"],
        response_model=Dict[str, Any],
        summary=f"Obtenir les modifications automatiques pour {resource_name}",
        tags=[resource_name]
    )

    # 6bis. Valeurs par défaut d'un nouvel enregistrement, dépendantes d'un contexte
    # (POST /api/generic/{resource_name}/defaults) — pendant de default_get() côté Odoo.
    router.add_api_route(
        path=f"/{resource_name}/defaults",
        endpoint=make_defaults_endpoint(model),
        methods=["POST"],
        response_model=Dict[str, Any],
        summary=f"Obtenir les valeurs par défaut pour un nouvel(le) {resource_name}",
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

