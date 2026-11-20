from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(20), index=True)
    store_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    prices: Mapped[list["PriceRecord"]] = relationship(back_populates="store")
    discounts: Mapped[list["DiscountRecord"]] = relationship(back_populates="store")


class PriceRecord(Base):
    __tablename__ = "prices"
    __table_args__ = (
        Index("ix_prices_product_time", "barcode_type", "gtin", "recorded_at"),
        Index("ix_prices_store_product", "store_id", "barcode_type", "gtin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    barcode_type: Mapped[str] = mapped_column(String(20))
    gtin: Mapped[str] = mapped_column(String(14))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    store: Mapped[UserRecord] = relationship(back_populates="prices")


class DiscountRecord(Base):
    __tablename__ = "discounts"
    __table_args__ = (Index("ix_discounts_product", "barcode_type", "gtin", "active"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    barcode_type: Mapped[str] = mapped_column(String(20))
    gtin: Mapped[str] = mapped_column(String(14))
    percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    store: Mapped[UserRecord] = relationship(back_populates="discounts")


class ShopperSearchRecord(Base):
    __tablename__ = "shopper_searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shopper_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    barcode_type: Mapped[str] = mapped_column(String(20))
    gtin: Mapped[str] = mapped_column(String(14))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    latitude: Mapped[float] = mapped_column()
    longitude: Mapped[float] = mapped_column()
    searched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditLogRecord(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    target_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str] = mapped_column(Text, default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
