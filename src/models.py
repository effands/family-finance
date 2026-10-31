from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal


@dataclass(frozen=True)
class Category:
    name: str
    keywords: list[str]
    emoji: str = "🎁"
    type: str = "both"


@dataclass
class Transaction:
    id: int | None
    user_id: str
    username: str
    chat_id: str
    type: str
    amount: int
    description: str
    category: str
    transaction_date: date
    created_at: datetime


@dataclass(frozen=True)
class TransactionFilters:
    chat_id: str
    start: date | None = None
    end: date | None = None
    user_id: str | None = None
    transaction_type: str | None = None
    category: str | None = None
    search: str | None = None
    sort_by: str = "transaction_date"
    sort_dir: str = "desc"


@dataclass
class FinancialAccount:
    id: int | None
    chat_id: str
    name: str
    account_type: Literal["bank", "ewallet", "cash", "investment"]
    provider: str
    holder_name: str
    account_identifier: str
    currency: str
    opening_balance: int
    opening_balance_date: date
    is_active: bool = True
    notes: str = ""


@dataclass(frozen=True)
class LedgerEntry:
    id: int | None
    operation_id: str
    chat_id: str
    account_id: int
    direction: Literal["debit", "credit"]
    amount: int
    entry_type: str
    description: str
    category: str
    transaction_date: date


@dataclass(frozen=True)
class LedgerOperation:
    id: str
    chat_id: str
    operation_type: str
    description: str
    transaction_date: date
    actor_user_id: str
    actor_username: str
    idempotency_key: str | None = None
    reversed_operation_id: str | None = None
