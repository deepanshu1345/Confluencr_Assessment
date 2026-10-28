from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
import asyncpg
from app.db.database import get_db_connection
from app.schemas.account import AccountCreate, AccountResponse, BalanceResponse
from app.schemas.transaction import TransactionListResponse, TransactionType
from app.services.account_service import AccountService
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account",
)
async def create_account(
    account_in: AccountCreate,
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """
    Create a new account.
    
    - **name**: Account holder name (required, alphabetical only).
    - **balance**: Always initialized to 0.00 by the system (clients cannot set this).
    - **id**: System-generated unique UUID.
    """
    service = AccountService(conn)
    return await service.create_account(account_in)


@router.get(
    "/{account_id}/balance",
    response_model=BalanceResponse,
    summary="Get the current balance of an account",
)
async def get_balance(
    account_id: UUID,
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """Returns the account's current balance. Unknown account returns 404."""
    return await AccountService(conn).get_balance(account_id)


@router.get(
    "/{account_id}/transactions",
    response_model=TransactionListResponse,
    summary="List an account's transactions",
)
async def list_transactions(
    account_id: UUID,
    type: TransactionType | None = Query(default=None, description="credit or debit; omit for both"),
    page: int = Query(default=1, ge=1, description="Page number, starting at 1"),
    page_size: int = Query(default=10, ge=1, le=100, description="Records per page (max 100)"),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """
    Paginated transactions for an account, sorted newest first (by created_at).
    Unknown account returns 404; invalid filters or paging values return 400.
    """
    return await TransactionService(conn).list_transactions(account_id, type, page, page_size)
