import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

GTIN = Annotated[str, Field(min_length=8, max_length=14)]
BarcodeType = Annotated[str, Field(min_length=2, max_length=20)]
Password = Annotated[str, Field(min_length=10, max_length=128)]
PriceAmount = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Latitude = Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
Longitude = Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]


class LoginRequest(BaseModel):
    username: Annotated[str, Field(min_length=1, max_length=80)]
    password: Annotated[str, Field(min_length=1, max_length=128)]


class ShopperRegistration(BaseModel):
    username: Annotated[str, Field(min_length=3, max_length=80)]
    password: Password


class StoreRegistration(ShopperRegistration):
    store_name: Annotated[str, Field(min_length=1, max_length=120)]
    latitude: Latitude
    longitude: Longitude


class AdminRegistration(ShopperRegistration):
    pass


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class AccountResponse(BaseModel):
    id: int
    username: str
    role: str
    store_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    approved: bool
    locked: bool

    @classmethod
    def from_account(cls, account):
        return cls(
            id=account.id,
            username=account.username,
            role=account.role,
            store_name=account.store_name,
            latitude=account.latitude,
            longitude=account.longitude,
            approved=account.approved,
            locked=account.locked,
        )


class PriceInput(BaseModel):
    barcode_type: BarcodeType
    gtin: GTIN
    price: PriceAmount
    timestamp: datetime

    @field_validator("gtin")
    @classmethod
    def gtin_is_digits(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9]{8,14}", value):
            raise ValueError("GTIN must contain 8 to 14 digits")
        return value

    @field_validator("barcode_type")
    @classmethod
    def normalize_barcode_type(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"GTIN", "EAN", "UPC"}:
            raise ValueError("barcode_type must be GTIN, EAN, or UPC")
        return normalized

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value


class PriceBatch(BaseModel):
    prices: Annotated[list[PriceInput], Field(min_length=1, max_length=1000)]


class DiscountInput(BaseModel):
    barcode_type: BarcodeType
    gtin: GTIN
    percentage: Annotated[Decimal, Field(gt=0, le=100, max_digits=5, decimal_places=2)]
    starts_at: datetime
    ends_at: datetime | None = None

    @field_validator("gtin")
    @classmethod
    def gtin_is_digits(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9]{8,14}", value):
            raise ValueError("GTIN must contain 8 to 14 digits")
        return value

    @field_validator("barcode_type")
    @classmethod
    def normalize_barcode_type(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"GTIN", "EAN", "UPC"}:
            raise ValueError("barcode_type must be GTIN, EAN, or UPC")
        return normalized

    @model_validator(mode="after")
    def validate_period(self):
        if self.starts_at.tzinfo is None or self.starts_at.utcoffset() is None:
            raise ValueError("starts_at must include a timezone")
        if self.ends_at and (
            self.ends_at.tzinfo is None or self.ends_at.utcoffset() is None
        ):
            raise ValueError("ends_at must include a timezone")
        if self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class PriceComparisonRequest(PriceInput):
    latitude: Latitude
    longitude: Longitude
    nearby_km: Annotated[float, Field(gt=0, le=100, allow_inf_nan=False)] = 10


class PriceOffer(BaseModel):
    store_id: int
    store_name: str
    latitude: float
    longitude: float
    distance_km: float
    price: Decimal
    discount_percent: Decimal
    current_price: Decimal
    label: str
    recorded_at: datetime


class PriceComparisonResponse(BaseModel):
    barcode_type: str
    gtin: str
    nearby_km: float
    offers: list[PriceOffer]


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int
    action: str
    target_user_id: int | None
    details: str
    occurred_at: datetime
