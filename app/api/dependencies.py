from typing import Annotated, Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import AUTO_APPROVE_STORES
from app.application.services import (
    AdministrationService,
    AuthenticationService,
    PriceComparisonService,
    StorePriceService,
)
from app.domain.entities import Account
from app.domain.errors import ForbiddenError, UnauthorizedError
from app.domain.pricing import RelativePriceLabelStrategy
from app.infrastructure.database import get_session
from app.infrastructure.jwt_tokens import JwtTokenService
from app.infrastructure.passwords import hash_password, verify_password
from app.infrastructure.repositories import AuditRepository, PriceRepository, UserRepository

bearer = HTTPBearer(auto_error=False)


class PasswordAdapter:
    hash = staticmethod(hash_password)
    verify = staticmethod(verify_password)


def get_authentication_service(
    session: Annotated[Session, Depends(get_session)],
) -> AuthenticationService:
    return AuthenticationService(
        UserRepository(session),
        PasswordAdapter(),
        JwtTokenService(),
        auto_approve_stores=AUTO_APPROVE_STORES,
    )


def get_current_account(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    service: Annotated[AuthenticationService, Depends(get_authentication_service)],
) -> Account:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in first",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        account = service.authenticate(credentials.credentials)
        request.state.user_id = account.id
        return account
    except UnauthorizedError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    except ForbiddenError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error


def require_roles(*roles: str) -> Callable:
    def role_dependency(
        account: Annotated[Account, Depends(get_current_account)],
    ) -> Account:
        if account.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return account

    return role_dependency


def get_store_price_service(
    session: Annotated[Session, Depends(get_session)],
) -> StorePriceService:
    return StorePriceService(PriceRepository(session))


def get_price_comparison_service(
    session: Annotated[Session, Depends(get_session)],
) -> PriceComparisonService:
    return PriceComparisonService(PriceRepository(session), RelativePriceLabelStrategy())


def get_administration_service(
    session: Annotated[Session, Depends(get_session)],
) -> AdministrationService:
    auth = AuthenticationService(
        UserRepository(session),
        PasswordAdapter(),
        JwtTokenService(),
        auto_approve_stores=AUTO_APPROVE_STORES,
    )
    return AdministrationService(UserRepository(session), AuditRepository(session), auth)
