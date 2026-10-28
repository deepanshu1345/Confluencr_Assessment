from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass
class Account:
    """Domain model representing an account entity."""
    id: UUID
    name: str
    balance: Decimal
    created_at: datetime
