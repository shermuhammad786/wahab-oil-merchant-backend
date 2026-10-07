from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.core.money import ZERO_MONEY, money, to_decimal
from app.models.ledger import SupplierLedgerEntry
from app.models.payment import SupplierPayment
from app.models.purchases import Purchase
from app.models.returns import PurchaseReturn
from app.models.supplier import Supplier


class SupplierRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, supplier_id: str, shop_id: str | None = None) -> Supplier | None:
        query = select(Supplier).where(Supplier.id == supplier_id)
        if shop_id:
            query = query.where(Supplier.shop_id == shop_id)
        return self.db.scalar(query)

    def list(self, search: str = "", status: str = "", page: int = 1, page_size: int = 50, shop_id: str | None = None) -> list[Supplier]:
        query = self.db.query(Supplier)
        if shop_id:
            query = query.filter(Supplier.shop_id == shop_id)
        if search:
            q = f"%{search}%"
            query = query.filter(or_(Supplier.name.ilike(q), Supplier.phone.ilike(q), Supplier.id.ilike(q)))
        if status and status != "All":
            query = query.filter(Supplier.status == status)
        query = query.order_by(Supplier.name.asc())
        return query.offset((page - 1) * page_size).limit(page_size).all()

    def create(self, *, name: str, phone: str | None = None, address: str | None = None, opening_balance: Decimal = ZERO_MONEY, status: str = "Active", shop_id: str | None = None) -> Supplier:
        supplier = Supplier(
            id=f"SUP-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}",
            shop_id=shop_id,
            name=name.strip(),
            phone=phone.strip() if phone else None,
            address=address.strip() if address else None,
            opening_balance=money(opening_balance),
            status=status,
        )
        self.db.add(supplier)
        self.db.commit()
        self.db.refresh(supplier)
        return supplier

    def update(self, supplier_id: str, payload: dict, shop_id: str | None = None) -> Supplier:
        supplier = self.get_by_id(supplier_id, shop_id=shop_id)
        if supplier is None:
            raise NotFoundError("Supplier not found")
        for key, value in payload.items():
            if value is not None:
                setattr(supplier, key, value)
        supplier.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(supplier)
        return supplier

    def deactivate(self, supplier_id: str, shop_id: str | None = None) -> Supplier:
        supplier = self.get_by_id(supplier_id, shop_id=shop_id)
        if supplier is None:
            raise NotFoundError("Supplier not found")
        supplier.status = "Inactive"
        supplier.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(supplier)
        return supplier

    def get_balance(self, supplier_id: str, shop_id: str | None = None) -> Decimal:
        supplier = self.get_by_id(supplier_id, shop_id=shop_id)
        if supplier is None:
            raise NotFoundError("Supplier not found")
        purchases_total = to_decimal(self.db.scalar(select(func.sum(Purchase.total)).where(Purchase.supplier_id == supplier_id, Purchase.shop_id == supplier.shop_id, Purchase.status == "completed")))
        payments_total = to_decimal(self.db.scalar(select(func.sum(SupplierPayment.amount)).where(SupplierPayment.supplier_id == supplier_id, SupplierPayment.shop_id == supplier.shop_id, SupplierPayment.status == "completed")))
        returns_total = to_decimal(self.db.scalar(select(func.sum(PurchaseReturn.amount)).where(PurchaseReturn.supplier_id == supplier_id, PurchaseReturn.shop_id == supplier.shop_id, PurchaseReturn.status == "completed")))
        return money(to_decimal(supplier.opening_balance) + purchases_total - payments_total - returns_total)

    def ledger_entries(self, supplier_id: str, from_date: str | None = None, to_date: str | None = None, shop_id: str | None = None) -> list[SupplierLedgerEntry]:
        query = self.db.query(SupplierLedgerEntry).filter(SupplierLedgerEntry.supplier_id == supplier_id)
        if shop_id:
            query = query.filter(SupplierLedgerEntry.shop_id == shop_id)
        if from_date:
            query = query.filter(SupplierLedgerEntry.entry_date >= from_date)
        if to_date:
            query = query.filter(SupplierLedgerEntry.entry_date <= to_date)
        return query.order_by(SupplierLedgerEntry.entry_date.asc(), SupplierLedgerEntry.created_at.asc()).all()
