import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    try:
        with TestClient(app) as c:
            yield c
    except OSError:
        pytest.skip("PostgreSQL not available")


def _new_account(client) -> str:
    return client.post("/api/v1/accounts", json={"name": "Balance Tester"}).json()["id"]


def test_new_account_has_zero_balance(client):
    account_id = _new_account(client)
    resp = client.get(f"/api/v1/accounts/{account_id}/balance")
    assert resp.status_code == 200
    data = resp.json()
    assert data["account_id"] == account_id
    assert Decimal(data["balance"]) == 0


def test_balance_reflects_transactions(client):
    account_id = _new_account(client)
    for kind, amount in [("credit", "100"), ("debit", "30.25")]:
        r = client.post(
            "/api/v1/transactions",
            json={"account_id": account_id, "type": kind, "amount": amount, "reference_id": f"{kind}-{uuid.uuid4()}"},
        )
        assert r.status_code == 201
    resp = client.get(f"/api/v1/accounts/{account_id}/balance")
    assert Decimal(resp.json()["balance"]) == Decimal("69.75")


def test_unknown_account_returns_404(client):
    resp = client.get(f"/api/v1/accounts/{uuid.uuid4()}/balance")
    assert resp.status_code == 404
    assert resp.json()["error"] == "Not Found"


def test_invalid_account_id_returns_400(client):
    assert client.get("/api/v1/accounts/not-a-uuid/balance").status_code == 400
