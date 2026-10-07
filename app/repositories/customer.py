from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.money import ZERO_MONEY, money, to_decimal
from app.models.customer import Customer
from app.models.ledger import CustomerLedgerEntry
from app.models.payment import CustomerPayment
from app.models.sales import Sale
from app.models.returns import SaleReturn


class CustomerRepository:
    def __init__(self, db: Session):
        self.db = db

    def _shop_id(self, shop_id: str | None) -> str:
        resolved = shop_id or self.db.info.get("shop_id")
        if not resolved:
            raise ValidationError("Authenticated shop context is required")
        return resolved

    def get_by_id(self, customer_id: str, shop_id: str | None = None) -> Customer | None:
        shop_id = self._shop_id(shop_id)
        return self.db.scalar(select(Customer).where(Customer.id == customer_id, Customer.shop_id == shop_id))

    def list(self, search: str = "", status: str = "", page: int = 1, page_size: int = 50, shop_id: str | None = None) -> list[Customer]:
        shop_id = self._shop_id(shop_id)
        query = select(Customer).where(Customer.shop_id == shop_id)
        if search:
            q = f"%{search}%"
            query = query.where(or_(Customer.name.ilike(q), Customer.phone.ilike(q), Customer.id.ilike(q)))
        if status and status != "All":
            query = query.where(Customer.status == status)
        query = query.order_by(Customer.name.asc())
        return self.db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()

    def count(self, search: str = "", status: str = "", shop_id: str | None = None) -> int:
        shop_id = self._shop_id(shop_id)
        query = select(func.count(Customer.id)).where(Customer.shop_id == shop_id)
        if search:
            q = f"%{search}%"
            query = query.where(or_(Customer.name.ilike(q), Customer.phone.ilike(q), Customer.id.ilike(q)))
        if status and status != "All":
            query = query.where(Customer.status == status)
        return self.db.scalar(query) or 0

    def create(self, *, name: str, phone: str | None = None, address: str | None = None, opening_balance: Decimal = ZERO_MONEY, status: str = "Active", shop_id: str | None = None) -> Customer:
        shop_id = self._shop_id(shop_id)
        customer = Customer(
            id=f"CUS-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
            shop_id=shop_id,
            name=name.strip(),
            phone=phone.strip() if phone else None,
            address=address.strip() if address else None,
            opening_balance=money(opening_balance),
            status=status,
        )
        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def update(self, customer_id: str, payload: dict, shop_id: str | None = None) -> Customer:
        customer = self.get_by_id(customer_id, shop_id=shop_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        for key, value in payload.items():
            if value is not None:
                setattr(customer, key, value)
        customer.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def deactivate(self, customer_id: str, shop_id: str | None = None) -> Customer:
        customer = self.get_by_id(customer_id, shop_id=shop_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        customer.status = "Inactive"
        customer.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def get_balance(self, customer_id: str, shop_id: str | None = None) -> Decimal:
        customer = self.get_by_id(customer_id, shop_id=shop_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        sales_total = to_decimal(self.db.scalar(select(func.sum(Sale.total)).where(Sale.customer_id == customer_id, Sale.shop_id == customer.shop_id, Sale.sale_type == "installment", Sale.status == "completed")))
        payments_total = to_decimal(self.db.scalar(select(func.sum(CustomerPayment.amount)).where(CustomerPayment.customer_id == customer_id, CustomerPayment.shop_id == customer.shop_id, CustomerPayment.status == "completed")))
        returns_total = to_decimal(self.db.scalar(select(func.sum(SaleReturn.amount)).where(SaleReturn.customer_id == customer_id, SaleReturn.shop_id == customer.shop_id, SaleReturn.status == "completed")))
        return money(to_decimal(customer.opening_balance) + sales_total - payments_total - returns_total)

    def ledger_entries(self, customer_id: str, from_date: str | None = None, to_date: str | None = None, shop_id: str | None = None) -> list[CustomerLedgerEntry]:
        shop_id = self._shop_id(shop_id)
        query = self.db.query(CustomerLedgerEntry).filter(CustomerLedgerEntry.customer_id == customer_id, CustomerLedgerEntry.shop_id == shop_id)
        if from_date:
            query = query.filter(CustomerLedgerEntry.entry_date >= from_date)
        if to_date:
            query = query.filter(CustomerLedgerEntry.entry_date <= to_date)
        return query.order_by(CustomerLedgerEntry.entry_date.asc(), CustomerLedgerEntry.created_at.asc()).all()
