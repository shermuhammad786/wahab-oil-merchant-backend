from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.security import require_admin
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    BankAccount,
    CashBookDraft,
    CashCreditPerson,
    CashCreditTransaction,
    CashDayClose,
    CashTransaction,
    Customer,
    CustomerLedgerEntry,
    CustomerPayment,
    Expense,
    Product,
    StockMovement,
    Supplier,
    SupplierLedgerEntry,
    SupplierPayment,
)
from app.models.shop import Shop
from app.services.operations import OperationsService


DAY = "2026-09-30"


@pytest.fixture
def cash_api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        db.add(Shop(id="SHOP-WOM", name="Wahab Oil Merchant", code="WOM"))
        db.info["shop_id"] = "SHOP-WOM"
        db.add_all([
            Supplier(id="SUP-A", shop_id="SHOP-WOM", name="Supplier A", opening_balance=40000, status="Active"),
            Supplier(id="SUP-B", shop_id="SHOP-WOM", name="Supplier B", opening_balance=40000, status="Active"),
            Customer(id="CUS-A", shop_id="SHOP-WOM", name="Customer A", opening_balance=40000, status="Active"),
            BankAccount(id="BANK-A", shop_id="SHOP-WOM", name="Test Bank", opening_balance=10000),
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


def post_customer(client, amount, customer_id="CUS-A"):
    return client.post("/api/v1/cash-book/customer-payments", json={
        "date": DAY,
        "payments": [{"customerId": customer_id, "amount": amount}],
    })


def post_supplier(client, amount, supplier_id="SUP-A"):
    return client.post("/api/v1/cash-book/supplier-payments", json={
        "date": DAY,
        "payments": [{"supplierId": supplier_id, "amount": amount}],
    })


def finalize(client):
    return client.post("/api/v1/cash-book/finalize", json={"date": DAY})


def test_customer_installment_is_pending_until_finalize(cash_api):
    client, db = cash_api
    response = post_customer(client, 10000)
    assert response.status_code == 200, response.text
    assert len(response.json()["pending_items"]) == 1
    assert db.scalars(select(CustomerPayment)).all() == []
    assert db.scalars(select(CustomerLedgerEntry)).all() == []
    assert db.scalars(select(CashTransaction)).all() == []
    assert OperationsService(db)._customer_balance("CUS-A") == 40000

    finalized = finalize(client)
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["pending_items"] == []
    assert len(db.scalars(select(CustomerPayment)).all()) == 1
    assert len(db.scalars(select(CustomerLedgerEntry)).all()) == 1
    assert len(db.scalars(select(CashTransaction)).all()) == 1
    assert OperationsService(db)._customer_balance("CUS-A") == 30000


def test_customer_batch_accepts_camel_and_snake_case_ids(cash_api):
    client, db = cash_api
    response = client.post("/api/v1/cash-book/customer-payments", json={"date": DAY, "payments": [
        {"customerId": "CUS-A", "amount": 10000},
        {"customer_id": "CUS-A", "amount": 10000},
    ]})
    assert response.status_code == 200, response.text
    assert len(response.json()["pending_items"]) == 2
    assert db.scalars(select(CustomerPayment)).all() == []
    assert finalize(client).status_code == 200
    assert len(db.scalars(select(CustomerPayment)).all()) == 2
    assert OperationsService(db)._customer_balance("CUS-A") == 20000


def test_cash_credit_detail_includes_transaction_history(cash_api):
    client, _ = cash_api
    created = client.post("/api/v1/cash-credit/people", json={
        "name": "Credit Person",
        "amountGiven": 100,
        "date": DAY,
        "note": "Initial credit",
    })
    assert created.status_code == 201, created.text
    person_id = created.json()["id"]

    given = client.post(f"/api/v1/cash-credit/people/{person_id}/give", json={
        "amount": 50,
        "date": DAY,
        "note": "Additional credit",
    })
    assert given.status_code == 200, given.text

    response = client.get(f"/api/v1/cash-credit/people/{person_id}")
    assert response.status_code == 200, response.text
    account = response.json()
    assert account["person"]["name"] == "Credit Person"
    assert [transaction["type"] for transaction in account["transactions"]] == ["Credit Given", "Credit Given"]
    assert [transaction["remaining"] for transaction in account["transactions"]] == [100, 150]


def test_cash_credit_detail_reads_legacy_cash_transaction_history(cash_api):
    client, db = cash_api
    db.add(Shop(id="SHOP-AH", name="Abdul Haq", code="AH"))
    db.commit()
    person = CashCreditPerson(
        id="CCP-LEGACY",
        shop_id="SHOP-WOM",
        name="Legacy Credit Person",
        total_cash_given=150,
        total_received=40,
    )
    db.add_all([
        person,
        CashTransaction(
            id="CSH-LEGACY-GIVEN",
            shop_id="SHOP-AH",
            transaction_date=datetime.fromisoformat(DAY),
            type="cash_out",
            category="cash_credit_given",
            description="Cash Credit Given",
            amount=150,
            reference_type="cash_credit",
            reference_id=person.id,
        ),
        CashTransaction(
            id="CSH-LEGACY-RECEIVED",
            shop_id="SHOP-AH",
            transaction_date=datetime.fromisoformat(DAY),
            type="cash_in",
            category="cash_credit_received",
            description="Cash Credit Received",
            amount=40,
            reference_type="cash_credit",
            reference_id=person.id,
        ),
    ])
    db.commit()

    response = client.get(f"/api/v1/cash-credit/people/{person.id}")
    assert response.status_code == 200, response.text
    transactions = response.json()["transactions"]
    assert [transaction["type"] for transaction in transactions] == ["Credit Given", "Payment Received"]
    assert [transaction["remaining"] for transaction in transactions] == [150, 110]


def test_invalid_later_supplier_payload_rejects_whole_draft_request(cash_api):
    client, db = cash_api
    response = client.post("/api/v1/cash-book/supplier-payments", json={"date": DAY, "payments": [
        {"supplierId": "SUP-A", "amount": 10000}, {"amount": 10000},
    ]})
    assert response.status_code == 422
    assert db.scalars(select(CashBookDraft)).all() == []
    assert db.scalars(select(SupplierPayment)).all() == []


def test_second_finalize_posts_only_new_customer_installment(cash_api):
    client, db = cash_api
    assert post_customer(client, 10000).status_code == 200
    assert finalize(client).status_code == 200
    assert OperationsService(db)._customer_balance("CUS-A") == 30000

    assert post_customer(client, 5000).status_code == 200
    assert OperationsService(db)._customer_balance("CUS-A") == 30000
    assert len(db.scalars(select(CustomerPayment)).all()) == 1
    response = finalize(client)
    assert response.status_code == 200, response.text

    assert len(db.scalars(select(CustomerPayment)).all()) == 2
    assert len(db.scalars(select(CustomerLedgerEntry)).all()) == 2
    assert len(db.scalars(select(CashTransaction)).all()) == 2
    assert OperationsService(db)._customer_balance("CUS-A") == 25000
    close = db.scalars(select(CashDayClose)).one()
    assert close.cash_in == Decimal("15000.00")


def test_same_day_business_operations_work_after_finalize(cash_api):
    client, db = cash_api
    db.add(Product(id="PRD-AFTER-CLOSE", shop_id="SHOP-WOM", name="Oil", unit="kg", current_stock=20, status="active"))
    db.commit()
    assert post_customer(client, 1000).status_code == 200
    assert finalize(client).status_code == 200
    original_payment = db.scalars(select(CustomerPayment)).one().id

    retail = client.post("/api/v1/sales", json={
        "date": DAY, "saleType": "retail", "paid": 1000,
        "items": [{"productId": "PRD-AFTER-CLOSE", "quantity": 1, "rate": 1000}],
    })
    assert retail.status_code == 201, retail.text
    installment = client.post("/api/v1/sales", json={
        "date": DAY, "saleType": "installment", "customerId": "CUS-A", "paid": 0,
        "items": [{"productId": "PRD-AFTER-CLOSE", "quantity": 1, "rate": 2000}],
    })
    assert installment.status_code == 201, installment.text
    assert len(db.scalars(select(CustomerLedgerEntry)).all()) == 2

    customer_payment = client.post(f"/api/v1/customers/CUS-A/payments", json={"date": DAY, "amount": 500})
    supplier_payment = client.post(f"/api/v1/suppliers/SUP-A/payments", json={"date": DAY, "amount": 500})
    expense = client.post("/api/v1/expenses", json={
        "date": DAY, "category": "Shop Expense", "subtype": "Utilities", "amount": 100,
    })
    purchase = client.post("/api/v1/purchases", json={
        "date": DAY, "supplierId": "SUP-A", "paid": 0,
        "items": [{"productId": "PRD-AFTER-CLOSE", "quantity": 1, "rate": 300}],
    })
    bank_deposit = client.post("/api/v1/banks/deposits", json={
        "date": DAY, "bankId": "BANK-A", "amount": 100,
    })
    bank_withdrawal = client.post("/api/v1/banks/withdrawals", json={
        "date": DAY, "bankId": "BANK-A", "amount": 50,
    })
    for response in (customer_payment, supplier_payment, expense, purchase, bank_deposit, bank_withdrawal):
        assert response.status_code in {200, 201}, response.text
    assert db.get(Product, "PRD-AFTER-CLOSE").current_stock == 19

    assert post_customer(client, 250).status_code == 200
    finalized = finalize(client)
    assert finalized.status_code == 200, finalized.text
    payments = db.scalars(select(CustomerPayment).order_by(CustomerPayment.created_at)).all()
    assert len(payments) == 3
    assert sum(payment.id == original_payment for payment in payments) == 1
    assert db.scalars(select(CashDayClose)).one().cash_in == Decimal("2800.00")


def test_supplier_payment_is_pending_then_posts_once(cash_api):
    client, db = cash_api
    assert post_supplier(client, 10000).status_code == 200
    assert len(db.scalars(select(SupplierPayment)).all()) == 0
    assert OperationsService(db)._supplier_balance("SUP-A") == 40000
    assert finalize(client).status_code == 200
    assert len(db.scalars(select(SupplierPayment)).all()) == 1
    assert len(db.scalars(select(SupplierLedgerEntry)).all()) == 1
    assert len(db.scalars(select(CashTransaction)).all()) == 1
    assert OperationsService(db)._supplier_balance("SUP-A") == 30000

    assert post_supplier(client, 5000).status_code == 200
    assert OperationsService(db)._supplier_balance("SUP-A") == 30000
    assert finalize(client).status_code == 200
    assert len(db.scalars(select(SupplierPayment)).all()) == 2
    assert len(db.scalars(select(SupplierLedgerEntry)).all()) == 2
    assert len(db.scalars(select(CashTransaction)).all()) == 2
    assert OperationsService(db)._supplier_balance("SUP-A") == 25000


@pytest.mark.parametrize("field", ["supplierId", "supplier_id"])
def test_supplier_draft_accepts_both_identifier_styles(cash_api, field):
    client, db = cash_api
    response = client.post("/api/v1/cash-book/supplier-payments", json={
        "date": DAY, "payments": [{field: "SUP-A", "amount": 10000, "paymentMethod": "Bank"}],
    })
    assert response.status_code == 200, response.text
    assert db.scalars(select(SupplierPayment)).all() == []
    assert response.json()["pending_items"][0]["amount"] == "10000.00"
    assert finalize(client).status_code == 200
    assert len(db.scalars(select(SupplierPayment)).all()) == 1
    assert db.scalars(select(SupplierPayment)).one().payment_method == "Cash"


@pytest.mark.parametrize("row", [
    {"amount": 10000},
    {"supplierId": "", "amount": 10000},
    {"supplierId": "SUP-A", "amount": 0},
    {"supplierId": "SUP-A", "amount": -1},
])
def test_invalid_supplier_draft_payload_is_rejected(cash_api, row):
    client, db = cash_api
    response = client.post("/api/v1/cash-book/supplier-payments", json={"date": DAY, "payments": [row]})
    assert response.status_code == 422, response.text
    assert db.scalars(select(CashBookDraft)).all() == []
    assert db.scalars(select(SupplierPayment)).all() == []


def test_supplier_batch_posts_all_rows_in_one_commit(cash_api):
    client, db = cash_api
    response = client.post("/api/v1/cash-book/supplier-payments", json={"date": DAY, "payments": [
        {"supplierId": "SUP-A", "amount": 5000},
        {"supplierId": "SUP-B", "amount": 10000},
        {"supplier_id": "SUP-A", "amount": 10000},
    ]})
    assert response.status_code == 200, response.text
    assert len(db.scalars(select(SupplierPayment)).all()) == 0
    with patch.object(db, "commit", wraps=db.commit) as commit:
        finalized = finalize(client)
        assert finalized.status_code == 200, finalized.text
        assert commit.call_count == 1
    assert len(db.scalars(select(SupplierPayment)).all()) == 3
    assert len(db.scalars(select(SupplierLedgerEntry)).all()) == 3
    assert len(db.scalars(select(CashTransaction)).all()) == 3
    assert OperationsService(db)._supplier_balance("SUP-A") == 25000
    assert OperationsService(db)._supplier_balance("SUP-B") == 30000


def test_later_supplier_failure_rolls_back_full_batch(cash_api):
    client, db = cash_api
    response = client.post("/api/v1/cash-book/supplier-payments", json={"date": DAY, "payments": [
        {"supplierId": "SUP-A", "amount": 5000},
        {"supplierId": "SUP-B", "amount": 10000},
        {"supplierId": "SUP-A", "amount": 36000},
    ]})
    assert response.status_code == 200, response.text
    finalized = finalize(client)
    assert finalized.status_code == 409, finalized.text
    with Session(db.bind) as verify:
        assert verify.scalars(select(SupplierPayment)).all() == []
        assert verify.scalars(select(SupplierLedgerEntry)).all() == []
        assert verify.scalars(select(CashTransaction)).all() == []
        drafts = verify.scalars(select(CashBookDraft)).all()
        assert len(drafts) == 3
        assert all(row.status == "pending" for row in drafts)
        assert OperationsService(verify)._supplier_balance("SUP-A") == 40000
        assert OperationsService(verify)._supplier_balance("SUP-B") == 40000


def test_cash_book_expense_is_draft_until_finalize(cash_api):
    client, db = cash_api
    response = client.post("/api/v1/cash-book/expenses", json={"date": DAY, "expenses": [{
        "category": "Home Expense", "subtype": "Extra Expense",
        "customSubtype": "Repairs", "amount": 1000, "note": "Daily repairs",
    }]})
    assert response.status_code == 200, response.text
    assert len(db.scalars(select(Expense)).all()) == 0
    assert len(db.scalars(select(CashTransaction)).all()) == 0
    assert OperationsService(db).daily(DAY)["cash_out"] == 0

    assert finalize(client).status_code == 200
    expense = db.scalars(select(Expense)).one()
    assert expense.custom_subtype == "Repairs"
    assert expense.description == "Daily repairs"
    assert expense.payment_method == "Cash"
    assert len(db.scalars(select(CashTransaction)).all()) == 1

    response = client.post("/api/v1/cash-book/expenses", json={"date": DAY, "expenses": [{
        "category": "Shop Expense", "subtype": "Utilities", "amount": 500, "note": "Power",
    }]})
    assert response.status_code == 200, response.text
    assert len(db.scalars(select(Expense)).all()) == 1
    assert finalize(client).status_code == 200
    assert len(db.scalars(select(Expense)).all()) == 2
    assert len(db.scalars(select(CashTransaction)).all()) == 2


def test_walkin_sale_and_stock_are_deferred_until_finalize(cash_api):
    client, db = cash_api
    db.add(Product(id="PRD-A", shop_id="SHOP-WOM", name="Oil", unit="kg", current_stock=10, status="active"))
    db.commit()
    response = client.post("/api/v1/cash-book/retail-sale", json={
        "date": DAY,
        "cashReceived": 1000,
        "items": [{"productId": "PRD-A", "quantity": 1, "rate": 1000}],
    })
    assert response.status_code == 200, response.text
    assert db.get(Product, "PRD-A").current_stock == 10
    assert len(db.scalars(select(StockMovement)).all()) == 0
    assert len(db.scalars(select(CashTransaction)).all()) == 0

    assert finalize(client).status_code == 200
    assert db.get(Product, "PRD-A").current_stock == 9
    assert len(db.scalars(select(StockMovement)).all()) == 1
    assert len(db.scalars(select(CashTransaction)).all()) == 1

    response = client.post("/api/v1/cash-book/retail-sale", json={
        "date": DAY,
        "cashReceived": 1000,
        "items": [{"productId": "PRD-A", "quantity": 1, "rate": 1000}],
    })
    assert response.status_code == 200, response.text
    assert db.get(Product, "PRD-A").current_stock == 9
    assert finalize(client).status_code == 200
    assert db.get(Product, "PRD-A").current_stock == 8
    assert len(db.scalars(select(StockMovement)).all()) == 2
    assert len(db.scalars(select(CashTransaction)).all()) == 2


def test_bank_deposit_is_deferred_until_finalize(cash_api):
    client, db = cash_api
    response = client.post("/api/v1/cash-book/bank-transactions", json={
        "date": DAY, "type": "Deposit", "bankId": "BANK-A", "amount": 2500,
    })
    assert response.status_code == 200, response.text
    ops = OperationsService(db)
    assert ops._bank_balance("BANK-A") == 10000
    assert ops.daily(DAY)["cash_out"] == 0

    assert finalize(client).status_code == 200
    assert ops._bank_balance("BANK-A") == 12500
    assert ops.daily(DAY)["cash_out"] == 2500


def test_bank_withdrawal_and_transfer_wait_for_finalize(cash_api):
    client, db = cash_api
    db.add(BankAccount(id="BANK-B", shop_id="SHOP-WOM", name="Second Test Bank", opening_balance=0))
    db.commit()
    ops = OperationsService(db)

    withdrawal = client.post("/api/v1/cash-book/bank-transactions", json={
        "date": DAY, "type": "Withdrawal", "bankId": "BANK-A", "amount": 2500,
    })
    assert withdrawal.status_code == 200, withdrawal.text
    assert ops._bank_balance("BANK-A") == 10000
    assert ops.daily(DAY)["cash_in"] == 0

    transfer = client.post("/api/v1/cash-book/bank-transactions", json={
        "date": DAY, "type": "Transfer", "fromBankId": "BANK-A", "toBankId": "BANK-B", "amount": 1000,
    })
    assert transfer.status_code == 200, transfer.text
    assert ops._bank_balance("BANK-A") == 10000
    assert ops._bank_balance("BANK-B") == 0
    assert len(db.scalars(select(CashTransaction)).all()) == 0

    finalized = finalize(client)
    assert finalized.status_code == 200, finalized.text
    assert ops._bank_balance("BANK-A") == 6500
    assert ops._bank_balance("BANK-B") == 1000
    assert ops.daily(DAY)["cash_in"] == 2500
    assert ops.daily(DAY)["cash_out"] == 0


def test_non_cashbook_bank_endpoint_still_posts_and_history_matches_ui(cash_api):
    client, db = cash_api
    response = client.post("/api/v1/banks/deposits", json={
        "date": DAY, "bankId": "BANK-A", "amount": 2500,
    })
    assert response.status_code == 200, response.text
    assert OperationsService(db)._bank_balance("BANK-A") == 12500

    history = client.get(f"/api/v1/banks/transactions?from={DAY}&to={DAY}")
    assert history.status_code == 200
    item = history.json()[0]
    assert item["date"].startswith(DAY)
    assert item["bank"] == "Test Bank"
    assert item["bank_id"] == "BANK-A"
    assert item["balance_impact"] == "2500.00"


def test_failed_batch_rolls_back_every_effect_and_keeps_drafts(cash_api):
    client, db = cash_api
    assert post_customer(client, 5000).status_code == 200
    assert post_customer(client, 40000).status_code == 200

    response = finalize(client)
    assert response.status_code == 409, response.text
    with Session(db.bind) as verify:
        assert verify.scalars(select(CustomerPayment)).all() == []
        assert verify.scalars(select(CustomerLedgerEntry)).all() == []
        assert verify.scalars(select(CashTransaction)).all() == []
        drafts = verify.scalars(select(CashBookDraft).order_by(CashBookDraft.created_at)).all()
        assert len(drafts) == 2
        assert all(draft.status == "pending" for draft in drafts)
        assert OperationsService(verify)._customer_balance("CUS-A") == 40000


def test_expense_failure_rolls_back_preceding_customer_draft(cash_api):
    client, db = cash_api
    assert post_customer(client, 5000).status_code == 200
    staged_expense = client.post("/api/v1/cash-book/expenses", json={"date": DAY, "expenses": [{
        "category": "Home Expense", "subtype": "Invalid subtype", "amount": 1000,
    }]})
    assert staged_expense.status_code == 200, staged_expense.text

    response = finalize(client)
    assert response.status_code == 422, response.text
    with Session(db.bind) as verify:
        assert verify.scalars(select(CustomerPayment)).all() == []
        assert verify.scalars(select(CustomerLedgerEntry)).all() == []
        assert verify.scalars(select(CashTransaction)).all() == []
        assert verify.scalars(select(Expense)).all() == []
        drafts = verify.scalars(select(CashBookDraft)).all()
        assert len(drafts) == 2
        assert all(row.status == "pending" for row in drafts)
        assert OperationsService(verify)._customer_balance("CUS-A") == 40000


def test_empty_finalize_is_safe_and_repeatable(cash_api):
    client, db = cash_api
    assert finalize(client).status_code == 200
    response = finalize(client)
    assert response.status_code == 200, response.text
    assert db.scalars(select(CustomerPayment)).all() == []
    assert db.scalars(select(SupplierPayment)).all() == []


def test_pending_draft_can_be_removed_without_posting(cash_api):
    client, db = cash_api
    response = post_customer(client, 10000)
    assert response.status_code == 200, response.text
    draft_id = response.json()["pending_items"][0]["id"]

    removed = client.delete(f"/api/v1/cash-book/drafts/{draft_id}?date={DAY}")
    assert removed.status_code == 200, removed.text
    assert removed.json()["pending_items"] == []
    assert db.scalars(select(CashBookDraft)).all() == []
    assert db.scalars(select(CustomerPayment)).all() == []
    assert db.scalars(select(CustomerLedgerEntry)).all() == []
    assert db.scalars(select(CashTransaction)).all() == []


def test_cash_credit_transactions_are_excluded_from_cash_book(cash_api):
    client, db = cash_api
    person = CashCreditPerson(id="CC-A", shop_id="SHOP-WOM", name="Cash Credit", total_cash_given=1000, total_received=0)
    db.add(person)
    db.add(CashCreditTransaction(id="CCT-A", shop_id="SHOP-WOM", person_id="CC-A", transaction_date=datetime.fromisoformat(DAY), type="Credit Given", amount=1000))
    db.add(CashTransaction(id="CSH-CC", shop_id="SHOP-WOM", transaction_date=datetime.fromisoformat(DAY), type="cash_in", category="cash_credit_received", description="Excluded", amount=1000, reference_type="cash_credit"))
    db.commit()

    response = client.get(f"/api/v1/cash-book/daily?date={DAY}")
    assert response.status_code == 200
    assert response.json()["total_cash_in"] == 0
    assert response.json()["closing_balance"] == 0


def test_standalone_supplier_payment_still_posts_immediately(cash_api):
    client, db = cash_api
    response = client.post("/api/v1/suppliers/SUP-A/payments", json={"amount": 10000, "date": DAY})
    assert response.status_code == 201, response.text
    assert len(db.scalars(select(SupplierPayment)).all()) == 1
    assert OperationsService(db)._supplier_balance("SUP-A") == 30000


def test_purchase_then_cash_book_supplier_payment_balance(cash_api):
    client, db = cash_api
    db.get(Supplier, "SUP-A").opening_balance = 0
    db.add(Product(id="PRD-PUR", shop_id="SHOP-WOM", name="Oil", unit="kg", current_stock=0, status="active"))
    db.commit()
    ops = OperationsService(db)
    ops.purchase({"supplierId": "SUP-A", "date": DAY, "paid": 50000,
                  "items": [{"productId": "PRD-PUR", "quantity": 90, "rate": 1000}]})
    assert ops._supplier_balance("SUP-A") == 40000

    response = post_supplier(client, 10000)
    assert response.status_code == 200, response.text
    assert ops._supplier_balance("SUP-A") == 40000
    assert finalize(client).status_code == 200
    assert ops._supplier_balance("SUP-A") == 30000
