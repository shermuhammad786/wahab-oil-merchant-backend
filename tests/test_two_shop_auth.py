from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import create_access_token, decode_token, hash_password, verify_password
from app.db.base import Base
from app.db.session import get_db
from app.models.customer import Customer
from app.models.cash_book import CashDayClose
from app.models.product import Product
from app.models.purchases import Purchase
from app.models.sales import Sale
from app.models.settings import AppSetting
from app.models.stock import StockMovement
from app.models.shop import Shop
from app.models.supplier import Supplier
from app.models.user import User
from app.main import app
from app.repositories.customer import CustomerRepository
from app.services.auth import AuthService
from app.services.operations import OperationsService


def make_test_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return SessionLocal()


def test_login_builds_shop_scoped_token():
    session = make_test_session()
    wom = Shop(id="SHOP-WOM", name="Wahab Oil Merchant", code="WOM")
    session.add(wom)
    session.commit()

    user = User(
        id="USR-WOM",
        name="Wahab Admin",
        email="wom@local.test",
        password_hash="hashed",
        role="admin",
        shop_id="SHOP-WOM",
        is_active=True,
    )
    session.add(user)
    session.commit()

    token = create_access_token(subject=user.email, shop_id=user.shop_id, role=user.role)
    payload = decode_token(token)

    assert payload["sub"] == user.email
    assert payload["shop_id"] == "SHOP-WOM"
    assert payload["role"] == "admin"
    session.close()


def test_login_rejects_wrong_shop_selection():
    session = make_test_session()
    wom = Shop(id="SHOP-WOM", name="Wahab Oil Merchant", code="WOM")
    ah = Shop(id="SHOP-AH", name="Abdul Haq", code="AH")
    session.add_all([wom, ah])
    session.commit()

    user = User(
        id="USR-WOM",
        name="Wahab Admin",
        email="wom@local.test",
        password_hash="$2b$12$2mSscE0G9rEOk4aR9m0u7O2eQF7sV.0z2Dg0Vw/0rN4e8bYx0F0Wm",
        role="admin",
        shop_id="SHOP-WOM",
        is_active=True,
    )
    session.add(user)
    session.commit()

    try:
        AuthService(session).login("wom@local.test", "secret123", shop_id="SHOP-AH")
        raise AssertionError("Wrong shop selection should be rejected")
    except Exception as exc:  # pragma: no cover - assertion is the behavior under test
        assert "shop" in str(exc).lower() or "invalid" in str(exc).lower()
    finally:
        session.close()


def test_change_password_requires_current_password_and_updates_only_current_shop_user():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as seed:
        seed.add_all([
            Shop(id="SHOP-WOM", name="Wahab Oil Merchant", code="WOM"),
            Shop(id="SHOP-AH", name="Abdul Haq", code="AH"),
            User(id="USR-WOM", name="WOM Admin", email="wom@local.test", password_hash=hash_password("old-wom-password"), role="admin", shop_id="SHOP-WOM", is_active=True),
            User(id="USR-AH", name="AH Admin", email="ah@local.test", password_hash=hash_password("old-ah-password"), role="admin", shop_id="SHOP-AH", is_active=True),
        ])
        seed.commit()

    def override_get_db():
        with SessionLocal() as request_session:
            yield request_session

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            wom_login = client.post("/api/v1/auth/login", json={"email": "wom@local.test", "password": "old-wom-password", "shop_id": "SHOP-WOM"})
            assert wom_login.status_code == 200
            token = wom_login.json()["access_token"]
            me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert me.status_code == 200
            assert me.json()["shop_name"] == "Wahab Oil Merchant"

            invalid = client.post(
                "/api/v1/auth/change-password",
                headers={"Authorization": f"Bearer {token}"},
                json={"current_password": "wrong-password", "new_password": "new-wom-password", "confirm_password": "new-wom-password"},
            )
            assert invalid.status_code == 401

            changed = client.post(
                "/api/v1/auth/change-password",
                headers={"Authorization": f"Bearer {token}"},
                json={"current_password": "old-wom-password", "new_password": "new-wom-password", "confirm_password": "new-wom-password"},
            )
            assert changed.status_code == 200, changed.text

            with SessionLocal() as verify:
                wom_user = verify.get(User, "USR-WOM")
                ah_user = verify.get(User, "USR-AH")
                assert verify_password("new-wom-password", wom_user.password_hash) is True
                assert verify_password("old-ah-password", ah_user.password_hash) is True

            failed_login = client.post("/api/v1/auth/login", json={"email": "wom@local.test", "password": "old-wom-password", "shop_id": "SHOP-WOM"})
            assert failed_login.status_code == 401
            success_login = client.post("/api/v1/auth/login", json={"email": "wom@local.test", "password": "new-wom-password", "shop_id": "SHOP-WOM"})
            assert success_login.status_code == 200
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def test_customer_repository_filters_out_other_shop_records():
    session = make_test_session()
    wom = Shop(id="SHOP-WOM", name="Wahab Oil Merchant", code="WOM")
    ah = Shop(id="SHOP-AH", name="Abdul Haq", code="AH")
    session.add_all([wom, ah])
    session.add_all([
        Customer(id="CUS-WOM", shop_id="SHOP-WOM", name="WOM Customer", status="Active"),
        Customer(id="CUS-AH", shop_id="SHOP-AH", name="AH Customer", status="Active"),
    ])
    session.commit()

    rows = CustomerRepository(session).list(shop_id="SHOP-WOM")

    assert [row.id for row in rows] == ["CUS-WOM"]
    assert CustomerRepository(session).get_by_id("CUS-AH", shop_id="SHOP-WOM") is None
    session.close()


def test_session_shop_scope_and_tenant_keys_isolate_direct_orm_reads():
    session = make_test_session()
    session.add_all([
        Shop(id="SHOP-WOM", name="Wahab Oil Merchant", code="WOM"),
        Shop(id="SHOP-AH", name="Abdul Haq", code="AH"),
        Customer(id="CUS-WOM", shop_id="SHOP-WOM", name="WOM Customer", status="Active"),
        Customer(id="CUS-AH", shop_id="SHOP-AH", name="AH Customer", status="Active"),
        AppSetting(key="invoice_prefix", shop_id="SHOP-WOM", value="WOM-INV"),
        AppSetting(key="invoice_prefix", shop_id="SHOP-AH", value="AH-INV"),
        CashDayClose(shop_id="SHOP-WOM", date=datetime(2026, 10, 4), opening_balance=0, cash_in=0, cash_out=0, closing_balance=0, finalized_at=datetime(2026, 10, 4)),
        CashDayClose(shop_id="SHOP-AH", date=datetime(2026, 10, 4), opening_balance=0, cash_in=0, cash_out=0, closing_balance=0, finalized_at=datetime(2026, 10, 4)),
    ])
    session.commit()

    session.info["shop_id"] = "SHOP-WOM"
    assert [row.id for row in session.scalars(select(Customer)).all()] == ["CUS-WOM"]
    assert session.scalar(select(func.count(Customer.id))) == 1
    assert session.get(Customer, "CUS-AH") is None
    assert session.scalar(select(AppSetting).where(AppSetting.key == "invoice_prefix")).value == "WOM-INV"
    assert len(session.scalars(select(CashDayClose)).all()) == 1
    assert session.execute(update(Customer).where(Customer.id == "CUS-AH").values(name="Changed by WOM")).rowcount == 0
    assert session.execute(delete(Customer).where(Customer.id == "CUS-AH")).rowcount == 0

    session.info["shop_id"] = "SHOP-AH"
    assert [row.id for row in session.scalars(select(Customer)).all()] == ["CUS-AH"]
    assert session.scalar(select(AppSetting).where(AppSetting.key == "invoice_prefix")).value == "AH-INV"
    assert len(session.scalars(select(CashDayClose)).all()) == 1
    session.close()


def test_cross_shop_sale_rejects_foreign_product_without_partial_records():
    session = make_test_session()
    session.info["shop_id"] = "SHOP-WOM"
    session.add_all([
        Shop(id="SHOP-WOM", name="Wahab Oil Merchant", code="WOM"),
        Shop(id="SHOP-AH", name="Abdul Haq", code="AH"),
        Product(id="PRD-AH", shop_id="SHOP-AH", name="AH Oil", unit="kg", current_stock=10, status="active"),
    ])
    session.commit()

    try:
        OperationsService(session).sale({
            "shopId": "SHOP-AH",
            "saleType": "retail",
            "date": "2026-10-04",
            "paid": 0,
            "items": [{"productId": "PRD-AH", "quantity": 1, "rate": 100}],
        })
        raise AssertionError("A WOM transaction must not use an AH product")
    except NotFoundError:
        pass

    assert session.scalars(select(Sale)).all() == []
    assert session.scalars(select(StockMovement)).all() == []
    session.close()


def test_customer_repository_requires_shop_context():
    session = make_test_session()
    try:
        CustomerRepository(session).list()
        raise AssertionError("Customer listing without an authenticated shop must fail closed")
    except ValidationError:
        pass
    session.close()


def test_customer_api_isolates_create_list_count_and_direct_ids():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as seed:
        seed.add_all([
            Shop(id="SHOP-WOM", name="Wahab Oil Merchant", code="WOM"),
            Shop(id="SHOP-AH", name="Abdul Haq", code="AH"),
            User(id="USR-WOM-API", name="WOM Admin", email="api-wom@test.local", password_hash=hash_password("wom-test-password"), role="admin", shop_id="SHOP-WOM", is_active=True),
            User(id="USR-AH-API", name="AH Admin", email="api-ah@test.local", password_hash=hash_password("ah-test-password"), role="admin", shop_id="SHOP-AH", is_active=True),
            Customer(id="CUS-WOM-API", shop_id="SHOP-WOM", name="WOM Customer", status="Active"),
            Customer(id="CUS-AH-API", shop_id="SHOP-AH", name="AH Customer", status="Active"),
            Product(id="PRD-WOM-API", shop_id="SHOP-WOM", name="WOM Oil", unit="kg", purchase_price=10, sale_price=12, current_stock=8, minimum_stock=1, status="active"),
            Product(id="PRD-AH-API", shop_id="SHOP-AH", name="AH Oil", unit="kg", purchase_price=20, sale_price=24, current_stock=5, minimum_stock=1, status="active"),
            Supplier(id="SUP-WOM-API", shop_id="SHOP-WOM", name="WOM Supplier", status="Active"),
            Supplier(id="SUP-AH-API", shop_id="SHOP-AH", name="AH Supplier", status="Active"),
            Sale(id="SAL-WOM-COUNTER", shop_id="SHOP-WOM", invoice_number="INV-1001", customer_name="Walk-in", sale_type="retail", sale_date=datetime(2026, 10, 4), subtotal=100, discount=0, total=100, paid=100, remaining=0, payment_status="paid", status="completed"),
            Sale(id="SAL-AH-COUNTER", shop_id="SHOP-AH", invoice_number="INV-1001", customer_name="Walk-in", sale_type="retail", sale_date=datetime(2026, 10, 4), subtotal=100, discount=0, total=100, paid=100, remaining=0, payment_status="paid", status="completed"),
            Purchase(id="PUR-WOM-COUNTER", shop_id="SHOP-WOM", purchase_number="PUR-1001", supplier_id="SUP-WOM-API", purchase_date=datetime(2026, 10, 4), subtotal=100, discount=0, total=100, paid=100, remaining=0, payment_status="paid", status="completed"),
            Purchase(id="PUR-AH-COUNTER", shop_id="SHOP-AH", purchase_number="PUR-1001", supplier_id="SUP-AH-API", purchase_date=datetime(2026, 10, 4), subtotal=100, discount=0, total=100, paid=100, remaining=0, payment_status="paid", status="completed"),
        ])
        seed.commit()

    def override_get_db():
        with SessionLocal() as request_session:
            yield request_session

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            ah_login = client.post("/api/v1/auth/login", json={"email": "api-ah@test.local", "password": "ah-test-password", "shop_id": "SHOP-AH"})
            wom_login = client.post("/api/v1/auth/login", json={"email": "api-wom@test.local", "password": "wom-test-password", "shop_id": "SHOP-WOM"})
            assert ah_login.status_code == 200
            assert wom_login.status_code == 200
            ah_token = ah_login.json()["access_token"]
            wom_token = wom_login.json()["access_token"]
            assert decode_token(ah_token)["shop_id"] == "SHOP-AH"
            assert decode_token(wom_token)["shop_id"] == "SHOP-WOM"
            ah_headers = {"Authorization": f"Bearer {ah_token}"}
            wom_headers = {"Authorization": f"Bearer {wom_token}"}

            created = client.post("/api/v1/customers", headers=ah_headers, json={"name": "Created in AH", "shopId": "SHOP-WOM"})
            assert created.status_code == 201, created.text
            created_id = created.json()["id"]
            with SessionLocal() as verify:
                assert verify.get(Customer, created_id).shop_id == "SHOP-AH"

            ah_list = client.get("/api/v1/customers", headers=ah_headers)
            wom_list = client.get("/api/v1/customers", headers=wom_headers)
            assert ah_list.status_code == wom_list.status_code == 200
            assert {row["id"] for row in ah_list.json()} == {"CUS-AH-API", created_id}
            assert {row["id"] for row in wom_list.json()} == {"CUS-WOM-API"}
            assert ah_list.headers["X-Total-Count"] == "2"
            assert wom_list.headers["X-Total-Count"] == "1"

            for headers, own_product, foreign_product, own_supplier, foreign_supplier in [
                (ah_headers, "PRD-AH-API", "PRD-WOM-API", "SUP-AH-API", "SUP-WOM-API"),
                (wom_headers, "PRD-WOM-API", "PRD-AH-API", "SUP-WOM-API", "SUP-AH-API"),
            ]:
                products = client.get("/api/v1/products?status=Active&page_size=500", headers=headers)
                suppliers = client.get("/api/v1/suppliers?status=Active&page_size=500", headers=headers)
                assert products.status_code == suppliers.status_code == 200
                assert {row["id"] for row in products.json()} == {own_product}
                assert {row["id"] for row in suppliers.json()} == {own_supplier}
                assert foreign_product not in {row["id"] for row in products.json()}
                assert foreign_supplier not in {row["id"] for row in suppliers.json()}

            for headers in (ah_headers, wom_headers):
                invoice = client.get("/api/v1/sales/next-invoice", headers=headers)
                purchase_number = client.get("/api/v1/purchases/next-number", headers=headers)
                assert invoice.json() == {"invoice_number": "INV-1002"}
                assert purchase_number.json() == {"purchase_number": "PUR-1002"}

            ah_id = "CUS-AH-API"
            wom_id = "CUS-WOM-API"
            for path, method, payload in [
                (f"/api/v1/customers/{ah_id}", "get", None),
                (f"/api/v1/customers/{ah_id}", "put", {"name": "forbidden"}),
                (f"/api/v1/customers/{ah_id}/deactivate", "post", {}),
                (f"/api/v1/customers/{ah_id}/ledger", "get", None),
                (f"/api/v1/customers/{ah_id}/installments", "get", None),
                (f"/api/v1/customers/{ah_id}/payments", "post", {"amount": 1, "date": "2026-10-04"}),
            ]:
                response = getattr(client, method)(path, headers=wom_headers, json=payload) if payload is not None else getattr(client, method)(path, headers=wom_headers)
                assert response.status_code == 404, f"{method.upper()} {path}: {response.status_code} {response.text}"

            with SessionLocal() as verify:
                sales_before_foreign_attempt = verify.scalar(select(func.count(Sale.id)))
            foreign_sale = client.post("/api/v1/sales", headers=wom_headers, json={
                "customerId": ah_id,
                "saleType": "installment",
                "date": "2026-10-04",
                "items": [],
            })
            assert foreign_sale.status_code == 404, foreign_sale.text
            assert client.get(f"/api/v1/customers/{wom_id}", headers=ah_headers).status_code == 404
            assert client.put(f"/api/v1/customers/{wom_id}", headers=ah_headers, json={"name": "forbidden"}).status_code == 404

            with SessionLocal() as verify:
                assert verify.scalar(select(func.count(Sale.id))) == sales_before_foreign_attempt
                assert verify.get(Customer, created_id).shop_id == "SHOP-AH"
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()
