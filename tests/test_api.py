import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from statistics import quantiles

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api import dependencies
from app.api.dependencies import get_session
from app.application.services import PriceComparisonService
from app.domain.entities import Account, Discount, Price, StoreQuote
from app.domain.pricing import RelativePriceLabelStrategy
from app.infrastructure import database
from app.infrastructure.models import PriceRecord
from app.infrastructure.jwt_tokens import JwtTokenService
from app.infrastructure.passwords import hash_password, verify_password
from app.infrastructure.repositories import UserRepository
from app.main import app


@pytest.fixture
def api(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(dependencies, "AUTO_APPROVE_STORES", False)
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(database, "engine", test_engine)

    def override_session():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as client:
        with Session(test_engine) as session:
            UserRepository(session).add(
                Account(
                    id=0,
                    username="test-admin",
                    password_hash=hash_password("test-admin-password"),
                    role="admin",
                    approved=True,
                )
            )
        yield client, test_engine
    app.dependency_overrides.clear()
    test_engine.dispose()


def register_store(client: TestClient, username="store-one", name="Store One"):
    response = client.post(
        "/api/v1/auth/register/store",
        json={
            "username": username,
            "password": "store-password-123",
            "store_name": name,
            "latitude": 60.4518,
            "longitude": 22.2666,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_and_approve_store(client: TestClient, admin_token: str, username="store-one"):
    store_id = register_store(client, username)
    response = client.post(
        f"/api/v1/admin/stores/{store_id}/approve", headers=auth(admin_token)
    )
    assert response.status_code == 200
    return store_id, login(client, username, "store-password-123")


def test_passwords_are_hashed_and_verified():
    password_hash = hash_password("a-long-password")
    assert password_hash != "a-long-password"
    assert verify_password("a-long-password", password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_browser_frontend_is_served_by_the_backend(api):
    client, _ = api
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Nearwise" in response.text
    assert 'const API = "/api/v1"' in response.text
    assert '"/prices/compare"' in response.text
    assert "if (registration.approved)" in response.text
    assert "Inventory uploads are available to store accounts only" in response.text


def test_development_mode_can_register_and_use_store_without_admin(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(dependencies, "AUTO_APPROVE_STORES", True)
    registration = client.post(
        "/api/v1/auth/register/store",
        json={
            "username": "demo-store",
            "password": "demo-store-password",
            "store_name": "Demo Store",
            "latitude": 60.4518,
            "longitude": 22.2666,
        },
    )
    assert registration.status_code == 201
    assert registration.json()["approved"] is True

    token = login(client, "demo-store", "demo-store-password")
    response = client.get("/api/v1/stores/me", headers=auth(token))
    assert response.status_code == 200
    assert response.json()["approved"] is True


def test_store_approval_and_role_authorization(api):
    client, _ = api
    admin_token = login(client, "test-admin", "test-admin-password")
    store_id = register_store(client)
    pending_login = client.post(
        "/api/v1/auth/login",
        json={"username": "store-one", "password": "store-password-123"},
    )
    assert pending_login.status_code == 403

    approval = client.post(
        f"/api/v1/admin/stores/{store_id}/approve", headers=auth(admin_token)
    )
    assert approval.status_code == 200
    store_token = login(client, "store-one", "store-password-123")
    assert client.post(
        "/api/v1/stores/prices",
        headers=auth(login(client, "test-admin", "test-admin-password")),
        json={
            "barcode_type": "GTIN",
            "gtin": "0123456789012",
            "price": "12.00",
            "timestamp": "2026-11-16T08:00:00Z",
        },
    ).status_code == 403
    assert client.get("/api/v1/admin/stores", headers=auth(store_token)).status_code == 403
    assert client.get("/api/v1/admin/stores").status_code == 401


def test_wrong_roles_are_denied_across_admin_store_and_shopper_endpoints(api):
    client, _ = api
    admin_token = login(client, "test-admin", "test-admin-password")
    _, store_token = register_and_approve_store(client, admin_token)
    client.post(
        "/api/v1/auth/register/shopper",
        json={"username": "role-shopper", "password": "shopper-password-123"},
    )
    shopper_token = login(client, "role-shopper", "shopper-password-123")

    price_body = {
        "barcode_type": "GTIN",
        "gtin": "0123456789012",
        "price": "12.00",
        "timestamp": "2026-11-16T08:00:00Z",
    }
    comparison_body = {
        **price_body,
        "latitude": 60.45,
        "longitude": 22.27,
        "nearby_km": 10,
    }
    discount_body = {
        "barcode_type": "GTIN",
        "gtin": "0123456789012",
        "percentage": "5",
        "starts_at": "2026-11-16T08:00:00Z",
    }

    assert client.get("/api/v1/admin/stores", headers=auth(shopper_token)).status_code == 403
    assert client.post(
        "/api/v1/stores/prices", headers=auth(shopper_token), json=price_body
    ).status_code == 403
    assert client.post(
        "/api/v1/stores/discounts", headers=auth(shopper_token), json=discount_body
    ).status_code == 403
    assert client.post(
        "/api/v1/prices/compare", headers=auth(store_token), json=comparison_body
    ).status_code == 403
    assert client.post(
        "/api/v1/stores/prices", headers=auth(admin_token), json=price_body
    ).status_code == 403
    assert client.post(
        "/api/v1/prices/compare", headers=auth(admin_token), json=comparison_body
    ).status_code == 403


def test_store_prices_discount_and_shopper_comparison(api):
    client, _ = api
    admin_token = login(client, "test-admin", "test-admin-password")
    _, store_token = register_and_approve_store(client, admin_token)

    shopper_signup = client.post(
        "/api/v1/auth/register/shopper",
        json={"username": "shopper-one", "password": "shopper-password-123"},
    )
    assert shopper_signup.status_code == 201
    shopper_token = login(client, "shopper-one", "shopper-password-123")

    price = client.post(
        "/api/v1/stores/prices",
        headers=auth(store_token),
        json={
            "barcode_type": "EAN",
            "gtin": "0123456789012",
            "price": "20.00",
            "timestamp": "2026-11-16T08:00:00Z",
        },
    )
    assert price.status_code == 201
    discount = client.post(
        "/api/v1/stores/discounts",
        headers=auth(store_token),
        json={
            "barcode_type": "EAN",
            "gtin": "0123456789012",
            "percentage": "15",
            "starts_at": "2026-11-16T00:00:00Z",
        },
    )
    assert discount.status_code == 201
    assert discount.json()["app_users_only"] is True

    comparison = client.post(
        "/api/v1/prices/compare",
        headers=auth(shopper_token),
        json={
            "barcode_type": "EAN",
            "gtin": "0123456789012",
            "price": "20.00",
            "latitude": 60.452,
            "longitude": 22.267,
            "timestamp": "2026-11-16T08:30:00Z",
            "nearby_km": 10,
        },
    )
    assert comparison.status_code == 200, comparison.text
    offers = comparison.json()["offers"]
    assert len(offers) == 1
    assert offers[0]["current_price"] == "17.00"
    assert offers[0]["discount_percent"] == "15.00"
    assert offers[0]["label"] == "Inexpensive"
    assert offers[0]["distance_km"] < 1


def test_batch_prices_are_saved_in_one_request(api):
    client, _ = api
    admin_token = login(client, "test-admin", "test-admin-password")
    _, store_token = register_and_approve_store(client, admin_token)
    response = client.post(
        "/api/v1/stores/prices/batch",
        headers=auth(store_token),
        json={
            "prices": [
                {
                    "barcode_type": "GTIN",
                    "gtin": "0123456789012",
                    "price": "5.20",
                    "timestamp": "2026-11-16T08:00:00Z",
                },
                {
                    "barcode_type": "GTIN",
                    "gtin": "0123456789013",
                    "price": "6.30",
                    "timestamp": "2026-11-16T08:01:00Z",
                },
            ]
        },
    )
    assert response.status_code == 201
    assert response.json() == {"saved": 2}


def test_invalid_gtin_price_and_coordinates_are_rejected(api):
    client, _ = api
    shopper_token = login(
        client,
        client.post(
            "/api/v1/auth/register/shopper",
            json={"username": "shopper-invalid", "password": "shopper-password-123"},
        ).json()["username"],
        "shopper-password-123",
    )
    headers = auth(shopper_token)
    base = {
        "barcode_type": "GTIN",
        "gtin": "1234567890123",
        "price": "10.00",
        "latitude": 60.45,
        "longitude": 22.27,
        "timestamp": "2026-11-16T08:00:00Z",
    }
    for update in (
        {"gtin": "not-digits"},
        {"price": "0"},
        {"latitude": 95},
        {"longitude": 190},
    ):
        response = client.post(
            "/api/v1/prices/compare", headers=headers, json={**base, **update}
        )
        assert response.status_code == 422


def test_admin_actions_create_audit_entries_and_lock_store(api):
    client, _ = api
    admin_token = login(client, "test-admin", "test-admin-password")
    store_id = register_store(client)
    assert client.post(
        f"/api/v1/admin/stores/{store_id}/approve", headers=auth(admin_token)
    ).status_code == 200
    assert client.post(
        f"/api/v1/admin/stores/{store_id}/lock", headers=auth(admin_token)
    ).status_code == 200
    locked_login = client.post(
        "/api/v1/auth/login",
        json={"username": "store-one", "password": "store-password-123"},
    )
    assert locked_login.status_code == 403
    assert client.post(
        f"/api/v1/admin/stores/{store_id}/unlock", headers=auth(admin_token)
    ).status_code == 200
    logs = client.get("/api/v1/admin/audit-logs", headers=auth(admin_token))
    assert logs.status_code == 200
    assert {entry["action"] for entry in logs.json()} >= {
        "approve_store",
        "lock_store",
        "unlock_store",
    }


def test_admin_can_create_another_admin_and_remove_store(api):
    client, test_engine = api
    admin_token = login(client, "test-admin", "test-admin-password")
    new_admin = client.post(
        "/api/v1/admin/admins",
        headers=auth(admin_token),
        json={"username": "second-admin", "password": "second-admin-password"},
    )
    assert new_admin.status_code == 201
    assert login(client, "second-admin", "second-admin-password")

    store_id, store_token = register_and_approve_store(
        client, admin_token, username="store-to-remove"
    )
    price_response = client.post(
        "/api/v1/stores/prices",
        headers=auth(store_token),
        json={
            "barcode_type": "GTIN",
            "gtin": "0123456789012",
            "price": "8.00",
            "timestamp": "2026-11-16T08:00:00Z",
        },
    )
    assert price_response.status_code == 201

    removed = client.delete(
        f"/api/v1/admin/stores/{store_id}", headers=auth(admin_token)
    )
    assert removed.status_code == 204
    with Session(test_engine) as session:
        assert session.scalar(
            select(PriceRecord.id).where(PriceRecord.store_id == store_id)
        ) is None


def test_price_label_strategy_rules():
    strategy = RelativePriceLabelStrategy()
    assert strategy.label(Decimal("7"), Decimal("10")) == "Very inexpensive"
    assert strategy.label(Decimal("9"), Decimal("10")) == "Inexpensive"
    assert strategy.label(Decimal("10"), Decimal("10")) == "Similar price"
    assert strategy.label(Decimal("11"), Decimal("10")) == "Expensive"
    assert strategy.label(Decimal("13"), Decimal("10")) == "Very expensive"


def test_application_comparison_service_uses_ports_without_database():
    shopper = Account(1, "shopper", "hash", "shopper", approved=True)
    cheaper_store = Account(
        2, "store-a", "hash", "store", "Store A", 60.45, 22.26, True
    )
    distant_store = Account(
        3, "store-b", "hash", "store", "Store B", 61.00, 25.00, True
    )
    price = Price(
        1, 2, "GTIN", "0123456789012", Decimal("10.00"),
        datetime(2026, 11, 16, tzinfo=timezone.utc),
    )
    discount = Discount(
        1, 2, "GTIN", "0123456789012", Decimal("20"),
        datetime(2026, 11, 1, tzinfo=timezone.utc), None,
    )

    class PriceRepositoryFake:
        def record_shopper_search(self, *args):
            self.search = args

        def nearby_product_prices(self, barcode_type, gtin):
            return [
                StoreQuote(price, cheaper_store, discount),
                StoreQuote(
                    Price(
                        2, 3, "GTIN", "0123456789012", Decimal("8.00"),
                        datetime(2026, 11, 16, tzinfo=timezone.utc),
                    ),
                    distant_store,
                    None,
                ),
            ]

    repository = PriceRepositoryFake()
    service = PriceComparisonService(repository, RelativePriceLabelStrategy())
    offers = service.compare(
        shopper,
        "GTIN",
        "0123456789012",
        Decimal("10.00"),
        60.45,
        22.26,
        datetime(2026, 11, 16, tzinfo=timezone.utc),
        10,
    )
    assert len(offers) == 1
    assert offers[0]["current_price"] == Decimal("8.00")
    assert offers[0]["label"] == "Very inexpensive"
    assert repository.search[0] == shopper.id


def test_price_comparison_p95_with_ten_thousand_price_records(api):
    client, test_engine = api
    with Session(test_engine) as session:
        store = UserRepository(session).add(
            Account(
                id=0,
                username="load-store",
                password_hash=hash_password("load-store-password"),
                role="store",
                store_name="Load Test Store",
                latitude=60.4518,
                longitude=22.2666,
                approved=True,
            )
        )
        shopper = UserRepository(session).add(
            Account(
                id=0,
                username="load-shopper",
                password_hash=hash_password("load-shopper-password"),
                role="shopper",
                approved=True,
            )
        )
        timestamp = datetime(2026, 11, 16, tzinfo=timezone.utc)
        session.add_all(
            [
                PriceRecord(
                    store_id=store.id,
                    barcode_type="GTIN",
                    gtin=f"{item_id:014d}",
                    price=Decimal("10.00"),
                    recorded_at=timestamp + timedelta(seconds=item_id),
                )
                for item_id in range(10_000)
            ]
        )
        session.commit()

    token = JwtTokenService().create(shopper.id, "shopper")
    request_data = {
        "barcode_type": "GTIN",
        "gtin": f"{1:014d}",
        "price": "10.00",
        "latitude": 60.452,
        "longitude": 22.267,
        "timestamp": "2026-11-16T08:30:00Z",
        "nearby_km": 10,
    }
    durations = []
    for _ in range(100):
        started = time.perf_counter()
        response = client.post(
            "/api/v1/prices/compare",
            headers=auth(token),
            json=request_data,
        )
        durations.append(time.perf_counter() - started)
        assert response.status_code == 200

    p95 = quantiles(durations, n=20)[18]
    print(f"10,000-record comparison load test: p95={p95:.4f}s across 100 requests")
    assert p95 < 1.0, f"p95 was {p95:.3f}s for 10,000 stored prices"
