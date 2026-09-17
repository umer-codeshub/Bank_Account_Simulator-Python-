from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
import streamlit as st

from bank.account import AccountType, Bank
from bank.exceptions import BankError, InvalidAmountError
from bank.storage import load_bank, save_bank


STATE_FILE = Path("bank_state.json")


def initialise_state() -> None:
    """Initialise Streamlit session state."""
    if "bank" not in st.session_state:
        st.session_state.bank = load_bank(STATE_FILE)

    if "selected_account" not in st.session_state:
        st.session_state.selected_account = None


def save_current_state() -> None:
    """Persist the current bank state to disk."""
    save_bank(st.session_state.bank, STATE_FILE)


def parse_decimal(value: str, field_name: str) -> Decimal:
    """Convert a user supplied string to Decimal."""
    try:
        amount = Decimal(value.strip())
    except (InvalidOperation, ValueError):
        raise InvalidAmountError(
            f"{field_name} must be a valid monetary amount."
        )

    if not amount.is_finite():
        raise InvalidAmountError(
            f"{field_name} must be a finite monetary amount."
        )

    if amount <= Decimal("0"):
        raise InvalidAmountError(
            f"{field_name} must be greater than zero."
        )

    return amount.quantize(Decimal("0.01"))


def money(value: Decimal) -> str:
    """Format a Decimal as currency."""
    return f"{value:,.2f}"


def render_sidebar(bank: Bank) -> None:
    """Render the application sidebar."""
    st.sidebar.title("Bank Account Simulator")

    accounts = bank.accounts

    if accounts:
        labels = {
            account.account_number: (
                f"{account.account_number} | "
                f"{account.owner_name} | "
                f"{account.account_type.value}"
            )
            for account in accounts.values()
        }

        account_numbers = list(labels.keys())

        current = st.session_state.selected_account
        if current not in account_numbers:
            current = account_numbers[0]

        selected = st.sidebar.selectbox(
            "Select account",
            account_numbers,
            index=account_numbers.index(current),
            format_func=lambda number: labels[number],
        )

        st.session_state.selected_account = selected
    else:
        st.sidebar.info("No accounts exist yet.")

    st.sidebar.divider()
    st.sidebar.subheader("Create New Account")

    with st.sidebar.form("create_account_form"):
        owner_name = st.text_input("Owner name")
        account_type = st.selectbox(
            "Account type",
            [AccountType.SAVINGS.value, AccountType.CHECKING.value],
        )
        opening_balance = st.text_input(
            "Opening balance",
            value="0.00",
        )

        overdraft_limit = st.text_input(
            "Overdraft limit",
            value="0.00",
            disabled=account_type != AccountType.CHECKING.value,
        )

        interest_rate = st.text_input(
            "Monthly interest rate",
            value="0.01",
            disabled=account_type != AccountType.SAVINGS.value,
        )

        withdrawal_limit = st.number_input(
            "Withdrawals per cycle",
            min_value=1,
            value=3,
            step=1,
            disabled=account_type != AccountType.SAVINGS.value,
        )

        submitted = st.form_submit_button("Create account")

    if submitted:
        try:
            if not owner_name.strip():
                st.sidebar.error("Owner name is required.")
                return

            balance = Decimal(opening_balance.strip())

            if balance < Decimal("0"):
                st.sidebar.error("Opening balance cannot be negative.")
                return

            if account_type == AccountType.CHECKING.value:
                overdraft = parse_decimal(
                    overdraft_limit,
                    "Overdraft limit",
                )
            else:
                overdraft = Decimal("0")

            if account_type == AccountType.SAVINGS.value:
                rate = Decimal(interest_rate.strip())

                if rate < Decimal("0"):
                    st.sidebar.error(
                        "Interest rate cannot be negative."
                    )
                    return

                if not rate.is_finite():
                    st.sidebar.error("Invalid interest rate.")
                    return

                account = bank.create_account(
                    owner_name=owner_name.strip(),
                    account_type=AccountType.SAVINGS,
                    opening_balance=balance,
                    monthly_interest_rate=rate,
                    withdrawal_limit=withdrawal_limit,
                )
            else:
                account = bank.create_account(
                    owner_name=owner_name.strip(),
                    account_type=AccountType.CHECKING,
                    opening_balance=balance,
                    overdraft_limit=overdraft,
                )

            st.session_state.selected_account = account.account_number
            save_current_state()
            st.sidebar.success(
                f"Created account {account.account_number}."
            )
            st.rerun()

        except (BankError, InvalidOperation, ValueError) as exc:
            st.sidebar.error(str(exc))


def get_selected_account(bank: Bank):
    """Return the currently selected account."""
    number = st.session_state.selected_account

    if number is None:
        return None

    try:
        return bank.get_account(number)
    except BankError:
        return None


def render_dashboard(account) -> None:
    """Render the dashboard tab."""
    st.subheader("Dashboard")

    balance = account.balance
    available = account.available_balance

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Balance", money(balance))
    col2.metric("Available", money(available))
    col3.metric("Transactions", len(account.ledger))

    if account.account_type == AccountType.CHECKING:
        col4.metric(
            "Overdraft Limit",
            money(account.overdraft_limit),
        )
    else:
        col4.metric(
            "Withdrawals Remaining",
            str(account.withdrawals_remaining),
        )

    st.divider()

    st.write(f"**Owner:** {account.owner_name}")
    st.write(f"**Account:** {account.account_number}")
    st.write(f"**Type:** {account.account_type.value}")

    if account.account_type == AccountType.SAVINGS:
        st.write(
            f"**Monthly interest rate:** "
            f"{account.monthly_interest_rate:.4f}"
        )
        st.write(
            f"**Withdrawal cycle limit:** "
            f"{account.withdrawal_limit}"
        )


def render_transactions(bank: Bank, account) -> None:
    """Render transaction forms."""
    st.subheader("Transactions")

    deposit_col, withdraw_col = st.columns(2)

    with deposit_col:
        st.markdown("### Deposit")

        with st.form("deposit_form"):
            amount = st.text_input("Deposit amount")
            description = st.text_input(
                "Description",
                value="Cash deposit",
            )
            submitted = st.form_submit_button("Deposit")

        if submitted:
            try:
                value = parse_decimal(amount, "Deposit amount")
                account.deposit(value, description)
                save_current_state()
                st.success("Deposit completed.")
                st.rerun()
            except BankError as exc:
                st.error(str(exc))

    with withdraw_col:
        st.markdown("### Withdraw")

        with st.form("withdraw_form"):
            amount = st.text_input(
                "Withdrawal amount",
                key="withdraw_amount",
            )
            description = st.text_input(
                "Description",
                value="Cash withdrawal",
                key="withdraw_description",
            )
            submitted = st.form_submit_button("Withdraw")

        if submitted:
            try:
                value = parse_decimal(
                    amount,
                    "Withdrawal amount",
                )
                account.withdraw(value, description)
                save_current_state()
                st.success("Withdrawal completed.")
                st.rerun()
            except BankError as exc:
                st.error(str(exc))

    st.divider()
    st.markdown("### Transfer")

    available_accounts = [
        item
        for item in bank.accounts.values()
        if item.account_number != account.account_number
    ]

    if not available_accounts:
        st.info("Create another account to enable transfers.")
        return

    with st.form("transfer_form"):
        target = st.selectbox(
            "Transfer to",
            available_accounts,
            format_func=lambda item: (
                f"{item.account_number} | {item.owner_name}"
            ),
        )

        amount = st.text_input(
            "Transfer amount",
            key="transfer_amount",
        )

        description = st.text_input(
            "Transfer description",
            value="Account transfer",
        )

        submitted = st.form_submit_button("Transfer")

    if submitted:
        try:
            value = parse_decimal(amount, "Transfer amount")

            bank.transfer(
                source_number=account.account_number,
                target_number=target.account_number,
                amount=value,
                description=description,
            )

            save_current_state()
            st.success("Transfer completed.")
            st.rerun()

        except BankError as exc:
            st.error(str(exc))


def render_history(account) -> None:
    """Render a filterable transaction history."""
    st.subheader("Transaction History")

    ledger = account.ledger

    if not ledger:
        st.info("No transactions available.")
        return

    col1, col2, col3 = st.columns(3)

    min_date = min(item.timestamp.date() for item in ledger)
    max_date = max(item.timestamp.date() for item in ledger)

    with col1:
        start_date = st.date_input(
            "From",
            value=min_date,
            min_value=min_date,
            max_value=max_date,
        )

    with col2:
        end_date = st.date_input(
            "To",
            value=max_date,
            min_value=min_date,
            max_value=max_date,
        )

    transaction_types = sorted(
        {item.transaction_type.value for item in ledger}
    )

    with col3:
        selected_types = st.multiselect(
            "Transaction type",
            transaction_types,
            default=transaction_types,
        )

    rows = []

    for transaction in ledger:
        transaction_date = transaction.timestamp.date()

        if transaction_date < start_date:
            continue

        if transaction_date > end_date:
            continue

        if transaction.transaction_type.value not in selected_types:
            continue

        rows.append(
            {
                "Timestamp": transaction.timestamp,
                "Type": transaction.transaction_type.value,
                "Amount": float(transaction.amount),
                "Balance After": float(transaction.balance_after),
                "Description": transaction.description,
            }
        )

    dataframe = pd.DataFrame(rows)

    if dataframe.empty:
        st.info("No transactions match the selected filters.")
    else:
        st.dataframe(
            dataframe,
            use_container_width=True,
            hide_index=True,
        )


def render_statements(account) -> None:
    """Render balance over time."""
    st.subheader("Statements")

    ledger = account.ledger

    if not ledger:
        st.info("No statement data available.")
        return

    rows = [
        {
            "Timestamp": transaction.timestamp,
            "Balance": float(transaction.balance_after),
        }
        for transaction in ledger
    ]

    dataframe = pd.DataFrame(rows)
    dataframe = dataframe.set_index("Timestamp")

    st.line_chart(dataframe["Balance"])

    st.download_button(
        "Download statement CSV",
        data=dataframe.to_csv(),
        file_name=f"{account.account_number}_statement.csv",
        mime="text/csv",
    )


def main() -> None:
    """Run the Streamlit application."""
    st.set_page_config(
        page_title="Bank Account Simulator",
        page_icon="🏦",
        layout="wide",
    )

    initialise_state()

    bank: Bank = st.session_state.bank

    render_sidebar(bank)

    account = get_selected_account(bank)

    if account is None:
        st.title("Bank Account Simulator")
        st.info("Create an account from the sidebar to get started.")
        return

    st.title("Bank Account Simulator")

    tabs = st.tabs(
        [
            "Dashboard",
            "Transactions",
            "History",
            "Statements",
        ]
    )

    with tabs[0]:
        render_dashboard(account)

    with tabs[1]:
        render_transactions(bank, account)

    with tabs[2]:
        render_history(account)

    with tabs[3]:
        render_statements(account)


if __name__ == "__main__":
    main()