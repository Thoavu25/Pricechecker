from fastapi import APIRouter, Depends

from app.api.dependencies import get_price_comparison_service, require_roles
from app.api.schemas import PriceComparisonRequest, PriceComparisonResponse
from app.application.services import PriceComparisonService
from app.domain.entities import Account

router = APIRouter(prefix="/prices", tags=["Price comparison"])


@router.post("/compare", response_model=PriceComparisonResponse)
def compare_prices(
    body: PriceComparisonRequest,
    shopper: Account = Depends(require_roles("shopper")),
    service: PriceComparisonService = Depends(get_price_comparison_service),
):
    offers = service.compare(
        shopper=shopper,
        barcode_type=body.barcode_type,
        gtin=body.gtin,
        reference_price=body.price,
        latitude=body.latitude,
        longitude=body.longitude,
        searched_at=body.timestamp,
        radius_km=body.nearby_km,
    )
    return PriceComparisonResponse(
        barcode_type=body.barcode_type,
        gtin=body.gtin,
        nearby_km=body.nearby_km,
        offers=offers,
    )
