import asyncpg
from app.core.exceptions import AccountNotFoundError, InsufficientFundsError
from app.schemas.transaction import (
    TransactionType,
    TransferCreate,
    TransferResponse,
)
from app.services.transaction_service import MAX_BALANCE, insert_transaction


class TransferService:
    """Moves money between two accounts as a single atomic operation."""

    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn

    async def transfer(self, t: TransferCreate) -> TransferResponse:
        """
        Debit the source and credit the destination in one DB transaction.
        - Both accounts are locked in id order, so opposite transfers (A->B and
          B->A) cannot deadlock and concurrent transfers cannot overdraw.
        - Any failure rolls back both legs: a partial transfer is impossible.
        - The same reference_id is recorded on both legs (it only has to be
          unique per account).
        """
        if t.source_account_id == t.destination_account_id:
            raise ValueError("Source and destination accounts must be different")

        async with self.conn.transaction():
            rows = await self.conn.fetch(
                "SELECT id, balance FROM accounts WHERE id = ANY($1::uuid[]) ORDER BY id FOR UPDATE;",
                [t.source_account_id, t.destination_account_id],
            )
            balances = {r["id"]: r["balance"] for r in rows}
            for label, account_id in (
                ("Source", t.source_account_id),
                ("Destination", t.destination_account_id),
            ):
                if account_id not in balances:
                    raise AccountNotFoundError(f"{label} account {account_id} not found")

            source_balance = balances[t.source_account_id]
            if source_balance < t.amount:
                raise InsufficientFundsError(
                    f"Insufficient balance: available {source_balance}, requested {t.amount}"
                )
            new_source = source_balance - t.amount
            new_destination = balances[t.destination_account_id] + t.amount
            if new_destination > MAX_BALANCE:
                raise ValueError("Transfer rejected: destination balance would exceed the maximum allowed")

            debit = await insert_transaction(
                self.conn, t.source_account_id, TransactionType.DEBIT, t.amount, t.description, t.reference_id
            )
            await self.conn.execute(
                "UPDATE accounts SET balance = $1 WHERE id = $2;", new_source, t.source_account_id
            )
            credit = await insert_transaction(
                self.conn, t.destination_account_id, TransactionType.CREDIT, t.amount, t.description, t.reference_id
            )
            await self.conn.execute(
                "UPDATE accounts SET balance = $1 WHERE id = $2;", new_destination, t.destination_account_id
            )

        return TransferResponse(
            source_transaction=debit,
            destination_transaction=credit,
            source_balance=new_source,
            destination_balance=new_destination,
        )
