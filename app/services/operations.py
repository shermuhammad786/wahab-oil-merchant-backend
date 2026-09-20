from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import StockMovementType
from app.core.exceptions import (
    ConflictError,
    InsufficientBankBalanceError,
    InsufficientStockError,
    NotFoundError,
    PaymentExceedsBalanceError,
    ValidationError,
)
from app.models import (
    AppSetting,
    AuditLog,
    BankAccount,
    BankTransaction,
    CashCreditPerson,
    CashCreditTransaction,
    CashDayClose,
    CashTransaction,
    Customer,
    CustomerLedgerEntry,
    CustomerPayment,
    Expense,
    IdempotencyRecord,
    Product,
    Purchase,
    PurchaseItem,
    PurchaseReturn,
    PurchaseReturnItem,
    Sale,
    SaleItem,
    SaleReturn,
    SaleReturnItem,
    StockMovement,
    Supplier,
    SupplierLedgerEntry,
    SupplierPayment,
)

MONEY = Decimal("0.01")
QTY = Decimal("0.001")
BANK_NAMES = ("Meezan Bank", "Bank Alfalah")


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def dec(value: object, default: str = "0") -> Decimal:
    return Decimal(str(value if value not in (None, "") else default))


def dt(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return datetime.fromisoformat(str(value)) if value else datetime.utcnow()


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def qty(value: Decimal) -> Decimal:
    return value.quantize(QTY)


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class OperationsService:
    def __init__(self, db: Session):
        self.db = db

    def _commit(self) -> None:
        self.db.commit()

    def _rollback(self) -> None:
        self.db.rollback()

    def _audit(self, action: str, entity_type: str, entity_id: str | None, user_id: str | None, metadata: dict | None = None) -> None:
        self.db.add(AuditLog(id=uid("AUD"), action=action, entity_type=entity_type, entity_id=entity_id, user_id=user_id, metadata_json=metadata))

    def idempotent(self, key: str | None, payload: dict, user_id: str | None) -> dict | None:
        if not key:
            return None
        record = self.db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.key == key, IdempotencyRecord.user_id == user_id))
        if record:
            if record.request_hash != payload_hash(payload):
                raise ConflictError("Idempotency key was already used for a different request")
            return json.loads(record.response_json)
        return None

    def save_idempotency(self, key: str | None, payload: dict, response: dict, user_id: str | None) -> None:
        if key:
            self.db.add(IdempotencyRecord(id=uid("IDP"), key=key, user_id=user_id, request_hash=payload_hash(payload), response_json=json.dumps(response, default=str)))

    def _closed(self, when: datetime) -> None:
        if self.db.scalar(select(CashDayClose).where(func.date(CashDayClose.date) == when.date())):
            raise ConflictError("This cash day is finalized")

    def _product(self, product_id: str, lock: bool = False) -> Product:
        query = select(Product).where(Product.id == product_id)
        if lock:
            query = query.with_for_update()
        product = self.db.scalar(query)
        if not product:
            raise NotFoundError("Product not found")
        if product.status != "active":
            raise ValidationError("Product is not active")
        return product

    def _stock(self, product: Product, amount: Decimal, movement_type: str, reference_type: str, reference_id: str, reason: str) -> None:
        current = dec(product.current_stock)
        new = qty(current + amount)
        if new < 0:
            raise InsufficientStockError(f"Insufficient stock for {product.name}")
        product.current_stock = new
        self.db.add(StockMovement(id=uid("STM"), product_id=product.id, movement_type=movement_type, quantity=qty(abs(amount)), previous_stock=current, new_stock=new, reference_type=reference_type, reference_id=reference_id, reason=reason))

    def _customer_balance(self, customer_id: str) -> Decimal:
        customer = self.db.get(Customer, customer_id)
        if not customer:
            raise NotFoundError("Customer not found")
        entries = self.db.scalars(select(CustomerLedgerEntry).where(CustomerLedgerEntry.customer_id == customer_id).order_by(CustomerLedgerEntry.entry_date, CustomerLedgerEntry.created_at)).all()
        if entries:
            return dec(entries[-1].balance_after)
        return dec(customer.opening_balance)

    def _supplier_balance(self, supplier_id: str) -> Decimal:
        supplier = self.db.get(Supplier, supplier_id)
        if not supplier:
            raise NotFoundError("Supplier not found")
        entries = self.db.scalars(select(SupplierLedgerEntry).where(SupplierLedgerEntry.supplier_id == supplier_id).order_by(SupplierLedgerEntry.entry_date, SupplierLedgerEntry.created_at)).all()
        if entries:
            return dec(entries[-1].balance_after)
        return dec(supplier.opening_balance)

    def _bank(self, bank_id: str, lock: bool = False) -> BankAccount:
        query = select(BankAccount).where(BankAccount.id == bank_id)
        if lock:
            query = query.with_for_update()
        bank = self.db.scalar(query)
        if not bank:
            raise NotFoundError("Bank not found")
        return bank

    def _bank_balance(self, bank_id: str, lock: bool = False) -> Decimal:
        bank = self._bank(bank_id, lock)
        rows = self.db.scalars(select(BankTransaction).where(BankTransaction.bank_account_id == bank_id)).all()
        balance = dec(bank.opening_balance)
        for row in rows:
            balance += dec(row.amount) if row.type in {"Deposit", "Transfer In", "Customer Payment"} else -dec(row.amount)
        return balance

    def ensure_banks(self) -> list[BankAccount]:
        for name in BANK_NAMES:
            if not self.db.scalar(select(BankAccount).where(BankAccount.name == name)):
                self.db.add(BankAccount(id=uid("BNK"), name=name, opening_balance=Decimal("0.00")))
        self._commit()
        return self.db.scalars(select(BankAccount).where(BankAccount.name.in_(BANK_NAMES)).order_by(BankAccount.name)).all()

    def sale(self, data: dict, user_id: str | None = None) -> dict:
        when = dt(data.get("date"))
        self._closed(when)
        sale_type = "retail" if str(data.get("sale_type", data.get("saleType", "installment"))).lower() == "retail" else "installment"
        customer = self.db.get(Customer, data.get("customer_id", data.get("customerId"))) if sale_type == "installment" else None
        if sale_type == "installment" and (not customer or customer.status != "Active"):
            raise NotFoundError("Active customer is required for an installment sale")
        items_data = data.get("items") or []
        if not items_data:
            raise ValidationError("Sale must contain at least one item")
        sale_id = uid("SAL")
        invoice = data.get("invoice_number", data.get("invoiceNumber")) or self.next_number("invoice_prefix", "INV", Sale, "invoice_number")
        if self.db.scalar(select(Sale).where(Sale.invoice_number == invoice)):
            raise ConflictError("Duplicate invoice number")
        items: list[SaleItem] = []
        subtotal = Decimal("0")
        try:
            for raw in items_data:
                product = self._product(str(raw.get("product_id", raw.get("productId"))), lock=True)
                quantity = qty(dec(raw.get("quantity")))
                rate = money(dec(raw.get("sale_rate", raw.get("rate"))))
                discount = money(dec(raw.get("discount")))
                if quantity <= 0 or rate <= 0 or discount < 0 or quantity * rate < discount:
                    raise ValidationError("Invalid sale item")
                amount = money(quantity * rate - discount)
                subtotal += quantity * rate
                items.append(SaleItem(id=uid("SIT"), sale_id=sale_id, product_id=product.id, product_name=product.name, quantity=quantity, rate=rate, discount=discount, amount=amount))
            total = max(Decimal("0"), money(subtotal - dec(data.get("discount"))))
            paid = money(dec(data.get("paid")))
            if paid < 0 or paid > total:
                raise ValidationError("Paid amount must be between zero and the sale total")
            remaining = total - paid
            sale = Sale(id=sale_id, invoice_number=invoice, customer_id=customer.id if customer else None, customer_name=str(data.get("customer_name", data.get("customerName", customer.name if customer else "Walk-in"))), sale_type=sale_type, sale_date=when, subtotal=money(subtotal), discount=money(dec(data.get("discount"))), total=total, paid=paid, remaining=remaining, payment_status="paid" if remaining == 0 else "partial" if paid else "unpaid", notes=data.get("notes"), status="completed")
            self.db.add(sale)
            self.db.add_all(items)
            for item in items:
                self._stock(self._product(item.product_id, lock=True), -dec(item.quantity), StockMovementType.SALE_OUT.value, "sale", sale_id, f"Sale {invoice}")
            if customer:
                balance = self._customer_balance(customer.id) + total - paid
                self.db.add(CustomerLedgerEntry(id=uid("CLE"), customer_id=customer.id, entry_date=when, description=f"Sale {invoice}", sale_amount=total, payment_amount=paid, balance_after=balance, reference_type="sale", reference_id=sale_id))
            if paid and customer:
                self._financial_payment("customer", customer.id, paid, data, when, sale_id)
            elif paid:
                method = str(data.get("payment_method", data.get("paymentMethod", "Cash"))).title()
                if method == "Cash":
                    self.db.add(CashTransaction(id=uid("CSH"), transaction_date=when, type="cash_in", category="retail_sale", description=f"Walk-in Sale {invoice}", amount=paid, reference_type="sale", reference_id=sale_id))
                elif method == "Bank":
                    bank = self._bank(data.get("bank_account_id", data.get("bankAccountId")), lock=True)
                    self.db.add(BankTransaction(id=uid("BTR"), bank_account_id=bank.id, transaction_date=when, type="Customer Payment", amount=paid, reference_type="sale", reference_id=sale_id))
                else:
                    raise ValidationError("Payment method must be Cash or Bank")
            self._audit("create", "sale", sale_id, user_id, {"invoice_number": invoice, "total": str(total)})
            self._commit()
            return self.sale_detail(sale_id)
        except Exception:
            self._rollback()
            raise

    def _financial_payment(self, party: str, party_id: str | None, amount: Decimal, data: dict, when: datetime, reference_id: str) -> None:
        method = str(data.get("payment_method", data.get("paymentMethod", "Cash"))).title()
        if method not in {"Cash", "Bank"}:
            raise ValidationError("Payment method must be Cash or Bank")
        if party == "customer":
            row = CustomerPayment(id=uid("CPY"), customer_id=party_id, payment_date=when, amount=amount, payment_method=method, reference=data.get("reference"), notes=data.get("notes"), sale_id=reference_id)
            cash_type, category, label = "cash_in", "customer_payment", "Customer Payment"
        else:
            row = SupplierPayment(id=uid("SPY"), supplier_id=party_id, payment_date=when, amount=amount, payment_method=method, reference=data.get("reference"), notes=data.get("notes"), purchase_id=reference_id)
            cash_type, category, label = "cash_out", "supplier_payment", "Supplier Payment"
        self.db.add(row)
        if method == "Cash":
            self.db.add(CashTransaction(id=uid("CSH"), transaction_date=when, type=cash_type, category=category, description=label, amount=amount, reference_type=party + "_payment", reference_id=row.id))
        else:
            bank_id = data.get("bank_account_id", data.get("bankAccountId"))
            bank = self._bank(bank_id, lock=True)
            if party == "supplier" and self._bank_balance(bank.id, lock=True) < amount:
                raise InsufficientBankBalanceError("Insufficient bank balance")
            row.bank_account_id = bank.id
            self.db.add(BankTransaction(id=uid("BTR"), bank_account_id=bank.id, transaction_date=when, type="Customer Payment" if party == "customer" else "Supplier Payment", amount=amount, reference=data.get("reference"), note=data.get("notes"), reference_type=party + "_payment", reference_id=row.id))

    def purchase(self, data: dict, user_id: str | None = None) -> dict:
        when = dt(data.get("date"))
        self._closed(when)
        supplier = self.db.get(Supplier, data.get("supplier_id", data.get("supplierId")))
        if not supplier or supplier.status != "Active":
            raise NotFoundError("Active supplier is required")
        raw_items = data.get("items") or []
        if not raw_items:
            raise ValidationError("Purchase must contain at least one item")
        purchase_id = uid("PUR")
        number = data.get("purchase_number", data.get("purchaseNumber")) or self.next_number("purchase_prefix", "PUR", Purchase, "purchase_number")
        if self.db.scalar(select(Purchase).where(Purchase.purchase_number == number)):
            raise ConflictError("Duplicate purchase number")
        try:
            items: list[PurchaseItem] = []
            subtotal = Decimal("0")
            for raw in raw_items:
                product = self._product(str(raw.get("product_id", raw.get("productId"))), lock=True)
                quantity = qty(dec(raw.get("quantity")))
                rate = money(dec(raw.get("purchase_rate", raw.get("rate"))))
                if quantity <= 0 or rate < 0:
                    raise ValidationError("Invalid purchase item")
                amount = money(quantity * rate)
                subtotal += amount
                items.append(PurchaseItem(id=uid("PIT"), purchase_id=purchase_id, product_id=product.id, product_name=product.name, quantity=quantity, rate=rate, amount=amount))
            discount = money(dec(data.get("discount")))
            total = max(Decimal("0"), money(subtotal - discount))
            paid = money(dec(data.get("paid")))
            if paid < 0 or paid > total:
                raise ValidationError("Paid amount must be between zero and the purchase total")
            purchase = Purchase(id=purchase_id, purchase_number=number, supplier_id=supplier.id, purchase_date=when, subtotal=money(subtotal), discount=discount, total=total, paid=paid, remaining=total - paid, payment_status="paid" if paid == total else "partial" if paid else "unpaid", notes=data.get("notes"), status="completed")
            self.db.add(purchase)
            self.db.add_all(items)
            for item in items:
                product = self._product(item.product_id, lock=True)
                self._stock(product, dec(item.quantity), StockMovementType.PURCHASE_IN.value, "purchase", purchase_id, f"Purchase {number}")
                product.purchase_price = item.rate
            balance = self._supplier_balance(supplier.id) + total - paid
            self.db.add(SupplierLedgerEntry(id=uid("SLE"), supplier_id=supplier.id, entry_date=when, description=f"Purchase {number}", purchase_amount=total, payment_amount=paid, balance_after=balance, reference_type="purchase", reference_id=purchase_id))
            if paid:
                self._financial_payment("supplier", supplier.id, paid, data, when, purchase_id)
            self._audit("create", "purchase", purchase_id, user_id, {"purchase_number": number, "total": str(total)})
            self._commit()
            return self.purchase_detail(purchase_id)
        except Exception:
            self._rollback()
            raise

    def next_number(self, setting_key: str, default: str, model: type, field: str) -> str:
        prefix_row = self.db.get(AppSetting, setting_key)
        prefix = prefix_row.value if prefix_row else default
        latest = self.db.scalar(select(getattr(model, field)).where(getattr(model, field).like(f"{prefix}-%")).order_by(getattr(model, field).desc()).with_for_update())
        try:
            number = int(str(latest).rsplit("-", 1)[1]) + 1 if latest else 1001
        except (IndexError, ValueError):
            number = 1001
        return f"{prefix}-{number}"

    def sale_detail(self, sale_id: str) -> dict:
        sale = self.db.get(Sale, sale_id)
        if not sale:
            raise NotFoundError("Sale not found")
        return {"id": sale.id, "invoice_number": sale.invoice_number, "customer_id": sale.customer_id, "customer_name": sale.customer_name, "sale_type": sale.sale_type, "date": sale.sale_date, "subtotal": sale.subtotal, "discount": sale.discount, "total": sale.total, "paid": sale.paid, "remaining": sale.remaining, "payment_status": sale.payment_status, "status": sale.status, "items": [{"id": i.id, "product_id": i.product_id, "product_name": i.product_name, "quantity": i.quantity, "sale_rate": i.rate, "discount": i.discount, "line_amount": i.amount} for i in sale.items]}

    def purchase_detail(self, purchase_id: str) -> dict:
        purchase = self.db.get(Purchase, purchase_id)
        if not purchase:
            raise NotFoundError("Purchase not found")
        return {"id": purchase.id, "purchase_number": purchase.purchase_number, "supplier_id": purchase.supplier_id, "date": purchase.purchase_date, "subtotal": purchase.subtotal, "discount": purchase.discount, "total": purchase.total, "paid": purchase.paid, "remaining": purchase.remaining, "payment_status": purchase.payment_status, "status": purchase.status, "items": [{"id": i.id, "product_id": i.product_id, "product_name": i.product_name, "quantity": i.quantity, "rate": i.rate, "line_amount": i.amount} for i in purchase.items]}

    def payment(self, party: str, party_id: str, data: dict, user_id: str | None = None) -> dict:
        when = dt(data.get("date"))
        self._closed(when)
        amount = money(dec(data.get("amount")))
        if amount <= 0:
            raise ValidationError("Amount must be positive")
        balance = self._customer_balance(party_id) if party == "customer" else self._supplier_balance(party_id)
        if amount > balance:
            raise PaymentExceedsBalanceError("Payment exceeds outstanding balance")
        try:
            if party == "customer":
                self.db.add(CustomerLedgerEntry(id=uid("CLE"), customer_id=party_id, entry_date=when, description=data.get("notes") or "Customer payment", payment_amount=amount, balance_after=balance - amount, reference_type="customer_payment"))
            else:
                self.db.add(SupplierLedgerEntry(id=uid("SLE"), supplier_id=party_id, entry_date=when, description=data.get("notes") or "Supplier payment", payment_amount=amount, balance_after=balance - amount, reference_type="supplier_payment"))
            self._financial_payment(party, party_id, amount, data, when, uid("PAY"))
            self._audit("create", f"{party}_payment", party_id, user_id, {"amount": str(amount)})
            if not data.get("_batch"):
                self._commit()
            return {"party_id": party_id, "type": party, "amount": amount, "date": when, "remaining": balance - amount}
        except Exception:
            self._rollback()
            raise

    def sale_return(self, sale_id: str, data: dict, user_id: str | None = None) -> dict:
        sale = self.db.get(Sale, sale_id)
        if not sale or sale.status != "completed":
            raise NotFoundError("Completed sale not found")
        when = dt(data.get("date"))
        self._closed(when)
        return_id = uid("SRT")
        try:
            total = Decimal("0")
            return_items: list[SaleReturnItem] = []
            for raw in data.get("items") or []:
                item = self.db.get(SaleItem, raw.get("sale_item_id", raw.get("saleItemId")))
                if not item or item.sale_id != sale.id:
                    raise ValidationError("Sale item does not belong to this sale")
                requested = qty(dec(raw.get("quantity")))
                returned = self.db.scalar(select(func.coalesce(func.sum(SaleReturnItem.quantity), 0)).where(SaleReturnItem.sale_item_id == item.id)) or 0
                if requested <= 0 or requested > dec(item.quantity) - dec(returned):
                    raise ValidationError("Return quantity exceeds eligible quantity")
                amount = money(requested * dec(item.rate))
                total += amount
                return_items.append(SaleReturnItem(id=uid("SRI"), return_id=return_id, sale_item_id=item.id, product_id=item.product_id, product_name=item.product_name, quantity=requested, rate=item.rate, amount=amount))
            if not return_items:
                raise ValidationError("Return must contain at least one item")
            row = SaleReturn(id=return_id, sale_id=sale.id, customer_id=sale.customer_id, return_date=when, amount=money(total), reference=data.get("reference"), notes=data.get("notes"), status="completed")
            self.db.add(row)
            self.db.add_all(return_items)
            for item in return_items:
                self._stock(self._product(item.product_id, lock=True), dec(item.quantity), StockMovementType.SALE_RETURN_IN.value, "sale_return", return_id, f"Return {sale.invoice_number}")
            if sale.customer_id:
                balance = self._customer_balance(sale.customer_id) - total
                self.db.add(CustomerLedgerEntry(id=uid("CLE"), customer_id=sale.customer_id, entry_date=when, description=f"Return {sale.invoice_number}", return_amount=total, balance_after=balance, reference_type="sale_return", reference_id=return_id))
            self._audit("return", "sale", sale.id, user_id, {"amount": str(total)})
            self._commit()
            return {"id": return_id, "sale_id": sale.id, "amount": total, "items": return_items}
        except Exception:
            self._rollback()
            raise

    def purchase_return(self, purchase_id: str, data: dict, user_id: str | None = None) -> dict:
        purchase = self.db.get(Purchase, purchase_id)
        if not purchase or purchase.status != "completed":
            raise NotFoundError("Completed purchase not found")
        when = dt(data.get("date"))
        self._closed(when)
        return_id = uid("PRT")
        try:
            total = Decimal("0")
            return_items: list[PurchaseReturnItem] = []
            for raw in data.get("items") or []:
                item = self.db.get(PurchaseItem, raw.get("purchase_item_id", raw.get("purchaseItemId")))
                if not item or item.purchase_id != purchase.id:
                    raise ValidationError("Purchase item does not belong to this purchase")
                requested = qty(dec(raw.get("quantity")))
                returned = self.db.scalar(select(func.coalesce(func.sum(PurchaseReturnItem.quantity), 0)).where(PurchaseReturnItem.purchase_item_id == item.id)) or 0
                product = self._product(item.product_id, lock=True)
                if requested <= 0 or requested > dec(item.quantity) - dec(returned):
                    raise ValidationError("Return quantity exceeds eligible quantity")
                if requested > dec(product.current_stock):
                    raise InsufficientStockError(f"Insufficient current stock for {product.name}")
                amount = money(requested * dec(item.rate))
                total += amount
                return_items.append(PurchaseReturnItem(id=uid("PRI"), return_id=return_id, purchase_item_id=item.id, product_id=item.product_id, product_name=item.product_name, quantity=requested, rate=item.rate, amount=amount))
            if not return_items:
                raise ValidationError("Return must contain at least one item")
            self.db.add(PurchaseReturn(id=return_id, purchase_id=purchase.id, supplier_id=purchase.supplier_id, return_date=when, amount=money(total), reference=data.get("reference"), notes=data.get("notes"), status="completed"))
            self.db.add_all(return_items)
            for item in return_items:
                self._stock(self._product(item.product_id, lock=True), -dec(item.quantity), StockMovementType.PURCHASE_RETURN_OUT.value, "purchase_return", return_id, f"Return {purchase.purchase_number}")
            balance = self._supplier_balance(purchase.supplier_id) - total
            self.db.add(SupplierLedgerEntry(id=uid("SLE"), supplier_id=purchase.supplier_id, entry_date=when, description=f"Return {purchase.purchase_number}", return_amount=total, balance_after=balance, reference_type="purchase_return", reference_id=return_id))
            self._audit("return", "purchase", purchase.id, user_id, {"amount": str(total)})
            self._commit()
            return {"id": return_id, "purchase_id": purchase.id, "amount": total, "items": return_items}
        except Exception:
            self._rollback()
            raise

    def bank_movement(self, kind: str, data: dict, user_id: str | None = None) -> dict:
        when = dt(data.get("date"))
        self._closed(when)
        amount = money(dec(data.get("amount")))
        if amount <= 0:
            raise ValidationError("Amount must be positive")
        try:
            if kind == "transfer":
                source_id, target_id = data.get("from_bank_id", data.get("fromBankId")), data.get("to_bank_id", data.get("toBankId"))
                if not source_id or source_id == target_id:
                    raise ValidationError("Select two different banks")
                source = self._bank(source_id, True)
                self._bank(target_id, True)
                if self._bank_balance(source.id, True) < amount:
                    raise InsufficientBankBalanceError("Insufficient source bank balance")
                self.db.add(BankTransaction(id=uid("BTR"), bank_account_id=source_id, transaction_date=when, type="Transfer Out", amount=amount, reference=data.get("reference"), note=data.get("note"), reference_type="bank_transfer"))
                self.db.add(BankTransaction(id=uid("BTR"), bank_account_id=target_id, transaction_date=when, type="Transfer In", amount=amount, reference=data.get("reference"), note=data.get("note"), reference_type="bank_transfer"))
            else:
                bank_id = data.get("bank_id", data.get("bankId"))
                bank = self._bank(bank_id, True)
                if kind == "withdrawal" and self._bank_balance(bank.id, True) < amount:
                    raise InsufficientBankBalanceError("Insufficient bank balance")
                if kind == "deposit":
                    self.db.add(CashTransaction(id=uid("CSH"), transaction_date=when, type="cash_out", category="bank_deposit", description=f"Deposit to {bank.name}", amount=amount, reference_type="bank_deposit"))
                    tx_type = "Deposit"
                else:
                    self.db.add(CashTransaction(id=uid("CSH"), transaction_date=when, type="cash_in", category="bank_withdrawal", description=f"Withdrawal from {bank.name}", amount=amount, reference_type="bank_withdrawal"))
                    tx_type = "Withdrawal"
                self.db.add(BankTransaction(id=uid("BTR"), bank_account_id=bank.id, transaction_date=when, type=tx_type, amount=amount, reference=data.get("reference"), note=data.get("note"), reference_type="cash_book"))
            self._audit(kind, "bank", None, user_id, {"amount": str(amount)})
            self._commit()
            return {"type": kind, "amount": amount, "date": when}
        except Exception:
            self._rollback()
            raise

    def expense(self, data: dict, user_id: str | None = None) -> dict:
        when = dt(data.get("date"))
        self._closed(when)
        amount = money(dec(data.get("amount")))
        category = str(data.get("category", "")).strip()
        subtype = str(data.get("subtype", data.get("expense_subtype", "Other Expense"))).strip()
        if amount <= 0 or category not in {"Home Expense", "Shop Expense", "Pocket Money"}:
            raise ValidationError("Invalid expense")
        if subtype == "Extra Expense" and not str(data.get("custom_subtype", data.get("customSubtype", ""))).strip():
            raise ValidationError("Extra Expense Name is required")
        try:
            row = Expense(id=uid("EXP"), category=category, subtype=subtype, custom_subtype=data.get("custom_subtype", data.get("customSubtype")), amount=amount, expense_date=when, description=data.get("description", data.get("note")), payment_method=str(data.get("payment_method", data.get("paymentMethod", "Cash"))))
            self.db.add(row)
            method = row.payment_method.title()
            if method == "Cash":
                self.db.add(CashTransaction(id=uid("CSH"), transaction_date=when, type="cash_out", category="expense", description=row.description or subtype, amount=amount, reference_type="expense", reference_id=row.id))
            elif method == "Bank":
                bank = self._bank(data.get("bank_id", data.get("bankId")), True)
                if self._bank_balance(bank.id, True) < amount:
                    raise InsufficientBankBalanceError("Insufficient bank balance")
                row.bank_account_id = bank.id
                self.db.add(BankTransaction(id=uid("BTR"), bank_account_id=bank.id, transaction_date=when, type="Expense", amount=amount, reference_type="expense", reference_id=row.id))
            else:
                raise ValidationError("Payment method must be Cash or Bank")
            self._audit("create", "expense", row.id, user_id, {"amount": str(amount)})
            if not data.get("_batch"):
                self._commit()
            return {"id": row.id, "category": category, "subtype": subtype, "custom_subtype": row.custom_subtype, "amount": amount, "date": when}
        except Exception:
            self._rollback()
            raise

    def cash_credit(self, action: str, data: dict, user_id: str | None = None) -> dict:
        try:
            if action == "create":
                row = CashCreditPerson(id=uid("CCP"), name=str(data.get("name", "")).strip(), phone=data.get("phone"), total_cash_given=money(dec(data.get("amount_given", data.get("amountGiven")))), total_received=Decimal("0"))
                if not row.name or row.total_cash_given <= 0:
                    raise ValidationError("Name and positive amount are required")
                self.db.add(row)
                self.db.add(CashCreditTransaction(id=uid("CCT"), person_id=row.id, transaction_date=dt(data.get("date")), type="Credit Given", amount=row.total_cash_given, notes=data.get("note")))
                self.db.add(CashTransaction(id=uid("CSH"), transaction_date=dt(data.get("date")), type="cash_out", category="cash_credit_given", description=f"Cash Credit Given - {row.name}", amount=row.total_cash_given, reference_type="cash_credit", reference_id=row.id))
            else:
                row = self.db.scalar(select(CashCreditPerson).where(CashCreditPerson.id == data.get("person_id", data.get("personId"))).with_for_update())
                if not row:
                    raise NotFoundError("Cash credit person not found")
                amount = money(dec(data.get("amount")))
                remaining = dec(row.total_cash_given) - dec(row.total_received)
                if amount <= 0 or (action == "receive" and amount > remaining):
                    raise ValidationError("Invalid cash credit repayment")
                if action == "give":
                    row.total_cash_given = dec(row.total_cash_given) + amount
                    tx_type, cash_type, category = "Credit Given", "cash_out", "cash_credit_given"
                else:
                    row.total_received = dec(row.total_received) + amount
                    tx_type, cash_type, category = "Payment Received", "cash_in", "cash_credit_received"
                self.db.add(CashCreditTransaction(id=uid("CCT"), person_id=row.id, transaction_date=dt(data.get("date")), type=tx_type, amount=amount, notes=data.get("note")))
                self.db.add(CashTransaction(id=uid("CSH"), transaction_date=dt(data.get("date")), type=cash_type, category=category, description=f"{tx_type} - {row.name}", amount=amount, reference_type="cash_credit", reference_id=row.id))
            self._audit(action, "cash_credit", row.id, user_id)
            self._commit()
            return {"id": row.id, "name": row.name, "total_cash_given": row.total_cash_given, "total_received": row.total_received, "remaining": dec(row.total_cash_given) - dec(row.total_received)}
        except Exception:
            self._rollback()
            raise

    def daily(self, day: str) -> dict:
        when = dt(day)
        closes = self.db.scalar(select(CashDayClose).where(func.date(CashDayClose.date) == when.date()))
        rows = self.db.scalars(select(CashTransaction).where(func.date(CashTransaction.transaction_date) == when.date()).order_by(CashTransaction.created_at)).all()
        if closes:
            opening = dec(closes.opening_balance)
        else:
            prior = self.db.scalar(select(CashDayClose).where(CashDayClose.date < when).order_by(CashDayClose.date.desc()))
            configured = self.db.get(AppSetting, "opening_cash")
            opening = dec(prior.closing_balance) if prior else dec(configured.value if configured else 0)
        cash_in = sum((dec(r.amount) for r in rows if r.type == "cash_in"), Decimal("0"))
        cash_out = sum((dec(r.amount) for r in rows if r.type == "cash_out"), Decimal("0"))
        return {"date": when.date(), "opening_balance": opening, "cash_in": cash_in, "cash_out": cash_out, "closing_balance": opening + cash_in - cash_out, "finalized": bool(closes), "actual_cash": closes.actual_cash if closes else None, "difference": closes.difference if closes else None, "items": rows}

    def finalize(self, data: dict, user_id: str | None = None) -> dict:
        day = dt(data.get("date"))
        if self.db.scalar(select(CashDayClose).where(func.date(CashDayClose.date) == day.date())):
            raise ConflictError("Cash day is already finalized")
        book = self.daily(str(day.date()))
        actual = data.get("actual_cash", data.get("actualCash"))
        row = CashDayClose(date=day, opening_balance=book["opening_balance"], cash_in=book["cash_in"], cash_out=book["cash_out"], closing_balance=book["closing_balance"], actual_cash=money(dec(actual)) if actual not in (None, "") else None, difference=money(dec(actual) - book["closing_balance"]) if actual not in (None, "") else None, finalized_at=datetime.utcnow())
        self.db.add(row)
        self._audit("finalize", "cash_day", str(day.date()), user_id)
        self._commit()
        return self.daily(str(day.date()))