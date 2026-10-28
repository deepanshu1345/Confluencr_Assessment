import uuid

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


@pytest.fixture
def account_id(client):
    """Account with 5 transactions created in order: c1, c2, d3, c4, d5."""
    acc = client.post("/api/v1/accounts", json={"name": "List Tester"}).json()["id"]
    for i, kind in enumerate(["credit", "credit", "debit", "credit", "debit"], start=1):
        r = client.post(
            "/api/v1/transactions",
            json={"account_id": acc, "type": kind, "amount": "10" if kind == "credit" else "1", "reference_id": f"r{i}"},
        )
        assert r.status_code == 201
    return acc


def _get(client, account_id, **params):
    return client.get(f"/api/v1/accounts/{account_id}/transactions", params=params)


def test_lists_both_types_latest_first(client, account_id):
    data = _get(client, account_id).json()
    assert [t["reference_id"] for t in data["items"]] == ["r5", "r4", "r3", "r2", "r1"]
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert data["total_records"] == 5
    assert data["total_pages"] == 1


@pytest.mark.parametrize(
    "kind,expected",
    [("credit", ["r4", "r2", "r1"]), ("debit", ["r5", "r3"])],
)
def test_filter_by_type(client, account_id, kind, expected):
    data = _get(client, account_id, type=kind).json()
    assert [t["reference_id"] for t in data["items"]] == expected
    assert all(t["type"] == kind for t in data["items"])
    assert data["total_records"] == len(expected)


def test_pagination(client, account_id):
    p1 = _get(client, account_id, page=1, page_size=2).json()
    p2 = _get(client, account_id, page=2, page_size=2).json()
    p3 = _get(client, account_id, page=3, page_size=2).json()
    assert [t["reference_id"] for t in p1["items"]] == ["r5", "r4"]
    assert [t["reference_id"] for t in p2["items"]] == ["r3", "r2"]
    assert [t["reference_id"] for t in p3["items"]] == ["r1"]
    assert (p1["total_records"], p1["total_pages"], p2["page"], p2["page_size"]) == (5, 3, 2, 2)


def test_page_beyond_last_is_empty(client, account_id):
    data = _get(client, account_id, page=9, page_size=2).json()
    assert data["items"] == []
    assert data["total_records"] == 5 and data["total_pages"] == 3


def test_account_without_transactions(client):
    acc = client.post("/api/v1/accounts", json={"name": "Empty Account"}).json()["id"]
    data = _get(client, acc).json()
    assert data["items"] == [] and data["total_records"] == 0 and data["total_pages"] == 0


def test_only_returns_that_accounts_transactions(client, account_id):
    other = client.post("/api/v1/accounts", json={"name": "Other Account"}).json()["id"]
    assert _get(client, other).json()["total_records"] == 0


def test_unknown_account_returns_404(client):
    assert _get(client, uuid.uuid4()).status_code == 404


@pytest.mark.parametrize(
    "params",
    [{"type": "transfer"}, {"page": 0}, {"page": -1}, {"page_size": 0}, {"page_size": 101}, {"page": "x"}],
)
def test_invalid_params_return_400(client, account_id, params):
    assert _get(client, account_id, **params).status_code == 400
