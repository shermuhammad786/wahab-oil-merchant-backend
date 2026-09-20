from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models.customer import Customer
from app.repositories.customer import CustomerRepository
from app.schemas.customer import CustomerCreate, CustomerUpdate


class CustomerService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = CustomerRepository(db)

    def list_customers(self, search: str = "", status: str = "", page: int = 1, page_size: int = 50):
        return self.repo.list(search=search, status=status, page=page, page_size=page_size)

    def get_customer(self, customer_id: str) -> Customer:
        customer = self.repo.get_by_id(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        return customer

    def create_customer(self, payload: CustomerCreate) -> Customer:
        if not payload.name or not payload.name.strip():
            raise ValidationError("Customer name is required")
        return self.repo.create(
            name=payload.name,
            phone=payload.phone,
            address=payload.address,
            opening_balance=payload.opening_balance or 0,
            status=payload.status or "Active",
        )

    def update_customer(self, customer_id: str, payload: CustomerUpdate) -> Customer:
        data = payload.model_dump(exclude_unset=True)
        if payload.name is not None and not payload.name.strip():
            raise ValidationError("Customer name is required")
        return self.repo.update(customer_id, data)

    def deactivate_customer(self, customer_id: str) -> Customer:
        return self.repo.deactivate(customer_id)

    def get_ledger(self, customer_id: str, from_date: str | None = None, to_date: str | None = None):
        self.get_customer(customer_id)
        entries = self.repo.ledger_entries(customer_id, from_date, to_date)
        return {
            "customer_id": customer_id,
            "balance": str(self.repo.get_balance(customer_id)),
            "entries": [
                {
                    "id": entry.id,
                    "entry_date": entry.entry_date.isoformat() if entry.entry_date else None,
                    "description": entry.description,
                    "sale_amount": str(entry.sale_amount),
                    "payment_amount": str(entry.payment_amount),
                    "return_amount": str(entry.return_amount),
                    "balance_after": str(entry.balance_after),
                    "reference_type": entry.reference_type,
                    "reference_id": entry.reference_id,
                }
                for entry in entries
            ],
        }

    def get_installments(self, customer_id: str):
        self.get_customer(customer_id)
        balance = self.repo.get_balance(customer_id)
        return {
            "customer_id": customer_id,
            "previous_remaining": "0.00",
            "current_bill": "0.00",
            "received_amount": "0.00",
            "current_remaining": "0.00",
            "grand_total_remaining": str(balance),
        }
