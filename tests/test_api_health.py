"""Tests for the public database health-check endpoint."""

from sqlalchemy.exc import SQLAlchemyError


def test_health_check_returns_ok_when_database_query_succeeds(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_check_returns_400_when_database_query_fails(client, db_session, monkeypatch):
    def raise_database_error(*_args, **_kwargs):
        raise SQLAlchemyError("connection unavailable")

    monkeypatch.setattr(db_session, "execute", raise_database_error)

    response = client.get("/api/health")

    assert response.status_code == 400
    assert response.json() == {"detail": "Database connection failed."}
