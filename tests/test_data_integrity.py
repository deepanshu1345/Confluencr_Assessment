import uuid
from decimal import Decimal

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.db import database
from app.db.database import get_db_connection
from app.main import app

TXN = "/api/v1/transactions"


@pytest.fixture(scope="module")
def client():
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    except OSError:
        pytest.skip("PostgreSQL not available")


@pytest.fixture
def account_id(client):
    return client.post("/api/v1/accounts", json={"name": "Integrity Tester"}).json()["id"]


def _txn(client, account_id, kind, amount, ref=None):
    return client.post(
        TXN,
        json={"account_id": account_id, "type": kind, "amount": amount, "reference_id": ref or f"r-{uuid.uuid4()}"},
    )


def _balance(client, account_id) -> Decimal:
    return Decimal(client.get(f"/api/v1/accounts/{account_id}/balance").json()["balance"])


def _db(client, fn):
    """Run an async DB function on the app's event loop."""
    async def run():
        async with database.pool.acquire() as conn:
            return await fn(conn)
    return client.portal.call(run)


# ---- balance consistency ----

def test_balance_matches_sum_of_valid_transactions(client, account_id):
    assert _balance(client, account_id) == 0
    for kind, amount in [("credit", "100"), ("credit", "50"), ("debit", "30"), ("debit", "20")]:
        assert _txn(client, account_id, kind, amount).status_code == 201
    assert _balance(client, account_id) == Decimal("100")

    async def ledger_sum(conn):
        return await conn.fetchval(
            """SELECT COALESCE(SUM(CASE WHEN type = 'credit' THEN amount ELSE -amount END), 0)
               FROM transactions WHERE account_id = $1""",
            uuid.UUID(account_id),
        )

    assert _db(client, ledger_sum) == _balance(client, account_id)


def test_rejected_transactions_do_not_change_balance(client, account_id):
    _txn(client, account_id, "credit", "100", ref="ok")
    assert _txn(client, account_id, "debit", "150").status_code == 400      # insufficient
    assert _txn(client, account_id, "credit", "5", ref="ok").status_code == 409  # duplicate
    assert _txn(client, account_id, "credit", "-5").status_code == 400      # invalid amount
    assert _txn(client, account_id, "credit", "99999999999999.9999").status_code == 400  # overflow
    assert _balance(client, account_id) == Decimal("100")

    async def count(conn):
        return await conn.fetchval("SELECT COUNT(*) FROM transactions WHERE account_id = $1", uuid.UUID(account_id))

    assert _db(client, count) == 1


def test_database_rejects_negative_balance(client, account_id):
    async def force_negative(conn):
        await conn.execute("UPDATE accounts SET balance = -1 WHERE id = $1", uuid.UUID(account_id))

    with pytest.raises(asyncpg.CheckViolationError):
        _db(client, force_negative)


# ---- immutability ----

@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_no_api_to_modify_or_delete_transactions(client, account_id, method):
    txn_id = _txn(client, account_id, "credit", "10").json()["id"]
    for path in (f"{TXN}/{txn_id}", TXN):
        resp = getattr(client, method)(path)
        assert resp.status_code in (404, 405)
        assert set(resp.json()) == {"error", "message"}
    assert _balance(client, account_id) == Decimal("10")


def test_database_blocks_update_and_delete_of_transactions(client, account_id):
    txn_id = uuid.UUID(_txn(client, account_id, "credit", "10").json()["id"])

    async def update(conn):
        await conn.execute("UPDATE transactions SET amount = 999 WHERE id = $1", txn_id)

    async def delete(conn):
        await conn.execute("DELETE FROM transactions WHERE id = $1", txn_id)

    for fn in (update, delete):
        with pytest.raises(asyncpg.RaiseError):
            _db(client, fn)

    async def amount(conn):
        return await conn.fetchval("SELECT amount FROM transactions WHERE id = $1", txn_id)

    assert _db(client, amount) == Decimal("10")


# ---- atomicity ----

class _FailOnBalanceUpdate:
    """Connection wrapper whose balance UPDATE fails, after the transaction row is inserted."""

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    async def execute(self, query, *args):
        if "UPDATE accounts" in query:
            raise RuntimeError("simulated failure while updating balance")
        return await self._conn.execute(query, *args)


def test_failure_after_insert_rolls_back_everything(client, account_id):
    _txn(client, account_id, "credit", "100")

    async def failing_conn():
        async with database.pool.acquire() as conn:
            yield _FailOnBalanceUpdate(conn)

    app.dependency_overrides[get_db_connection] = failing_conn
    try:
        resp = _txn(client, account_id, "credit", "50", ref="will-fail")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 500
    assert resp.json() == {"error": "Internal Server Error", "message": "An unexpected error occurred"}
    assert _balance(client, account_id) == Decimal("100")

    async def exists(conn):
        return await conn.fetchval(
            "SELECT COUNT(*) FROM transactions WHERE account_id = $1 AND reference_id = 'will-fail'",
            uuid.UUID(account_id),
        )

    assert _db(client, exists) == 0


# ---- consistent error shape ----

@pytest.mark.parametrize(
    "method,path,kwargs",
    [
        ("get", "/nope", {}),
        ("get", f"/api/v1/accounts/{uuid.uuid4()}/balance", {}),
        ("get", f"/api/v1/accounts/{uuid.uuid4()}/transactions", {}),
        ("get", "/api/v1/accounts/bad-id/balance", {}),
        ("get", "/api/v1/accounts/bad-id/transactions", {}),
        ("post", "/api/v1/accounts", {"json": {}}),
        ("post", "/api/v1/accounts", {"content": "{", "headers": {"content-type": "application/json"}}),
        ("post", TXN, {"json": {}}),
        ("post", TXN, {"json": {"account_id": str(uuid.uuid4()), "type": "credit", "amount": "1", "reference_id": "x"}}),
    ],
)
def test_all_errors_share_one_shape(client, method, path, kwargs):
    resp = getattr(client, method)(path, **kwargs)
    assert 400 <= resp.status_code < 500
    body = resp.json()
    assert {"error", "message"} <= set(body)
    assert isinstance(body["message"], str) and body["message"]
