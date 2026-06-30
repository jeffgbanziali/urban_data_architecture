import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

HOST = os.environ.get("POSTGRES_GOLD_HOST", "postgres-gold")
DB = os.environ.get("POSTGRES_GOLD_DB", "gold")
USER = os.environ.get("POSTGRES_GOLD_USER", "gold_user")
PASSWORD = os.environ.get("POSTGRES_GOLD_PASSWORD", "gold_pass")

DATABASE_URL = f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:5432/{DB}"

engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
