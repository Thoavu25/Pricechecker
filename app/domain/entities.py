from datetime import datetime
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Account:
    id: int
    username: str
    password_hash: str
    role: str
    store_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    approved: bool = False
    locked: bool = False


@dataclass
class Price:
    id: int
    store_id: int
    barcode_type: str
    gtin: str
    amount: Decimal
    recorded_at: datetime


@dataclass
class Discount:
    id: int
    store_id: int
    barcode_type: str
    gtin: str
    percentage: Decimal
    starts_at: datetime
    ends_at: datetime | None


@dataclass
class StoreQuote:
    price: Price
    store: Account
    discount: Discount | None


@dataclass
class AuditEvent:
    id: int
    actor_id: int
    action: str
    target_user_id: int | None
    details: str
    occurred_at: datetime

