from dataclasses import dataclass
from datetime import date, datetime


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
