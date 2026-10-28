from urllib.parse import urlparse
import asyncpg
from typing import AsyncGenerator
from app.core.config import settings

pool: asyncpg.Pool | None = None

CREATE_ACCOUNTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS accounts (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    balance NUMERIC(18, 4) NOT NULL DEFAULT 0.0000,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
"""

CREATE_TRANSACTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES accounts(id),
    type VARCHAR(10) NOT NULL CHECK (type IN ('credit', 'debit')),
    amount NUMERIC(18, 4) NOT NULL CHECK (amount > 0),
    description VARCHAR(500),
    reference_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_transactions_account_reference UNIQUE (account_id, reference_id)
);
"""

# A balance can never go negative, even if application code has a bug.
ACCOUNT_BALANCE_CHECK_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_accounts_balance_non_negative') THEN
        ALTER TABLE accounts ADD CONSTRAINT ck_accounts_balance_non_negative CHECK (balance >= 0);
    END IF;
END $$;
"""

# Transactions are immutable: block UPDATE and DELETE at the database level.
TRANSACTIONS_IMMUTABLE_SQL = """
CREATE OR REPLACE FUNCTION prevent_transaction_modification() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'transactions are immutable and cannot be updated or deleted';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_transactions_immutable ON transactions;
CREATE TRIGGER trg_transactions_immutable
    BEFORE UPDATE OR DELETE ON transactions
    FOR EACH ROW EXECUTE FUNCTION prevent_transaction_modification();
"""


async def init_tables(db_pool: asyncpg.Pool) -> None:
    """Ensure required tables and integrity rules exist."""
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            # Serialize schema setup if several workers start at once.
            await conn.execute("SELECT pg_advisory_xact_lock(727001);")
            await conn.execute(CREATE_ACCOUNTS_TABLE_SQL)
            await conn.execute(CREATE_TRANSACTIONS_TABLE_SQL)
            await conn.execute(ACCOUNT_BALANCE_CHECK_SQL)
            await conn.execute(TRANSACTIONS_IMMUTABLE_SQL)


def pool_kwargs(dsn: str) -> dict:
    """
    Extra asyncpg settings for the target database.
    Supabase requires SSL, and its pooler (PgBouncer) does not support
    prepared statements, so the statement cache is disabled for it.
    """
    host = urlparse(dsn).hostname or ""
    if host.endswith(".supabase.co") or host.endswith(".supabase.com"):
        return {"ssl": "require", "statement_cache_size": 0}
    return {}


async def init_db_pool() -> asyncpg.Pool:
    """Initialize the asyncpg connection pool and setup tables."""
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=2,
            max_size=10,
            **pool_kwargs(settings.DATABASE_URL),
        )
        await init_tables(pool)
    return pool


async def close_db_pool() -> None:
    """Close the asyncpg connection pool."""
    global pool
    if pool is not None:
        await pool.close()
        pool = None


async def get_db_pool() -> asyncpg.Pool:
    """Retrieve the initialized connection pool."""
    if pool is None:
        return await init_db_pool()
    return pool


async def get_db_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Dependency that yields a database connection from the pool."""
    db_pool = await get_db_pool()
    async with db_pool.acquire() as conn:
        yield conn
