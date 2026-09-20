from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.models.supplier import Supplier
from app.repositories.supplier import SupplierRepository
from app.schemas.supplier import SupplierCreate, SupplierUpdate


class SupplierService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = SupplierRepository(db)

    def get_supplier(self, supplier_id: str) -> Supplier:
        supplier = self.repo.get_by_id(supplier_id)
        if supplier is None:
            raise NotFoundError("Supplier not found")
        return supplier

    def create_supplier(self, payload: SupplierCreate) -> Supplier:
        if not payload.name or not payload.name.strip():
            raise ValidationError("Supplier name is required")
        return self.repo.create(
            name=payload.name,
            phone=payload.phone,
            address=payload.address,
            opening_balance=payload.opening_balance or 0,
            status=payload.status or "Active",
        )

    def update_supplier(self, supplier_id: str, payload: SupplierUpdate) -> Supplier:
        data = payload.model_dump(exclude_unset=True)
        if payload.name is not None and not payload.name.strip():
            raise ValidationError("Supplier name is required")
        return self.repo.update(supplier_id, data)

    def deactivate_supplier(self, supplier_id: str) -> Supplier:
        return self.repo.deactivate(supplier_id)

    def get_ledger(self, supplier_id: str, from_date: str | None = None, to_date: str | None = None):
        self.get_supplier(supplier_id)
        entries = self.repo.ledger_entries(supplier_id, from_date, to_date)
        return {
            "supplier_id": supplier_id,
            "balance": str(self.repo.get_balance(supplier_id)),
            "entries": [
                {
                    "id": entry.id,
                    "entry_date": entry.entry_date.isoformat() if entry.entry_date else None,
                    "description": entry.description,
                    "purchase_amount": str(entry.purchase_amount),
                    "payment_amount": str(entry.payment_amount),
                    "return_amount": str(entry.return_amount),
                    "balance_after": str(entry.balance_after),
                    "reference_type": entry.reference_type,
                    "reference_id": entry.reference_id,
                }
                for entry in entries
            ],
        }

    def get_installments(self, supplier_id: str):
        self.get_supplier(supplier_id)
        balance = self.repo.get_balance(supplier_id)
        return {
            "supplier_id": supplier_id,
            "previous_remaining": "0.00",
            "current_stock_in_bill": "0.00",
            "paid_amount": "0.00",
            "current_remaining": "0.00",
            "grand_total_remaining": str(balance),
        }
