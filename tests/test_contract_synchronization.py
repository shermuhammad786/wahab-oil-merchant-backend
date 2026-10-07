from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.constants import EXPENSE_SUBTYPES
from app.db.base import Base
from app.core.security import get_current_user
from app.main import app
from app.models.cash_book import CashTransaction
from app.models.customer import Customer
from app.models.payment import CustomerPayment, SupplierPayment
from app.models.product import Product
from app.models.purchases import Purchase
from app.models.returns import PurchaseReturn, SaleReturn
from app.models.sales import Sale, SaleItem
from app.models.shop import Shop
from app.models.supplier import Supplier
from app.models.user import User
from app.repositories.customer import CustomerRepository
from app.repositories.supplier import SupplierRepository
from app.schemas.customer import CustomerCreate
from app.schemas.customer import CustomerRead
from app.schemas.product import ProductCreate, ProductUpdate
from app.schemas.stock import StockAdjustmentRequest
from app.services.customer import CustomerService
from app.services.operations import OperationsService


def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(Shop(id="SHOP-WOM", name="Wahab Oil Merchant", code="WOM"))
    session.commit()
    session.info["shop_id"] = "SHOP-WOM"
    return session


def test_removed_product_fields_are_not_active_schema_fields():
    assert "sale_price" not in ProductCreate.model_fields
    assert "brand" not in ProductCreate.model_fields
    assert "packaging" not in ProductCreate.model_fields
    assert "unit" not in ProductCreate.model_fields
    assert "current_stock" not in ProductUpdate.model_fields


def test_customer_create_does_not_require_credit_limit():
    customer = CustomerCreate(name="Customer")
    assert customer.opening_balance == Decimal("0.00")
    assert "credit_limit" not in CustomerCreate.model_fields


def test_customer_create_response_has_decimal_zero_balance():
    db = session()
    customer = CustomerService(db).create_customer(CustomerCreate(name="Customer"), shop_id="SHOP-WOM")
    response = CustomerRead.model_validate(customer).model_copy(update={"current_balance": CustomerRepository(db).get_balance(customer.id)})

    assert response.current_balance == Decimal("0.00")
    assert isinstance(response.current_balance, Decimal)
    db.close()


def test_customer_create_response_preserves_decimal_opening_balance():
    db = session()
    customer = CustomerService(db).create_customer(CustomerCreate(name="Customer", opening_balance=Decimal("5000.00")), shop_id="SHOP-WOM")
    response = CustomerRead.model_validate(customer).model_copy(update={"current_balance": CustomerRepository(db).get_balance(customer.id)})

    assert response.current_balance == Decimal("5000.00")
    assert isinstance(response.current_balance, Decimal)
    db.close()


def test_stock_adjustment_accepts_current_frontend_payload():
    request = StockAdjustmentRequest.model_validate({"productId": "PRD-1", "quantityDelta": "2.500"})
    assert request.product_id == "PRD-1"
    assert request.quantity == Decimal("2.500")
    assert request.direction == "increase"


def test_expense_subtypes_are_centralized():
    assert "Extra Expense" in EXPENSE_SUBTYPES["Home Expense"]
    assert "Other Expense" in EXPENSE_SUBTYPES["Shop Expense"]
    assert "Shopping" in EXPENSE_SUBTYPES["Pocket Money"]


def test_customer_balance_is_transaction_derived():
    db = session()
    now = datetime(2026, 9, 22)
    db.add(Customer(id="CUS-1", shop_id="SHOP-WOM", name="Customer", opening_balance=Decimal("5.00"), status="Active"))
    db.add(Sale(id="SAL-1", shop_id="SHOP-WOM", invoice_number="INV-1", customer_id="CUS-1", customer_name="Customer", sale_type="installment", sale_date=now, subtotal=Decimal("100.00"), discount=Decimal("0.00"), total=Decimal("100.00"), paid=Decimal("0.00"), remaining=Decimal("100.00"), payment_status="unpaid", status="completed"))
    db.add(CustomerPayment(id="CPY-1", shop_id="SHOP-WOM", customer_id="CUS-1", payment_date=now, amount=Decimal("30.00"), payment_method="Cash", status="completed"))
    db.add(SaleReturn(id="SRT-1", shop_id="SHOP-WOM", sale_id="SAL-1", customer_id="CUS-1", return_date=now, amount=Decimal("10.00"), status="completed"))
    db.commit()
    assert CustomerRepository(db).get_balance("CUS-1") == Decimal("65.00")
    db.close()


def test_customer_balance_normalizes_float_opening_balance():
    db = session()
    db.add(Customer(id="CUS-2", shop_id="SHOP-WOM", name="Customer", opening_balance=5.0, status="Active"))
    db.flush()

    assert CustomerRepository(db).get_balance("CUS-2") == Decimal("5.0")
    db.close()


def test_installment_sale_with_initial_payment_persists_all_sale_children():
    db = session()
    db.add(Customer(id="CUS-SALE-1", shop_id="SHOP-WOM", name="Installment Customer", opening_balance=Decimal("0.00"), status="Active"))
    db.add(Product(id="PRD-SALE-1", shop_id="SHOP-WOM", name="Cooking Oil", unit="kg", current_stock=Decimal("10.000"), status="active"))
    db.commit()

    result = OperationsService(db).sale({
        "customer_id": "CUS-SALE-1",
        "customer_name": "Installment Customer",
        "sale_type": "installment",
        "date": "2026-09-24",
        "paid": "40.00",
        "payment_method": "Cash",
        "items": [{"product_id": "PRD-SALE-1", "quantity": "1", "rate": "40.00", "discount": "0"}],
    })

    sale = db.get(Sale, result["id"])
    payment = db.query(CustomerPayment).filter_by(sale_id=sale.id).one()
    item = db.query(SaleItem).filter_by(sale_id=sale.id).one()
    product = db.get(Product, "PRD-SALE-1")

    assert sale is not None
    assert payment.sale_id == sale.id
    assert payment.amount == Decimal("40.00")
    assert payment.bank_account_id is None
    assert sale.remaining == Decimal("0.00")
    assert item.product_id == product.id
    assert product.current_stock == Decimal("9.000")
    assert CustomerRepository(db).get_balance("CUS-SALE-1") == Decimal("0.00")
    db.close()


def test_customer_installments_returns_frontend_account_shape():
    db = session()
    db.add(Customer(id="CUS-INSTALLMENT-1", shop_id="SHOP-WOM", name="Customer 0222", status="Active"))
    db.commit()

    result = CustomerService(db).get_installments("CUS-INSTALLMENT-1")

    assert result["customer"].id == "CUS-INSTALLMENT-1"
    assert result["customer"].name == "Customer 0222"
    assert result["total_credit_sales"] == Decimal("0.00")
    assert result["total_payments"] == Decimal("0.00")
    assert result["total_returns"] == Decimal("0.00")
    assert result["remaining"] == Decimal("0.00")
    assert result["entries"] == []
    db.close()


def test_supplier_balance_payment_reduces_payable():
    db = session()
    now = datetime(2026, 9, 22)
    db.add(Supplier(id="SUP-1", shop_id="SHOP-WOM", name="Supplier", opening_balance=Decimal("0.00"), status="Active"))
    db.add(Purchase(id="PUR-1", shop_id="SHOP-WOM", purchase_number="PUR-1", supplier_id="SUP-1", purchase_date=now, subtotal=Decimal("100.00"), discount=Decimal("0.00"), total=Decimal("100.00"), paid=Decimal("0.00"), remaining=Decimal("100.00"), payment_status="unpaid", status="completed"))
    db.add(SupplierPayment(id="SPY-1", shop_id="SHOP-WOM", supplier_id="SUP-1", payment_date=now, amount=Decimal("40.00"), payment_method="Cash", status="completed"))
    db.add(PurchaseReturn(id="PRT-1", shop_id="SHOP-WOM", purchase_id="PUR-1", supplier_id="SUP-1", return_date=now, amount=Decimal("10.00"), status="completed"))
    db.commit()
    assert SupplierRepository(db).get_balance("SUP-1") == Decimal("50.00")
    db.close()


def test_supplier_balance_normalizes_float_opening_balance():
    db = session()
    db.add(Supplier(id="SUP-2", shop_id="SHOP-WOM", name="Supplier", opening_balance=5.0, status="Active"))
    db.flush()

    assert SupplierRepository(db).get_balance("SUP-2") == Decimal("5.00")
    db.close()


def test_cash_credit_transactions_are_excluded_from_daily_cash_book():
    db = session()
    now = datetime(2026, 9, 22)
    db.add_all([
        CashTransaction(id="CSH-1", shop_id="SHOP-WOM", transaction_date=now, type="cash_out", category="expense", description="Expense", amount=Decimal("10.00"), reference_type="expense"),
        CashTransaction(id="CSH-2", shop_id="SHOP-WOM", transaction_date=now, type="cash_out", category="cash_credit_given", description="Cash credit", amount=Decimal("50.00"), reference_type="cash_credit"),
    ])
    db.commit()
    book = OperationsService(db).daily("2026-09-22")
    assert book["cash_out"] == Decimal("10.00")
    assert all(item["category"] != "cash_credit_given" for item in book["categories"])
    db.close()


def test_daily_cash_book_endpoint_returns_serializable_items(client, db_session):
    day = "2099-01-02"
    db_session.add_all([
        CashTransaction(id="CSH-HTTP-SERIALIZED-IN", shop_id="SHOP-WOM", transaction_date=datetime(2099, 1, 2), type="cash_in", category="retail_sale", description="Walk-in Sale", amount=Decimal("25.00"), reference_type="sale", reference_id="SAL-HTTP"),
        CashTransaction(id="CSH-HTTP-SERIALIZED-OUT", shop_id="SHOP-WOM", transaction_date=datetime(2099, 1, 2), type="cash_out", category="expense", description="Expenses", amount=Decimal("10.00"), reference_type="expense", reference_id="EXP-HTTP"),
        CashTransaction(id="CSH-HTTP-SERIALIZED-EXCLUDED", shop_id="SHOP-WOM", transaction_date=datetime(2099, 1, 2), type="cash_out", category="cash_credit_given", description="Cash Credit", amount=Decimal("50.00"), reference_type="cash_credit"),
    ])
    db_session.commit()
    app.dependency_overrides[get_current_user] = lambda: User(id="USR-HTTP-TEST", name="Test Admin", email="test-admin@example.com", role="admin", is_active=True)
    try:
        response = client.get(f"/api/v1/cash-book/daily?date={day}")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    assert all(isinstance(item, dict) for item in payload["items"])
    assert all(item["category"] != "cash_credit_given" for item in payload["items"])
    assert payload["total_cash_in"] == 25.0
    assert payload["total_cash_out"] == 10.0
    assert payload["closing_balance"] == 15.0
    assert payload["items"][-1]["running_balance"] == 15.0
