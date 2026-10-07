"""Require shop ownership and tenant-key daily closes and settings."""

from alembic import op
import sqlalchemy as sa


revision = "20261004_shop_tenant_keys"
down_revision = "20261003_shop_scoping"
branch_labels = None
depends_on = None


SHOP_TABLES = (
    "users",
    "customers",
    "suppliers",
    "product_categories",
    "products",
    "sales",
    "sale_items",
    "purchases",
    "purchase_items",
    "customer_payments",
    "supplier_payments",
    "sale_returns",
    "sale_return_items",
    "purchase_returns",
    "purchase_return_items",
    "stock_movements",
    "customer_ledger_entries",
    "supplier_ledger_entries",
    "expenses",
    "bank_accounts",
    "bank_transactions",
    "cash_day_closes",
    "cash_book_drafts",
    "cash_transactions",
    "cash_credit_people",
    "cash_credit_transactions",
    "settings",
    "audit_logs",
)


def upgrade() -> None:
    bind = op.get_bind()

    for shop_id, name, code in (
        ("SHOP-WOM", "Wahab Oil Merchant", "WOM"),
        ("SHOP-AH", "Abdul Haq", "AH"),
    ):
        bind.execute(
            sa.text(
                "INSERT INTO shops (id, name, code, is_active, created_at, updated_at) "
                "SELECT :id, :name, :code, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
                "WHERE NOT EXISTS (SELECT 1 FROM shops WHERE id = :id)"
            ),
            {"id": shop_id, "name": name, "code": code},
        )
        bind.execute(
            sa.text("UPDATE shops SET name = :name, code = :code, is_active = 1 WHERE id = :id"),
            {"id": shop_id, "name": name, "code": code},
        )

    for table_name in SHOP_TABLES:
        op.execute(sa.text(f"UPDATE {table_name} SET shop_id = 'SHOP-WOM' WHERE shop_id IS NULL"))
        if table_name != "audit_logs":
            op.alter_column(
                table_name,
                "shop_id",
                existing_type=sa.String(length=64),
                nullable=False,
            )

    with op.batch_alter_table("cash_day_closes") as batch_op:
        batch_op.drop_constraint("PRIMARY", type_="primary")
        batch_op.create_primary_key("pk_cash_day_closes", ["shop_id", "date"])

    with op.batch_alter_table("settings") as batch_op:
        batch_op.drop_constraint("PRIMARY", type_="primary")
        batch_op.create_primary_key("pk_settings", ["shop_id", "key"])


def downgrade() -> None:
    with op.batch_alter_table("settings") as batch_op:
        batch_op.drop_constraint("pk_settings", type_="primary")
        batch_op.create_primary_key("PRIMARY", ["key"])

    with op.batch_alter_table("cash_day_closes") as batch_op:
        batch_op.drop_constraint("pk_cash_day_closes", type_="primary")
        batch_op.create_primary_key("PRIMARY", ["date"])

    for table_name in SHOP_TABLES:
        if table_name != "audit_logs":
            op.alter_column(
                table_name,
                "shop_id",
                existing_type=sa.String(length=64),
                nullable=True,
            )