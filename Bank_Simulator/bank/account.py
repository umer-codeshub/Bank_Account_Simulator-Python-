"""Bank account domain models and banking service."""

from __future__ import annotations

from abc import ABC, abstractmethod
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any

from bank.exceptions import (
    AccountAlreadyExistsError,
    AccountNotFoundError,
    InsufficientFundsError,
    InvalidAccountTypeError,
    InvalidAmountError,
    InvalidOwnerError,
    WithdrawalLimitExceededError,
)
from bank.transaction import Transaction, TransactionType


CENT = Decimal("0.01")


def quantize_money(value: Decimal) -> Decimal:
    """Round a monetary value to two decimal places."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def validate_amount(amount: Decimal) -> Decimal:
    """Validate and normalise a monetary amount."""
    if not isinstance(amount, Decimal):
        raise InvalidAmountError("Amount must be a Decimal.")

    if not amount.is_finite() or amount <= Decimal("0"):
        raise InvalidAmountError(
            "Amount must be a finite value greater than zero."
        )

    return quantize_money(amount)


def add_months(value: datetime, months: int) -> datetime:
    """Return a datetime moved forward by the requested number of months."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1

    day = min(value.day, monthrange(year, month)[1])

    return value.replace(
        year=year,
        month=month,
        day=day,
    )


class AccountType(str, Enum):
    """Supported account types."""

    SAVINGS = "Savings"
    CHECKING = "Checking"


@dataclass
class Account(ABC):
    """Abstract base class for all bank accounts."""

    account_number: str
    owner_name: str
    opening_balance: Decimal = Decimal("0.00")
    _balance: Decimal = field(
        default=Decimal("0.00"),
        repr=False,
    )
    _ledger: list[Transaction] = field(
        default_factory=list,
        repr=False,
    )

    def __post_init__(self) -> None:
        """Validate and initialise an account."""
        if not self.owner_name.strip():
            raise InvalidOwnerError("Owner name cannot be empty.")

        if self.opening_balance < Decimal("0"):
            raise InvalidAmountError(
                "Opening balance cannot be negative."
            )

        self.opening_balance = quantize_money(self.opening_balance)
        self._balance = quantize_money(self._balance)

        if not self._ledger:
            self._record(
                transaction_type=TransactionType.OPENING,
                amount=self.opening_balance,
                description="Opening balance",
            )

    @property
    @abstractmethod
    def account_type(self) -> AccountType:
        """Return the account type."""

    @property
    def balance(self) -> Decimal:
        """Return the current account balance."""
        return self._balance

    @property
    def available_balance(self) -> Decimal:
        """Return the amount currently available for withdrawal."""
        return self._available_balance()

    @property
    def ledger(self) -> tuple[Transaction, ...]:
        """Return an immutable view of the transaction ledger."""
        return tuple(self._ledger)

    def deposit(
        self,
        amount: Decimal,
        description: str = "Deposit",
    ) -> Transaction:
        """Deposit money into the account."""
        value = validate_amount(amount)

        self._balance = quantize_money(self._balance + value)

        return self._record(
            transaction_type=TransactionType.DEPOSIT,
            amount=value,
            description=description,
        )

    def withdraw(
        self,
        amount: Decimal,
        description: str = "Withdrawal",
    ) -> Transaction:
        """Withdraw money from the account."""
        value = validate_amount(amount)

        self._validate_withdrawal(value)

        self._balance = quantize_money(self._balance - value)

        return self._record(
            transaction_type=TransactionType.WITHDRAWAL,
            amount=value,
            description=description,
        )

    def _record(
        self,
        transaction_type: TransactionType,
        amount: Decimal,
        description: str,
    ) -> Transaction:
        """Append an immutable transaction to the ledger."""
        transaction = Transaction(
            timestamp=datetime.now(),
            transaction_type=transaction_type,
            amount=quantize_money(amount),
            balance_after=self._balance,
            description=description,
        )

        self._ledger.append(transaction)
        return transaction

    @abstractmethod
    def _available_balance(self) -> Decimal:
        """Return available funds for this account type."""

    @abstractmethod
    def _validate_withdrawal(self, amount: Decimal) -> None:
        """Validate whether a withdrawal is allowed."""

    def _record_transfer_out(
        self,
        amount: Decimal,
        description: str,
    ) -> Transaction:
        """Record the outgoing side of a transfer."""
        return self._record(
            transaction_type=TransactionType.TRANSFER_OUT,
            amount=amount,
            description=description,
        )

    def _record_transfer_in(
        self,
        amount: Decimal,
        description: str,
    ) -> Transaction:
        """Record the incoming side of a transfer."""
        return self._record(
            transaction_type=TransactionType.TRANSFER_IN,
            amount=amount,
            description=description,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the account into a JSON serialisable dictionary."""
        return {
            "account_type": self.account_type.value,
            "account_number": self.account_number,
            "owner_name": self.owner_name,
            "opening_balance": str(self.opening_balance),
            "balance": str(self._balance),
            "ledger": [
                transaction.to_dict()
                for transaction in self._ledger
            ],
        }


@dataclass
class CheckingAccount(Account):
    """Bank account that supports configurable overdraft."""

    overdraft_limit: Decimal = Decimal("0.00")

    @property
    def account_type(self) -> AccountType:
        """Return the checking account type."""
        return AccountType.CHECKING

    def __post_init__(self) -> None:
        """Validate checking account configuration."""
        super().__post_init__()

        if self.overdraft_limit < Decimal("0"):
            raise InvalidAmountError(
                "Overdraft limit cannot be negative."
            )

        self.overdraft_limit = quantize_money(self.overdraft_limit)

    def _available_balance(self) -> Decimal:
        """Return balance plus the configured overdraft."""
        return quantize_money(
            self._balance + self.overdraft_limit
        )

    def _validate_withdrawal(self, amount: Decimal) -> None:
        """Validate a checking account withdrawal."""
        if amount > self.available_balance:
            raise InsufficientFundsError(
                "Withdrawal exceeds available balance and overdraft."
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert the checking account to a dictionary."""
        data = super().to_dict()
        data["overdraft_limit"] = str(self.overdraft_limit)
        return data


@dataclass
class SavingsAccount(Account):
    """Savings account with interest and withdrawal limits."""

    monthly_interest_rate: Decimal = Decimal("0.01")
    withdrawal_limit: int = 3
    withdrawals_this_cycle: int = 0
    last_interest_accrual: datetime | None = None

    @property
    def account_type(self) -> AccountType:
        """Return the savings account type."""
        return AccountType.SAVINGS

    def __post_init__(self) -> None:
        """Validate savings account configuration."""
        super().__post_init__()

        if self.monthly_interest_rate < Decimal("0"):
            raise InvalidAmountError(
                "Interest rate cannot be negative."
            )

        if self.withdrawal_limit < 1:
            raise InvalidAmountError(
                "Withdrawal limit must be at least one."
            )

        self.monthly_interest_rate = Decimal(
            self.monthly_interest_rate
        )

        if self.last_interest_accrual is None:
            self.last_interest_accrual = datetime.now()

    @property
    def withdrawals_remaining(self) -> int:
        """Return the remaining withdrawals in the current cycle."""
        return max(
            self.withdrawal_limit - self.withdrawals_this_cycle,
            0,
        )

    def _available_balance(self) -> Decimal:
        """Return the current savings balance."""
        return self._balance

    def _validate_withdrawal(self, amount: Decimal) -> None:
        """Validate a savings withdrawal."""
        if amount > self._balance:
            raise InsufficientFundsError(
                "Withdrawal exceeds savings account balance."
            )

        if self.withdrawals_this_cycle >= self.withdrawal_limit:
            raise WithdrawalLimitExceededError(
                "Monthly savings withdrawal limit has been reached."
            )

    def withdraw(
        self,
        amount: Decimal,
        description: str = "Withdrawal",
    ) -> Transaction:
        """Withdraw money while enforcing the savings withdrawal limit."""
        transaction = super().withdraw(amount, description)
        self.withdrawals_this_cycle += 1
        return transaction

    def accrue_interest(
        self,
        as_of: datetime | None = None,
    ) -> Decimal:
        """Accrue one or more completed months of interest."""
        current_time = as_of or datetime.now()

        if current_time < self.last_interest_accrual:
            raise ValueError(
                "Interest accrual date cannot be before the last accrual."
            )

        months = 0
        cursor = self.last_interest_accrual

        while add_months(cursor, 1) <= current_time:
            cursor = add_months(cursor, 1)
            months += 1

        if months == 0:
            return Decimal("0.00")

        total_interest = Decimal("0.00")

        for _ in range(months):
            interest = quantize_money(
                self._balance * self.monthly_interest_rate
            )

            if interest > Decimal("0"):
                self._balance = quantize_money(
                    self._balance + interest
                )

                self._record(
                    transaction_type=TransactionType.INTEREST,
                    amount=interest,
                    description="Monthly interest",
                )

                total_interest += interest

            self.withdrawals_this_cycle = 0

        self.last_interest_accrual = cursor

        return quantize_money(total_interest)

    def to_dict(self) -> dict[str, Any]:
        """Convert the savings account to a dictionary."""
        data = super().to_dict()
        data.update(
            {
                "monthly_interest_rate": str(
                    self.monthly_interest_rate
                ),
                "withdrawal_limit": self.withdrawal_limit,
                "withdrawals_this_cycle": self.withdrawals_this_cycle,
                "last_interest_accrual": (
                    self.last_interest_accrual.isoformat()
                    if self.last_interest_accrual
                    else None
                ),
            }
        )
        return data


class Bank:
    """Service that manages multiple bank accounts."""

    def __init__(self) -> None:
        """Create an empty bank."""
        self._accounts: dict[str, Account] = {}

    @property
    def accounts(self) -> dict[str, Account]:
        """Return all accounts indexed by account number."""
        return dict(self._accounts)

    def create_account(
        self,
        owner_name: str,
        account_type: AccountType,
        opening_balance: Decimal = Decimal("0.00"),
        *,
        account_number: str | None = None,
        overdraft_limit: Decimal = Decimal("0.00"),
        monthly_interest_rate: Decimal = Decimal("0.01"),
        withdrawal_limit: int = 3,
    ) -> Account:
        """Create and register a new bank account."""
        if not owner_name.strip():
            raise InvalidOwnerError("Owner name cannot be empty.")

        if account_number is None:
            account_number = self._generate_account_number()

        if account_number in self._accounts:
            raise AccountAlreadyExistsError(
                f"Account {account_number} already exists."
            )

        if account_type == AccountType.CHECKING:
            account = CheckingAccount(
                account_number=account_number,
                owner_name=owner_name.strip(),
                opening_balance=opening_balance,
                _balance=opening_balance,
                overdraft_limit=overdraft_limit,
            )
        elif account_type == AccountType.SAVINGS:
            account = SavingsAccount(
                account_number=account_number,
                owner_name=owner_name.strip(),
                opening_balance=opening_balance,
                _balance=opening_balance,
                monthly_interest_rate=monthly_interest_rate,
                withdrawal_limit=withdrawal_limit,
            )
        else:
            raise InvalidAccountTypeError(
                f"Unsupported account type: {account_type}"
            )

        self._accounts[account_number] = account
        return account

    def get_account(self, account_number: str) -> Account:
        """Return an account by account number."""
        try:
            return self._accounts[account_number]
        except KeyError:
            raise AccountNotFoundError(
                f"Account {account_number} was not found."
            )

    def transfer(
        self,
        source_number: str,
        target_number: str,
        amount: Decimal,
        description: str = "Account transfer",
    ) -> None:
        """Transfer money atomically between two accounts."""
        if source_number == target_number:
            raise ValueError(
                "Source and target accounts must be different."
            )

        value = validate_amount(amount)

        source = self.get_account(source_number)
        target = self.get_account(target_number)

        source._validate_withdrawal(value)

        source._balance = quantize_money(
            source._balance - value
        )

        target._balance = quantize_money(
            target._balance + value
        )

        source._record_transfer_out(
            value,
            f"{description} to {target_number}",
        )

        target._record_transfer_in(
            value,
            f"{description} from {source_number}",
        )

        if isinstance(source, SavingsAccount):
            source.withdrawals_this_cycle += 1

    def accrue_all_interest(
        self,
        as_of: datetime | None = None,
    ) -> Decimal:
        """Accrue interest for every savings account."""
        total = Decimal("0.00")

        for account in self._accounts.values():
            if isinstance(account, SavingsAccount):
                total += account.accrue_interest(as_of)

        return quantize_money(total)

    def _generate_account_number(self) -> str:
        """Generate a unique sequential account number."""
        number = 10000001 + len(self._accounts)

        while str(number) in self._accounts:
            number += 1

        return str(number)

    def to_dict(self) -> dict[str, Any]:
        """Convert the bank state to a dictionary."""
        return {
            "accounts": [
                account.to_dict()
                for account in self._accounts.values()
            ]
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Bank:
        """Create a Bank instance from persisted data."""
        bank = cls()

        for account_data in data.get("accounts", []):
            account_type = AccountType(
                account_data["account_type"]
            )

            ledger = [
                Transaction.from_dict(item)
                for item in account_data.get("ledger", [])
            ]

            common = {
                "account_number": account_data["account_number"],
                "owner_name": account_data["owner_name"],
                "opening_balance": Decimal(
                    account_data["opening_balance"]
                ),
                "_balance": Decimal(account_data["balance"]),
                "_ledger": ledger,
            }

            if account_type == AccountType.CHECKING:
                account = CheckingAccount(
                    **common,
                    overdraft_limit=Decimal(
                        account_data["overdraft_limit"]
                    ),
                )
            elif account_type == AccountType.SAVINGS:
                last_accrual = account_data.get(
                    "last_interest_accrual"
                )

                account = SavingsAccount(
                    **common,
                    monthly_interest_rate=Decimal(
                        account_data["monthly_interest_rate"]
                    ),
                    withdrawal_limit=int(
                        account_data["withdrawal_limit"]
                    ),
                    withdrawals_this_cycle=int(
                        account_data["withdrawals_this_cycle"]
                    ),
                    last_interest_accrual=(
                        datetime.fromisoformat(last_accrual)
                        if last_accrual
                        else None
                    ),
                )
            else:
                raise InvalidAccountTypeError(
                    f"Unsupported account type: {account_type}"
                )

            bank._accounts[account.account_number] = account

        return bank