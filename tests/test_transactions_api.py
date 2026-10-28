import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db_connection
from app.main import app

URL = "/api/v1/transactions"


def _body(_account_id, **overrides):
    body = {
        "account_id": str(_account_id),
        "type": "credit",
        "amount": "50",
        "description": "test",
        "reference_id": f"ref-{uuid.uuid4()}",
    }
    body.update(overrides)
    return body


# ---- validation (no database needed) ----

async def _no_db():
    yield None


@pytest.fixture
def offline_client():
    app.dependency_overrides[get_db_connection] = _no_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "overrides",
    [
        {"type": "transfer"},
        {"amount": "0"},
        {"amount": "-5"},
        {"amount": "1.23456"},
        {"amount": "abc"},
        {"reference_id": "   "},
        {"account_id": "not-a-uuid"},
        {"id": str(uuid.uuid4())},
        {"created_at": "2020-01-01T00:00:00Z"},
    ],
)
def test_invalid_payload_returns_400(offline_client, overrides):
    resp = offline_client.post(URL, json=_body(uuid.uuid4(), **overrides))
    assert resp.status_code == 400


def test_missing_reference_id_returns_400(offline_client):
    body = _body(uuid.uuid4())
    del body["reference_id"]
    assert offline_client.post(URL, json=body).status_code == 400


# ---- behaviour against PostgreSQL ----

@pytest.fixture(scope="module")
def db_client():
    try:
        with TestClient(app) as c:
            yield c
    except OSError:
        pytest.skip("PostgreSQL not available")


@pytest.fixture
def account_id(db_client):
    resp = db_client.post("/api/v1/accounts", json={"name": "Test User"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _balance(db_client, account_id) -> Decimal:
    return Decimal(db_client.get(f"/api/v1/accounts/{account_id}/balance").json()["balance"])


def test_credit_then_debit_updates_balance(db_client, account_id):
    r = db_client.post(URL, json=_body(account_id, type="credit", amount="100"))
    assert r.status_code == 201
    data = r.json()
    assert data["type"] == "credit" and data["account_id"] == account_id
    assert data["id"] and data["created_at"]
    assert _balance(db_client, account_id) == Decimal("100")

    assert db_client.post(URL, json=_body(account_id, type="credit", amount="50")).status_code == 201
    assert _balance(db_client, account_id) == Decimal("150")

    assert db_client.post(URL, json=_body(account_id, type="debit", amount="50")).status_code == 201
    assert _balance(db_client, account_id) == Decimal("100")


def test_debit_with_insufficient_balance_is_rejected(db_client, account_id):
    db_client.post(URL, json=_body(account_id, type="credit", amount="100"))
    r = db_client.post(URL, json=_body(account_id, type="debit", amount="150"))
    assert r.status_code == 400
    assert _balance(db_client, account_id) == Decimal("100")


def test_duplicate_reference_same_account_rejected(db_client, account_id):
    body = _body(account_id, reference_id="dup-1")
    assert db_client.post(URL, json=body).status_code == 201
    assert db_client.post(URL, json=body).status_code == 409
    assert _balance(db_client, account_id) == Decimal("50")


def test_same_reference_allowed_on_different_accounts(db_client, account_id):
    other = db_client.post("/api/v1/accounts", json={"name": "Other User"}).json()["id"]
    assert db_client.post(URL, json=_body(account_id, reference_id="shared")).status_code == 201
    assert db_client.post(URL, json=_body(other, reference_id="shared")).status_code == 201


def test_unknown_account_returns_404(db_client):
    assert db_client.post(URL, json=_body(uuid.uuid4())).status_code == 404


def test_concurrent_debits_never_overdraw(db_client, account_id):
    db_client.post(URL, json=_body(account_id, type="credit", amount="100"))

    def debit(_):
        return db_client.post(URL, json=_body(account_id, type="debit", amount="30")).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(debit, range(8)))

    assert codes.count(201) == 3
    assert _balance(db_client, account_id) == Decimal("10")
