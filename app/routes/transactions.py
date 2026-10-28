from fastapi import APIRouter, Depends, status
import asyncpg
from app.db.database import get_db_connection
from app.schemas.transaction import TransactionCreate, TransactionResponse
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.post(
    "",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Credit or debit an account",
)
async def create_transaction(
    txn_in: TransactionCreate,
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """
    Apply a credit (adds to balance) or debit (subtracts from balance).

    - **amount**: positive, up to 4 decimal places.
    - **reference_id**: must be unique per account (409 if reused).
    - A debit exceeding the balance is rejected (400) and the balance is unchanged.
    - Unknown account returns 404.
    """
    return await TransactionService(conn).create_transaction(txn_in)
