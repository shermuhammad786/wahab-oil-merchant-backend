from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models import (
    AppSetting,
    BankAccount,
    BankTransaction,
    CashCreditPerson,
    Customer,
    CustomerLedgerEntry,
    CustomerPayment,
    Expense,
    Product,
    Purchase,
    Sale,
    StockMovement,
    Supplier,
    SupplierLedgerEntry,
    SupplierPayment,
)
from app.models.user import User
from app.services.operations import OperationsService, dec

router = APIRouter(tags=["operations"])


def service(db: Session) -> OperationsService:
    return OperationsService(db)


def user_id(user: User) -> str:
    return user.id


@router.get("/sales")
def list_sales(page: int = 1, page_size: int = 50, customer_id: str | None = None, sale_type: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    query = select(Sale).order_by(Sale.sale_date.desc(), Sale.created_at.desc())
    if customer_id and customer_id.lower() not in {"all", "null", "undefined"}:
        query = query.where(Sale.customer_id == customer_id)
    if sale_type and sale_type.lower() != "all":
        query = query.where(Sale.sale_type == sale_type)
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    total = db.scalar(select(func.count()).select_from(Sale)) or 0
    return {"items": [service(db).sale_detail(row.id) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/sales", status_code=status.HTTP_201_CREATED)
def create_sale(payload: dict[str, Any], idempotency_key: str | None = Header(default=None), db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    existing = service(db).idempotent(idempotency_key, payload, user_id(current))
    if existing:
        return existing
    result = service(db).sale(payload, user_id(current))
    service(db).save_idempotency(idempotency_key, payload, result, user_id(current))
    db.commit()
    return result


@router.get("/sales/next-invoice")
def next_invoice(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, str]:
    return {"invoice_number": service(db).next_number("invoice_prefix", "INV", Sale, "invoice_number")}


@router.get("/sales/{sale_id}")
def get_sale(sale_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).sale_detail(sale_id)


@router.post("/sales/{sale_id}/cancel")
def cancel_sale(sale_id: str, db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    row = db.get(Sale, sale_id)
    if not row:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Sale not found")
    row.status = "cancelled"
    db.commit()
    return service(db).sale_detail(sale_id)


@router.post("/sales/{sale_id}/returns", status_code=status.HTTP_201_CREATED)
def return_sale(sale_id: str, payload: dict[str, Any], idempotency_key: str | None = Header(default=None), db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).sale_return(sale_id, payload, user_id(current))


@router.get("/purchases")
def list_purchases(page: int = 1, page_size: int = 50, supplier_id: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    query = select(Purchase).order_by(Purchase.purchase_date.desc(), Purchase.created_at.desc())
    if supplier_id and supplier_id.lower() not in {"all", "null", "undefined"}:
        query = query.where(Purchase.supplier_id == supplier_id)
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    total = db.scalar(select(func.count()).select_from(Purchase)) or 0
    return {"items": [service(db).purchase_detail(row.id) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/purchases", status_code=status.HTTP_201_CREATED)
def create_purchase(payload: dict[str, Any], idempotency_key: str | None = Header(default=None), db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    existing = service(db).idempotent(idempotency_key, payload, user_id(current))
    if existing:
        return existing
    result = service(db).purchase(payload, user_id(current))
    service(db).save_idempotency(idempotency_key, payload, result, user_id(current))
    db.commit()
    return result


@router.get("/purchases/next-number")
def next_purchase_number(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, str]:
    return {"purchase_number": service(db).next_number("purchase_prefix", "PUR", Purchase, "purchase_number")}


@router.get("/purchases/{purchase_id}")
def get_purchase(purchase_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).purchase_detail(purchase_id)


@router.post("/purchases/{purchase_id}/returns", status_code=status.HTTP_201_CREATED)
def return_purchase(purchase_id: str, payload: dict[str, Any], idempotency_key: str | None = Header(default=None), db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).purchase_return(purchase_id, payload, user_id(current))


@router.get("/payments")
def list_payments(page: int = 1, page_size: int = 50, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    customer_rows = db.scalars(select(CustomerPayment).order_by(CustomerPayment.payment_date.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    supplier_rows = db.scalars(select(SupplierPayment).order_by(SupplierPayment.payment_date.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    items = [{"id": row.id, "type": "Customer", "party_id": row.customer_id, "amount": row.amount, "date": row.payment_date, "payment_method": row.payment_method} for row in customer_rows]
    items += [{"id": row.id, "type": "Supplier", "party_id": row.supplier_id, "amount": row.amount, "date": row.payment_date, "payment_method": row.payment_method} for row in supplier_rows]
    return {"items": sorted(items, key=lambda item: item["date"], reverse=True), "total": len(items), "page": page, "page_size": page_size}


@router.post("/customers/{customer_id}/payments", status_code=status.HTTP_201_CREATED)
def customer_payment(customer_id: str, payload: dict[str, Any], idempotency_key: str | None = Header(default=None), db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    payload = {**payload, "customer_id": customer_id}
    existing = service(db).idempotent(idempotency_key, payload, user_id(current))
    if existing:
        return existing
    result = service(db).payment("customer", customer_id, payload, user_id(current))
    service(db).save_idempotency(idempotency_key, payload, result, user_id(current))
    db.commit()
    return result


@router.post("/suppliers/{supplier_id}/payments", status_code=status.HTTP_201_CREATED)
def supplier_payment(supplier_id: str, payload: dict[str, Any], idempotency_key: str | None = Header(default=None), db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    payload = {**payload, "supplier_id": supplier_id}
    existing = service(db).idempotent(idempotency_key, payload, user_id(current))
    if existing:
        return existing
    result = service(db).payment("supplier", supplier_id, payload, user_id(current))
    service(db).save_idempotency(idempotency_key, payload, result, user_id(current))
    db.commit()
    return result


@router.get("/banks")
def list_banks(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> list[dict[str, Any]]:
    rows = service(db).ensure_banks()
    return [{"id": row.id, "name": row.name, "opening_balance": row.opening_balance, "balance": service(db)._bank_balance(row.id)} for row in rows]


@router.get("/banks/transactions")
def bank_transactions(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> list[dict[str, Any]]:
    rows = db.scalars(select(BankTransaction).order_by(BankTransaction.transaction_date.desc())).all()
    return [
        {
            "id": row.id,
            "bank_account_id": row.bank_account_id,
            "transaction_date": row.transaction_date,
            "type": row.type,
            "amount": row.amount,
            "reference": row.reference,
            "note": row.note,
            "reference_type": row.reference_type,
            "reference_id": row.reference_id,
        }
        for row in rows
    ]


@router.post("/banks/deposits")
def bank_deposit(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).bank_movement("deposit", payload, user_id(current))


@router.post("/banks/withdrawals")
def bank_withdrawal(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).bank_movement("withdrawal", payload, user_id(current))


@router.post("/banks/transfers")
def bank_transfer(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).bank_movement("transfer", payload, user_id(current))


@router.get("/expenses")
def list_expenses(page: int = 1, page_size: int = 50, include_other: bool = False, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    query = select(Expense).order_by(Expense.expense_date.desc())
    if not include_other:
        query = query.where(Expense.subtype != "Other Expense")
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": rows, "total": len(rows), "page": page, "page_size": page_size}


@router.post("/expenses", status_code=status.HTTP_201_CREATED)
def create_expense(payload: dict[str, Any], idempotency_key: str | None = Header(default=None), db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).expense(payload, user_id(current))


@router.get("/cash-credit/people")
def list_cash_credit(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    rows = db.scalars(select(CashCreditPerson).order_by(CashCreditPerson.name)).all()
    return {"items": [{"id": row.id, "name": row.name, "phone": row.phone, "total_cash_given": row.total_cash_given, "total_received": row.total_received, "remaining": dec(row.total_cash_given) - dec(row.total_received)} for row in rows], "total": len(rows)}


@router.post("/cash-credit/people", status_code=status.HTTP_201_CREATED)
def create_cash_credit(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).cash_credit("create", payload, user_id(current))


@router.get("/cash-credit/people/{person_id}")
def get_cash_credit(person_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    row = db.get(CashCreditPerson, person_id)
    if not row:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Cash credit person not found")
    return {"id": row.id, "name": row.name, "phone": row.phone, "total_cash_given": row.total_cash_given, "total_received": row.total_received, "remaining": dec(row.total_cash_given) - dec(row.total_received)}


@router.post("/cash-credit/people/{person_id}/give")
def give_cash_credit(person_id: str, payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).cash_credit("give", {**payload, "person_id": person_id}, user_id(current))


@router.post("/cash-credit/people/{person_id}/receive")
def receive_cash_credit(person_id: str, payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).cash_credit("receive", {**payload, "person_id": person_id}, user_id(current))


@router.get("/cash-book/daily")
def daily_cash_book(date: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).daily(date or datetime.utcnow().date().isoformat())


@router.get("/cash-book")
def cash_book(date: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).daily(date or datetime.utcnow().date().isoformat())


@router.post("/cash-book/opening-balance")
def opening_balance(payload: dict[str, Any], db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    setting = db.get(AppSetting, "opening_cash") or AppSetting(key="opening_cash", value="0")
    setting.value = str(dec(payload.get("amount")))
    db.add(setting)
    db.commit()
    return service(db).daily(str(payload.get("date") or datetime.utcnow().date()))


@router.post("/cash-book/finalize")
def finalize_cash_book(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).finalize(payload, user_id(current))


@router.post("/cash-book/retail-sale")
def daily_retail_sale(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).sale({**payload, "sale_type": "retail", "customer_name": "Daily Walk-in"}, user_id(current))


@router.post("/cash-book/customer-payments")
def daily_customer_payments(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> list[dict[str, Any]]:
    try:
        results = [service(db).payment("customer", row["customer_id"], {**row, "_batch": True, "payment_method": "Cash", "date": payload.get("date")}, user_id(current)) for row in payload.get("payments", []) if dec(row.get("amount")) > 0]
        db.commit()
        return results
    except Exception:
        db.rollback()
        raise


@router.post("/cash-book/supplier-payments")
def daily_supplier_payments(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> list[dict[str, Any]]:
    try:
        results = [service(db).payment("supplier", row["supplier_id"], {**row, "_batch": True, "payment_method": "Cash", "date": payload.get("date")}, user_id(current)) for row in payload.get("payments", []) if dec(row.get("amount")) > 0]
        db.commit()
        return results
    except Exception:
        db.rollback()
        raise


@router.post("/cash-book/expenses")
def daily_expenses(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> list[dict[str, Any]]:
    try:
        results = [service(db).expense({**row, "_batch": True, "payment_method": "Cash", "date": payload.get("date")}, user_id(current)) for row in payload.get("expenses", []) if dec(row.get("amount")) > 0]
        db.commit()
        return results
    except Exception:
        db.rollback()
        raise


@router.get("/customer-ledger/{customer_id}")
def customer_ledger(customer_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    rows = db.scalars(select(CustomerLedgerEntry).where(CustomerLedgerEntry.customer_id == customer_id).order_by(CustomerLedgerEntry.entry_date, CustomerLedgerEntry.created_at)).all()
    return {"items": rows, "balance": service(db)._customer_balance(customer_id)}


@router.get("/supplier-ledger/{supplier_id}")
def supplier_ledger(supplier_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    rows = db.scalars(select(SupplierLedgerEntry).where(SupplierLedgerEntry.supplier_id == supplier_id).order_by(SupplierLedgerEntry.entry_date, SupplierLedgerEntry.created_at)).all()
    return {"items": rows, "balance": service(db)._supplier_balance(supplier_id)}


@router.get("/reports/{report_name}")
def report(report_name: str, from_date: str | None = Query(default=None, alias="from"), to_date: str | None = Query(default=None, alias="to"), customer_id: str | None = None, supplier_id: str | None = None, product_id: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    if report_name == "sales":
        query = select(Sale).where(Sale.status == "completed").order_by(Sale.sale_date.desc())
        if from_date:
            query = query.where(func.date(Sale.sale_date) >= from_date)
        if to_date:
            query = query.where(func.date(Sale.sale_date) <= to_date)
        if customer_id and customer_id.lower() not in {"all", "null", "undefined"}:
            query = query.where(Sale.customer_id == customer_id)
        rows = db.scalars(query).all()
    elif report_name == "purchases":
        query = select(Purchase).where(Purchase.status == "completed").order_by(Purchase.purchase_date.desc())
        if from_date:
            query = query.where(func.date(Purchase.purchase_date) >= from_date)
        if to_date:
            query = query.where(func.date(Purchase.purchase_date) <= to_date)
        if supplier_id and supplier_id.lower() not in {"all", "null", "undefined"}:
            query = query.where(Purchase.supplier_id == supplier_id)
        rows = db.scalars(query).all()
    elif report_name == "stock":
        rows = db.scalars(select(Product).where(Product.status == "active")).all()
    elif report_name == "expenses":
        query = select(Expense).order_by(Expense.expense_date.desc())
        if from_date:
            query = query.where(func.date(Expense.expense_date) >= from_date)
        if to_date:
            query = query.where(func.date(Expense.expense_date) <= to_date)
        rows = db.scalars(query).all()
    elif report_name == "receivables":
        rows = [{"customer_id": row.id, "balance": service(db)._customer_balance(row.id)} for row in db.scalars(select(Customer).where(Customer.status == "Active")).all()]
    elif report_name == "payables":
        rows = [{"supplier_id": row.id, "balance": service(db)._supplier_balance(row.id)} for row in db.scalars(select(Supplier).where(Supplier.status == "Active")).all()]
    elif report_name == "cash-book":
        return service(db).daily(from_date or datetime.utcnow().date().isoformat())
    elif report_name == "customer-ledger":
        rows = db.scalars(select(CustomerLedgerEntry).order_by(CustomerLedgerEntry.entry_date)).all()
    elif report_name == "supplier-ledger":
        rows = db.scalars(select(SupplierLedgerEntry).order_by(SupplierLedgerEntry.entry_date)).all()
    elif report_name in {"profit-loss", "profitLoss"}:
        sales_total = db.scalar(select(func.coalesce(func.sum(Sale.total), 0)).where(Sale.status == "completed")) or 0
        purchase_total = db.scalar(select(func.coalesce(func.sum(Purchase.total), 0)).where(Purchase.status == "completed")) or 0
        expense_total = db.scalar(select(func.coalesce(func.sum(Expense.amount), 0))) or 0
        return {"sales": sales_total, "purchases": purchase_total, "expenses": expense_total, "net_profit": dec(sales_total) - dec(purchase_total) - dec(expense_total)}
    else:
        rows = []
    return {"items": rows, "count": len(rows)}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    today = datetime.utcnow().date()
    sales = db.scalar(select(func.coalesce(func.sum(Sale.total), 0)).where(func.date(Sale.sale_date) == today, Sale.status == "completed")) or 0
    purchases = db.scalar(select(func.coalesce(func.sum(Purchase.total), 0)).where(func.date(Purchase.purchase_date) == today, Purchase.status == "completed")) or 0
    low_stock = db.scalars(select(Product).where(Product.status == "active", Product.current_stock <= Product.minimum_stock)).all()
    return {"todays_sales": sales, "todays_purchases": purchases, "total_receivables": sum((service(db)._customer_balance(c.id) for c in db.scalars(select(Customer).where(Customer.status == "Active")).all()), Decimal("0")), "total_payables": sum((service(db)._supplier_balance(s.id) for s in db.scalars(select(Supplier).where(Supplier.status == "Active")).all()), Decimal("0")), "stock_value": sum((dec(p.current_stock) * dec(p.purchase_price) for p in db.scalars(select(Product).where(Product.status == "active")).all()), Decimal("0")), "low_stock": low_stock, "trend": []}


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, str]:
    return {row.key: row.value for row in db.scalars(select(AppSetting)).all()}


@router.put("/settings")
def update_settings(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, str]:
    for key, value in payload.items():
        row = db.get(AppSetting, key) or AppSetting(key=key, value="")
        row.value = str(value)
        db.add(row)
    db.commit()
    return get_settings(db, current)