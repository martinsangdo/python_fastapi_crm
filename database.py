"""
database.py
-----------
Sets up the connection to the PostgreSQL database (Supabase compatible).

This file only prepares the tools we need to talk to the database later.
It does NOT create any tables or models yet.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Load the variables from the .env file into the environment.
load_dotenv()

# Read the database connection string from the environment.
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )
# The "engine" is the core connection to the database.
# SQLAlchemy uses it to open and manage connections for us.
engine = create_engine(DATABASE_URL)

# A "session" is one conversation with the database.
# We create a session factory here and make a new session per request later.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# "Base" is the parent class that future database models will inherit from.
# We define it now so it is ready when you add models later.
Base = declarative_base()


def get_db():
    """
    Provide a database session and make sure it is closed afterward.

    Use this as a FastAPI dependency in your routes later, for example:
        def my_route(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
