from datetime import datetime
from decimal import Decimal

import pytest

from bank.account import (
    AccountType,
    Bank,
    CheckingAccount,
    SavingsAccount,
)
from bank.exceptions import (
    AccountAlreadyExistsError,
    AccountNotFoundError,
    InsufficientFundsError,
    InvalidAmountError,
    InvalidOwnerError,
    WithdrawalLimitExceededError,
)
from bank.storage import load_bank, save_bank
from bank.transaction import TransactionType


def test_deposit() -> None:
    """Deposits should increase the account balance."""
    bank = Bank()

    account = bank.create_account(
        owner_name="Umer",
        account_type=AccountType.CHECKING,
        opening_balance=Decimal("100.00"),
    )

    transaction = account.deposit(
        Decimal("50.00"),
        "Salary",
    )

    assert account.balance == Decimal("150.00")
    assert transaction.transaction_type == TransactionType.DEPOSIT
    assert transaction.balance_after == Decimal("150.00")


def test_withdrawal() -> None:
    """Withdrawals should decrease the account balance."""
    bank = Bank()

    account = bank.create_account(
        owner_name="Umer",
        account_type=AccountType.SAVINGS,
        opening_balance=Decimal("500.00"),
    )

    account.withdraw(Decimal("125.00"))

    assert account.balance == Decimal("375.00")


def test_checking_overdraft_boundary() -> None:
    """Checking should allow withdrawal exactly up to overdraft."""
    bank = Bank()

    account = bank.create_account(
        owner_name="Umer",
        account_type=AccountType.CHECKING,
        opening_balance=Decimal("100.00"),
        overdraft_limit=Decimal("50.00"),
    )

    account.withdraw(Decimal("150.00"))

    assert account.balance == Decimal("-50.00")
    assert account.available_balance == Decimal("0.00")


def test_checking_overdraft_rejected() -> None:
    """Checking should reject withdrawals beyond overdraft."""
    bank = Bank()

    account = bank.create_account(
        owner_name="Umer",
        account_type=AccountType.CHECKING,
        opening_balance=Decimal("100.00"),
        overdraft_limit=Decimal("50.00"),
    )

    with pytest.raises(InsufficientFundsError):
        account.withdraw(Decimal("150.01"))


def test_savings_withdrawal_beyond_balance() -> None:
    """Savings should reject withdrawals beyond the balance."""
    bank = Bank()

    account = bank.create_account(
        owner_name="Umer",
        account_type=AccountType.SAVINGS,
        opening_balance=Decimal("100.00"),
    )

    with pytest.raises(InsufficientFundsError):
        account.withdraw(Decimal("100.01"))


def test_savings_withdrawal_limit() -> None:
    """Savings should enforce the configured withdrawal limit."""
    bank = Bank()

    account = bank.create_account(
        owner_name="Umer",
        account_type=AccountType.SAVINGS,
        opening_balance=Decimal("500.00"),
        withdrawal_limit=2,
    )

    account.withdraw(Decimal("10.00"))
    account.withdraw(Decimal("10.00"))

    with pytest.raises(WithdrawalLimitExceededError):
        account.withdraw(Decimal("10.00"))


def test_transfer() -> None:
    """Transfers should update both accounts and both ledgers."""
    bank = Bank()

    source = bank.create_account(
        owner_name="Alice",
        account_type=AccountType.CHECKING,
        opening_balance=Decimal("500.00"),
    )

    target = bank.create_account(
        owner_name="Bob",
        account_type=AccountType.SAVINGS,
        opening_balance=Decimal("100.00"),
    )

    bank.transfer(
        source.account_number,
        target.account_number,
        Decimal("150.00"),
    )

    assert source.balance == Decimal("350.00")
    assert target.balance == Decimal("250.00")

    assert (
        source.ledger[-1].transaction_type
        == TransactionType.TRANSFER_OUT
    )

    assert (
        target.ledger[-1].transaction_type
        == TransactionType.TRANSFER_IN
    )


def test_transfer_insufficient_funds() -> None:
    """Transfers should reject amounts unavailable to the source."""
    bank = Bank()

    source = bank.create_account(
        owner_name="Alice",
        account_type=AccountType.CHECKING,
        opening_balance=Decimal("50.00"),
    )

    target = bank.create_account(
        owner_name="Bob",
        account_type=AccountType.CHECKING,
        opening_balance=Decimal("100.00"),
    )

    with pytest.raises(InsufficientFundsError):
        bank.transfer(
            source.account_number,
            target.account_number,
            Decimal("50.01"),
        )


def test_interest_calculation() -> None:
    """Savings interest should be calculated monthly."""
    bank = Bank()

    account = bank.create_account(
        owner_name="Umer",
        account_type=AccountType.SAVINGS,
        opening_balance=Decimal("1000.00"),
        monthly_interest_rate=Decimal("0.01"),
    )

    start = account.last_interest_accrual
    assert start is not None

    future = datetime(
        start.year + (start.month // 12),
        start.month % 12 + 1,
        min(start.day, 28),
    )

    interest = account.accrue_interest(future)

    assert interest == Decimal("10.00")
    assert account.balance == Decimal("1010.00")


def test_interest_multiple_months() -> None:
    """Interest should compound over multiple completed months."""
    bank = Bank()

    account = bank.create_account(
        owner_name="Umer",
        account_type=AccountType.SAVINGS,
        opening_balance=Decimal("1000.00"),
        monthly_interest_rate=Decimal("0.01"),
    )

    start = account.last_interest_accrual
    assert start is not None

    future = start.replace(
        year=start.year + 1,
        month=start.month,
        day=min(start.day, 28),
    )

    interest = account.accrue_interest(future)

    assert interest > Decimal("120.00")
    assert account.balance > Decimal("1120.00")


def test_invalid_amount() -> None:
    """Invalid monetary values should raise InvalidAmountError."""
    bank = Bank()

    account = bank.create_account(
        owner_name="Umer",
        account_type=AccountType.CHECKING,
    )

    with pytest.raises(InvalidAmountError):
        account.deposit(Decimal("0.00"))

    with pytest.raises(InvalidAmountError):
        account.withdraw(Decimal("-10.00"))


def test_invalid_owner() -> None:
    """Empty owner names should be rejected."""
    bank = Bank()

    with pytest.raises(InvalidOwnerError):
        bank.create_account(
            owner_name="",
            account_type=AccountType.CHECKING,
        )


def test_account_not_found() -> None:
    """Unknown accounts should raise AccountNotFoundError."""
    bank = Bank()

    with pytest.raises(AccountNotFoundError):
        bank.get_account("DOES-NOT-EXIST")


def test_duplicate_account_number() -> None:
    """Duplicate account numbers should be rejected."""
    bank = Bank()

    bank.create_account(
        owner_name="Alice",
        account_type=AccountType.CHECKING,
        account_number="123",
    )

    with pytest.raises(AccountAlreadyExistsError):
        bank.create_account(
            owner_name="Bob",
            account_type=AccountType.CHECKING,
            account_number="123",
        )


def test_transfer_unknown_account() -> None:
    """Transfers should reject unknown account numbers."""
    bank = Bank()

    account = bank.create_account(
        owner_name="Alice",
        account_type=AccountType.CHECKING,
    )

    with pytest.raises(AccountNotFoundError):
        bank.transfer(
            account.account_number,
            "UNKNOWN",
            Decimal("10.00"),
        )


def test_transfer_to_same_account() -> None:
    """Transfers to the same account should be rejected."""
    bank = Bank()

    account = bank.create_account(
        owner_name="Alice",
        account_type=AccountType.CHECKING,
    )

    with pytest.raises(ValueError):
        bank.transfer(
            account.account_number,
            account.account_number,
            Decimal("10.00"),
        )


def test_ledger_is_immutable_view() -> None:
    """The public ledger should not expose a mutable list."""
    bank = Bank()

    account = bank.create_account(
        owner_name="Umer",
        account_type=AccountType.CHECKING,
    )

    assert isinstance(account.ledger, tuple)


def test_json_persistence(tmp_path) -> None:
    """Bank state should survive JSON save and load."""
    path = tmp_path / "bank_state.json"

    bank = Bank()

    account = bank.create_account(
        owner_name="Umer",
        account_type=AccountType.CHECKING,
        opening_balance=Decimal("250.00"),
        overdraft_limit=Decimal("100.00"),
    )

    account.deposit(Decimal("50.00"))

    save_bank(bank, path)

    loaded = load_bank(path)
    loaded_account = loaded.get_account(
        account.account_number
    )

    assert loaded_account.owner_name == "Umer"
    assert loaded_account.balance == Decimal("300.00")
    assert loaded_account.overdraft_limit == Decimal("100.00")
    assert len(loaded_account.ledger) == 2


def test_missing_state_file(tmp_path) -> None:
    """Missing state files should produce an empty bank."""
    bank = load_bank(tmp_path / "missing.json")

    assert bank.accounts == {}


def test_corrupted_state_file(tmp_path) -> None:
    """Corrupted JSON should be handled gracefully."""
    path = tmp_path / "broken.json"
    path.write_text(
        "{ this is not valid json",
        encoding="utf-8",
    )

    bank = load_bank(path)

    assert bank.accounts == {}