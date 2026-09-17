# Bank Account Simulator

A production-style Bank Account Simulator built with Python, dataclasses,
Decimal based monetary calculations, JSON persistence, pytest, and Streamlit.

The application separates the banking domain logic from the Streamlit
presentation layer.

## Features

### Account Management

* Create Savings and Checking accounts
* Unique account numbers
* Multiple accounts in the same application session
* Owner name and opening balance
* Configurable Checking overdraft limit
* Configurable Savings monthly interest rate
* Configurable Savings withdrawal limit

### Transactions

* Deposits
* Withdrawals
* Transfers between accounts
* Checking overdraft support
* Savings withdrawal limits
* Monthly Savings interest
* Immutable transaction ledger

### Transaction History

Every account maintains a transaction ledger containing:

* Timestamp
* Transaction type
* Amount
* Balance after transaction
* Description

The Streamlit interface supports filtering transactions by:

* Date range
* Transaction type

### Persistence

Application state is stored locally in:

```text
bank_state.json