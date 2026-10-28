import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db_connection
from app.main import app


async def _no_db():
    yield None


@pytest.fixture
def client():
    # No `with` block: the lifespan (and so the DB pool) is not started.
    app.dependency_overrides[get_db_connection] = _no_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "Alice123"},
        {"name": "Bob@Bank!"},
        {"name": "   "},
        {},
        {"name": "Bob", "balance": 1000},
        {"name": "Bob", "id": "00000000-0000-0000-0000-000000000000"},
    ],
)
def test_invalid_payload_returns_400(client, payload):
    resp = client.post("/api/v1/accounts", json=payload)
    assert resp.status_code == 400
    assert resp.json()["error"] == "Bad Request"


def test_malformed_body_returns_400(client):
    resp = client.post(
        "/api/v1/accounts", content="not json", headers={"content-type": "application/json"}
    )
    assert resp.status_code == 400
