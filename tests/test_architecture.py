import ast
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.application.services import (
    AdministrationService,
    AuthenticationService,
    PriceComparisonService,
)
from app.domain.entities import Account, Price, StoreQuote
from app.domain.errors import ConflictError, ForbiddenError
from app.domain.pricing import PriceLabelStrategy, RelativePriceLabelStrategy


APP_ROOT = Path(__file__).parents[1] / "app"


def _imported_modules(source_file: Path) -> set[str]:
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_domain_layer_imports_only_itself_and_standard_library():
    domain_dir = APP_ROOT / "domain"
    violations = {
        f"{source_file.relative_to(APP_ROOT)} imports {module}"
        for source_file in domain_dir.glob("*.py")
        for module in _imported_modules(source_file)
        if module == "app" or module.startswith("app.") and not module.startswith("app.domain")
    }
    assert not violations, "\n".join(sorted(violations))


def test_application_layer_does_not_import_outer_layers_or_configuration():
    application_dir = APP_ROOT / "application"
    forbidden_prefixes = ("app.api", "app.infrastructure", "app.config")
    violations = {
        f"{source_file.relative_to(APP_ROOT)} imports {module}"
        for source_file in application_dir.glob("*.py")
        for module in _imported_modules(source_file)
        if module == "app" or module.startswith(forbidden_prefixes)
    }
    assert not violations, "\n".join(sorted(violations))


class InMemoryUsers:
    def __init__(self):
        self.accounts: dict[int, Account] = {}

    def get_by_username(self, username: str) -> Account | None:
        return next(
            (account for account in self.accounts.values() if account.username == username),
            None,
        )

    def get(self, user_id: int) -> Account | None:
        return self.accounts.get(user_id)

    def add(self, account: Account) -> Account:
        if self.get_by_username(account.username):
            raise ConflictError("Username is already registered")
        account.id = len(self.accounts) + 1
        self.accounts[account.id] = account
        return account

    def save(self, account: Account) -> None:
        self.accounts[account.id] = account


class FakePasswords:
    def hash(self, password: str) -> str:
        return f"hashed:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return self.hash(password) == password_hash


class FakeTokens:
    def create(self, user_id: int, role: str) -> str:
        return f"{user_id}:{role}"

    def read_claims(self, token: str) -> dict:
        user_id, role = token.split(":")
        return {"sub": user_id, "role": role}


def test_application_authentication_use_cases_run_without_database():
    users = InMemoryUsers()
    service = AuthenticationService(users, FakePasswords(), FakeTokens())

    shopper = service.register_shopper("shopper", "password")
    assert shopper.approved
    assert shopper.password_hash == "hashed:password"
    with pytest.raises(ConflictError, match="already registered"):
        service.register_shopper("shopper", "another-password")

    store = service.register_store("store", "password", "Shop", 60.0, 22.0)
    assert not store.approved
    with pytest.raises(ForbiddenError, match="awaiting admin approval"):
        service.login("store", "password")

    token, account = service.login("shopper", "password")
    assert token == "1:shopper"
    assert service.authenticate(token) is account


def test_application_authentication_supports_injected_store_approval_policy():
    users = InMemoryUsers()
    service = AuthenticationService(
        users, FakePasswords(), FakeTokens(), auto_approve_stores=True
    )

    store = service.register_store("approved-store", "password", "Shop", 60.0, 22.0)
    assert store.approved
    assert service.login("approved-store", "password")[1] is store


def test_application_admin_use_case_records_approval_without_database():
    store = Account(1, "store", "hash", "store", approved=False)
    users = InMemoryUsers()
    users.accounts[store.id] = store

    class FakeAudit:
        def __init__(self):
            self.events = []

        def record(self, actor_id, action, target_user_id, details):
            self.events.append((actor_id, action, target_user_id, details))

    audit = FakeAudit()
    authentication = AuthenticationService(users, FakePasswords(), FakeTokens())
    service = AdministrationService(users, audit, authentication)

    result = service.approve_store(actor_id=9, store_id=store.id)

    assert result.approved
    assert audit.events == [(9, "approve_store", store.id, "store")]


def test_price_comparison_accepts_a_new_label_strategy_without_service_changes():
    shopper = Account(1, "shopper", "hash", "shopper", approved=True)
    store = Account(2, "store", "hash", "store", "Shop", 60.0, 22.0, approved=True)
    quote = StoreQuote(
        Price(
            1,
            store.id,
            "GTIN",
            "0123456789012",
            Decimal("8.00"),
            datetime(2026, 11, 16, tzinfo=timezone.utc),
        ),
        store,
        None,
    )

    class PriceRepositoryFake:
        def record_shopper_search(self, *args):
            pass

        def nearby_product_prices(self, barcode_type, gtin):
            return [quote]

    class FixedLabelStrategy(PriceLabelStrategy):
        def label(self, price: Decimal, reference_price: Decimal) -> str:
            return "Special offer"

    result = PriceComparisonService(
        PriceRepositoryFake(), FixedLabelStrategy()
    ).compare(
        shopper,
        "GTIN",
        "0123456789012",
        Decimal("10.00"),
        60.0,
        22.0,
        datetime(2026, 11, 16, tzinfo=timezone.utc),
        5,
    )

    assert result[0]["label"] == "Special offer"
    assert RelativePriceLabelStrategy().label(Decimal("8"), Decimal("10")) == "Very inexpensive"
