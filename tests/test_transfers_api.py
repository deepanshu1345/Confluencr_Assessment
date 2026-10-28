import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db import database
from app.db.database import get_db_connection
from app.main import app

URL = "/api/v1/transfers"


@pytest.fixture(scope="module")
def client():
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    except OSError:
        pytest.skip("PostgreSQL not available")


def _account(client, balance="0") -> str:
    acc = client.post("/api/v1/accounts", json={"name": "Transfer Tester"}).json()["id"]
    if Decimal(balance) > 0:
        r = client.post(
            "/api/v1/transactions",
            json={"account_id": acc, "type": "credit", "amount": balance, "reference_id": f"seed-{uuid.uuid4()}"},
        )
        assert r.status_code == 201
    return acc


def _balance(client, account_id) -> Decimal:
    return Decimal(client.get(f"/api/v1/accounts/{account_id}/balance").json()["balance"])


def _body(src, dst, amount="30", ref=None, **extra):
    return {
        "source_account_id": src,
        "destination_account_id": dst,
        "amount": amount,
        "reference_id": ref or f"tr-{uuid.uuid4()}",
        **extra,
    }


def _txn_count(client, account_id) -> int:
    return client.get(f"/api/v1/accounts/{account_id}/transactions").json()["total_records"]


def test_transfer_moves_money(client):
    a, b = _account(client, "100"), _account(client, "50")
    resp = client.post(URL, json=_body(a, b, "30", description="rent"))
    assert resp.status_code == 201
    data = resp.json()
    assert Decimal(data["source_balance"]) == 70 and Decimal(data["destination_balance"]) == 80
    assert data["source_transaction"]["type"] == "debit"
    assert data["source_transaction"]["account_id"] == a
    assert data["destination_transaction"]["type"] == "credit"
    assert data["destination_transaction"]["account_id"] == b
    assert data["source_transaction"]["reference_id"] == data["destination_transaction"]["reference_id"]
    assert _balance(client, a) == 70 and _balance(client, b) == 80


def test_transfer_appears_in_both_histories(client):
    a, b = _account(client, "100"), _account(client, "0")
    client.post(URL, json=_body(a, b, "40", ref="hist"))
    last_a = client.get(f"/api/v1/accounts/{a}/transactions").json()["items"][0]
    last_b = client.get(f"/api/v1/accounts/{b}/transactions").json()["items"][0]
    assert (last_a["type"], last_a["reference_id"]) == ("debit", "hist")
    assert (last_b["type"], last_b["reference_id"]) == ("credit", "hist")


def test_insufficient_balance_changes_nothing(client):
    a, b = _account(client, "100"), _account(client, "50")
    resp = client.post(URL, json=_body(a, b, "150"))
    assert resp.status_code == 400 and resp.json()["error"] == "Insufficient Funds"
    assert _balance(client, a) == 100 and _balance(client, b) == 50
    assert _txn_count(client, a) == 1 and _txn_count(client, b) == 1  # only the seed credits


def test_unknown_accounts_return_404(client):
    a = _account(client, "100")
    assert client.post(URL, json=_body(a, str(uuid.uuid4()))).status_code == 404
    assert client.post(URL, json=_body(str(uuid.uuid4()), a)).status_code == 404
    assert _balance(client, a) == 100


def test_same_account_rejected(client):
    a = _account(client, "100")
    assert client.post(URL, json=_body(a, a)).status_code == 400
    assert _balance(client, a) == 100


def test_duplicate_reference_rejected_and_not_applied_twice(client):
    a, b = _account(client, "100"), _account(client, "0")
    body = _body(a, b, "30", ref="once")
    assert client.post(URL, json=body).status_code == 201
    assert client.post(URL, json=body).status_code == 409
    assert _balance(client, a) == 70 and _balance(client, b) == 30


def test_reference_already_used_on_destination_rolls_back_source_debit(client):
    a, b = _account(client, "100"), _account(client, "0")
    client.post("/api/v1/transactions", json={"account_id": b, "type": "credit", "amount": "1", "reference_id": "taken"})
    assert client.post(URL, json=_body(a, b, "30", ref="taken")).status_code == 409
    assert _balance(client, a) == 100 and _balance(client, b) == 1
    assert _txn_count(client, a) == 1  # the debit leg was rolled back


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": "0"},
        {"amount": "-1"},
        {"amount": "1.00001"},
        {"amount": "abc"},
        {"reference_id": " "},
        {"source_account_id": "bad"},
        {"destination_account_id": "bad"},
        {"id": "x"},
    ],
)
def test_invalid_payload_returns_400(client, overrides):
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    assert client.post(URL, json={**_body(a, b), **overrides}).status_code == 400


def test_missing_fields_return_400(client):
    assert client.post(URL, json={}).status_code == 400


class _FailOnSecondBalanceUpdate:
    """Fails the destination's balance update, after the debit leg was fully applied."""

    def __init__(self, conn):
        self._conn = conn
        self._updates = 0

    def __getattr__(self, name):
        return getattr(self._conn, name)

    async def execute(self, query, *args):
        if "UPDATE accounts" in query:
            self._updates += 1
            if self._updates == 2:
                raise RuntimeError("simulated failure while crediting destination")
        return await self._conn.execute(query, *args)


def test_failure_midway_rolls_back_both_legs(client):
    a, b = _account(client, "100"), _account(client, "50")

    async def failing_conn():
        async with database.pool.acquire() as conn:
            yield _FailOnSecondBalanceUpdate(conn)

    app.dependency_overrides[get_db_connection] = failing_conn
    try:
        resp = client.post(URL, json=_body(a, b, "30"))
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 500
    assert _balance(client, a) == 100 and _balance(client, b) == 50
    assert _txn_count(client, a) == 1 and _txn_count(client, b) == 1


def test_concurrent_transfers_never_overdraw(client):
    a, b = _account(client, "100"), _account(client, "0")

    def go(_):
        return client.post(URL, json=_body(a, b, "30")).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(go, range(8)))

    assert codes.count(201) == 3
    assert _balance(client, a) == 10 and _balance(client, b) == 90


def test_opposite_transfers_do_not_deadlock(client):
    a, b = _account(client, "100"), _account(client, "100")

    def go(i):
        src, dst = (a, b) if i % 2 == 0 else (b, a)
        return client.post(URL, json=_body(src, dst, "1")).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(go, range(20)))

    assert set(codes) == {201}
    assert _balance(client, a) + _balance(client, b) == 200
