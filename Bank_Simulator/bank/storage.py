"""JSON persistence for the banking application."""

from __future__ import annotations

import json
from pathlib import Path

from bank.account import Bank


def save_bank(bank: Bank, path: str | Path) -> None:
    """Save bank state to a JSON file."""
    target = Path(path)
    temporary = target.with_suffix(".tmp")

    temporary.write_text(
        json.dumps(
            bank.to_dict(),
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary.replace(target)


def load_bank(path: str | Path) -> Bank:
    """Load bank state from JSON, returning an empty bank on failure."""
    target = Path(path)

    if not target.exists():
        return Bank()

    try:
        data = json.loads(
            target.read_text(encoding="utf-8")
        )

        if not isinstance(data, dict):
            return Bank()

        return Bank.from_dict(data)

    except (
        OSError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return Bank()