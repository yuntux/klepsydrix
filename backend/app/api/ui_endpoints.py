import json
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.core.database import get_db, current_db_user
from backend.app.core.instance_session import InstanceSession, require_instance_session

router = APIRouter(prefix="/api/ui")


def validate_menu_ids(nodes: list, parent_label: str = "racine") -> None:
    """
    Vérifie qu'aucun id n'est dupliqué parmi des nœuds frères (même niveau, même parent) de
    l'arbre ui.json — condition nécessaire à la résolution d'un chemin d'URL de navigation (ex:
    /timetable_root/teachers_setting/teachers_preferences_tab, voir architecture.md) : deux
    frères partageant le même id rendraient cette résolution ambiguë côté frontend. Lève
    ValueError plutôt que de laisser un ui.json cassé produire une navigation incohérente en
    silence.
    """
    seen = set()
    for node in nodes:
        node_id = node.get("id")
        if node_id in seen:
            raise ValueError(f"ui.json invalide : id « {node_id} » dupliqué parmi les nœuds enfants de « {parent_label} ».")
        seen.add(node_id)
        children = node.get("children")
        if children:
            validate_menu_ids(children, parent_label=node_id)


def _resource_model(resource_key: str):
    from backend.app.api.generic import MODEL_MAP
    return MODEL_MAP.get(resource_key)


def _has_access(db: Session, resource_key: str, user, operation: str) -> bool:
    """Ressource inconnue de MODEL_MAP : ne bloque pas silencieusement (pas le rôle de ce filtre de
    valider ui.json), laisse passer — validate_menu_ids et les tests couvrent déjà la cohérence du fichier."""
    model = _resource_model(resource_key)
    if model is None:
        return True
    from backend.app.core.access_control import access_rows_for
    return bool(access_rows_for(db, model, user, operation))


def filter_menu_for_user(nodes: list, db: Session, user, group_names: set) -> list:
    """
    Filtrage bottom-up de l'arbre ui.json par droits (voir architecture.md, moteur de droits) :
    - Balise `groups` (liste de noms de ResGroup) sur N'IMPORTE QUEL nœud : l'utilisateur doit
      appartenir à au moins un de ces groupes (héritage compris) pour que la branche entière soit
      affichée — vérifié EN PLUS des règles ci-dessous, pas à la place.
    - Nœud intermédiaire (`children`) : affiché seulement si au moins un enfant filtré subsiste.
    - Feuille `panels` : affichée seulement si l'utilisateur a au moins un droit de LECTURE sur
      CHAQUE `resourceKey` référencé par ses panels (un panel sans resourceKey — ex: TimetableGrid,
      PreferenceGrid — n'est pas concerné, pas de ressource unique à vérifier). Chaque panel avec
      `resourceKey` reçoit en plus `panel.access.readOnly` (pas de droit d'ÉCRITURE sur cette
      ressource) — lu par le frontend pour désactiver l'édition, voir App.vue.
    - Feuille `action` (ex: "Générer les cours") : affichée seulement si l'utilisateur a un droit
      d'ÉCRITURE sur son `resourceKey` — une action est par nature une opération de mutation, pas
      une simple consultation.
    """
    filtered = []
    for node in nodes:
        node_groups = node.get("groups")
        if node_groups and not (set(node_groups) & group_names):
            continue

        if node.get("children"):
            kept_children = filter_menu_for_user(node["children"], db, user, group_names)
            if not kept_children:
                continue
            filtered.append({**node, "children": kept_children})
            continue

        if "action" in node:
            resource_key = node["action"].get("resourceKey")
            if resource_key and not _has_access(db, resource_key, user, "write"):
                continue
            filtered.append(node)
            continue

        panels = node.get("panels", [])
        resource_keys = {p["resourceKey"] for p in panels if "resourceKey" in p}
        if resource_keys and not all(_has_access(db, rk, user, "read") for rk in resource_keys):
            continue

        new_panels = []
        for panel in panels:
            new_panel = dict(panel)
            if "resourceKey" in panel:
                new_panel["access"] = {"readOnly": not _has_access(db, panel["resourceKey"], user, "write")}
            new_panels.append(new_panel)
        filtered.append({**node, "panels": new_panels})

    return filtered


@router.get("/menus")
def get_menus(db: Session = Depends(get_db), user=Depends(current_db_user)):
    file_path = os.path.join(os.path.dirname(__file__), "ui.json")
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    try:
        validate_menu_ids(data)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    from backend.app.core.access_control import resolve_effective_group_objects
    group_names = {g.name for g in resolve_effective_group_objects(user)}
    return filter_menu_for_user(data, db, user, group_names)


@router.get("/whoami")
def whoami(
    session: InstanceSession = Depends(require_instance_session),
    db: Session = Depends(get_db),
    user=Depends(current_db_user),
):
    """
    Identité de l'utilisateur connecté sur la base courante, et son statut d'admin — sert à l'IHM
    (NotebooksTree.vue) pour afficher qui est connecté et proposer un lien vers la console
    d'administration (voir architecture.md §19) SANS dupliquer d'appel à /api/instance/admin/
    databases. `is_admin` : super-admin d'instance (indépendant de toute base, voir
    instance_admin.py::is_super_admin) OU membre du groupe "Admin" DANS CETTE base précise — les
    deux donnent accès à au moins une action de la console pour la base courante.

    `must_change_password` : reflète l'identité locale de l'utilisateur (voir models/user.py::
    UserIdentityProvider), `False` si aucune (compte purement OIDC). Cette route est explicitement
    EXEMPTÉE du blocage `PASSWORD_CHANGE_REQUIRED` (voir database.py::current_db_user) — c'est le
    seul moyen pour le frontend de détecter l'état et de rediriger (NotebooksTree.vue), toute autre
    route étant bloquée tant que le flag est posé.
    """
    from backend.app.core.access_control import resolve_effective_group_objects
    from backend.app.core.instance_admin import is_super_admin
    from backend.app.models.user import UserIdentityProvider
    group_names = {g.name for g in resolve_effective_group_objects(user)}
    local_idp = db.query(UserIdentityProvider).filter(
        UserIdentityProvider.provider_key == "local",
        UserIdentityProvider.user_id == user.id,
    ).first()
    from backend.app.core.config import settings
    return {
        "id": user.id,
        "display_name": user.display_name,
        "email": user.email,
        "is_admin": is_super_admin(session) or "Admin" in group_names,
        "must_change_password": bool(local_idp and local_idp.must_change_password),
        # Plafond d'envoi de fichier, servi ici plutôt que recopié en dur côté frontend : le
        # contrôle client (widgets/BinaryFileField.vue) n'est qu'un confort — il évite de charger
        # 400 Mo en mémoire pour se faire répondre 413 — et doit annoncer la MÊME valeur que celle
        # réellement appliquée (core/upload_limits.py). whoami est déjà appelé au démarrage de
        # l'IHM (NotebooksTree.vue) : aucun aller-retour supplémentaire.
        "max_upload_mb": settings.server.max_upload_mb,
    }
