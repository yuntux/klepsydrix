"""
Moteur de test partagé par tous les fichiers de `backend/tests/` — SQLite en mémoire par défaut,
PostgreSQL local si la variable d'environnement KLEPSYDRIX_TEST_DB_BACKEND=postgres est positionnée
(voir architecture.md, compatibilité multi-SGBD). Rejouer toute la suite deux fois (une par
backend) est la façon de vérifier que rien ne dépend implicitement des spécificités de SQLite.

Prérequis PostgreSQL (une fois, en local — pas de CI pour ce chantier, voir architecture.md §16.B) :
    createdb -h /var/run/postgresql klepsydrix_test
Le rôle "ubuntu" (superutilisateur local, authentification "peer" par socket unix) est utilisé
tel quel, sans mot de passe.

Chaque fichier de test garde son propre fixture `db_session` (create_all/drop_all par test,
scope="function") — ce module ne fabrique que le moteur, pas la session.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

POSTGRES_TEST_URL = "postgresql+psycopg://ubuntu@/klepsydrix_test?host=/var/run/postgresql"


def is_postgres_backend() -> bool:
    return os.environ.get("KLEPSYDRIX_TEST_DB_BACKEND") == "postgres"


def make_test_engine(**engine_kwargs):
    engine_kwargs.pop("connect_args", None)
    engine_kwargs.pop("poolclass", None)
    if is_postgres_backend():
        return create_engine(POSTGRES_TEST_URL, **engine_kwargs)
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        **engine_kwargs,
    )
