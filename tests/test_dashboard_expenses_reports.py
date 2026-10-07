from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1 import operations as operations_api
from app.core.security import require_admin
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Category, Customer, Expense, Product, Purchase, Sale, Shop, Supplier


TODAY = datetime(2026, 9, 30)


@pytest.fixture
def api_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        db.info["shop_id"] = "SHOP-WOM"
        db.add_all([
            Shop(id="SHOP-WOM", name="Wahab Oil Merchant", code="WOM"),
            Customer(id="CUS-1", shop_id="SHOP-WOM", name="Customer One", opening_balance=2000, status="Active"),
            Supplier(id="SUP-1", shop_id="SHOP-WOM", name="Supplier One", opening_balance=3000, status="Active"),
            Product(id="PRD-1", shop_id="SHOP-WOM", name="Oil", unit="kg", current_stock=10, purchase_price=20, minimum_stock=1, status="active"),
        ])
        db.commit()

        def override_db():
            yield db

        previous = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id="TEST-USER", shop_id="SHOP-WOM")
        try:
            with TestClient(app) as client:
                yield client, db
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)
    engine.dispose()


def add_sale(db, sale_id, sold_at, total, status="completed", created_at=None, shop_id="SHOP-WOM", customer_id=None, sale_type="retail", paid=None):
    db.add(Sale(
        id=sale_id,
        shop_id=shop_id,
        invoice_number=f"INV-{sale_id}",
        customer_id=customer_id,
        customer_name=f"Customer {sale_id}",
        sale_type=sale_type,
        sale_date=sold_at,
        subtotal=total,
        discount=0,
        total=total,
        paid=total if paid is None else paid,
        remaining=0 if paid is None else total - paid,
        payment_status="paid" if paid is None or paid == total else "unpaid" if paid == 0 else "partial",
        status=status,
        created_at=created_at or sold_at,
        updated_at=created_at or sold_at,
    ))


def add_purchase(db, purchase_id, purchased_at, total, status="completed", shop_id="SHOP-WOM", supplier_id="SUP-1"):
    db.add(Purchase(
        id=purchase_id,
        shop_id=shop_id,
        purchase_number=f"PUR-{purchase_id}",
        supplier_id=supplier_id,
        purchase_date=purchased_at,
        subtotal=total,
        discount=0,
        total=total,
        paid=total,
        remaining=0,
        payment_status="paid",
        status=status,
    ))


def add_expense(db, expense_id, expense_date, subtype, amount, custom=None, description=None, category="Home Expense", shop_id="SHOP-WOM"):
    db.add(Expense(
        id=expense_id,
        shop_id=shop_id,
        category=category,
        subtype=subtype,
        custom_subtype=custom,
        amount=amount,
        expense_date=expense_date,
        description=description,
        payment_method="Cash",
    ))


def test_dashboard_returns_today_profit_and_loss_and_seven_real_days(api_db, monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def utcnow(cls):
            return TODAY

    monkeypatch.setattr(operations_api, "datetime", FrozenDateTime)
    client, db = api_db
    db.get(Product, "PRD-1").current_stock = 0
    add_sale(db, "OLD-SALE", datetime(2026, 9, 24, 9), 200)
    add_sale(db, "TODAY-SALE", datetime(2026, 9, 30, 10), 1000)
    add_sale(db, "CANCELLED", datetime(2026, 9, 30, 11), 9000, status="cancelled")
    add_purchase(db, "OLD-PURCHASE", datetime(2026, 9, 26, 9), 500)
    add_purchase(db, "TODAY-PURCHASE", datetime(2026, 9, 30, 10), 300)
    add_expense(db, "OLD-EXP", datetime(2026, 9, 28), "Rent", 80)
    add_expense(db, "TODAY-EXP", datetime(2026, 9, 30), "Rent", 100)
    db.commit()

    response = client.get("/api/v1/dashboard")
    assert response.status_code == 200, response.text
    dashboard = response.json()
    trend = dashboard["trend"]
    assert len(trend) == 7
    assert [row["date"] for row in trend] == [
        "2026-09-24", "2026-09-25", "2026-09-26", "2026-09-27",
        "2026-09-28", "2026-09-29", "2026-09-30",
    ]
    assert [row["name"] for row in trend] == ["09/24", "09/25", "09/26", "09/27", "09/28", "09/29", "09/30"]
    assert [row["sales"] for row in trend] == [200, 0, 0, 0, 0, 0, 1000]
    assert [row["purchases"] for row in trend] == [0, 0, 500, 0, 0, 0, 300]
    assert dashboard["todays_sales"] == 1000
    assert dashboard["todays_purchases"] == 300
    assert dashboard["todays_profit_loss"] == 600
    assert dashboard["recent_sales"][0]["id"] == "TODAY-SALE"
    assert dashboard["recent_sales"][0]["invoice_number"] == "INV-TODAY-SALE"
    assert dashboard["recent_sales"][0]["customer_name"] == "Customer TODAY-SALE"
    assert dashboard["recent_sales"][0]["total"] == 1000
    assert dashboard["recent_sales"][0]["payment_status"] == "paid"
    assert dashboard["recent_sales"][-1]["id"] == "OLD-SALE"
    assert len(dashboard["low_stock"]) == 1
    low_stock = dashboard["low_stock"][0]
    assert low_stock == {
        "id": "PRD-1",
        "name": "Oil",
        "category": "",
        "category_id": None,
        "purchase_price": 20,
        "current_stock": 0,
        "minimum_stock": 1,
        "status": "Out of Stock",
        "active": True,
    }


def test_expense_list_serializes_filters_and_excludes_other(api_db):
    client, db = api_db
    add_expense(db, "NORMAL", datetime(2026, 9, 30), "Rent", 100, description="Shop rent")
    add_expense(db, "EXTRA", datetime(2026, 9, 30), "Extra Expense", 50, custom="Generator repair", description="filter target")
    add_expense(db, "OTHER", datetime(2026, 9, 30), "Other Expense", 900, description="hidden secret")
    add_expense(db, "OLDER", datetime(2026, 9, 20), "Utilities", 25, description="old bill")
    db.commit()

    response = client.get("/api/v1/expenses?page=1&page_size=1&from=2026-09-30&to=2026-09-30&category=Home%20Expense&subtype=Extra%20Expense&search=filter")
    assert response.status_code == 200, response.text
    result = response.json()
    assert set(("items", "total", "page", "page_size", "summary")).issubset(result)
    assert result["total"] == 1
    assert result["items"][0]["id"] == "EXTRA"
    assert result["items"][0]["custom_subtype"] == "Generator repair"
    assert result["summary"]["total"] == 50

    hidden = client.get("/api/v1/expenses?search=hidden%20secret")
    assert hidden.status_code == 200
    assert hidden.json()["items"] == []
    assert hidden.json()["total"] == 0
    hidden_override = client.get("/api/v1/expenses?include_other=true&search=hidden%20secret")
    assert hidden_override.status_code == 200
    assert hidden_override.json()["items"] == []

    normal = client.get("/api/v1/expenses?search=Shop%20rent")
    assert normal.status_code == 200
    assert [item["id"] for item in normal.json()["items"]] == ["NORMAL"]

    paged = client.get("/api/v1/expenses?page=1&page_size=1&from=All&to=null&category=All&subtype=undefined")
    assert paged.status_code == 200
    assert paged.json()["total"] == 3
    assert len(paged.json()["items"]) == 1
    assert paged.json()["summary"]["total"] == 175


def test_accounts_and_reports_receive_authoritative_summary_contracts(api_db, monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def utcnow(cls):
            return TODAY

    monkeypatch.setattr(operations_api, "datetime", FrozenDateTime)
    client, db = api_db
    add_sale(db, "SALE-A", datetime(2026, 9, 30, 9), 1200)
    add_sale(db, "SALE-B", datetime(2026, 9, 29, 9), 800)
    add_sale(db, "SALE-CANCELLED", datetime(2026, 9, 30, 11), 5000, status="cancelled")
    add_purchase(db, "PUR-A", datetime(2026, 9, 30, 9), 500)
    add_expense(db, "EXP-A", datetime(2026, 9, 30), "Rent", 100)
    db.commit()

    sales = client.get("/api/v1/reports/sales?page=1&page_size=1&customer_id=All&from=All&to=undefined")
    assert sales.status_code == 200, sales.text
    sales_data = sales.json()
    assert sales_data["summary"]["count"] == 2
    assert sales_data["summary"]["total"] == 2000
    assert sales_data["total"] == 2
    assert len(sales_data["items"]) == 1

    purchases = client.get("/api/v1/reports/purchases?page_size=1&supplier_id=all&from=null&to=All")
    expenses = client.get("/api/v1/reports/expenses?page_size=1&from=All&to=undefined")
    stock = client.get("/api/v1/reports/stock?page_size=1&product_id=All")
    profit = client.get("/api/v1/reports/profit-loss?from=2026-09-30&to=2026-09-30")
    assert purchases.json()["summary"]["total"] == 500
    assert purchases.json()["summary"]["count"] == 1
    assert expenses.json()["summary"]["total"] == 100
    assert expenses.json()["summary"]["count"] == 1
    assert stock.json()["summary"]["count"] == 1
    assert stock.json()["items"][0]["stock_value"] == 200
    assert profit.json()["net_profit"] == 600

    dashboard = client.get("/api/v1/dashboard").json()
    assert dashboard["total_receivables"] == 2000
    assert dashboard["total_payables"] == 3500
    assert dashboard["todays_sales"] == 1200


def test_stock_report_serializes_product_category_name(api_db):
    client, db = api_db
    category = Category(id="CAT-1", shop_id="SHOP-WOM", name="Fuel")
    db.add(category)
    product = db.get(Product, "PRD-1")
    product.category_id = category.id
    product.category = category
    db.commit()

    response = client.get("/api/v1/reports/stock?page=1&page_size=25&product_id=All")
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["category"] == "Fuel"


def test_dashboard_query_count_stays_bounded_with_many_parties(api_db):
    client, db = api_db
    db.add_all([
        Customer(id=f"CUS-BULK-{index}", shop_id="SHOP-WOM", name=f"Customer {index}", opening_balance=100, status="Active")
        for index in range(30)
    ])
    db.add_all([
        Supplier(id=f"SUP-BULK-{index}", shop_id="SHOP-WOM", name=f"Supplier {index}", opening_balance=100, status="Active")
        for index in range(30)
    ])
    db.commit()
    statement_count = 0

    def count_statement(*_args):
        nonlocal statement_count
        statement_count += 1

    event.listen(db.bind, "before_cursor_execute", count_statement)
    try:
        response = client.get("/api/v1/dashboard")
    finally:
        event.remove(db.bind, "before_cursor_execute", count_statement)

    assert response.status_code == 200, response.text
    assert statement_count < 30


def test_dashboard_isolates_every_metric_without_session_level_scope(api_db, monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def utcnow(cls):
            return TODAY

    monkeypatch.setattr(operations_api, "datetime", FrozenDateTime)
    client, db = api_db
    db.info.pop("shop_id", None)
    db.add_all([
        Shop(id="SHOP-AH", name="Abdul Haq", code="AH"),
        Customer(id="CUS-AH-DASH", shop_id="SHOP-AH", name="AH Customer", opening_balance=200, status="Active"),
        Supplier(id="SUP-AH-DASH", shop_id="SHOP-AH", name="AH Supplier", opening_balance=300, status="Active"),
        Product(id="PRD-AH-DASH", shop_id="SHOP-AH", name="AH Product", unit="kg", current_stock=0, purchase_price=50, minimum_stock=2, status="active"),
    ])
    add_sale(db, "WOM-DASH-SALE", TODAY, 10000, customer_id="CUS-1", sale_type="installment", paid=0)
    add_sale(db, "AH-DASH-SALE", TODAY, 50000, shop_id="SHOP-AH", customer_id="CUS-AH-DASH", sale_type="installment", paid=0)
    add_purchase(db, "WOM-DASH-PURCHASE", TODAY, 4000)
    add_purchase(db, "AH-DASH-PURCHASE", TODAY, 20000, shop_id="SHOP-AH", supplier_id="SUP-AH-DASH")
    add_expense(db, "WOM-DASH-EXPENSE", TODAY, "Rent", 500)
    add_expense(db, "AH-DASH-EXPENSE", TODAY, "Rent", 2500, shop_id="SHOP-AH")
    db.get(Product, "PRD-1").current_stock = 0
    db.commit()

    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id="WOM-ADMIN", shop_id="SHOP-WOM")
    wom = client.get("/api/v1/dashboard")
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id="AH-ADMIN", shop_id="SHOP-AH")
    ah = client.get("/api/v1/dashboard")
    assert wom.status_code == ah.status_code == 200
    wom_data, ah_data = wom.json(), ah.json()
    assert wom_data["todays_sales"] == 10000
    assert wom_data["todays_purchases"] == 4000
    assert wom_data["todays_profit_loss"] == 5500
    assert wom_data["total_receivables"] == 12000
    assert wom_data["total_payables"] == 7000
    assert [row["sales"] for row in wom_data["trend"]][-1] == 10000
    assert [row["purchases"] for row in wom_data["trend"]][-1] == 4000
    assert {row["id"] for row in wom_data["recent_sales"]} == {"WOM-DASH-SALE"}
    assert {row["id"] for row in wom_data["low_stock"]} == {"PRD-1"}
    assert ah_data["todays_sales"] == 50000
    assert ah_data["todays_purchases"] == 20000
    assert ah_data["todays_profit_loss"] == 27500
    assert ah_data["total_receivables"] == 50200
    assert ah_data["total_payables"] == 20300
    assert [row["sales"] for row in ah_data["trend"]][-1] == 50000
    assert [row["purchases"] for row in ah_data["trend"]][-1] == 20000
    assert {row["id"] for row in ah_data["recent_sales"]} == {"AH-DASH-SALE"}
    assert {row["id"] for row in ah_data["low_stock"]} == {"PRD-AH-DASH"}
