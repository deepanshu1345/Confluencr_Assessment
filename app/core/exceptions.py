class AccountNotFoundError(Exception):
    """Raised when the target account does not exist."""


class InsufficientFundsError(Exception):
    """Raised when a debit exceeds the available balance."""


class DuplicateReferenceError(Exception):
    """Raised when a reference_id was already used for the same account."""
