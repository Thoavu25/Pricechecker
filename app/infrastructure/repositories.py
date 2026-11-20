from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.entities import Account, AuditEvent, Discount, Price, StoreQuote
from app.domain.errors import ConflictError
from app.infrastructure.models import (
    AuditLogRecord,
    DiscountRecord,
    PriceRecord,
    ShopperSearchRecord,
    UserRecord,
)


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _account(record: UserRecord | None) -> Account | None:
        if record is None:
            return None
        return Account(
            id=record.id,
            username=record.username,
            password_hash=record.password_hash,
            role=record.role,
            store_name=record.store_name,
            latitude=record.latitude,
            longitude=record.longitude,
            approved=record.approved,
            locked=record.locked,
        )

    def get(self, user_id: int) -> Account | None:
        return self._account(self.session.get(UserRecord, user_id))

    def get_by_username(self, username: str) -> Account | None:
        return self._account(self.session.scalar(select(UserRecord).where(UserRecord.username == username)))

    def add(self, account: Account) -> Account:
        user = UserRecord(
            username=account.username,
            password_hash=account.password_hash,
            role=account.role,
            store_name=account.store_name,
            latitude=account.latitude,
            longitude=account.longitude,
            approved=account.approved,
            locked=account.locked,
        )
        self.session.add(user)
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise ConflictError("Username is already registered") from error
        self.session.refresh(user)
        return self._account(user)

    def pending_stores(self) -> list[Account]:
        records = self.session.scalars(
            select(UserRecord).where(
                UserRecord.role == "store", UserRecord.approved.is_(False)
            )
        )
        return [self._account(record) for record in records]

    def stores(self) -> list[Account]:
        records = self.session.scalars(
            select(UserRecord).where(UserRecord.role == "store")
        )
        return [self._account(record) for record in records]

    def save(self, account: Account) -> None:
        user = self.session.get(UserRecord, account.id)
        if user is None:
            raise ValueError("Account no longer exists")
        user.approved = account.approved
        user.locked = account.locked
        user.password_hash = account.password_hash
        self.session.commit()

    def delete(self, account: Account) -> None:
        user = self.session.get(UserRecord, account.id)
        if user is None:
            raise ValueError("Account no longer exists")
        self.session.execute(delete(PriceRecord).where(PriceRecord.store_id == account.id))
        self.session.execute(delete(DiscountRecord).where(DiscountRecord.store_id == account.id))
        self.session.delete(user)
        self.session.commit()

    def active_admin_count(self) -> int:
        return self.session.scalar(
            select(func.count(UserRecord.id)).where(
                UserRecord.role == "admin", UserRecord.locked.is_(False)
            )
        ) or 0


class PriceRepository:
    def __init__(self, session: Session):
        self.session = session

    def add_price(
        self,
        store_id: int,
        barcode_type: str,
        gtin: str,
        price: Decimal,
        recorded_at: datetime,
    ) -> None:
        self.session.add(
            PriceRecord(
                store_id=store_id,
                barcode_type=barcode_type,
                gtin=gtin,
                price=price,
                recorded_at=recorded_at,
            )
        )
        self.session.commit()

    def add_price_batch(
        self, store_id: int, records: list[dict[str, object]]
    ) -> None:
        self.session.add_all(
            [PriceRecord(store_id=store_id, **record) for record in records]
        )
        self.session.commit()

    def add_discount(
        self,
        store_id: int,
        barcode_type: str,
        gtin: str,
        percentage: Decimal,
        starts_at: datetime,
        ends_at: datetime | None,
    ) -> Discount:
        discount = DiscountRecord(
            store_id=store_id,
            barcode_type=barcode_type,
            gtin=gtin,
            percentage=percentage,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        self.session.add(discount)
        self.session.commit()
        return Discount(
            id=discount.id,
            store_id=discount.store_id,
            barcode_type=discount.barcode_type,
            gtin=discount.gtin,
            percentage=discount.percentage,
            starts_at=discount.starts_at,
            ends_at=discount.ends_at,
        )

    def record_shopper_search(
        self,
        shopper_id: int,
        barcode_type: str,
        gtin: str,
        price: Decimal,
        latitude: float,
        longitude: float,
        searched_at: datetime,
    ) -> None:
        self.session.add(
            ShopperSearchRecord(
                shopper_id=shopper_id,
                barcode_type=barcode_type,
                gtin=gtin,
                price=price,
                latitude=latitude,
                longitude=longitude,
                searched_at=searched_at,
            )
        )
        self.session.commit()

    def nearby_product_prices(
        self, barcode_type: str, gtin: str
    ) -> list[StoreQuote]:
        latest_timestamp_per_store = (
            select(
                PriceRecord.store_id,
                func.max(PriceRecord.recorded_at).label("latest"),
            )
            .where(PriceRecord.barcode_type == barcode_type, PriceRecord.gtin == gtin)
            .group_by(PriceRecord.store_id)
            .subquery()
        )
        latest_price_per_store = (
            select(func.max(PriceRecord.id).label("price_id"))
            .join(
                latest_timestamp_per_store,
                (PriceRecord.store_id == latest_timestamp_per_store.c.store_id)
                & (PriceRecord.recorded_at == latest_timestamp_per_store.c.latest),
            )
            .where(PriceRecord.barcode_type == barcode_type, PriceRecord.gtin == gtin)
            .group_by(PriceRecord.store_id)
            .subquery()
        )
        statement = (
            select(PriceRecord, UserRecord)
            .join(
                latest_price_per_store,
                PriceRecord.id == latest_price_per_store.c.price_id,
            )
            .join(UserRecord, UserRecord.id == PriceRecord.store_id)
            .where(
                PriceRecord.barcode_type == barcode_type,
                PriceRecord.gtin == gtin,
                UserRecord.role == "store",
                UserRecord.approved.is_(True),
                UserRecord.locked.is_(False),
            )
        )
        rows = list(self.session.execute(statement))
        now = datetime.now(timezone.utc)
        store_ids = {store.id for _, store in rows}
        discounts = self.session.scalars(
            select(DiscountRecord)
            .where(
                DiscountRecord.store_id.in_(store_ids),
                DiscountRecord.barcode_type == barcode_type,
                DiscountRecord.gtin == gtin,
                DiscountRecord.active.is_(True),
                DiscountRecord.starts_at <= now,
                (DiscountRecord.ends_at.is_(None)) | (DiscountRecord.ends_at > now),
            )
            .order_by(DiscountRecord.percentage.desc())
        )
        discount_by_store: dict[int, DiscountRecord] = {}
        for discount in discounts:
            discount_by_store.setdefault(discount.store_id, discount)

        result = []
        for price, store in rows:
            discount = discount_by_store.get(store.id)
            result.append(
                StoreQuote(
                    price=Price(
                        id=price.id,
                        store_id=price.store_id,
                        barcode_type=price.barcode_type,
                        gtin=price.gtin,
                        amount=price.price,
                        recorded_at=(
                            price.recorded_at
                            if price.recorded_at.tzinfo
                            else price.recorded_at.replace(tzinfo=timezone.utc)
                        ),
                    ),
                    store=UserRepository._account(store),
                    discount=(
                        Discount(
                            id=discount.id,
                            store_id=discount.store_id,
                            barcode_type=discount.barcode_type,
                            gtin=discount.gtin,
                            percentage=discount.percentage,
                            starts_at=discount.starts_at,
                            ends_at=discount.ends_at,
                        )
                        if discount
                        else None
                    ),
                )
            )
        return result


class AuditRepository:
    def __init__(self, session: Session):
        self.session = session

    def record(self, actor_id: int, action: str, target_user_id: int | None, details: str) -> None:
        self.session.add(
            AuditLogRecord(
                actor_id=actor_id,
                action=action,
                target_user_id=target_user_id,
                details=details,
            )
        )
        self.session.commit()

    def list_all(self) -> list[AuditEvent]:
        records = self.session.scalars(
            select(AuditLogRecord).order_by(AuditLogRecord.occurred_at.desc())
        )
        return [
            AuditEvent(
                record.id,
                record.actor_id,
                record.action,
                record.target_user_id,
                record.details,
                (
                    record.occurred_at
                    if record.occurred_at.tzinfo
                    else record.occurred_at.replace(tzinfo=timezone.utc)
                ),
            )
            for record in records
        ]
