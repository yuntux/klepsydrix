import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Klepsydrix"
    API_V1_STR: str = "/api"
    DATABASE_URL: str = "sqlite:///./timetable.db"
    
    # Limite de temps pour le solveur Timefold en secondes
    SOLVER_TIME_LIMIT_SECONDS: int = 5

    # Charger le fichier .env s'il existe
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
