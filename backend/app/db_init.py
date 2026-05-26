"""Create all tables. Run: python -m app.db_init"""
from app.db import engine, Base
from app.models import *  # noqa: import all models so they register

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("✓ Tables created")
