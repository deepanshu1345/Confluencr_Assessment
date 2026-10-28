# Transaction Ledger API

A FastAPI + PostgreSQL service for managing accounts and an immutable transaction ledger: create accounts, credit/debit them, check balances, list history with filtering and pagination, and transfer money between accounts atomically.

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [Error Responses](#error-responses)
- [Design Decisions](#design-decisions)
- [Testing](#testing)
- [Docker](#docker)

## Features

- Create accounts (balance always starts at 0 and cannot be set by the client)
- Credit and debit transactions with automatic balance updates
- Get the current balance of an account
- List an account's transactions with a `credit`/`debit` filter, pagination and newest-first sorting
- Atomic money transfers between two accounts
- Idempotency through a per-account unique `reference_id`
- Immutable ledger: transactions cannot be edited or deleted, through the API or the database
- Consistent JSON error format and meaningful HTTP status codes

## Tech Stack

| Area | Choice |
|---|---|
| Language | Python 3.14 |
| Framework | FastAPI |
| Database | PostgreSQL via `asyncpg` (raw SQL, connection pool) |
| Validation | Pydantic v2 |
| Packaging | `uv` (`pyproject.toml`, `uv.lock`) |
| Tests | pytest + FastAPI `TestClient` |

## Project Structure

```text
├── app/
│   ├── main.py                    # App setup, lifespan, error handlers
│   ├── routes/                    # HTTP endpoints
│   │   ├── accounts.py            #   create account, balance, list transactions
│   │   ├── transactions.py        #   credit / debit
│   │   └── transfers.py           #   account-to-account transfer
│   ├── services/                  # Business logic and SQL
│   │   ├── account_service.py
│   │   ├── transaction_service.py
│   │   └── transfer_service.py
│   ├── schemas/                   # Pydantic request/response models
│   ├── models/                    # Domain dataclasses
│   ├── db/database.py             # Connection pool, schema, integrity rules
│   └── core/
│       ├── config.py              # Settings (.env + environment variables)
│       └── exceptions.py          # Domain exceptions
├── tests/                         # pytest suite
├── scripts/                       # Manual helper scripts
├── .env.example                   # Environment template
├── Dockerfile
├── pyproject.toml / uv.lock       # Dependencies
└── requirements.txt               # pip-compatible dependency list
```

## Getting Started

### Prerequisites

- Python 3.14+
- PostgreSQL running locally, with an empty database (for example `app_db`)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### 1. Configure the environment

```bash
cp .env.example .env
```

Edit `.env` and set your database connection:

```env
PROJECT_NAME="Transaction Ledger API"
ENVIRONMENT="development"
DEBUG=True
API_V1_STR="/api/v1"
DATABASE_URL="postgresql://user:password@localhost:5432/app_db"
```

Environment variables override values in `.env`. `.env` is git-ignored.

### 2. Install dependencies

```bash
uv sync
# or: pip install -r requirements.txt
```

### 3. Run the server

```bash
uv run uvicorn app.main:app --reload
# or: uvicorn app.main:app --reload
```

The tables, constraints and triggers are created automatically on startup.

- Swagger UI: http://127.0.0.1:8000/docs
- Root: http://127.0.0.1:8000/

## API Reference

Base path: `/api/v1`. All amounts are decimals with up to 4 decimal places.

| Method | Endpoint | Description | Success |
|---|---|---|---|
| `POST` | `/accounts` | Create an account | `201` |
| `GET` | `/accounts/{account_id}/balance` | Get the current balance | `200` |
| `GET` | `/accounts/{account_id}/transactions` | List transactions (filter, paginate) | `200` |
| `POST` | `/transactions` | Credit or debit an account | `201` |
| `POST` | `/transfers` | Transfer money between two accounts | `201` |

### Create account — `POST /accounts`

```json
{ "name": "Alice Smith" }
```

`name` is required and may contain only letters and spaces. `id` and `balance` are system-controlled; sending them returns `400`.

```json
{
  "id": "0b6f1f0e-4d6c-4f43-9b43-2f1c5c1b7a10",
  "name": "Alice Smith",
  "balance": "0.0000",
  "created_at": "2026-10-28T09:30:00Z"
}
```

### Get balance — `GET /accounts/{account_id}/balance`

```json
{ "account_id": "0b6f1f0e-...", "balance": "100.0000" }
```

### Create transaction — `POST /transactions`

```json
{
  "account_id": "0b6f1f0e-...",
  "type": "credit",
  "amount": "50.00",
  "description": "Salary",
  "reference_id": "ref-1001"
}
```

| Field | Rules |
|---|---|
| `account_id` | Required, must be an existing account |
| `type` | `credit` or `debit` |
| `amount` | Greater than 0, at most 4 decimal places |
| `description` | Optional, up to 500 characters |
| `reference_id` | Required, up to 255 characters, unique per account |

`id` and `created_at` are generated by the system. A debit larger than the balance is rejected and the balance is unchanged.

```json
{
  "id": "c1a2...",
  "account_id": "0b6f1f0e-...",
  "type": "credit",
  "amount": "50.0000",
  "description": "Salary",
  "reference_id": "ref-1001",
  "created_at": "2026-10-28T09:31:00Z"
}
```

### List transactions — `GET /accounts/{account_id}/transactions`

| Query param | Default | Description |
|---|---|---|
| `type` | both | `credit` or `debit` |
| `page` | `1` | Page number, starting at 1 |
| `page_size` | `10` | Records per page, 1–100 |

Results are sorted newest first by `created_at`.

```json
{
  "items": [ { "id": "...", "type": "debit", "amount": "1.0000", "reference_id": "r5", "...": "..." } ],
  "page": 1,
  "page_size": 10,
  "total_records": 5,
  "total_pages": 1
}
```

`total_records` and `total_pages` respect the `type` filter. A page past the end returns an empty `items` list.

### Transfer — `POST /transfers`

```json
{
  "source_account_id": "<uuid>",
  "destination_account_id": "<uuid>",
  "amount": "30",
  "description": "Rent",
  "reference_id": "tr-1"
}
```

Example: A has 100 and B has 50. Transferring 30 from A to B leaves A at 70 and B at 80.

```json
{
  "source_transaction": { "type": "debit", "...": "..." },
  "destination_transaction": { "type": "credit", "...": "..." },
  "source_balance": "70.0000",
  "destination_balance": "80.0000"
}
```

Both accounts must exist and be different, and the source needs enough balance. The same `reference_id` is recorded on both legs.

## Error Responses

Every error uses the same shape:

```json
{ "error": "Insufficient Funds", "message": "Insufficient balance: available 100.0000, requested 150" }
```

Validation errors also include a `details` list.

| Status | `error` | When |
|---|---|---|
| `400` | `Bad Request` | Invalid body, type, amount, UUID or pagination values; extra fields; same-account transfer |
| `400` | `Insufficient Funds` | Debit or transfer exceeds the balance |
| `404` | `Not Found` | Account (or route) does not exist |
| `405` | `Method Not Allowed` | e.g. `PUT`/`PATCH`/`DELETE` on transactions |
| `409` | `Conflict` | `reference_id` already used for the account |
| `500` | `Internal Server Error` | Unexpected failure; internals are never exposed |

## Design Decisions

- **Atomicity:** inserting the transaction and updating the balance happen in one database transaction. A transfer does both legs in one transaction, so a partial transfer cannot occur.
- **Concurrency:** account rows are locked with `SELECT ... FOR UPDATE` before the balance check. Transfers lock both rows in `id` order, which prevents overdrafts and deadlocks.
- **Immutability:** there are no update or delete endpoints, and a database trigger rejects `UPDATE` and `DELETE` on the `transactions` table.
- **Balance integrity:** the balance is only changed together with a ledger entry, and a database `CHECK` prevents negative balances.
- **Idempotency:** `UNIQUE (account_id, reference_id)` is enforced by the database. Generate the `reference_id` once per user action and reuse it when retrying, so a retry gets `409` instead of a second charge.
- **Money type:** `NUMERIC(18, 4)` in PostgreSQL and `Decimal` in Python; floats are never used.

## Testing

```bash
uv run pytest
```

Validation tests run without a database. Behavior tests (balances, atomicity, concurrency, transfers) need PostgreSQL via `DATABASE_URL` and are skipped if it is unreachable.

Test files live in `tests/`:

| File | Covers |
|---|---|
| `test_accounts_api.py` | Account creation validation |
| `test_account_balance_api.py` | Balance endpoint |
| `test_transactions_api.py` | Credit/debit rules, duplicates, concurrency |
| `test_list_transactions_api.py` | Filtering, pagination, sorting |
| `test_data_integrity.py` | Immutability, balance consistency, atomicity, error format |
| `test_transfers_api.py` | Transfers, rollback, deadlock safety |

> The tests create accounts and transactions in the configured database, and transactions cannot be deleted. Point `DATABASE_URL` at a throwaway database when testing.

## Docker

```bash
docker build -t transaction-ledger-api .
docker run -p 8000:8000 -e DATABASE_URL="postgresql://user:password@host.docker.internal:5432/app_db" transaction-ledger-api
```

The container needs a reachable PostgreSQL instance; `localhost` inside the container refers to the container itself, so use `host.docker.internal` (or your database host).
