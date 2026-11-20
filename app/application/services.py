from datetime import datetime
from decimal import Decimal
from math import asin, cos, radians, sin, sqrt

from app.application.ports import (
    AuditRepository,
    PasswordHasher,
    PriceLabelStrategy,
    PriceRepository,
    TokenService,
    UserRepository,
)
from app.domain.entities import Account
from app.domain.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)


class AuthenticationService:
    def __init__(
        self,
        users: UserRepository,
        passwords: PasswordHasher,
        tokens: TokenService,
        auto_approve_stores: bool = False,
    ):
        self.users = users
        self.passwords = passwords
        self.tokens = tokens
        self.auto_approve_stores = auto_approve_stores

    def register_shopper(self, username: str, password: str) -> Account:
        return self._register(username, password, "shopper", approved=True)

    def register_store(
        self,
        username: str,
        password: str,
        store_name: str,
        latitude: float,
        longitude: float,
    ) -> Account:
        return self._register(
            username,
            password,
            "store",
            store_name=store_name,
            latitude=latitude,
            longitude=longitude,
            approved=self.auto_approve_stores,
        )

    def create_admin(self, username: str, password: str) -> Account:
        return self._register(username, password, "admin", approved=True)

    def _register(
        self,
        username: str,
        password: str,
        role: str,
        store_name: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        approved: bool = False,
    ) -> Account:
        if self.users.get_by_username(username) is not None:
            raise ConflictError("Username is already registered")
        return self.users.add(
            Account(
                id=0,
                username=username,
                password_hash=self.passwords.hash(password),
                role=role,
                store_name=store_name,
                latitude=latitude,
                longitude=longitude,
                approved=approved,
            )
        )

    def login(self, username: str, password: str) -> tuple[str, Account]:
        account = self.users.get_by_username(username)
        if account is None or not self.passwords.verify(password, account.password_hash):
            raise UnauthorizedError("Invalid username or password")
        if account.locked:
            raise ForbiddenError("Account is locked")
        if account.role == "store" and not account.approved:
            raise ForbiddenError("Store account is awaiting admin approval")
        return self.tokens.create(account.id, account.role), account

    def authenticate(self, token: str) -> Account:
        claims = self.tokens.read_claims(token)
        try:
            account_id = int(claims["sub"])
        except (KeyError, ValueError, TypeError) as error:
            raise UnauthorizedError("Invalid token") from error
        account = self.users.get(account_id)
        if account is None or account.locked or account.role != claims.get("role"):
            raise UnauthorizedError("Invalid or inactive account")
        if account.role == "store" and not account.approved:
            raise ForbiddenError("Store account is awaiting admin approval")
        return account


class AdministrationService:
    def __init__(
        self,
        users: UserRepository,
        audit: AuditRepository,
        authentication: AuthenticationService,
    ):
        self.users = users
        self.audit = audit
        self.authentication = authentication

    def pending_stores(self, actor_id: int) -> list[Account]:
        self.audit.record(actor_id, "list_pending_stores", None, "")
        return self.users.pending_stores()

    def stores(self, actor_id: int) -> list[Account]:
        self.audit.record(actor_id, "list_stores", None, "")
        return self.users.stores()

    def approve_store(self, actor_id: int, store_id: int) -> Account:
        account = self._store(store_id)
        account.approved = True
        self.users.save(account)
        self.audit.record(actor_id, "approve_store", store_id, account.username)
        return account

    def set_locked(self, actor_id: int, store_id: int, locked: bool) -> Account:
        account = self._store(store_id)
        account.locked = locked
        self.users.save(account)
        action = "lock_store" if locked else "unlock_store"
        self.audit.record(actor_id, action, store_id, account.username)
        return account

    def remove_store(self, actor_id: int, store_id: int) -> None:
        account = self._store(store_id)
        self.users.delete(account)
        self.audit.record(actor_id, "remove_store", store_id, account.username)

    def create_admin(self, actor_id: int, username: str, password: str) -> Account:
        account = self.authentication.create_admin(username, password)
        self.audit.record(actor_id, "create_admin", account.id, account.username)
        return account

    def audit_logs(self, actor_id: int):
        self.audit.record(actor_id, "view_audit_logs", None, "")
        return self.audit.list_all()

    def _store(self, store_id: int) -> Account:
        account = self.users.get(store_id)
        if account is None or account.role != "store":
            raise NotFoundError("Store user was not found")
        return account


class StorePriceService:
    def __init__(self, prices: PriceRepository):
        self.prices = prices

    def add_price(
        self,
        store_id: int,
        barcode_type: str,
        gtin: str,
        price: Decimal,
        recorded_at: datetime,
    ) -> None:
        self.prices.add_price(store_id, barcode_type, gtin, price, recorded_at)

    def add_batch(self, store_id: int, records: list[dict]) -> None:
        self.prices.add_price_batch(store_id, records)

    def add_discount(
        self,
        store_id: int,
        barcode_type: str,
        gtin: str,
        percentage: Decimal,
        starts_at: datetime,
        ends_at: datetime | None,
    ):
        return self.prices.add_discount(
            store_id, barcode_type, gtin, percentage, starts_at, ends_at
        )


class PriceComparisonService:
    def __init__(self, prices: PriceRepository, labels: PriceLabelStrategy):
        self.prices = prices
        self.labels = labels

    def compare(
        self,
        shopper: Account,
        barcode_type: str,
        gtin: str,
        reference_price: Decimal,
        latitude: float,
        longitude: float,
        searched_at: datetime,
        radius_km: float,
    ) -> list[dict]:
        self.prices.record_shopper_search(
            shopper.id,
            barcode_type,
            gtin,
            reference_price,
            latitude,
            longitude,
            searched_at,
        )
        offers = []
        for quote in self.prices.nearby_product_prices(barcode_type, gtin):
            if quote.store.latitude is None or quote.store.longitude is None:
                continue
            distance = _distance_km(
                latitude, longitude, quote.store.latitude, quote.store.longitude
            )
            if distance > radius_km:
                continue
            discount_percent = (
                quote.discount.percentage if quote.discount else Decimal("0")
            )
            current_price = quote.price.amount * (
                Decimal("1") - discount_percent / Decimal("100")
            )
            offers.append(
                {
                    "store_id": quote.store.id,
                    "store_name": quote.store.store_name,
                    "latitude": quote.store.latitude,
                    "longitude": quote.store.longitude,
                    "distance_km": round(distance, 2),
                    "price": quote.price.amount,
                    "discount_percent": discount_percent,
                    "current_price": current_price.quantize(Decimal("0.01")),
                    "label": self.labels.label(current_price, reference_price),
                    "recorded_at": quote.price.recorded_at,
                }
            )
        offers.sort(key=lambda offer: offer["current_price"])
        return offers


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0088
    lat1_rad, lat2_rad = radians(lat1), radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    haversine = (
        sin(delta_lat / 2) ** 2
        + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    )
    return 2 * earth_radius_km * asin(sqrt(haversine))
