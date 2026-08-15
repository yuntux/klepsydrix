import pytest
from backend.app.core.config import settings
from backend.tests.db_test_utils import is_postgres_backend, make_test_engine

@pytest.fixture(scope="session", autouse=True)
def override_settings():
    settings.SOLVER_TIME_LIMIT_SECONDS = 2


@pytest.fixture(scope="session", autouse=True)
def _clean_postgres_test_database():
    """
    Filet de sécurité pour KLEPSYDRIX_TEST_DB_BACKEND=postgres uniquement : purge les tables au
    début de la session, au cas où une exécution précédente aurait été interrompue avant son
    drop_all (chaque fichier de test isole déjà correctement ses propres tests via drop_all en
    scope="function" — voir db_test_utils.py — ceci ne couvre que l'état laissé par un crash).
    """
    if not is_postgres_backend():
        return
    from backend.app.models.base import Base
    engine = make_test_engine()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
