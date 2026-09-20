from decimal import Decimal


from app.core.constants import StockMovementType
from app.services.operations import money, qty


def test_sale_and_purchase_precision_helpers():
    assert money(Decimal("12.345")) == Decimal("12.35")
    assert qty(Decimal("12.3456")) == Decimal("12.346")


def test_required_stock_movement_types_are_defined_by_workflows():
    expected = {
        "sale_out",
        "sale_return_in",
        "purchase_in",
        "purchase_return_out",
        "manual_in",
        "manual_out",
    }
    assert {movement.value for movement in StockMovementType} == expected


def test_phase2_routes_are_mounted():
    source = open("app/api/routes.py", encoding="utf-8").read()
    assert "operations_router" in source
    assert 'prefix="/api/v1"' in source


def test_financial_models_use_decimal_columns():
    for path in (
        "app/models/sales.py",
        "app/models/purchases.py",
        "app/models/payment.py",
        "app/models/ledger.py",
        "app/models/bank.py",
        "app/models/expense.py",
        "app/models/cash_book.py",
    ):
        source = open(path, encoding="utf-8").read()
        assert "DECIMAL(18, 2)" in source


def test_final_migration_contains_audit_and_idempotency():
    source = open("alembic/versions/20260919_final_phase2.py", encoding="utf-8").read()
    assert 'op.create_table("audit_logs"' in source
    assert 'op.create_table("idempotency_records"' in source
