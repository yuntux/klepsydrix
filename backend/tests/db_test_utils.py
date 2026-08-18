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

Fournit aussi `make_admin_user_override()`, le substitut de `current_db_user` utilisé par les
suites qui appellent l'API via TestClient (voir plus bas).
"""
import os
from fastapi import Depends
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


TEST_USER_EMAIL = "tests@klepsydrix.local"


def make_admin_user_override(get_db_dependency):
    """
    Substitut de `current_db_user` pour les suites qui appellent l'API via TestClient : évite de
    simuler une vraie session instance (cookie signé, fournisseur d'identité) à chaque requête,
    mais pose bien `db.klepsydrix_user_id` comme le fait la vraie dépendance à la frontière HTTP.

    Une version antérieure retournait simplement `None`, laissant le drapeau absent : ces suites
    s'exécutaient alors en MODE SYSTÈME, moteur de droits entièrement désactivé (voir
    base.py::_apply_access_read_filter). Elles ne validaient donc rien du comportement réel des
    routes vis-à-vis des droits, et obligeaient les vérifications explicites (ex:
    endpoints.py::_require_course_access) à tolérer un drapeau absent plutôt qu'à refuser.

    L'utilisateur posé est un admin complet, via le MÊME amorçage qu'en production
    (`init_db.seed_admin_access`) : ce que les tests existants observent est inchangé — un admin
    voit tout — mais c'est désormais obtenu EN PASSANT par le moteur de droits au lieu de le
    court-circuiter.

    `get_db_dependency` est passé en paramètre plutôt qu'importé : la dépendance à déclarer est
    celle que l'appelant a lui-même substituée dans `app.dependency_overrides`, pour que FastAPI
    réutilise la session de la requête (mise en cache par dépendance) et non une seconde session.
    """
    def override_current_db_user(db=Depends(get_db_dependency)):
        from backend.app.core.init_db import seed_admin_access
        from backend.app.models.access import ResGroup
        from backend.app.models.user import User

        admin_group = db.query(ResGroup).filter(ResGroup.name == "Admin").first()
        if admin_group is None:
            # Amorçage paresseux : les tables ne sont créées que par la fixture `db_session`, pas
            # au moment où les overrides sont posés. Fait une fois par test, à la 1re requête.
            seed_admin_access(db)
            admin_group = db.query(ResGroup).filter(ResGroup.name == "Admin").first()

        user = db.query(User).filter(User.email == TEST_USER_EMAIL).first()
        if user is None:
            # Le drapeau n'est pas encore posé : création en mode système, jamais bloquée.
            user = User.create(db, {"first_name": "Tests", "last_name": "Automatisés", "email": TEST_USER_EMAIL})
            admin_group.update(db, {"user_ids": [user.id]})
            db.commit()

        db.klepsydrix_user_id = user.id
        return user

    return override_current_db_user
