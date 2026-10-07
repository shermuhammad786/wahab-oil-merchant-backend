from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.security import get_current_user
from app.db.session import get_db
from app.repositories.supplier import SupplierRepository
from app.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate
from app.services.supplier import SupplierService

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("", response_model=list[SupplierRead])
def list_suppliers(
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[SupplierRead]:
    items = SupplierRepository(db).list(search=search or "", status=status or "", page=page, page_size=page_size, shop_id=current_user.shop_id)
    service = SupplierService(db)
    return [SupplierRead.model_validate(item).model_copy(update={"current_balance": service.repo.get_balance(item.id, shop_id=current_user.shop_id)}) for item in items]


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> SupplierRead:
    service = SupplierService(db)
    supplier = service.create_supplier(payload, shop_id=current_user.shop_id)
    return SupplierRead.model_validate(supplier).model_copy(update={"current_balance": service.repo.get_balance(supplier.id, shop_id=current_user.shop_id)})


@router.get("/{supplier_id}", response_model=SupplierRead)
def get_supplier(supplier_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> SupplierRead:
    try:
        service = SupplierService(db)
        supplier = service.get_supplier(supplier_id, shop_id=current_user.shop_id)
        return SupplierRead.model_validate(supplier).model_copy(update={"current_balance": service.repo.get_balance(supplier.id, shop_id=current_user.shop_id)})
    except NotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.put("/{supplier_id}", response_model=SupplierRead)
def update_supplier(supplier_id: str, payload: SupplierUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> SupplierRead:
    try:
        service = SupplierService(db)
        supplier = service.update_supplier(supplier_id, payload, shop_id=current_user.shop_id)
        return SupplierRead.model_validate(supplier).model_copy(update={"current_balance": service.repo.get_balance(supplier.id, shop_id=current_user.shop_id)})
    except NotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/{supplier_id}/deactivate", response_model=SupplierRead)
def deactivate_supplier(supplier_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> SupplierRead:
    try:
        service = SupplierService(db)
        supplier = service.deactivate_supplier(supplier_id, shop_id=current_user.shop_id)
        return SupplierRead.model_validate(supplier).model_copy(update={"current_balance": service.repo.get_balance(supplier.id, shop_id=current_user.shop_id)})
    except NotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/{supplier_id}/ledger")
def get_supplier_ledger(
    supplier_id: str,
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        return SupplierService(db).get_ledger(supplier_id, from_date, to_date, shop_id=current_user.shop_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/{supplier_id}/installments")
def get_supplier_installments(supplier_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    try:
        return SupplierService(db).get_installments(supplier_id, shop_id=current_user.shop_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
