from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_authentication_service
from app.api.schemas import (
    AccountResponse,
    LoginRequest,
    ShopperRegistration,
    StoreRegistration,
    TokenResponse,
)
from app.application.services import AuthenticationService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register/shopper", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def register_shopper(
    body: ShopperRegistration,
    service: AuthenticationService = Depends(get_authentication_service),
):
    account = service.register_shopper(body.username, body.password)
    return AccountResponse.from_account(account)


@router.post("/register/store", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def register_store(
    body: StoreRegistration,
    service: AuthenticationService = Depends(get_authentication_service),
):
    account = service.register_store(
        body.username, body.password, body.store_name, body.latitude, body.longitude
    )
    return AccountResponse.from_account(account)


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    service: AuthenticationService = Depends(get_authentication_service),
):
    token, account = service.login(body.username, body.password)
    return TokenResponse(access_token=token, role=account.role)
