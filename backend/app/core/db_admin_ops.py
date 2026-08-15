"""
Opérations physiques sur une base de l'instance (créer/dupliquer/sauvegarder/restaurer/supprimer)
— voir architecture.md §20, console d'administration. Séparé de `db_registry.py` (qui ne fait que
mettre en cache des moteurs) : ce module touche le système de fichiers ou lance des sous-processus
(`pg_dump`/`pg_restore`), une responsabilité distincte.
"""
import subprocess
import tempfile
from pathlib import Path
from sqlalchemy import create_engine, text

from backend.app.core.config import settings, build_database_url, DatabaseBackend
from backend.app.core import db_registry


def physical_slug_for_new_database(bare_name: str) -> str:
    """
    Le nom saisi par l'admin est "nu" (ex: "college-jean-jaures") ; le slug physique diffère selon
    le backend — SQLite : identique (nom de fichier) ; PostgreSQL : préfixé (database_prefix), sans
    quoi la base créée ne serait même pas redécouverte ensuite par known_slugs().
    """
    if settings.database.backend == DatabaseBackend.SQLITE:
        return bare_name
    prefix = settings.database.database_prefix
    return bare_name if bare_name.startswith(prefix) else f"{prefix}{bare_name}"


def _maintenance_engine():
    """Connexion PostgreSQL à la base "postgres" — jamais mise en cache dans db_registry (pas une
    base applicative), utilisée pour les commandes qui ne peuvent pas s'exécuter DANS la base cible
    (CREATE/DROP DATABASE, interdits dans une transaction sur la base elle-même)."""
    return create_engine(build_database_url("postgres"), isolation_level="AUTOCOMMIT")


def create_database(slug: str):
    """Crée le fichier/la base vide. L'appelant est responsable d'y jouer le schéma ensuite
    (init_db.py::init_prod_data, sur une session ouverte via db_registry.sessionmaker_for(slug))."""
    if settings.database.backend == DatabaseBackend.SQLITE:
        # Rien à faire explicitement : create_engine()/create_all() créent le fichier à la volée
        # au premier accès réel (voir engine_for()) — pas de fichier vide à créer à part.
        return
    engine = _maintenance_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{slug}"'))
    finally:
        engine.dispose()


def backup_database(slug: str) -> Path:
    """Copie cohérente vers un fichier temporaire (l'appelant est responsable de le supprimer après
    l'avoir servi) — jamais un simple `cp`/lecture directe du fichier vivant, qui pourrait capturer
    un état incohérent pendant une écriture concurrente."""
    if settings.database.backend == DatabaseBackend.SQLITE:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        engine = db_registry.engine_for(slug)
        with engine.connect() as conn:
            conn.execute(text("VACUUM INTO :path"), {"path": tmp.name})
        return Path(tmp.name)

    tmp = tempfile.NamedTemporaryFile(suffix=".dump", delete=False)
    tmp.close()
    _run_pg_dump(slug, Path(tmp.name))
    return Path(tmp.name)


def duplicate_database(source_slug: str, new_slug: str):
    if settings.database.backend == DatabaseBackend.SQLITE:
        target_path = db_registry._sqlite_directory() / f"{new_slug}.db"
        engine = db_registry.engine_for(source_slug)
        with engine.connect() as conn:
            conn.execute(text("VACUUM INTO :path"), {"path": str(target_path)})
        return

    # PostgreSQL : CREATE DATABASE ... WITH TEMPLATE exige qu'aucune AUTRE connexion ne soit
    # ouverte sur la base modèle — on libère au moins celles de CE process (best-effort : une
    # connexion externe encore ouverte fera échouer la commande avec un message clair de PostgreSQL,
    # pas un échec silencieux).
    db_registry.dispose(source_slug)
    engine = _maintenance_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{new_slug}" WITH TEMPLATE "{source_slug}"'))
    finally:
        engine.dispose()


def restore_database(slug: str, uploaded_content: bytes):
    """"Annule et remplace" — le contenu actuel de `slug` est intégralement perdu."""
    db_registry.dispose(slug)
    if settings.database.backend == DatabaseBackend.SQLITE:
        target_path = db_registry._sqlite_directory() / f"{slug}.db"
        target_path.write_bytes(uploaded_content)
        return

    engine = _maintenance_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{slug}"'))
            conn.execute(text(f'CREATE DATABASE "{slug}"'))
    finally:
        engine.dispose()
    with tempfile.NamedTemporaryFile(suffix=".dump", delete=True) as tmp:
        tmp.write(uploaded_content)
        tmp.flush()
        _run_pg_restore(slug, Path(tmp.name))


def delete_database(slug: str):
    db_registry.dispose(slug)
    if settings.database.backend == DatabaseBackend.SQLITE:
        target_path = db_registry._sqlite_directory() / f"{slug}.db"
        target_path.unlink(missing_ok=True)
        return

    engine = _maintenance_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{slug}"'))
    finally:
        engine.dispose()


def _pg_connection_args() -> list[str]:
    cfg = settings.database
    args = []
    if cfg.host:
        args += ["-h", cfg.host]
    if not cfg.host.startswith("/"):
        args += ["-p", str(cfg.port)]
    if cfg.user:
        args += ["-U", cfg.user]
    return args


def _pg_env() -> dict:
    import os
    env = os.environ.copy()
    if settings.database.password:
        env["PGPASSWORD"] = settings.database.password
    return env


def _run_pg_dump(slug: str, output_path: Path):
    cmd = ["pg_dump", "-Fc", "-f", str(output_path), *_pg_connection_args(), slug]
    result = subprocess.run(cmd, env=_pg_env(), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump a échoué : {result.stderr}")


def _run_pg_restore(slug: str, input_path: Path):
    cmd = ["pg_restore", "--no-owner", "-d", slug, *_pg_connection_args(), str(input_path)]
    result = subprocess.run(cmd, env=_pg_env(), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"pg_restore a échoué : {result.stderr}")
