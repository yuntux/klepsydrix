"""
Tests pour la validation d'unicité des IDs de menu dans ui.json (voir
backend/app/api/ui_endpoints.py::validate_menu_ids) — condition nécessaire à la résolution d'un
chemin d'URL de navigation (ex: /timetable_root/teachers_setting/teachers_preferences_tab).
"""
import json
import os
import pytest
from backend.app.api.ui_endpoints import validate_menu_ids


class TestValidateMenuIds:
    def test_raises_on_duplicate_sibling_ids(self):
        tree = [
            {"id": "root_a", "children": [
                {"id": "child_1"},
                {"id": "child_1"},
            ]}
        ]
        with pytest.raises(ValueError, match="dupliqué"):
            validate_menu_ids(tree)

    def test_allows_same_id_reused_at_different_parents(self):
        # Deux frères de PARENTS différents peuvent partager un id sans ambiguïté pour la
        # résolution d'un chemin complet (chaque niveau n'est comparé qu'à ses propres frères).
        tree = [
            {"id": "root_a", "children": [{"id": "leaf"}]},
            {"id": "root_b", "children": [{"id": "leaf"}]},
        ]
        validate_menu_ids(tree)

    def test_no_duplicates_passes_silently(self):
        tree = [
            {"id": "root_a", "children": [{"id": "child_1"}, {"id": "child_2"}]},
            {"id": "root_b"},
        ]
        validate_menu_ids(tree)


class TestRealUiJson:
    def test_real_ui_json_has_no_duplicate_sibling_ids(self):
        file_path = os.path.join(os.path.dirname(__file__), "..", "app", "api", "ui.json")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        validate_menu_ids(data)
