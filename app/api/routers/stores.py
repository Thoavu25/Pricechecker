from datetime import timezone
from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_store_price_service, require_roles
from app.api.schemas import AccountResponse, DiscountInput, PriceBatch, PriceInput
from app.application.services import StorePriceService
from app.domain.entities import Account

router = APIRouter(prefix="/stores", tags=["Store prices"])


@router.get("/me", response_model=AccountResponse)
def get_store_account(store: Account = Depends(require_roles("store"))):
    return AccountResponse.from_account(store)


@router.post("/prices", status_code=status.HTTP_201_CREATED)
def add_price(
    body: PriceInput,
    store: Account = Depends(require_roles("store")),
    service: StorePriceService = Depends(get_store_price_service),
):
    service.add_price(
        store.id, body.barcode_type, body.gtin, body.price,
        body.timestamp.astimezone(timezone.utc),
    )
    return {"saved": True}


@router.post("/prices/batch", status_code=status.HTTP_201_CREATED)
def add_price_batch(
    body: PriceBatch,
    store: Account = Depends(require_roles("store")),
    service: StorePriceService = Depends(get_store_price_service),
):
    records = [
        {
            "barcode_type": item.barcode_type,
            "gtin": item.gtin,
            "price": item.price,
            "recorded_at": item.timestamp.astimezone(timezone.utc),
        }
        for item in body.prices
    ]
    service.add_batch(store.id, records)
    return {"saved": len(records)}


@router.post("/discounts", status_code=status.HTTP_201_CREATED)
def add_discount(
    body: DiscountInput,
    store: Account = Depends(require_roles("store")),
    service: StorePriceService = Depends(get_store_price_service),
):
    discount = service.add_discount(
        store.id,
        body.barcode_type,
        body.gtin,
        body.percentage,
        body.starts_at.astimezone(timezone.utc),
        body.ends_at.astimezone(timezone.utc) if body.ends_at else None,
    )
    return {
        "id": discount.id,
        "barcode_type": discount.barcode_type,
        "gtin": discount.gtin,
        "percentage": discount.percentage,
        "starts_at": discount.starts_at,
        "ends_at": discount.ends_at,
        "app_users_only": True,
    }
