from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.config import settings

# Configuration spéciale pour SQLite afin de supporter le multithreading asynchrone
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Fonction utilitaire de récupération de session de base de données
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
