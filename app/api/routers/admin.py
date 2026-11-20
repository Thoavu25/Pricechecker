from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_administration_service, require_roles
from app.api.schemas import AccountResponse, AdminRegistration, AuditLogResponse
from app.application.services import AdministrationService
from app.domain.entities import Account

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get("/stores/pending", response_model=list[AccountResponse])
def pending_stores(
    admin: Account = Depends(require_roles("admin")),
    service: AdministrationService = Depends(get_administration_service),
):
    return [
        AccountResponse.from_account(account)
        for account in service.pending_stores(admin.id)
    ]


@router.get("/stores", response_model=list[AccountResponse])
def list_stores(
    admin: Account = Depends(require_roles("admin")),
    service: AdministrationService = Depends(get_administration_service),
):
    return [
        AccountResponse.from_account(account)
        for account in service.stores(admin.id)
    ]


@router.post("/stores/{store_id}/approve", response_model=AccountResponse)
def approve_store(
    store_id: int,
    admin: Account = Depends(require_roles("admin")),
    service: AdministrationService = Depends(get_administration_service),
):
    return AccountResponse.from_account(service.approve_store(admin.id, store_id))


@router.post("/stores/{store_id}/lock", response_model=AccountResponse)
def lock_store(
    store_id: int,
    admin: Account = Depends(require_roles("admin")),
    service: AdministrationService = Depends(get_administration_service),
):
    return AccountResponse.from_account(service.set_locked(admin.id, store_id, True))


@router.post("/stores/{store_id}/unlock", response_model=AccountResponse)
def unlock_store(
    store_id: int,
    admin: Account = Depends(require_roles("admin")),
    service: AdministrationService = Depends(get_administration_service),
):
    return AccountResponse.from_account(service.set_locked(admin.id, store_id, False))


@router.delete("/stores/{store_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_store(
    store_id: int,
    admin: Account = Depends(require_roles("admin")),
    service: AdministrationService = Depends(get_administration_service),
):
    service.remove_store(admin.id, store_id)


@router.post("/admins", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_admin(
    body: AdminRegistration,
    admin: Account = Depends(require_roles("admin")),
    service: AdministrationService = Depends(get_administration_service),
):
    return AccountResponse.from_account(
        service.create_admin(admin.id, body.username, body.password)
    )


@router.get("/audit-logs", response_model=list[AuditLogResponse])
def audit_logs(
    admin: Account = Depends(require_roles("admin")),
    service: AdministrationService = Depends(get_administration_service),
):
    return service.audit_logs(admin.id)
