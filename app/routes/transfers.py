from fastapi import APIRouter, Depends, status
import asyncpg
from app.db.database import get_db_connection
from app.schemas.transaction import TransferCreate, TransferResponse
from app.services.transfer_service import TransferService

router = APIRouter(prefix="/transfers", tags=["Transfers"])


@router.post(
    "",
    response_model=TransferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Transfer money between two accounts",
)
async def create_transfer(
    transfer_in: TransferCreate,
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """
    Atomically debit the source account and credit the destination account.

    - Both accounts must exist (404) and be different (400).
    - The source needs enough balance (400); nothing changes otherwise.
    - **reference_id** must be unused on both accounts (409).
    - Creates a debit on the source and a credit on the destination, both
      sharing the reference_id.
    """
    return await TransferService(conn).transfer(transfer_in)
