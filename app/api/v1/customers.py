from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.customer import Customer
from app.models.ledger import CustomerLedgerEntry
from app.models.payment import CustomerPayment
from app.models.sales import Sale
from app.models.returns import SaleReturn
from app.repositories.customer import CustomerRepository
from app.schemas.customer import CustomerCreate, CustomerRead, CustomerUpdate
from app.services.customer import CustomerService

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerRead])
def list_customers(
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[CustomerRead]:
    repo = CustomerRepository(db)
    items = repo.list(search=search or "", status=status or "", page=page, page_size=page_size)
    return [CustomerRead.model_validate(item) for item in items]


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(payload: CustomerCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> CustomerRead:
    service = CustomerService(db)
    return CustomerRead.model_validate(service.create_customer(payload))


@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> CustomerRead:
    try:
        return CustomerRead.model_validate(CustomerService(db).get_customer(customer_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.put("/{customer_id}", response_model=CustomerRead)
def update_customer(customer_id: str, payload: CustomerUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> CustomerRead:
    try:
        return CustomerRead.model_validate(CustomerService(db).update_customer(customer_id, payload))
    except NotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/{customer_id}/deactivate", response_model=CustomerRead)
def deactivate_customer(customer_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)) -> CustomerRead:
    try:
        return CustomerRead.model_validate(CustomerService(db).deactivate_customer(customer_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/{customer_id}/ledger")
def get_customer_ledger(
    customer_id: str,
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        return CustomerService(db).get_ledger(customer_id, from_date, to_date)
    except NotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/{customer_id}/installments")
def get_customer_installments(customer_id: str, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    try:
        return CustomerService(db).get_installments(customer_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
