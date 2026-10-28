from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TransactionType(str, Enum):
    CREDIT = "credit"
    DEBIT = "debit"


class TransactionCreate(BaseModel):
    """Request body for a credit/debit. id and created_at are system generated."""
    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    type: TransactionType
    amount: Decimal = Field(..., gt=0, max_digits=18, decimal_places=4, allow_inf_nan=False)
    description: str | None = Field(default=None, max_length=500)
    reference_id: str = Field(..., min_length=1, max_length=255)

    @field_validator("reference_id")
    @classmethod
    def strip_reference_id(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("reference_id cannot be empty or only whitespace")
        return clean


class TransactionResponse(BaseModel):
    id: UUID
    account_id: UUID
    type: TransactionType
    amount: Decimal
    description: str | None
    reference_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TransactionListResponse(BaseModel):
    """A page of transactions plus pagination metadata."""
    items: list[TransactionResponse]
    page: int
    page_size: int
    total_records: int
    total_pages: int


class TransferCreate(BaseModel):
    """Request body for moving money between two accounts."""
    model_config = ConfigDict(extra="forbid")

    source_account_id: UUID
    destination_account_id: UUID
    amount: Decimal = Field(..., gt=0, max_digits=18, decimal_places=4, allow_inf_nan=False)
    description: str | None = Field(default=None, max_length=500)
    reference_id: str = Field(..., min_length=1, max_length=255)

    @field_validator("reference_id")
    @classmethod
    def strip_reference_id(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("reference_id cannot be empty or only whitespace")
        return clean


class TransferResponse(BaseModel):
    source_transaction: TransactionResponse
    destination_transaction: TransactionResponse
    source_balance: Decimal
    destination_balance: Decimal
