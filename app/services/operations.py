from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import EXPENSE_SUBTYPES, StockMovementType
from app.core.exceptions import (
    ConflictError,
    InsufficientBankBalanceError,
    InsufficientStockError,
    NotFoundError,
    PaymentExceedsBalanceError,
    ValidationError,
)
from app.core.money import MONEY_QUANTUM, ZERO_MONEY, money as quantize_money, to_decimal
from app.models import (
    AppSetting,
    AuditLog,
    BankAccount,
    BankTransaction,
    CashBookDraft,
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

MONEY = MONEY_QUANTUM
QTY = Decimal("0.001")
BANK_NAMES = ("Meezan Bank", "Bank Alfalah")


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def dec(value: object, default: str = "0") -> Decimal:
    return to_decimal(default if value in (None, "") else value)


def dt(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return datetime.fromisoformat(str(value)) if value else datetime.utcnow()


def money(value: Decimal) -> Decimal:
    return quantize_money(value)


def qty(value: Decimal) -> Decimal:
    return value.quantize(QTY)


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


class OperationsService:
    def __init__(self, db: Session, shop_id: str | None = None):
        self.db = db
        self.shop_id = shop_id or db.info.get("shop_id")

    def _scope(self, model: type, query=None):
        if self.shop_id is None:
            return query if query is not None else select(model)
        if query is None:
            query = select(model)
        return query.where(model.shop_id == self.shop_id)

    def _ensure_same_shop(self, row: object | None, entity_name: str) -> object | None:
        if row is None:
            return None
        if getattr(row, "shop_id", None) is not None and getattr(row, "shop_id") != self.shop_id:
            raise NotFoundError(f"{entity_name} not found")
        return row

    def _required_shop_id(self, shop_id: str | None = None) -> str:
        resolved = shop_id or self.shop_id
        if not resolved:
            raise ValidationError("Authenticated shop context is required")
        return resolved

    def _commit(self) -> None:
        self.db.commit()

    def _rollback(self) -> None:
        self.db.rollback()

    def _audit(self, action: str, entity_type: str, entity_id: str | None, user_id: str | None, metadata: dict | None = None) -> None:
        self.db.add(AuditLog(id=uid("AUD"), shop_id=self.shop_id, action=action, entity_type=entity_type, entity_id=entity_id, user_id=user_id, metadata_json=metadata))

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

    def _product(self, product_id: str, lock: bool = False, shop_id: str | None = None) -> Product:
        shop_id = shop_id or self.shop_id
        query = select(Product).where(Product.id == product_id)
        if shop_id:
            query = query.where(Product.shop_id == shop_id)
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
        self.db.add(StockMovement(id=uid("STM"), shop_id=product.shop_id, product_id=product.id, movement_type=movement_type, quantity=qty(abs(amount)), previous_stock=current, new_stock=new, reference_type=reference_type, reference_id=reference_id, reason=reason))

    def _customer_balance(self, customer_id: str, shop_id: str | None = None) -> Decimal:
        shop_id = shop_id or self.shop_id
        customer = self.db.get(Customer, customer_id)
        if not customer:
            raise NotFoundError("Customer not found")
        if shop_id and customer.shop_id != shop_id:
            raise NotFoundError("Customer not found")
        sales = self.db.scalar(select(func.sum(Sale.total)).where(Sale.customer_id == customer_id, Sale.shop_id == customer.shop_id, Sale.sale_type == "installment", Sale.status == "completed")) or ZERO_MONEY
        payments = self.db.scalar(select(func.sum(CustomerPayment.amount)).where(CustomerPayment.customer_id == customer_id, CustomerPayment.shop_id == customer.shop_id, CustomerPayment.status == "completed")) or ZERO_MONEY
        returns = self.db.scalar(select(func.sum(SaleReturn.amount)).where(SaleReturn.customer_id == customer_id, SaleReturn.shop_id == customer.shop_id, SaleReturn.status == "completed")) or ZERO_MONEY
        return dec(customer.opening_balance) + dec(sales) - dec(payments) - dec(returns)

    def _supplier_balance(self, supplier_id: str, shop_id: str | None = None) -> Decimal:
        shop_id = shop_id or self.shop_id
        supplier = self.db.get(Supplier, supplier_id)
        if not supplier:
            raise NotFoundError("Supplier not found")
        if shop_id and supplier.shop_id != shop_id:
            raise NotFoundError("Supplier not found")
        purchases = self.db.scalar(select(func.sum(Purchase.total)).where(Purchase.supplier_id == supplier_id, Purchase.shop_id == supplier.shop_id, Purchase.status == "completed")) or ZERO_MONEY
        payments = self.db.scalar(select(func.sum(SupplierPayment.amount)).where(SupplierPayment.supplier_id == supplier_id, SupplierPayment.shop_id == supplier.shop_id, SupplierPayment.status == "completed")) or ZERO_MONEY
        returns = self.db.scalar(select(func.sum(PurchaseReturn.amount)).where(PurchaseReturn.supplier_id == supplier_id, PurchaseReturn.shop_id == supplier.shop_id, PurchaseReturn.status == "completed")) or ZERO_MONEY
        return dec(supplier.opening_balance) + dec(purchases) - dec(payments) - dec(returns)

    def _bank(self, bank_id: str, lock: bool = False, shop_id: str | None = None) -> BankAccount:
        shop_id = shop_id or self.shop_id
        query = select(BankAccount).where(BankAccount.id == bank_id)
        if shop_id:
            query = query.where(BankAccount.shop_id == shop_id)
        if lock:
            query = query.with_for_update()
        bank = self.db.scalar(query)
        if not bank:
            raise NotFoundError("Bank not found")
        return bank

    def _bank_balance(self, bank_id: str, lock: bool = False, shop_id: str | None = None) -> Decimal:
        bank = self._bank(bank_id, lock, shop_id=shop_id)
        rows = self.db.scalars(
            select(BankTransaction).where(
                BankTransaction.bank_account_id == bank_id,
                BankTransaction.shop_id == (shop_id or bank.shop_id),
            )
        ).all()
        balance = dec(bank.opening_balance)
        for row in rows:
            balance += dec(row.amount) if row.type in {"Deposit", "Transfer In", "Customer Payment"} else -dec(row.amount)
        return balance

    def ensure_banks(self, shop_id: str | None = None) -> list[BankAccount]:
        shop_id = shop_id or self.shop_id
        for name in BANK_NAMES:
            if not self.db.scalar(select(BankAccount).where(BankAccount.name == name, BankAccount.shop_id == shop_id)):
                self.db.add(BankAccount(id=uid("BNK"), shop_id=shop_id, name=name, opening_balance=Decimal("0.00")))
        self._commit()
        return self.db.scalars(select(BankAccount).where(BankAccount.name.in_(BANK_NAMES), BankAccount.shop_id == shop_id).order_by(BankAccount.name)).all()

    def sale(self, data: dict, user_id: str | None = None, shop_id: str | None = None) -> dict:
        shop_id = self._required_shop_id(shop_id)
        when = dt(data.get("date"))
        sale_type = "retail" if str(data.get("sale_type", data.get("saleType", "installment"))).lower() == "retail" else "installment"
        customer = self.db.get(Customer, data.get("customer_id", data.get("customerId"))) if sale_type == "installment" else None
        if customer and shop_id and customer.shop_id != shop_id:
            raise NotFoundError("Active customer is required for an installment sale")
        if sale_type == "installment" and (not customer or customer.status != "Active"):
            raise NotFoundError("Active customer is required for an installment sale")
        items_data = data.get("items") or []
        if not items_data:
            raise ValidationError("Sale must contain at least one item")
        sale_id = uid("SAL")
        invoice = data.get("invoice_number", data.get("invoiceNumber")) or self.next_number("invoice_prefix", "INV", Sale, "invoice_number")
        if self.db.scalar(select(Sale).where(Sale.invoice_number == invoice, Sale.shop_id == shop_id)):
            raise ConflictError("Duplicate invoice number")
        items: list[SaleItem] = []
        subtotal = Decimal("0")
        try:
            for raw in items_data:
                product = self._product(str(raw.get("product_id", raw.get("productId"))), lock=True, shop_id=shop_id)
                quantity = qty(dec(raw.get("quantity")))
                rate = money(dec(raw.get("sale_rate", raw.get("rate"))))
                discount = money(dec(raw.get("discount")))
                if quantity <= 0 or rate <= 0 or discount < 0 or quantity * rate < discount:
                    raise ValidationError("Invalid sale item")
                amount = money(quantity * rate - discount)
                subtotal += quantity * rate
                items.append(SaleItem(id=uid("SIT"), shop_id=shop_id, sale_id=sale_id, product_id=product.id, product_name=product.name, quantity=quantity, rate=rate, discount=discount, amount=amount))
            total = max(Decimal("0"), money(subtotal - dec(data.get("discount"))))
            paid = money(dec(data.get("paid")))
            if paid < 0 or paid > total:
                raise ValidationError("Paid amount must be between zero and the sale total")
            remaining = total - paid
            sale = Sale(id=sale_id, shop_id=shop_id, invoice_number=invoice, customer_id=customer.id if customer else None, customer_name=str(data.get("customer_name", data.get("customerName", customer.name if customer else "Walk-in"))), sale_type=sale_type, sale_date=when, subtotal=money(subtotal), discount=money(dec(data.get("discount"))), total=total, paid=paid, remaining=remaining, payment_status="paid" if remaining == 0 else "partial" if paid else "unpaid", notes=data.get("notes"), status="completed")
            self.db.add(sale)
            self.db.flush()
            if sale.id != sale_id or self.db.get(Sale, sale.id) is None:
                raise RuntimeError("Sale was not persisted before child records")
            self.db.add_all(items)
            for item in items:
                self._stock(self._product(item.product_id, lock=True, shop_id=shop_id), -dec(item.quantity), StockMovementType.SALE_OUT.value, "sale", sale_id, f"Sale {invoice}")
            if customer:
                balance = self._customer_balance(customer.id, shop_id=shop_id) + total - paid
                self.db.add(CustomerLedgerEntry(id=uid("CLE"), shop_id=shop_id, customer_id=customer.id, entry_date=when, description=f"Sale {invoice}", sale_amount=total, payment_amount=paid, balance_after=balance, reference_type="sale", reference_id=sale_id))
            if paid and customer:
                self._financial_payment("customer", customer.id, paid, data, when, sale.id, sale=sale, shop_id=shop_id)
            elif paid:
                method = str(data.get("payment_method", data.get("paymentMethod", "Cash"))).title()
                if method == "Cash":
                    self.db.add(CashTransaction(id=uid("CSH"), shop_id=shop_id, transaction_date=when, type="cash_in", category="retail_sale", description=f"Walk-in Sale {invoice}", amount=paid, reference_type="sale", reference_id=sale_id))
                elif method == "Bank":
                    bank = self._bank(data.get("bank_account_id", data.get("bankAccountId")), lock=True, shop_id=shop_id)
                    self.db.add(BankTransaction(id=uid("BTR"), shop_id=shop_id, bank_account_id=bank.id, transaction_date=when, type="Customer Payment", amount=paid, reference_type="sale", reference_id=sale_id))
                else:
                    raise ValidationError("Payment method must be Cash or Bank")
            self._audit("create", "sale", sale_id, user_id, {"invoice_number": invoice, "total": str(total)})
            if data.get("_batch"):
                self.db.flush()
            else:
                self._commit()
            return self.sale_detail(sale_id, shop_id=shop_id)
        except Exception:
            self._rollback()
            raise

    def _financial_payment(self, party: str, party_id: str | None, amount: Decimal, data: dict, when: datetime, reference_id: str, sale: Sale | None = None, purchase_id: str | None = None, shop_id: str | None = None) -> str:
        shop_id = self._required_shop_id(shop_id)
        method = str(data.get("payment_method", data.get("paymentMethod", "Cash"))).title()
        if method not in {"Cash", "Bank"}:
            raise ValidationError("Payment method must be Cash or Bank")
        if party == "customer":
            row = CustomerPayment(id=uid("CPY"), shop_id=shop_id, customer_id=party_id, payment_date=when, amount=amount, payment_method=method, reference=data.get("reference"), notes=data.get("notes"), sale_id=sale.id if sale else None, bank_account_id=None, sale=sale)
            cash_type, category, label = "cash_in", "customer_payment", "Customer Payment"
        else:
            row = SupplierPayment(id=uid("SPY"), shop_id=shop_id, supplier_id=party_id, payment_date=when, amount=amount, payment_method=method, reference=data.get("reference"), notes=data.get("notes"), purchase_id=purchase_id)
            cash_type, category, label = "cash_out", "supplier_payment", "Supplier Payment"
        self.db.add(row)
        if method == "Cash":
            self.db.add(CashTransaction(id=uid("CSH"), shop_id=shop_id, transaction_date=when, type=cash_type, category=category, description=label, amount=amount, reference_type=party + "_payment", reference_id=row.id))
        else:
            bank_id = data.get("bank_account_id", data.get("bankAccountId"))
            bank = self._bank(bank_id, lock=True, shop_id=shop_id)
            if party == "supplier" and self._bank_balance(bank.id, lock=True, shop_id=shop_id) < amount:
                raise InsufficientBankBalanceError("Insufficient bank balance")
            row.bank_account_id = bank.id
            self.db.add(BankTransaction(id=uid("BTR"), shop_id=shop_id, bank_account_id=bank.id, transaction_date=when, type="Customer Payment" if party == "customer" else "Supplier Payment", amount=amount, reference=data.get("reference"), note=data.get("notes"), reference_type=party + "_payment", reference_id=row.id))
        return row.id

    def purchase(self, data: dict, user_id: str | None = None, shop_id: str | None = None) -> dict:
        shop_id = self._required_shop_id(shop_id)
        when = dt(data.get("date"))
        supplier = self.db.get(Supplier, data.get("supplier_id", data.get("supplierId")))
        if supplier and shop_id and supplier.shop_id != shop_id:
            raise NotFoundError("Active supplier is required")
        if not supplier or supplier.status != "Active":
            raise NotFoundError("Active supplier is required")
        raw_items = data.get("items") or []
        if not raw_items:
            raise ValidationError("Purchase must contain at least one item")
        purchase_id = uid("PUR")
        number = data.get("purchase_number", data.get("purchaseNumber")) or self.next_number("purchase_prefix", "PUR", Purchase, "purchase_number")
        if self.db.scalar(select(Purchase).where(Purchase.purchase_number == number, Purchase.shop_id == shop_id)):
            raise ConflictError("Duplicate purchase number")
        try:
            items: list[PurchaseItem] = []
            subtotal = Decimal("0")
            for raw in raw_items:
                product = self._product(str(raw.get("product_id", raw.get("productId"))), lock=True, shop_id=shop_id)
                quantity = qty(dec(raw.get("quantity")))
                rate = money(dec(raw.get("purchase_rate", raw.get("rate"))))
                if quantity <= 0 or rate < 0:
                    raise ValidationError("Invalid purchase item")
                amount = money(quantity * rate)
                subtotal += amount
                items.append(PurchaseItem(id=uid("PIT"), shop_id=shop_id, purchase_id=purchase_id, product_id=product.id, product_name=product.name, quantity=quantity, rate=rate, amount=amount))
            discount = money(dec(data.get("discount")))
            total = max(Decimal("0"), money(subtotal - discount))
            paid = money(dec(data.get("paid")))
            if paid < 0 or paid > total:
                raise ValidationError("Paid amount must be between zero and the purchase total")
            purchase = Purchase(id=purchase_id, shop_id=shop_id, purchase_number=number, supplier_id=supplier.id, purchase_date=when, subtotal=money(subtotal), discount=discount, total=total, paid=paid, remaining=total - paid, payment_status="paid" if paid == total else "partial" if paid else "unpaid", notes=data.get("notes"), status="completed")
            self.db.add(purchase)
            self.db.add_all(items)
            self.db.flush()
            for item in items:
                product = self._product(item.product_id, lock=True, shop_id=shop_id)
                self._stock(product, dec(item.quantity), StockMovementType.PURCHASE_IN.value, "purchase", purchase_id, f"Purchase {number}")
                product.purchase_price = item.rate
            balance = self._supplier_balance(supplier.id, shop_id=shop_id) + total - paid
            self.db.add(SupplierLedgerEntry(id=uid("SLE"), shop_id=shop_id, supplier_id=supplier.id, entry_date=when, description=f"Purchase {number}", purchase_amount=total, payment_amount=paid, balance_after=balance, reference_type="purchase", reference_id=purchase_id))
            if paid:
                self._financial_payment("supplier", supplier.id, paid, data, when, purchase_id, purchase_id=purchase_id, shop_id=shop_id)
            self._audit("create", "purchase", purchase_id, user_id, {"purchase_number": number, "total": str(total)})
            self._commit()
            return self.purchase_detail(purchase_id, shop_id=shop_id)
        except Exception:
            self._rollback()
            raise

    def sale_detail(self, sale_id: str, shop_id: str | None = None) -> dict:
        shop_id = shop_id or self.shop_id
        sale = self.db.get(Sale, sale_id)
        if not sale or (shop_id and sale.shop_id != shop_id):
            raise NotFoundError("Sale not found")
        returns = self.db.scalar(select(func.sum(SaleReturn.amount)).where(SaleReturn.sale_id == sale.id, SaleReturn.shop_id == sale.shop_id, SaleReturn.status == "completed")) or ZERO_MONEY
        current_remaining = max(Decimal("0.00"), money(dec(sale.total) - dec(sale.paid) - dec(returns)))
        previous_remaining = Decimal("0.00")
        if sale.customer_id and sale.sale_type == "installment":
            entry = self.db.scalar(select(CustomerLedgerEntry).where(CustomerLedgerEntry.reference_type == "sale", CustomerLedgerEntry.reference_id == sale.id, CustomerLedgerEntry.shop_id == sale.shop_id).order_by(CustomerLedgerEntry.created_at.desc()))
            previous_remaining = dec(entry.balance_after) - dec(entry.sale_amount) + dec(entry.payment_amount) if entry else self._customer_balance(sale.customer_id, shop_id=shop_id) - current_remaining
        return {"id": sale.id, "invoice_number": sale.invoice_number, "customer_id": sale.customer_id, "customer_name": sale.customer_name, "sale_type": sale.sale_type, "date": sale.sale_date, "subtotal": sale.subtotal, "discount": sale.discount, "total": sale.total, "paid": sale.paid, "remaining": current_remaining, "previous_remaining": previous_remaining, "current_bill": sale.total, "received_amount": sale.paid, "current_remaining": current_remaining, "grand_total_remaining": previous_remaining + current_remaining, "payment_status": sale.payment_status, "status": sale.status, "items": [{"id": i.id, "product_id": i.product_id, "product_name": i.product_name, "quantity": i.quantity, "rate": i.rate, "amount": i.amount, "discount": i.discount} for i in sale.items]}

    def purchase_detail(self, purchase_id: str, shop_id: str | None = None) -> dict:
        shop_id = shop_id or self.shop_id
        purchase = self.db.get(Purchase, purchase_id)
        if not purchase or (shop_id and purchase.shop_id != shop_id):
            raise NotFoundError("Purchase not found")
        returns = self.db.scalar(select(func.sum(PurchaseReturn.amount)).where(PurchaseReturn.purchase_id == purchase.id, PurchaseReturn.shop_id == purchase.shop_id, PurchaseReturn.status == "completed")) or ZERO_MONEY
        current_remaining = max(Decimal("0.00"), money(dec(purchase.total) - dec(purchase.paid) - dec(returns)))
        entry = self.db.scalar(select(SupplierLedgerEntry).where(SupplierLedgerEntry.reference_type == "purchase", SupplierLedgerEntry.reference_id == purchase.id, SupplierLedgerEntry.shop_id == purchase.shop_id).order_by(SupplierLedgerEntry.created_at.desc()))
        previous_remaining = dec(entry.balance_after) - dec(entry.purchase_amount) + dec(entry.payment_amount) if entry else self._supplier_balance(purchase.supplier_id, shop_id=shop_id) - current_remaining
        return {"id": purchase.id, "purchase_number": purchase.purchase_number, "supplier_id": purchase.supplier_id, "date": purchase.purchase_date, "subtotal": purchase.subtotal, "discount": purchase.discount, "total": purchase.total, "paid": purchase.paid, "remaining": current_remaining, "previous_remaining": previous_remaining, "current_stock_in_bill": purchase.total, "paid_amount": purchase.paid, "current_remaining": current_remaining, "grand_total_remaining": previous_remaining + current_remaining, "payment_status": purchase.payment_status, "status": purchase.status, "items": [{"id": i.id, "product_id": i.product_id, "product_name": i.product_name, "quantity": i.quantity, "rate": i.rate, "amount": i.amount} for i in purchase.items]}

    def payment(self, party: str, party_id: str, data: dict, user_id: str | None = None, shop_id: str | None = None) -> dict:
        shop_id = self._required_shop_id(shop_id)
        when = dt(data.get("date"))
        amount = money(dec(data.get("amount")))
        if amount <= 0:
            raise ValidationError("Amount must be positive")
        balance = self._customer_balance(party_id, shop_id=shop_id) if party == "customer" else self._supplier_balance(party_id, shop_id=shop_id)
        if amount > balance:
            raise PaymentExceedsBalanceError("Payment exceeds outstanding balance")
        try:
            if party == "customer":
                self.db.add(CustomerLedgerEntry(id=uid("CLE"), shop_id=shop_id, customer_id=party_id, entry_date=when, description=data.get("notes") or "Customer payment", payment_amount=amount, balance_after=balance - amount, reference_type="customer_payment"))
            else:
                self.db.add(SupplierLedgerEntry(id=uid("SLE"), shop_id=shop_id, supplier_id=party_id, entry_date=when, description=data.get("notes") or "Supplier payment", payment_amount=amount, balance_after=balance - amount, reference_type="supplier_payment"))
            payment_id = self._financial_payment(party, party_id, amount, data, when, uid("PAY"), shop_id=shop_id)
            self._audit("create", f"{party}_payment", party_id, user_id, {"amount": str(amount)})
            if data.get("_batch"):
                self.db.flush()
            else:
                self._commit()
            return {"id": payment_id, "party_id": party_id, "type": party, "amount": amount, "date": when, "remaining": balance - amount}
        except Exception:
            self._rollback()
            raise

    def next_number(self, setting_key: str, default: str, model: type, field: str) -> str:
        shop_id = self._required_shop_id()
        prefix_row = self.db.scalar(select(AppSetting).where(AppSetting.key == setting_key, AppSetting.shop_id == shop_id))
        prefix = prefix_row.value if prefix_row else default
        latest = self.db.scalar(select(getattr(model, field)).where(getattr(model, field).like(f"{prefix}-%"), model.shop_id == shop_id).order_by(getattr(model, field).desc()).with_for_update())
        try:
            number = int(str(latest).rsplit("-", 1)[1]) + 1 if latest else 1001
        except (IndexError, ValueError):
            number = 1001
        return f"{prefix}-{number}"


    def sale_return(self, sale_id: str, data: dict, user_id: str | None = None) -> dict:
        shop_id = self._required_shop_id()
        sale = self.db.scalar(select(Sale).where(Sale.id == sale_id, Sale.shop_id == shop_id))
        if not sale or sale.status != "completed":
            raise NotFoundError("Completed sale not found")
        when = dt(data.get("date"))
        return_id = uid("SRT")
        try:
            total = Decimal("0")
            return_items: list[SaleReturnItem] = []
            for raw in data.get("items") or []:
                item = self.db.scalar(select(SaleItem).where(SaleItem.id == raw.get("sale_item_id", raw.get("saleItemId")), SaleItem.shop_id == shop_id))
                if not item or item.sale_id != sale.id:
                    raise ValidationError("Sale item does not belong to this sale")
                requested = qty(dec(raw.get("quantity")))
                returned = self.db.scalar(select(func.coalesce(func.sum(SaleReturnItem.quantity), 0)).where(SaleReturnItem.sale_item_id == item.id, SaleReturnItem.shop_id == shop_id)) or 0
                if requested <= 0 or requested > dec(item.quantity) - dec(returned):
                    raise ValidationError("Return quantity exceeds eligible quantity")
                amount = money(requested * dec(item.rate))
                total += amount
                return_items.append(SaleReturnItem(id=uid("SRI"), shop_id=shop_id, return_id=return_id, sale_item_id=item.id, product_id=item.product_id, product_name=item.product_name, quantity=requested, rate=item.rate, amount=amount))
            if not return_items:
                raise ValidationError("Return must contain at least one item")
            row = SaleReturn(id=return_id, shop_id=shop_id, sale_id=sale.id, customer_id=sale.customer_id, return_date=when, amount=money(total), reference=data.get("reference"), notes=data.get("notes"), status="completed")
            self.db.add(row)
            self.db.add_all(return_items)
            for item in return_items:
                self._stock(self._product(item.product_id, lock=True, shop_id=shop_id), dec(item.quantity), StockMovementType.SALE_RETURN_IN.value, "sale_return", return_id, f"Return {sale.invoice_number}")
            if sale.customer_id:
                balance = self._customer_balance(sale.customer_id, shop_id=shop_id) - total
                self.db.add(CustomerLedgerEntry(id=uid("CLE"), shop_id=shop_id, customer_id=sale.customer_id, entry_date=when, description=f"Return {sale.invoice_number}", return_amount=total, balance_after=balance, reference_type="sale_return", reference_id=return_id))
            self._audit("return", "sale", sale.id, user_id, {"amount": str(total)})
            self._commit()
            return {
                "id": return_id,
                "sale_id": sale.id,
                "amount": total,
                "items": [
                    {
                        "id": item.id,
                        "sale_item_id": item.sale_item_id,
                        "product_id": item.product_id,
                        "product_name": item.product_name,
                        "quantity": item.quantity,
                        "rate": item.rate,
                        "amount": item.amount,
                    }
                    for item in return_items
                ],
            }
        except Exception:
            self._rollback()
            raise

    def purchase_return(self, purchase_id: str, data: dict, user_id: str | None = None) -> dict:
        shop_id = self._required_shop_id()
        purchase = self.db.scalar(select(Purchase).where(Purchase.id == purchase_id, Purchase.shop_id == shop_id))
        if not purchase or purchase.status != "completed":
            raise NotFoundError("Completed purchase not found")
        when = dt(data.get("date"))
        return_id = uid("PRT")
        try:
            total = Decimal("0")
            return_items: list[PurchaseReturnItem] = []
            for raw in data.get("items") or []:
                item = self.db.scalar(select(PurchaseItem).where(PurchaseItem.id == raw.get("purchase_item_id", raw.get("purchaseItemId")), PurchaseItem.shop_id == shop_id))
                if not item or item.purchase_id != purchase.id:
                    raise ValidationError("Purchase item does not belong to this purchase")
                requested = qty(dec(raw.get("quantity")))
                returned = self.db.scalar(select(func.coalesce(func.sum(PurchaseReturnItem.quantity), 0)).where(PurchaseReturnItem.purchase_item_id == item.id, PurchaseReturnItem.shop_id == shop_id)) or 0
                product = self._product(item.product_id, lock=True, shop_id=shop_id)
                if requested <= 0 or requested > dec(item.quantity) - dec(returned):
                    raise ValidationError("Return quantity exceeds eligible quantity")
                if requested > dec(product.current_stock):
                    raise InsufficientStockError(f"Insufficient current stock for {product.name}")
                amount = money(requested * dec(item.rate))
                total += amount
                return_items.append(PurchaseReturnItem(id=uid("PRI"), shop_id=shop_id, return_id=return_id, purchase_item_id=item.id, product_id=item.product_id, product_name=item.product_name, quantity=requested, rate=item.rate, amount=amount))
            if not return_items:
                raise ValidationError("Return must contain at least one item")
            self.db.add(PurchaseReturn(id=return_id, shop_id=shop_id, purchase_id=purchase.id, supplier_id=purchase.supplier_id, return_date=when, amount=money(total), reference=data.get("reference"), notes=data.get("notes"), status="completed"))
            self.db.add_all(return_items)
            for item in return_items:
                self._stock(self._product(item.product_id, lock=True, shop_id=shop_id), -dec(item.quantity), StockMovementType.PURCHASE_RETURN_OUT.value, "purchase_return", return_id, f"Return {purchase.purchase_number}")
            balance = self._supplier_balance(purchase.supplier_id, shop_id=shop_id) - total
            self.db.add(SupplierLedgerEntry(id=uid("SLE"), shop_id=shop_id, supplier_id=purchase.supplier_id, entry_date=when, description=f"Return {purchase.purchase_number}", return_amount=total, balance_after=balance, reference_type="purchase_return", reference_id=return_id))
            self._audit("return", "purchase", purchase.id, user_id, {"amount": str(total)})
            self._commit()
            return {
                "id": return_id,
                "purchase_id": purchase.id,
                "amount": total,
                "items": [
                    {
                        "id": item.id,
                        "purchase_item_id": item.purchase_item_id,
                        "product_id": item.product_id,
                        "product_name": item.product_name,
                        "quantity": item.quantity,
                        "rate": item.rate,
                        "amount": item.amount,
                    }
                    for item in return_items
                ],
            }
        except Exception:
            self._rollback()
            raise

    def bank_movement(self, kind: str, data: dict, user_id: str | None = None) -> dict:
        shop_id = self._required_shop_id()
        when = dt(data.get("date"))
        amount = money(dec(data.get("amount")))
        if amount <= 0:
            raise ValidationError("Amount must be positive")
        try:
            if kind == "transfer":
                source_id, target_id = data.get("from_bank_id", data.get("fromBankId")), data.get("to_bank_id", data.get("toBankId"))
                if not source_id or source_id == target_id:
                    raise ValidationError("Select two different banks")
                source = self._bank(source_id, True, shop_id=shop_id)
                self._bank(target_id, True, shop_id=shop_id)
                if self._bank_balance(source.id, True, shop_id=shop_id) < amount:
                    raise InsufficientBankBalanceError("Insufficient source bank balance")
                effect_id = uid("BTR")
                self.db.add(BankTransaction(id=effect_id, shop_id=shop_id, bank_account_id=source_id, transaction_date=when, type="Transfer Out", amount=amount, reference=data.get("reference"), note=data.get("note"), reference_type="bank_transfer"))
                self.db.add(BankTransaction(id=uid("BTR"), shop_id=shop_id, bank_account_id=target_id, transaction_date=when, type="Transfer In", amount=amount, reference=data.get("reference"), note=data.get("note"), reference_type="bank_transfer"))
            else:
                bank_id = data.get("bank_id", data.get("bankId"))
                bank = self._bank(bank_id, True, shop_id=shop_id)
                if kind == "withdrawal" and self._bank_balance(bank.id, True, shop_id=shop_id) < amount:
                    raise InsufficientBankBalanceError("Insufficient bank balance")
                if kind == "deposit":
                    self.db.add(CashTransaction(id=uid("CSH"), shop_id=shop_id, transaction_date=when, type="cash_out", category="bank_deposit", description=f"Deposit to {bank.name}", amount=amount, reference_type="bank_deposit"))
                    tx_type = "Deposit"
                else:
                    self.db.add(CashTransaction(id=uid("CSH"), shop_id=shop_id, transaction_date=when, type="cash_in", category="bank_withdrawal", description=f"Withdrawal from {bank.name}", amount=amount, reference_type="bank_withdrawal"))
                    tx_type = "Withdrawal"
                effect_id = uid("BTR")
                self.db.add(BankTransaction(id=effect_id, shop_id=shop_id, bank_account_id=bank.id, transaction_date=when, type=tx_type, amount=amount, reference=data.get("reference"), note=data.get("note"), reference_type="cash_book"))
            self._audit(kind, "bank", None, user_id, {"amount": str(amount)})
            if data.get("_batch"):
                self.db.flush()
            else:
                self._commit()
            return {"id": effect_id, "type": kind, "amount": amount, "date": when}
        except Exception:
            self._rollback()
            raise

    def expense(self, data: dict, user_id: str | None = None) -> dict:
        shop_id = self._required_shop_id()
        when = dt(data.get("date"))
        amount = money(dec(data.get("amount")))
        category = str(data.get("category", "")).strip()
        subtype = str(data.get("subtype", data.get("expense_subtype", "Other Expense"))).strip()
        if amount <= 0 or category not in {"Home Expense", "Shop Expense", "Pocket Money"}:
            raise ValidationError("Invalid expense")
        if subtype == "Other":
            subtype = "Other Expense"
        if subtype not in EXPENSE_SUBTYPES[category]:
            raise ValidationError("Invalid expense subtype")
        custom_subtype = str(data.get("custom_subtype", data.get("customSubtype", ""))).strip()
        if subtype == "Extra Expense" and not custom_subtype:
            raise ValidationError("Extra Expense Name is required")
        try:
            row = Expense(id=uid("EXP"), shop_id=shop_id, category=category, subtype=subtype, custom_subtype=custom_subtype or None, amount=amount, expense_date=when, description=data.get("description", data.get("note")), payment_method=str(data.get("payment_method", data.get("paymentMethod", "Cash"))), reference=data.get("reference"))
            self.db.add(row)
            method = row.payment_method.title()
            if method == "Cash":
                self.db.add(CashTransaction(id=uid("CSH"), shop_id=shop_id, transaction_date=when, type="cash_out", category="expense", description=row.description or subtype, amount=amount, reference_type="expense", reference_id=row.id))
            elif method == "Bank":
                bank = self._bank(data.get("bank_id", data.get("bankId", data.get("bank_account_id", data.get("bankAccountId")))), True, shop_id=shop_id)
                if self._bank_balance(bank.id, True, shop_id=shop_id) < amount:
                    raise InsufficientBankBalanceError("Insufficient bank balance")
                row.bank_account_id = bank.id
                self.db.add(BankTransaction(id=uid("BTR"), shop_id=shop_id, bank_account_id=bank.id, transaction_date=when, type="Expense", amount=amount, reference_type="expense", reference_id=row.id))
            else:
                raise ValidationError("Payment method must be Cash or Bank")
            self._audit("create", "expense", row.id, user_id, {"amount": str(amount)})
            if data.get("_batch"):
                self.db.flush()
            else:
                self._commit()
            return {"id": row.id, "category": category, "subtype": subtype, "custom_subtype": row.custom_subtype, "amount": amount, "date": when}
        except Exception:
            self._rollback()
            raise

    def cash_credit(self, action: str, data: dict, user_id: str | None = None) -> dict:
        shop_id = self._required_shop_id()
        try:
            if action == "create":
                row = CashCreditPerson(id=uid("CCP"), shop_id=shop_id, name=str(data.get("name", "")).strip(), phone=data.get("phone"), total_cash_given=money(dec(data.get("amount_given", data.get("amountGiven")))), total_received=Decimal("0"))
                if not row.name or row.total_cash_given <= 0:
                    raise ValidationError("Name and positive amount are required")
                self.db.add(row)
                self.db.add(CashCreditTransaction(id=uid("CCT"), shop_id=shop_id, person_id=row.id, transaction_date=dt(data.get("date")), type="Credit Given", amount=row.total_cash_given, notes=data.get("note")))
            else:
                row = self.db.scalar(select(CashCreditPerson).where(CashCreditPerson.id == data.get("person_id", data.get("personId")), CashCreditPerson.shop_id == shop_id).with_for_update())
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
                self.db.add(CashCreditTransaction(id=uid("CCT"), shop_id=shop_id, person_id=row.id, transaction_date=dt(data.get("date")), type=tx_type, amount=amount, notes=data.get("note")))
            self._audit(action, "cash_credit", row.id, user_id)
            self._commit()
            return {"id": row.id, "name": row.name, "total_cash_given": row.total_cash_given, "total_received": row.total_received, "remaining": dec(row.total_cash_given) - dec(row.total_received)}
        except Exception:
            self._rollback()
            raise

    def stage_cash_entries(self, day: str, entries: list[dict], user_id: str | None = None) -> dict:
        shop_id = self._required_shop_id()
        when = dt(day)
        try:
            for entry in entries:
                amount = money(dec(entry.get("amount")))
                if amount <= 0:
                    raise ValidationError("Cash Book amount must be positive")
                payload = json.loads(json.dumps(entry.get("payload") or {}, default=str))
                payload["date"] = when.date().isoformat()
                self.db.add(CashBookDraft(
                    id=uid("CBD"),
                    shop_id=shop_id,
                    entry_date=when,
                    entry_type=str(entry["entry_type"]),
                    category=str(entry["category"]),
                    amount=amount,
                    description=str(entry.get("description") or entry["category"]),
                    payload=payload,
                    status="pending",
                ))
            self._audit("stage", "cash_book", str(when.date()), user_id, {"entries": len(entries)})
            self._commit()
            return self.daily(when.date().isoformat())
        except Exception:
            self._rollback()
            raise

    def delete_cash_draft(self, draft_id: str, day: str) -> dict:
        shop_id = self._required_shop_id()
        when = dt(day)
        row = self.db.scalar(
            select(CashBookDraft)
            .where(CashBookDraft.id == draft_id, CashBookDraft.shop_id == shop_id, func.date(CashBookDraft.entry_date) == when.date())
            .with_for_update()
        )
        if not row:
            raise NotFoundError("Pending Cash Book entry not found")
        if row.status != "pending":
            raise ConflictError("Only pending Cash Book entries can be removed")
        self.db.delete(row)
        self._commit()
        return self.daily(when.date().isoformat())

    def daily(self, day: str) -> dict:
        shop_id = self._required_shop_id()
        when = dt(day)
        closes = self.db.scalar(select(CashDayClose).where(func.date(CashDayClose.date) == when.date()))
        rows = [
            row
            for row in self.db.scalars(
                select(CashTransaction)
                .where(func.date(CashTransaction.transaction_date) == when.date())
                .order_by(CashTransaction.created_at)
            ).all()
            if row.reference_type != "cash_credit" and not (row.category or "").startswith("cash_credit")
        ]
        drafts = self.db.scalars(
            select(CashBookDraft)
            .where(func.date(CashBookDraft.entry_date) == when.date())
            .order_by(CashBookDraft.created_at)
        ).all()
        if closes:
            opening = dec(closes.opening_balance)
        else:
            prior = self.db.scalar(select(CashDayClose).where(CashDayClose.date < when).order_by(CashDayClose.date.desc()))
            configured = self.db.scalar(select(AppSetting).where(AppSetting.key == "opening_cash", AppSetting.shop_id == shop_id))
            opening = dec(prior.closing_balance) if prior else dec(configured.value if configured else 0)
        cash_in = sum((dec(r.amount) for r in rows if r.type == "cash_in"), Decimal("0"))
        cash_out = sum((dec(r.amount) for r in rows if r.type == "cash_out"), Decimal("0"))
        labels = {"retail_sale": "Walk-in Sale", "customer_payment": "Customer Credit Installment", "supplier_payment": "Vendor Payment", "expense": "Expenses", "bank_deposit": "Bank Deposit", "bank_withdrawal": "Bank Withdrawal"}
        category_totals: dict[tuple[str, str], Decimal] = {}
        for row in rows:
            key = (row.category or "", row.type)
            category_totals[key] = category_totals.get(key, Decimal("0")) + dec(row.amount)
        categories = [{"category": category, "type": kind, "amount": amount, "label": labels.get(category, category)} for (category, kind), amount in category_totals.items()]
        running_balance = opening
        items = []
        for row in rows:
            amount = dec(row.amount)
            is_cash_in = row.type == "cash_in"
            running_balance += amount if is_cash_in else -amount
            items.append({
                "id": row.id,
                "date": row.transaction_date,
                "category": row.category,
                "type": row.type,
                "description": row.description,
                "amount": amount,
                "cash_in": amount if is_cash_in else Decimal("0"),
                "cash_out": Decimal("0") if is_cash_in else amount,
                "reference": row.reference_id or row.reference_type or "",
                "running_balance": running_balance,
            })
        return {
            "date": when.date(),
            "opening_balance": opening,
            "cash_in": cash_in,
            "cash_out": cash_out,
            "total_cash_in": cash_in,
            "total_cash_out": cash_out,
            "closing_balance": opening + cash_in - cash_out,
            "categories": categories,
            "finalized": bool(closes),
            "actual_cash": closes.actual_cash if closes else None,
            "difference": closes.difference if closes else None,
            "items": items,
            "pending_items": [
                {
                    "id": row.id,
                    "date": row.entry_date,
                    "type": row.entry_type,
                    "category": row.category,
                    "amount": row.amount,
                    "description": row.description,
                    "payload": row.payload,
                    "status": row.status,
                    "posted_transaction_id": row.posted_transaction_id,
                }
                for row in drafts
                if row.status == "pending"
            ],
        }

    def finalize(self, data: dict, user_id: str | None = None) -> dict:
        shop_id = self._required_shop_id()
        day = dt(data.get("date"))
        try:
            pending = self.db.scalars(
                select(CashBookDraft)
                .where(func.date(CashBookDraft.entry_date) == day.date(), CashBookDraft.status == "pending")
                .order_by(CashBookDraft.created_at, CashBookDraft.id)
                .with_for_update()
            ).all()
            for draft in pending:
                payload = {**draft.payload, "date": day.date().isoformat(), "_batch": True}
                if draft.entry_type == "retail_sale":
                    payload.update({"sale_type": "retail", "customer_name": payload.get("customer_name", "Daily Walk-in"), "paid": payload.get("cash_received", payload.get("cashReceived", 0)), "payment_method": "Cash"})
                    result = self.sale(payload, user_id)
                elif draft.entry_type == "customer_payment":
                    payload["payment_method"] = "Cash"
                    result = self.payment("customer", str(payload.get("customer_id", payload.get("customerId"))), payload, user_id)
                elif draft.entry_type == "supplier_payment":
                    payload["payment_method"] = "Cash"
                    result = self.payment("supplier", str(payload.get("supplier_id", payload.get("supplierId"))), payload, user_id)
                elif draft.entry_type == "expense":
                    payload["payment_method"] = "Cash"
                    result = self.expense(payload, user_id)
                elif draft.entry_type in {"bank_deposit", "bank_withdrawal", "bank_transfer"}:
                    kind = {"bank_deposit": "deposit", "bank_withdrawal": "withdrawal", "bank_transfer": "transfer"}[draft.entry_type]
                    result = self.bank_movement(kind, payload, user_id)
                else:
                    raise ValidationError("Unsupported Cash Book draft type")
                draft.status = "posted"
                draft.posted_at = datetime.utcnow()
                draft.posted_transaction_id = result.get("id")
                self.db.flush()

            book = self.daily(day.date().isoformat())
            close = self.db.scalar(select(CashDayClose).where(func.date(CashDayClose.date) == day.date()).with_for_update())
            actual = data.get("actual_cash", data.get("actualCash"))
            if actual in (None, "") and close:
                actual = close.actual_cash
            difference = money(dec(actual) - book["closing_balance"]) if actual not in (None, "") else None
            if close:
                close.opening_balance = book["opening_balance"]
                close.cash_in = book["cash_in"]
                close.cash_out = book["cash_out"]
                close.closing_balance = book["closing_balance"]
                close.actual_cash = money(dec(actual)) if actual not in (None, "") else None
                close.difference = difference
                close.finalized_at = datetime.utcnow()
            else:
                close = CashDayClose(
                    shop_id=shop_id,
                    date=datetime.combine(day.date(), datetime.min.time()),
                    opening_balance=book["opening_balance"],
                    cash_in=book["cash_in"],
                    cash_out=book["cash_out"],
                    closing_balance=book["closing_balance"],
                    actual_cash=money(dec(actual)) if actual not in (None, "") else None,
                    difference=difference,
                    finalized_at=datetime.utcnow(),
                )
                self.db.add(close)
            self._audit("finalize", "cash_day", str(day.date()), user_id, {"posted_entries": len(pending)})
            self._commit()
            return self.daily(day.date().isoformat())
        except Exception:
            self._rollback()
            raise
