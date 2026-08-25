"""Public database health-check endpoint."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from models import User

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """Confirm that the application can query the Supabase database."""
    try:
        # Running a real query (rather than only opening a session) verifies
        # both the database connection and access to the users table.
        db.execute(select(User.id).limit(1)).first()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database connection failed.",
        )

    return {"status": "ok"}
