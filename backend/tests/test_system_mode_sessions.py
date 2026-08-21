"""
Garde-fou sur le MODE SYSTÈME (voir models/base.py, core/access_control.py).

Le moteur de droits ne s'applique qu'à une session SQLAlchemy portant le drapeau ambiant
`db.klepsydrix_user_id`, posé par `database.py::current_db_user` — donc uniquement sur le chemin
HTTP. Une session ouverte ailleurs (`SessionLocal()`, `sessionmaker_for(slug)()`) travaille en
**mode système** : accès total, aucun domaine appliqué. C'est indispensable (démarrage, solveur,
console d'administration, seeds) et parfaitement légitime — mais c'est aussi une ouverture qui ne
fait aucun bruit : rien ne plante, rien n'est journalisé, les données sortent simplement sans
filtre.

`route_guard.assert_all_routes_scoped` couvre déjà l'oubli côté ROUTES (une route qui oublierait
`current_db_user` empêche le serveur de démarrer). Ce test couvre l'autre moitié : l'ouverture de
session HORS requête. Il n'interdit rien — il exige que chacune soit **assumée par écrit**, pour
qu'ajouter la prochaine soit une décision et non un réflexe.
"""
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"

# Ouverture directe d'une session, sous ses deux formes dans ce projet.
_SESSION_OPENING = re.compile(r"(SessionLocal\(\)|sessionmaker_for\([^)]*\)\(\))")

# Un commentaire dans les lignes qui précèdent doit contenir l'un de ces termes : c'est la trace
# écrite que l'auteur savait ce qu'il ouvrait.
_JUSTIFICATION_TERMS = ("mode système", "mode systeme", "hors requête", "hors requete", "sans requête HTTP")

# Fichiers dont l'objet MÊME est d'ouvrir une session hors requête — la justification est dans leur
# docstring de module, pas ligne à ligne.
_EXEMPT_FILES = {
    "core/database.py",       # get_db : c'est LUI qui ouvre la session des requêtes HTTP
    "core/init_demo.py",      # seed : script hors ligne par nature
}


def _lines_before(lines: list[str], index: int, count: int = 6) -> str:
    return "\n".join(lines[max(0, index - count):index])


def test_every_out_of_request_session_is_justified_in_writing():
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        relative = path.relative_to(APP_DIR).as_posix()
        if relative in _EXEMPT_FILES:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if not _SESSION_OPENING.search(line):
                continue
            contexte = (_lines_before(lines, index) + line).lower()
            if not any(terme.lower() in contexte for terme in _JUSTIFICATION_TERMS):
                offenders.append(f"{relative}:{index + 1}")

    assert not offenders, (
        "Session SQLAlchemy ouverte hors requête HTTP sans justification écrite : "
        + ", ".join(offenders)
        + ". Ces sessions travaillent en MODE SYSTÈME (aucun droit appliqué, voir models/base.py). "
        "Si c'est voulu, dites-le en commentaire juste au-dessus, en écrivant « mode système » et "
        "pourquoi il est légitime ici ; sinon, passez par une dépendance FastAPI (get_db)."
    )
