"""
Registre des bases de l'instance : découverte (pas de fichier registre à maintenir — voir
architecture.md) et cache des moteurs SQLAlchemy par slug de base.

- SQLite : chaque fichier `*.db` du répertoire `database.directory` = une base, le nom de fichier
  (sans extension) est le slug.
- PostgreSQL : chaque base du serveur dont le nom commence par `database.database_prefix` = une
  base, le nom complet de la base est le slug.

Le cache d'engines est un simple dict en mémoire process (voir constat sur SolverState/multi-
process dans le plan — même limite ici, acceptable tant qu'un seul process Klepsydrix tourne par
déploiement).
"""
import re
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import settings, build_database_url, DatabaseBackend, REPO_ROOT

# Un slug doit rester un identifiant simple : il finit dans un chemin de fichier (SQLite) ou une
# URL de connexion construite par concaténation (PostgreSQL, voir build_database_url) — jamais de
# séparateur de chemin, jamais de caractère qui aurait un sens dans une DSN.
SLUG_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

# Nom de la base par défaut pour les usages mono-base restants (voir database.py, solver.py) —
# reproduit le comportement d'avant l'introduction du registre : le fichier s'appelait déjà
# "timetable.db".
DEFAULT_DB_NAME = "timetable"

_engines: dict[str, tuple] = {}


def _sqlite_directory() -> Path:
    directory = Path(settings.database.directory).expanduser()
    if not directory.is_absolute():
        directory = REPO_ROOT / directory
    return directory.resolve()


def known_slugs() -> set[str]:
    cfg = settings.database
    if cfg.backend == DatabaseBackend.SQLITE:
        return {p.stem for p in _sqlite_directory().glob("*.db")}

    # PostgreSQL : connexion de maintenance dédiée (base "postgres"), jamais mise en cache dans
    # _engines — ce n'est pas une base applicative.
    maintenance_engine = create_engine(build_database_url("postgres"))
    try:
        with maintenance_engine.connect() as conn:
            rows = conn.execute(
                text("SELECT datname FROM pg_database WHERE datname LIKE :pattern"),
                {"pattern": f"{cfg.database_prefix}%"},
            )
            return {row[0] for row in rows}
    finally:
        maintenance_engine.dispose()


def is_known_slug(slug: str) -> bool:
    """
    Chemin rapide : un slug déjà résolu dans le cache est accepté sans re-vérifier la liste
    (évite une requête PostgreSQL ou un `glob` du système de fichiers à chaque requête HTTP) — la
    découverte complète (known_slugs()) n'est appelée que pour un slug encore jamais vu par ce
    process.
    """
    if not SLUG_PATTERN.match(slug):
        return False
    if slug in _engines:
        return True
    return slug in known_slugs()


def engine_for(slug: str):
    if slug not in _engines:
        connect_args = {"check_same_thread": False} if settings.database.backend == DatabaseBackend.SQLITE else {}
        engine = create_engine(build_database_url(slug), connect_args=connect_args, pool_size=5)
        _engines[slug] = (engine, sessionmaker(autocommit=False, autoflush=False, bind=engine))
    return _engines[slug][0]


def sessionmaker_for(slug: str):
    engine_for(slug)  # garantit la création du couple (engine, sessionmaker) si absent
    return _engines[slug][1]


def slug_for_engine(engine) -> str | None:
    """
    Retrouve le slug d'un moteur déjà enregistré (identité d'objet, pas comparaison d'URL) — utilisé
    par le solveur (voir solver.py) pour retrouver la base d'une session déjà ouverte quand
    l'appelant ne connaît/ne fournit pas explicitement le slug (ex: un appel direct depuis les
    tests, dont le moteur SQLite/PostgreSQL de test n'est de toute façon jamais enregistré ici —
    retourne alors None, l'appelant retombe sur la base par défaut).
    """
    for slug, (eng, _) in _engines.items():
        if eng is engine:
            return slug
    return None


def slug_for_session(db) -> str:
    """Pendant de slug_for_engine() pour une Session déjà ouverte, avec repli sur DEFAULT_DB_NAME."""
    return slug_for_engine(db.bind) or DEFAULT_DB_NAME


def dispose(slug: str):
    if slug in _engines:
        _engines[slug][0].dispose()
        del _engines[slug]
