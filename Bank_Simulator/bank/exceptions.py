"""Custom exceptions for the banking domain."""


class BankError(Exception):
    """Base exception for all bank related errors."""


class InvalidAmountError(BankError):
    """Raised when a monetary amount is invalid."""


class InsufficientFundsError(BankError):
    """Raised when an account cannot cover a withdrawal."""


class AccountNotFoundError(BankError):
    """Raised when an account cannot be found."""


class AccountAlreadyExistsError(BankError):
    """Raised when an account number already exists."""


class InvalidOwnerError(BankError):
    """Raised when an account owner name is invalid."""


class InvalidAccountTypeError(BankError):
    """Raised when an unsupported account type is requested."""


class WithdrawalLimitExceededError(BankError):
    """Raised when a savings withdrawal limit is exceeded."""