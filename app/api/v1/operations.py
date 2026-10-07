from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.core.money import ZERO_MONEY
from app.db.session import get_db
from app.models import (
    AppSetting,
    BankAccount,
    BankTransaction,
    Category,
    CashCreditPerson,
    CashCreditTransaction,
    CashTransaction,
    Customer,
    CustomerLedgerEntry,
    CustomerPayment,
    Expense,
    Product,
    Purchase,
    PurchaseItem,
    Sale,
    SaleItem,
    SaleReturn,
    StockMovement,
    Supplier,
    SupplierLedgerEntry,
    SupplierPayment,
    PurchaseReturn,
)
from app.models.user import User
from app.schemas.cash_book import DailyCustomerPayments, DailySupplierPayments
from app.services.operations import OperationsService, dec

router = APIRouter(tags=["operations"])


def service(db: Session) -> OperationsService:
    return OperationsService(db)


def user_id(user: User) -> str:
    return user.id


def active_filter(value: str | None) -> str | None:
    return value.strip() if value and value.strip().lower() not in {"all", "null", "undefined"} else None


def expense_dict(row: Expense) -> dict[str, Any]:
    return {
        "id": row.id,
        "category": row.category,
        "subtype": row.subtype,
        "custom_subtype": row.custom_subtype,
        "amount": float(row.amount),
        "date": row.expense_date,
        "description": row.description,
        "payment_method": row.payment_method,
        "reference": row.reference,
        "created_at": row.created_at,
    }


def category_name(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    name = getattr(value, "name", None)
    return str(name) if name is not None else ""


def profit_loss_totals(db: Session, shop_id: str, from_date: str | None = None, to_date: str | None = None) -> dict[str, float]:
    sales_query = select(func.sum(Sale.total)).where(Sale.shop_id == shop_id, Sale.status == "completed")
    purchases_query = select(func.sum(Purchase.total)).where(Purchase.shop_id == shop_id, Purchase.status == "completed")
    expenses_query = select(func.sum(Expense.amount)).where(Expense.shop_id == shop_id)
    if from_date:
        sales_query = sales_query.where(func.date(Sale.sale_date) >= from_date)
        purchases_query = purchases_query.where(func.date(Purchase.purchase_date) >= from_date)
        expenses_query = expenses_query.where(func.date(Expense.expense_date) >= from_date)
    if to_date:
        sales_query = sales_query.where(func.date(Sale.sale_date) <= to_date)
        purchases_query = purchases_query.where(func.date(Purchase.purchase_date) <= to_date)
        expenses_query = expenses_query.where(func.date(Expense.expense_date) <= to_date)
    sales_total = db.scalar(sales_query) or ZERO_MONEY
    purchase_total = db.scalar(purchases_query) or ZERO_MONEY
    expense_total = db.scalar(expenses_query) or ZERO_MONEY
    return {
        "sales": float(dec(sales_total)),
        "purchases": float(dec(purchase_total)),
        "expenses": float(dec(expense_total)),
        "net_profit": float(dec(sales_total) - dec(purchase_total) - dec(expense_total)),
    }


@router.get("/sales")
def list_sales(page: int = 1, page_size: int = 50, customer_id: str | None = None, sale_type: str | None = None, search: str | None = None, from_date: str | None = Query(default=None, alias="from"), to_date: str | None = Query(default=None, alias="to"), db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    query = select(Sale).order_by(Sale.sale_date.desc(), Sale.created_at.desc())
    if customer_id and customer_id.lower() not in {"all", "null", "undefined"}:
        query = query.where(Sale.customer_id == customer_id)
    if sale_type and sale_type.lower() != "all":
        query = query.where(Sale.sale_type == sale_type)
    if search:
        pattern = f"%{search}%"
        query = query.where(Sale.invoice_number.ilike(pattern) | Sale.customer_name.ilike(pattern))
    if from_date:
        query = query.where(func.date(Sale.sale_date) >= from_date)
    if to_date:
        query = query.where(func.date(Sale.sale_date) <= to_date)
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
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
def next_invoice(db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, str]:
    return {"invoice_number": OperationsService(db, shop_id=current.shop_id).next_number("invoice_prefix", "INV", Sale, "invoice_number")}


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
def list_purchases(page: int = 1, page_size: int = 50, supplier_id: str | None = None, search: str | None = None, from_date: str | None = Query(default=None, alias="from"), to_date: str | None = Query(default=None, alias="to"), db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    query = select(Purchase).order_by(Purchase.purchase_date.desc(), Purchase.created_at.desc())
    if supplier_id and supplier_id.lower() not in {"all", "null", "undefined"}:
        query = query.where(Purchase.supplier_id == supplier_id)
    if search:
        query = query.where(Purchase.purchase_number.ilike(f"%{search}%"))
    if from_date:
        query = query.where(func.date(Purchase.purchase_date) >= from_date)
    if to_date:
        query = query.where(func.date(Purchase.purchase_date) <= to_date)
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
def next_purchase_number(db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, str]:
    return {"purchase_number": OperationsService(db, shop_id=current.shop_id).next_number("purchase_prefix", "PUR", Purchase, "purchase_number")}


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
def bank_transactions(from_date: str | None = Query(default=None, alias="from"), to_date: str | None = Query(default=None, alias="to"), bank_id: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> list[dict[str, Any]]:
    query = select(BankTransaction).order_by(BankTransaction.transaction_date.desc())
    if from_date:
        query = query.where(func.date(BankTransaction.transaction_date) >= from_date)
    if to_date:
        query = query.where(func.date(BankTransaction.transaction_date) <= to_date)
    if bank_id and bank_id.lower() not in {"all", "null", "undefined"}:
        query = query.where(BankTransaction.bank_account_id == bank_id)
    rows = db.scalars(query).all()
    return [
        {
            "id": row.id,
            "bank_id": row.bank_account_id,
            "bank": (db.get(BankAccount, row.bank_account_id).name if db.get(BankAccount, row.bank_account_id) else ""),
            "date": row.transaction_date,
            "type": row.type,
            "amount": row.amount,
            "reference": row.reference,
            "note": row.note,
            "reference_type": row.reference_type,
            "reference_id": row.reference_id,
            "balance_impact": row.amount if row.type in {"Deposit", "Transfer In", "Customer Payment"} else -row.amount,
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
def list_expenses(
    page: int = 1,
    page_size: int = 50,
    category: str | None = None,
    subtype: str | None = None,
    search: str | None = None,
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    query = select(Expense)
    query = query.where(Expense.subtype.notin_(("Other Expense", "Other")))
    category = active_filter(category)
    subtype = active_filter(subtype)
    search = active_filter(search)
    from_date, to_date = active_filter(from_date), active_filter(to_date)
    if category:
        query = query.where(Expense.category == category)
    if subtype:
        query = query.where(Expense.subtype == subtype)
    if from_date:
        query = query.where(func.date(Expense.expense_date) >= from_date)
    if to_date:
        query = query.where(func.date(Expense.expense_date) <= to_date)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            Expense.category.ilike(pattern)
            | Expense.subtype.ilike(pattern)
            | Expense.custom_subtype.ilike(pattern)
            | Expense.description.ilike(pattern)
            | Expense.reference.ilike(pattern)
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    matching = query.subquery()
    summary_rows = db.execute(
        select(Expense.category, func.sum(Expense.amount))
        .where(Expense.id.in_(select(matching.c.id)))
        .group_by(Expense.category)
    ).all()
    rows = db.scalars(
        query.order_by(Expense.expense_date.desc(), Expense.created_at.desc())
        .offset(max(page - 1, 0) * page_size)
        .limit(page_size)
    ).all()
    by_category = {category_name: float(amount or ZERO_MONEY) for category_name, amount in summary_rows}
    return {
        "items": [expense_dict(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "summary": {"total": sum(by_category.values()), "by_category": by_category},
    }


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
def get_cash_credit(person_id: str, db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    row = db.scalar(select(CashCreditPerson).where(CashCreditPerson.id == person_id, CashCreditPerson.shop_id == current.shop_id))
    if not row:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Cash credit person not found")
    total_cash_given = dec(row.total_cash_given)
    total_received = dec(row.total_received)
    remaining = total_cash_given - total_received
    transaction_rows = db.connection().execute(
        select(CashCreditTransaction.__table__)
        .where(CashCreditTransaction.person_id == row.id)
        .order_by(CashCreditTransaction.transaction_date, CashCreditTransaction.created_at, CashCreditTransaction.id)
    ).mappings().all()
    history_rows = [
        (transaction["id"], transaction["transaction_date"], transaction["type"], transaction["amount"], transaction["notes"], transaction["created_at"])
        for transaction in transaction_rows
    ]
    if not history_rows:
        legacy_rows = db.connection().execute(
            select(CashTransaction.__table__)
            .where(
                CashTransaction.reference_type == "cash_credit",
                CashTransaction.reference_id == row.id,
            )
            .order_by(CashTransaction.transaction_date, CashTransaction.created_at, CashTransaction.id)
        ).mappings().all()
        history_rows = [
            (
                transaction["id"],
                transaction["transaction_date"],
                "Credit Given" if transaction["category"] == "cash_credit_given" or transaction["type"].lower() == "cash_out" else "Payment Received",
                transaction["amount"],
                transaction["description"],
                transaction["created_at"],
            )
            for transaction in legacy_rows
        ]
    running_remaining = Decimal("0")
    transactions = []
    for transaction_id, transaction_date, transaction_type, transaction_amount, note, created_at in history_rows:
        amount = dec(transaction_amount)
        running_remaining += amount if transaction_type == "Credit Given" else -amount
        transactions.append({
            "id": transaction_id,
            "date": transaction_date,
            "type": transaction_type,
            "amount": float(amount),
            "remaining": float(running_remaining),
            "note": note or "",
            "createdAt": created_at,
        })
    person = {
        "id": row.id,
        "name": row.name,
        "phone": row.phone or "",
        "totalCashGiven": float(total_cash_given),
        "totalReceived": float(total_received),
        "remaining": float(remaining),
        "status": "Paid" if remaining <= 0 else "Partial" if total_received > 0 else "Unpaid",
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }
    return {
        "person": person,
        "transactions": transactions,
        "totalCashGiven": float(total_cash_given),
        "totalReceived": float(total_received),
        "remaining": float(remaining),
    }


@router.post("/cash-credit/people/{person_id}/give")
def give_cash_credit(person_id: str, payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).cash_credit("give", {**payload, "person_id": person_id}, user_id(current))


@router.post("/cash-credit/people/{person_id}/receive")
def receive_cash_credit(person_id: str, payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).cash_credit("receive", {**payload, "person_id": person_id}, user_id(current))


@router.get("/cash-book/daily")
def daily_cash_book(date: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    return jsonable_encoder(service(db).daily(date or datetime.utcnow().date().isoformat()))


@router.get("/cash-book")
def cash_book(date: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).daily(date or datetime.utcnow().date().isoformat())


@router.post("/cash-book/opening-balance")
def opening_balance(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == "opening_cash", AppSetting.shop_id == current.shop_id)) or AppSetting(key="opening_cash", shop_id=current.shop_id, value="0")
    setting.value = str(dec(payload.get("amount")))
    db.add(setting)
    db.commit()
    return service(db).daily(str(payload.get("date") or datetime.utcnow().date()))


@router.post("/cash-book/finalize")
def finalize_cash_book(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).finalize(payload, user_id(current))


@router.delete("/cash-book/drafts/{draft_id}")
def delete_cash_book_draft(draft_id: str, date: str, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    return service(db).delete_cash_draft(draft_id, date)


@router.post("/cash-book/retail-sale")
def daily_retail_sale(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    amount = payload.get("cash_received", payload.get("cashReceived", 0))
    return service(db).stage_cash_entries(str(payload.get("date") or datetime.utcnow().date()), [{
        "entry_type": "retail_sale",
        "category": "Walk-in Sale",
        "amount": amount,
        "description": payload.get("note") or "Walk-in Sale",
        "payload": payload,
    }], user_id(current))


@router.post("/cash-book/bank-transactions")
def daily_bank_transaction(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    kind = str(payload.get("type", "")).strip().lower()
    entry_type = {"deposit": "bank_deposit", "withdrawal": "bank_withdrawal", "transfer": "bank_transfer"}.get(kind)
    if not entry_type:
        from app.core.exceptions import ValidationError
        raise ValidationError("Unsupported Cash Book bank transaction type")
    return service(db).stage_cash_entries(str(payload.get("date") or datetime.utcnow().date()), [{
        "entry_type": entry_type,
        "category": f"Bank {kind.title()}",
        "amount": payload.get("amount"),
        "description": payload.get("note") or f"Bank {kind.title()}",
        "payload": payload,
    }], user_id(current))


@router.post("/cash-book/customer-payments")
def daily_customer_payments(payload: DailyCustomerPayments, db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    entries = [{
        "entry_type": "customer_payment",
        "category": "Customer Credit Installment",
        "amount": row.amount,
        "description": row.notes or f"Customer installment {row.customer_id}",
        "payload": row.model_dump(),
    } for row in payload.payments]
    return service(db).stage_cash_entries(payload.date.isoformat(), entries, user_id(current))


@router.post("/cash-book/supplier-payments")
def daily_supplier_payments(payload: DailySupplierPayments, db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    entries = [{
        "entry_type": "supplier_payment",
        "category": "Vendor Payment",
        "amount": row.amount,
        "description": row.notes or f"Vendor payment {row.supplier_id}",
        "payload": row.model_dump(),
    } for row in payload.payments]
    return service(db).stage_cash_entries(payload.date.isoformat(), entries, user_id(current))


@router.post("/cash-book/expenses")
def daily_expenses(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    entries = [{
        "entry_type": "expense",
        "category": "Expenses",
        "amount": row.get("amount"),
        "description": row.get("note") or row.get("description") or row.get("subtype") or "Expense",
        "payload": row,
    } for row in payload.get("expenses", []) if dec(row.get("amount")) > 0]
    return service(db).stage_cash_entries(str(payload.get("date") or datetime.utcnow().date()), entries, user_id(current))


@router.get("/customer-ledger/{customer_id}")
def customer_ledger(customer_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    rows = db.scalars(select(CustomerLedgerEntry).where(CustomerLedgerEntry.customer_id == customer_id).order_by(CustomerLedgerEntry.entry_date, CustomerLedgerEntry.created_at)).all()
    return {"items": rows, "balance": service(db)._customer_balance(customer_id)}


@router.get("/supplier-ledger/{supplier_id}")
def supplier_ledger(supplier_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, Any]:
    rows = db.scalars(select(SupplierLedgerEntry).where(SupplierLedgerEntry.supplier_id == supplier_id).order_by(SupplierLedgerEntry.entry_date, SupplierLedgerEntry.created_at)).all()
    return {"items": rows, "balance": service(db)._supplier_balance(supplier_id)}


@router.get("/reports/{report_name}")
def report(
    report_name: str,
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    customer_id: str | None = None,
    supplier_id: str | None = None,
    product_id: str | None = None,
    category: str | None = None,
    subtype: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict[str, Any]:
    customer_id, supplier_id, product_id = map(active_filter, (customer_id, supplier_id, product_id))
    category, subtype, search = map(active_filter, (category, subtype, search))
    from_date, to_date = active_filter(from_date), active_filter(to_date)
    if report_name == "sales":
        query = select(Sale).where(Sale.status == "completed").order_by(Sale.sale_date.desc())
        if from_date:
            query = query.where(func.date(Sale.sale_date) >= from_date)
        if to_date:
            query = query.where(func.date(Sale.sale_date) <= to_date)
        if customer_id and customer_id.lower() not in {"all", "null", "undefined"}:
            query = query.where(Sale.customer_id == customer_id)
        if product_id and product_id.lower() not in {"all", "null", "undefined"}:
            query = query.where(Sale.items.any(SaleItem.product_id == product_id))
        count = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
        matched_sales = query.order_by(None).subquery()
        matching_ids = select(matched_sales.c.id)
        summary = {
            "count": count,
            "total": float(db.scalar(select(func.sum(Sale.total)).where(Sale.id.in_(matching_ids))) or ZERO_MONEY),
            "paid": float(db.scalar(select(func.sum(Sale.paid)).where(Sale.id.in_(matching_ids))) or ZERO_MONEY),
            "remaining": float(db.scalar(select(func.sum(Sale.remaining)).where(Sale.id.in_(matching_ids))) or ZERO_MONEY),
        }
        rows = db.scalars(query.offset(max(page - 1, 0) * page_size).limit(page_size)).all()
        result_items = []
        for row in rows:
            item = service(db).sale_detail(row.id)
            for field in ("total", "paid", "remaining"):
                item[field] = float(item[field])
            result_items.append(item)
    elif report_name == "purchases":
        query = select(Purchase).where(Purchase.status == "completed").order_by(Purchase.purchase_date.desc())
        if from_date:
            query = query.where(func.date(Purchase.purchase_date) >= from_date)
        if to_date:
            query = query.where(func.date(Purchase.purchase_date) <= to_date)
        if supplier_id and supplier_id.lower() not in {"all", "null", "undefined"}:
            query = query.where(Purchase.supplier_id == supplier_id)
        if product_id and product_id.lower() not in {"all", "null", "undefined"}:
            query = query.where(Purchase.items.any(PurchaseItem.product_id == product_id))
        count = db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
        matched_purchases = query.order_by(None).subquery()
        matching_ids = select(matched_purchases.c.id)
        summary = {
            "count": count,
            "total": float(db.scalar(select(func.sum(Purchase.total)).where(Purchase.id.in_(matching_ids))) or ZERO_MONEY),
            "paid": float(db.scalar(select(func.sum(Purchase.paid)).where(Purchase.id.in_(matching_ids))) or ZERO_MONEY),
            "remaining": float(db.scalar(select(func.sum(Purchase.remaining)).where(Purchase.id.in_(matching_ids))) or ZERO_MONEY),
        }
        rows = db.scalars(query.offset(max(page - 1, 0) * page_size).limit(page_size)).all()
        result_items = []
        for row in rows:
            item = service(db).purchase_detail(row.id)
            for field in ("total", "paid", "remaining"):
                item[field] = float(item[field])
            supplier = db.get(Supplier, row.supplier_id)
            item["supplier_name"] = supplier.name if supplier else ""
            result_items.append(item)
    elif report_name == "stock":
        query = select(Product).where(Product.status == "active")
        count = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = db.scalars(query.order_by(Product.name).offset(max(page - 1, 0) * page_size).limit(page_size)).all()
        result_items = [{
            "id": row.id,
            "name": row.name,
            "category": category_name(getattr(row, "category", None)),
            "current_stock": float(row.current_stock),
            "unit": row.unit,
            "stock_value": float(dec(row.current_stock) * dec(row.purchase_price)),
        } for row in rows]
        total_value = sum((dec(row.current_stock) * dec(row.purchase_price) for row in db.scalars(query).all()), Decimal("0"))
        summary = {"count": count, "total": float(total_value)}
    elif report_name == "expenses":
        query = select(Expense).where(Expense.subtype != "Other Expense")
        if category:
            query = query.where(Expense.category == category)
        if subtype:
            query = query.where(Expense.subtype == subtype)
        if search:
            pattern = f"%{search}%"
            query = query.where(Expense.category.ilike(pattern) | Expense.subtype.ilike(pattern) | Expense.custom_subtype.ilike(pattern) | Expense.description.ilike(pattern) | Expense.reference.ilike(pattern))
        if from_date:
            query = query.where(func.date(Expense.expense_date) >= from_date)
        if to_date:
            query = query.where(func.date(Expense.expense_date) <= to_date)
        count = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        matched_expenses = query.subquery()
        matching_ids = select(matched_expenses.c.id)
        summary = {"count": count, "total": float(db.scalar(select(func.sum(Expense.amount)).where(Expense.id.in_(matching_ids))) or ZERO_MONEY)}
        rows = db.scalars(query.order_by(Expense.expense_date.desc(), Expense.created_at.desc()).offset(max(page - 1, 0) * page_size).limit(page_size)).all()
        result_items = [expense_dict(row) for row in rows]
    elif report_name == "receivables":
        result_items = [{"customer_id": row.id, "balance": service(db)._customer_balance(row.id)} for row in db.scalars(select(Customer).where(Customer.status == "Active")).all()]
        summary = {"count": len(result_items), "total": float(sum((dec(row["balance"]) for row in result_items), Decimal("0")))}
    elif report_name == "payables":
        result_items = [{"supplier_id": row.id, "balance": service(db)._supplier_balance(row.id)} for row in db.scalars(select(Supplier).where(Supplier.status == "Active")).all()]
        summary = {"count": len(result_items), "total": float(sum((dec(row["balance"]) for row in result_items), Decimal("0")))}
    elif report_name == "cash-book":
        result = service(db).daily(from_date or datetime.utcnow().date().isoformat())
        for key in ("opening_balance", "cash_in", "cash_out", "total_cash_in", "total_cash_out", "closing_balance", "actual_cash", "difference"):
            if result[key] is not None:
                result[key] = float(result[key])
        for collection in ("categories", "items", "pending_items"):
            for item in result[collection]:
                if "amount" in item:
                    item["amount"] = float(item["amount"])
        return result
    elif report_name == "customer-ledger":
        result_items = db.scalars(select(CustomerLedgerEntry).order_by(CustomerLedgerEntry.entry_date)).all()
        summary = {"count": len(result_items), "total": ZERO_MONEY}
    elif report_name == "supplier-ledger":
        result_items = db.scalars(select(SupplierLedgerEntry).order_by(SupplierLedgerEntry.entry_date)).all()
        summary = {"count": len(result_items), "total": ZERO_MONEY}
    elif report_name in {"profit-loss", "profitLoss"}:
        return profit_loss_totals(db, _.shop_id, from_date, to_date)
    else:
        result_items = []
        summary = {"count": 0, "total": ZERO_MONEY}
    return {"items": result_items, "total": summary["count"], "count": summary["count"], "summary": summary, "page": page, "page_size": page_size}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, Any]:
    shop_id = current.shop_id
    today = datetime.utcnow().date()
    today_totals = profit_loss_totals(db, shop_id, today.isoformat(), today.isoformat())
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    start = days[0]
    start_at = datetime.combine(start, datetime.min.time())
    end_at = datetime.combine(today + timedelta(days=1), datetime.min.time())
    sales_rows = db.execute(
        select(func.date(Sale.sale_date), func.sum(Sale.total))
        .where(Sale.shop_id == shop_id, Sale.sale_date >= start_at, Sale.sale_date < end_at, Sale.status == "completed")
        .group_by(func.date(Sale.sale_date))
    ).all()
    purchase_rows = db.execute(
        select(func.date(Purchase.purchase_date), func.sum(Purchase.total))
        .where(Purchase.shop_id == shop_id, Purchase.purchase_date >= start_at, Purchase.purchase_date < end_at, Purchase.status == "completed")
        .group_by(func.date(Purchase.purchase_date))
    ).all()
    sales_by_day = {day: Decimal("0") for day in days}
    purchases_by_day = {day: Decimal("0") for day in days}
    for day_value, amount in sales_rows:
        sales_by_day[date.fromisoformat(str(day_value)[:10])] = dec(amount)
    for day_value, amount in purchase_rows:
        purchases_by_day[date.fromisoformat(str(day_value)[:10])] = dec(amount)
    recent_sales = [
        {
            "id": row.id,
            "invoice_number": row.invoice_number,
            "date": row.sale_date,
            "total": float(row.total),
            "paid": float(row.paid),
            "remaining": float(row.remaining),
            "customer_name": row.customer_name,
            "payment_status": row.payment_status,
            "status": row.status,
        }
        for row in db.scalars(
            select(Sale)
            .where(Sale.shop_id == shop_id, Sale.status == "completed")
            .order_by(Sale.sale_date.desc(), Sale.created_at.desc())
            .limit(5)
        ).all()
    ]
    recent_purchase_rows = db.execute(
        select(Purchase, Supplier.name)
        .join(Supplier, (Supplier.id == Purchase.supplier_id) & (Supplier.shop_id == Purchase.shop_id))
        .where(Purchase.shop_id == shop_id, Supplier.shop_id == shop_id, Purchase.status == "completed")
        .order_by(Purchase.purchase_date.desc(), Purchase.created_at.desc())
        .limit(5)
    ).all()
    recent_purchases = [
        {
            "id": purchase.id,
            "purchase_number": purchase.purchase_number,
            "date": purchase.purchase_date,
            "total": float(purchase.total),
            "paid": float(purchase.paid),
            "remaining": float(purchase.remaining),
            "supplier_name": supplier_name,
            "payment_status": purchase.payment_status,
            "status": purchase.status,
        }
        for purchase, supplier_name in recent_purchase_rows
    ]
    cash_rows = db.execute(
        select(CashTransaction.type, func.sum(CashTransaction.amount))
        .where(
            CashTransaction.shop_id == shop_id,
            CashTransaction.transaction_date >= datetime.combine(today, datetime.min.time()),
            CashTransaction.transaction_date < end_at,
            or_(CashTransaction.reference_type.is_(None), CashTransaction.reference_type != "cash_credit"),
            or_(CashTransaction.category.is_(None), ~CashTransaction.category.like("cash_credit%")),
        )
        .group_by(CashTransaction.type)
    ).all()
    cash_totals = {transaction_type: dec(amount) for transaction_type, amount in cash_rows}
    active_customers = select(Customer.id).where(Customer.shop_id == shop_id, Customer.status == "Active")
    customer_opening = db.scalar(select(func.sum(Customer.opening_balance)).where(Customer.shop_id == shop_id, Customer.status == "Active")) or ZERO_MONEY
    customer_sales = db.scalar(select(func.sum(Sale.total)).where(Sale.shop_id == shop_id, Sale.customer_id.in_(active_customers), Sale.sale_type == "installment", Sale.status == "completed")) or ZERO_MONEY
    customer_payments = db.scalar(select(func.sum(CustomerPayment.amount)).where(CustomerPayment.shop_id == shop_id, CustomerPayment.customer_id.in_(active_customers), CustomerPayment.status == "completed")) or ZERO_MONEY
    customer_returns = db.scalar(select(func.sum(SaleReturn.amount)).where(SaleReturn.shop_id == shop_id, SaleReturn.customer_id.in_(active_customers), SaleReturn.status == "completed")) or ZERO_MONEY
    active_suppliers = select(Supplier.id).where(Supplier.shop_id == shop_id, Supplier.status == "Active")
    supplier_opening = db.scalar(select(func.sum(Supplier.opening_balance)).where(Supplier.shop_id == shop_id, Supplier.status == "Active")) or ZERO_MONEY
    supplier_purchases = db.scalar(select(func.sum(Purchase.total)).where(Purchase.shop_id == shop_id, Purchase.supplier_id.in_(active_suppliers), Purchase.status == "completed")) or ZERO_MONEY
    supplier_payments = db.scalar(select(func.sum(SupplierPayment.amount)).where(SupplierPayment.shop_id == shop_id, SupplierPayment.supplier_id.in_(active_suppliers), SupplierPayment.status == "completed")) or ZERO_MONEY
    supplier_returns = db.scalar(select(func.sum(PurchaseReturn.amount)).where(PurchaseReturn.shop_id == shop_id, PurchaseReturn.supplier_id.in_(active_suppliers), PurchaseReturn.status == "completed")) or ZERO_MONEY
    low_stock_rows = db.execute(
        select(Product, Category.name)
        .outerjoin(Category, (Category.id == Product.category_id) & (Category.shop_id == Product.shop_id))
        .where(Product.shop_id == shop_id, Product.status == "active", Product.current_stock <= Product.minimum_stock)
        .order_by(Product.name)
    ).all()
    low_stock = [
        {
            "id": product.id,
            "name": product.name,
            "category": category_name or "",
            "category_id": product.category_id,
            "purchase_price": float(product.purchase_price),
            "current_stock": float(product.current_stock),
            "minimum_stock": float(product.minimum_stock),
            "status": "Out of Stock" if dec(product.current_stock) <= 0 else "Low Stock",
            "active": True,
        }
        for product, category_name in low_stock_rows
    ]
    stock_value = db.scalar(
        select(func.sum(Product.current_stock * Product.purchase_price)).where(Product.shop_id == shop_id, Product.status == "active")
    ) or ZERO_MONEY
    return {
        "todays_sales": today_totals["sales"],
        "todays_purchases": today_totals["purchases"],
        "todays_cash_in": float(cash_totals.get("cash_in", Decimal("0"))),
        "todays_cash_out": float(cash_totals.get("cash_out", Decimal("0"))),
        "todays_profit_loss": today_totals["net_profit"],
        "total_receivables": float(dec(customer_opening) + dec(customer_sales) - dec(customer_payments) - dec(customer_returns)),
        "total_payables": float(dec(supplier_opening) + dec(supplier_purchases) - dec(supplier_payments) - dec(supplier_returns)),
        "stock_value": float(stock_value),
        "recent_sales": recent_sales,
        "recent_purchases": recent_purchases,
        "low_stock": low_stock,
        "trend": [{"name": day.strftime("%m/%d"), "date": day.isoformat(), "sales": float(sales_by_day[day]), "purchases": float(purchases_by_day[day])} for day in days],
    }


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(require_admin)) -> dict[str, str]:
    return {row.key: row.value for row in db.scalars(select(AppSetting)).all()}


@router.put("/settings")
def update_settings(payload: dict[str, Any], db: Session = Depends(get_db), current: User = Depends(require_admin)) -> dict[str, str]:
    for key, value in payload.items():
        row = db.scalar(select(AppSetting).where(AppSetting.key == key, AppSetting.shop_id == current.shop_id)) or AppSetting(key=key, shop_id=current.shop_id, value="")
        row.value = str(value)
        db.add(row)
    db.commit()
    return get_settings(db, current)
