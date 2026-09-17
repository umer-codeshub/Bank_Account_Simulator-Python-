"""Transaction domain objects."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class TransactionType(str, Enum):
    """Supported transaction types."""

    OPENING = "opening"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    INTEREST = "interest"


@dataclass(frozen=True)
class Transaction:
    """Immutable transaction ledger entry."""

    timestamp: datetime
    transaction_type: TransactionType
    amount: Decimal
    balance_after: Decimal
    description: str

    def to_dict(self) -> dict[str, str]:
        """Convert the transaction to a JSON serialisable dictionary."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["transaction_type"] = self.transaction_type.value
        data["amount"] = str(self.amount)
        data["balance_after"] = str(self.balance_after)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Transaction:
        """Create a transaction from a dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            transaction_type=TransactionType(
                data["transaction_type"]
            ),
            amount=Decimal(data["amount"]),
            balance_after=Decimal(data["balance_after"]),
            description=data["description"],
        )