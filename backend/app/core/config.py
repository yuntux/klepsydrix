import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Klepsydrix"
    API_V1_STR: str = "/api"
    DATABASE_URL: str = "sqlite:///./timetable.db"
    
    # Limite de temps pour le solveur Timefold en secondes
    SOLVER_TIME_LIMIT_SECONDS: int = 3

    # Charger le fichier .env s'il existe
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def __init__(self, **values):
        super().__init__(**values)
        if self.DATABASE_URL.startswith("sqlite:///./"):
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            db_name = self.DATABASE_URL.replace("sqlite:///./", "")
            self.DATABASE_URL = f"sqlite:///{os.path.abspath(os.path.join(base_dir, db_name))}"
        elif self.DATABASE_URL.startswith("sqlite:///"):
            path = self.DATABASE_URL.replace("sqlite:///", "")
            if not os.path.isabs(path):
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                self.DATABASE_URL = f"sqlite:///{os.path.abspath(os.path.join(base_dir, path))}"


settings = Settings()
