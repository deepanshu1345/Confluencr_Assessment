from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass
class Transaction:
    """Domain model representing a ledger transaction."""
    id: UUID
    account_id: UUID
    type: str
    amount: Decimal
    description: str | None
    reference_id: str
    created_at: datetime
