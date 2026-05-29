import json
import os
from fastapi import APIRouter

router = APIRouter(prefix="/api/ui")

@router.get("/menus")
def get_menus():
    file_path = os.path.join(os.path.dirname(__file__), "ui.json")
    if not os.path.exists(file_path):
        return []
        
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data
