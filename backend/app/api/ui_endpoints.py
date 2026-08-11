import json
import os
from fastapi import APIRouter, HTTPException

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


@router.get("/menus")
def get_menus():
    file_path = os.path.join(os.path.dirname(__file__), "ui.json")
    if not os.path.exists(file_path):
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    try:
        validate_menu_ids(data)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return data
