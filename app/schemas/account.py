import re
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccountBase(BaseModel):
    """Base account schema with common fields."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255, description="Account holder name")

    @field_validator("name")
    @classmethod
    def validate_alphabetical_name(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("Account name cannot be empty or only whitespace")
        # Only alphabetical characters and spaces are allowed (no digits or special symbols)
        if not re.match(r"^[a-zA-Z\s]+$", clean):
            raise ValueError("Account name must contain only alphabetical characters (no digits or special characters)")
        return clean


class AccountCreate(AccountBase):
    """
    Schema for creating an account.
    
    The client is only permitted to supply the account name.
    Balance and ID cannot be set by the client.
    """
    pass


class AccountResponse(BaseModel):
    """
    Schema returned to clients representing an account.
    """
    id: UUID
    name: str
    balance: Decimal = Field(default=Decimal("0.00"), description="Account balance, initially zero")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BalanceResponse(BaseModel):
    """Current balance of an account."""
    account_id: UUID
    balance: Decimal
