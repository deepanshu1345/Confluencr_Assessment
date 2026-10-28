import math
from decimal import Decimal
from uuid import UUID, uuid4
import asyncpg
from app.core.exceptions import (
    AccountNotFoundError,
    DuplicateReferenceError,
    InsufficientFundsError,
)
from app.models.transaction import Transaction
from app.schemas.transaction import (
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
    TransactionType,
)


# Largest value NUMERIC(18, 4) can hold.
MAX_BALANCE = Decimal("99999999999999.9999")


async def insert_transaction(
    conn: asyncpg.Connection,
    account_id: UUID,
    txn_type: TransactionType,
    amount: Decimal,
    description: str | None,
    reference_id: str,
) -> TransactionResponse:
    """
    Insert one ledger row. Must be called inside a DB transaction that also
    updates the balance. Raises DuplicateReferenceError on a repeated
    (account_id, reference_id).
    """
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO transactions (id, account_id, type, amount, description, reference_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, account_id, type, amount, description, reference_id, created_at;
            """,
            uuid4(),
            account_id,
            txn_type.value,
            amount,
            description,
            reference_id,
        )
    except asyncpg.UniqueViolationError:
        raise DuplicateReferenceError(
            f"reference_id '{reference_id}' already used for this account"
        )
    return TransactionResponse.model_validate(Transaction(**dict(row)))


class TransactionService:
    """Applies credits and debits to account balances atomically."""

    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def create_transaction(self, txn_in: TransactionCreate) -> TransactionResponse:
        """
        Record a credit or debit and update the account balance in one DB transaction.
        - The account row is locked (FOR UPDATE) so concurrent requests cannot overdraw it.
        - A debit larger than the balance is rejected and nothing is written.
        - (account_id, reference_id) is unique; a repeat is rejected.
        """
        async with self.conn.transaction():
            row = await self.conn.fetchrow(
                "SELECT balance FROM accounts WHERE id = $1 FOR UPDATE;",
                txn_in.account_id,
            )
            if row is None:
                raise AccountNotFoundError(f"Account {txn_in.account_id} not found")

            balance = row["balance"]
            if txn_in.type is TransactionType.DEBIT:
                if balance < txn_in.amount:
                    raise InsufficientFundsError(
                        f"Insufficient balance: available {balance}, requested {txn_in.amount}"
                    )
                new_balance = balance - txn_in.amount
            else:
                new_balance = balance + txn_in.amount
                if new_balance > MAX_BALANCE:
                    raise ValueError("Credit rejected: resulting balance exceeds the maximum allowed")

            txn = await insert_transaction(
                self.conn,
                txn_in.account_id,
                txn_in.type,
                txn_in.amount,
                txn_in.description,
                txn_in.reference_id,
            )

            await self.conn.execute(
                "UPDATE accounts SET balance = $1 WHERE id = $2;",
                new_balance,
                txn_in.account_id,
            )

        return txn

    async def list_transactions(
        self,
        account_id: UUID,
        txn_type: TransactionType | None,
        page: int,
        page_size: int,
    ) -> TransactionListResponse:
        """
        Return one page of an account's transactions, newest first.
        txn_type=None returns both credits and debits.
        """
        exists = await self.conn.fetchval("SELECT 1 FROM accounts WHERE id = $1;", account_id)
        if exists is None:
            raise AccountNotFoundError(f"Account {account_id} not found")

        type_value = txn_type.value if txn_type else None
        total = await self.conn.fetchval(
            """
            SELECT COUNT(*) FROM transactions
            WHERE account_id = $1 AND ($2::text IS NULL OR type = $2);
            """,
            account_id,
            type_value,
        )
        rows = await self.conn.fetch(
            """
            SELECT id, account_id, type, amount, description, reference_id, created_at
            FROM transactions
            WHERE account_id = $1 AND ($2::text IS NULL OR type = $2)
            ORDER BY created_at DESC, id DESC
            LIMIT $3 OFFSET $4;
            """,
            account_id,
            type_value,
            page_size,
            (page - 1) * page_size,
        )
        return TransactionListResponse(
            items=[TransactionResponse.model_validate(Transaction(**dict(r))) for r in rows],
            page=page,
            page_size=page_size,
            total_records=total,
            total_pages=math.ceil(total / page_size),
        )
