from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.customer import Customer
from app.models.ledger import CustomerLedgerEntry
from app.models.payment import CustomerPayment
from app.models.sales import Sale
from app.models.returns import SaleReturn


class CustomerRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, customer_id: str) -> Customer | None:
        return self.db.get(Customer, customer_id)

    def list(self, search: str = "", status: str = "", page: int = 1, page_size: int = 50) -> list[Customer]:
        query = select(Customer)
        if search:
            q = f"%{search}%"
            query = query.where(or_(Customer.name.ilike(q), Customer.phone.ilike(q), Customer.id.ilike(q)))
        if status and status != "All":
            query = query.where(Customer.status == status)
        query = query.order_by(Customer.name.asc())
        return self.db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()

    def create(self, *, name: str, phone: str | None = None, address: str | None = None, opening_balance: Decimal | float = 0, status: str = "Active") -> Customer:
        customer = Customer(
            id=f"CUS-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
            name=name.strip(),
            phone=phone.strip() if phone else None,
            address=address.strip() if address else None,
            opening_balance=Decimal(str(opening_balance)),
            status=status,
        )
        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def update(self, customer_id: str, payload: dict) -> Customer:
        customer = self.get_by_id(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        for key, value in payload.items():
            if value is not None:
                setattr(customer, key, value)
        customer.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def deactivate(self, customer_id: str) -> Customer:
        customer = self.get_by_id(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        customer.status = "Inactive"
        customer.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def get_balance(self, customer_id: str) -> Decimal:
        customer = self.get_by_id(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        sales_total = self.db.query(Sale).filter(Sale.customer_id == customer_id, Sale.status == "completed").with_entities(__import__("sqlalchemy").func.coalesce(__import__("sqlalchemy").func.sum(Sale.total), 0)).scalar() or Decimal("0.00")
        payments_total = self.db.query(CustomerPayment).filter(CustomerPayment.customer_id == customer_id, CustomerPayment.status == "completed").with_entities(__import__("sqlalchemy").func.coalesce(__import__("sqlalchemy").func.sum(CustomerPayment.amount), 0)).scalar() or Decimal("0.00")
        returns_total = self.db.query(SaleReturn).filter(SaleReturn.customer_id == customer_id, SaleReturn.status == "completed").with_entities(__import__("sqlalchemy").func.coalesce(__import__("sqlalchemy").func.sum(SaleReturn.amount), 0)).scalar() or Decimal("0.00")
        return customer.opening_balance + sales_total - payments_total - returns_total

    def ledger_entries(self, customer_id: str, from_date: str | None = None, to_date: str | None = None) -> list[CustomerLedgerEntry]:
        query = self.db.query(CustomerLedgerEntry).filter(CustomerLedgerEntry.customer_id == customer_id)
        if from_date:
            query = query.filter(CustomerLedgerEntry.entry_date >= from_date)
        if to_date:
            query = query.filter(CustomerLedgerEntry.entry_date <= to_date)
        return query.order_by(CustomerLedgerEntry.entry_date.asc(), CustomerLedgerEntry.created_at.asc()).all()
