from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models.customer import Customer
from app.models.bank import BankAccount
from app.repositories.customer import CustomerRepository
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.models.ledger import CustomerLedgerEntry
from app.models.payment import CustomerPayment
from app.models.returns import SaleReturn
from app.models.sales import Sale


class CustomerService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = CustomerRepository(db)

    def list_customers(self, search: str = "", status: str = "", page: int = 1, page_size: int = 50, shop_id: str | None = None):
        return self.repo.list(search=search, status=status, page=page, page_size=page_size, shop_id=shop_id)

    def get_customer(self, customer_id: str, shop_id: str | None = None) -> Customer:
        customer = self.repo.get_by_id(customer_id, shop_id=shop_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        return customer

    def create_customer(self, payload: CustomerCreate, shop_id: str | None = None) -> Customer:
        if not payload.name or not payload.name.strip():
            raise ValidationError("Customer name is required")
        return self.repo.create(
            name=payload.name,
            phone=payload.phone,
            address=payload.address,
            opening_balance=payload.opening_balance or 0,
            status=payload.status or "Active",
            shop_id=shop_id,
        )

    def update_customer(self, customer_id: str, payload: CustomerUpdate, shop_id: str | None = None) -> Customer:
        data = payload.model_dump(exclude_unset=True)
        if payload.name is not None and not payload.name.strip():
            raise ValidationError("Customer name is required")
        return self.repo.update(customer_id, data, shop_id=shop_id)

    def deactivate_customer(self, customer_id: str, shop_id: str | None = None) -> Customer:
        return self.repo.deactivate(customer_id, shop_id=shop_id)

    def get_ledger(self, customer_id: str, from_date: str | None = None, to_date: str | None = None, shop_id: str | None = None):
        self.get_customer(customer_id, shop_id=shop_id)
        entries = self.repo.ledger_entries(customer_id, from_date, to_date, shop_id=shop_id)
        return {
            "customer_id": customer_id,
            "balance": str(self.repo.get_balance(customer_id, shop_id=shop_id)),
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

    def get_installments(self, customer_id: str, shop_id: str | None = None):
        customer = self.get_customer(customer_id, shop_id=shop_id)
        balance = self.repo.get_balance(customer_id, shop_id=shop_id)
        sales_total = self.db.scalar(
            select(func.sum(Sale.total)).where(
                Sale.customer_id == customer_id,
                Sale.shop_id == customer.shop_id,
                Sale.sale_type == "installment",
                Sale.status == "completed",
            )
        ) or Decimal("0.00")
        payments_total = self.db.scalar(
            select(func.sum(CustomerPayment.amount)).where(
                CustomerPayment.customer_id == customer_id,
                CustomerPayment.shop_id == customer.shop_id,
                CustomerPayment.status == "completed",
            )
        ) or Decimal("0.00")
        returns_total = self.db.scalar(
            select(func.sum(SaleReturn.amount)).where(
                SaleReturn.customer_id == customer_id,
                SaleReturn.shop_id == customer.shop_id,
                SaleReturn.status == "completed",
            )
        ) or Decimal("0.00")
        payment_details = {
            payment.id: payment
            for payment in self.db.scalars(
                select(CustomerPayment).where(CustomerPayment.customer_id == customer_id, CustomerPayment.shop_id == customer.shop_id)
            ).all()
        }
        sale_payments = {
            payment.sale_id: payment
            for payment in payment_details.values()
            if payment.sale_id
        }
        sale_invoices = {
            sale.id: sale.invoice_number
            for sale in self.db.scalars(select(Sale).where(Sale.customer_id == customer_id, Sale.shop_id == customer.shop_id)).all()
        }
        invoice_payments = {
            payment.reference: payment
            for payment in payment_details.values()
            if payment.reference
        }
        bank_names = {
            bank.id: bank.name
            for bank in self.db.scalars(select(BankAccount)).all()
        }
        entries = []
        for entry in self.repo.ledger_entries(customer_id, shop_id=customer.shop_id):
            payment = (
                payment_details.get(entry.reference_id)
                or sale_payments.get(entry.reference_id)
                or invoice_payments.get(sale_invoices.get(entry.reference_id))
            )
            entries.append({
                "id": entry.id,
                "date": entry.entry_date.isoformat() if entry.entry_date else None,
                "type": "Sale" if entry.reference_type == "sale" else "Payment" if entry.reference_type == "customer_payment" else "Return" if entry.reference_type == "sale_return" else "Adjustment",
                "reference": entry.reference_id or "",
                "total": entry.sale_amount,
                "paid_or_return": entry.payment_amount or entry.return_amount,
                "remaining": entry.balance_after,
                "note": entry.description,
                "payment_method": payment.payment_method if payment else None,
                "bank_name": bank_names.get(payment.bank_account_id) if payment and payment.bank_account_id else None,
            })
        remaining = Decimal(customer.opening_balance or 0) + sales_total - payments_total - returns_total
        return {
            "customer_id": customer_id,
            "customer": customer,
            "total_credit_sales": sales_total,
            "total_payments": payments_total,
            "total_returns": returns_total,
            "remaining": remaining,
            "status_label": "Customer Credit" if remaining < 0 else "Paid" if remaining <= Decimal("0.01") else "Partial" if payments_total > 0 else "Unpaid",
            "entries": entries,
        }
