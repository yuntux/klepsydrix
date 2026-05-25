import pytest
from backend.app.core.config import settings

@pytest.fixture(scope="session", autouse=True)
def override_settings():
    settings.SOLVER_TIME_LIMIT_SECONDS = 2
