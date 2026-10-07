"""Add the two-shop model and shop ownership to transactional tables."""

from alembic import op
import sqlalchemy as sa


revision = "20261003_shop_scoping"
down_revision = "20260930_cash_book_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shops",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_shops_id"), "shops", ["id"], unique=False)
    op.create_index(op.f("ix_shops_code"), "shops", ["code"], unique=True)

    tables_with_shop_id = [
        ("users", "users"),
        ("customers", "customers"),
        ("suppliers", "suppliers"),
        ("product_categories", "product_categories"),
        ("products", "products"),
        ("sales", "sales"),
        ("sale_items", "sale_items"),
        ("purchases", "purchases"),
        ("purchase_items", "purchase_items"),
        ("customer_payments", "customer_payments"),
        ("supplier_payments", "supplier_payments"),
        ("sale_returns", "sale_returns"),
        ("sale_return_items", "sale_return_items"),
        ("purchase_returns", "purchase_returns"),
        ("purchase_return_items", "purchase_return_items"),
        ("stock_movements", "stock_movements"),
        ("customer_ledger_entries", "customer_ledger_entries"),
        ("supplier_ledger_entries", "supplier_ledger_entries"),
        ("expenses", "expenses"),
        ("bank_accounts", "bank_accounts"),
        ("bank_transactions", "bank_transactions"),
        ("cash_day_closes", "cash_day_closes"),
        ("cash_book_drafts", "cash_book_drafts"),
        ("cash_transactions", "cash_transactions"),
        ("cash_credit_people", "cash_credit_people"),
        ("cash_credit_transactions", "cash_credit_transactions"),
        ("settings", "settings"),
        ("audit_logs", "audit_logs"),
    ]

    for table_name, _ in tables_with_shop_id:
        op.add_column(table_name, sa.Column("shop_id", sa.String(length=64), nullable=True))
        op.create_index(op.f(f"ix_{table_name}_shop_id"), table_name, ["shop_id"], unique=False)
        op.create_foreign_key(
            f"fk_{table_name}_shop_id",
            table_name,
            "shops",
            ["shop_id"],
            ["id"],
        )

    op.create_unique_constraint("uq_sales_shop_invoice_number", "sales", ["shop_id", "invoice_number"])
    op.create_unique_constraint("uq_purchases_shop_purchase_number", "purchases", ["shop_id", "purchase_number"])


def downgrade() -> None:
    for table_name in [
        "sales",
        "purchases",
        "users",
        "customers",
        "suppliers",
        "product_categories",
        "products",
        "sale_items",
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
    ]:
        op.drop_index(f"ix_{table_name}_shop_id", table_name=table_name)
        op.drop_constraint(f"fk_{table_name}_shop_id", table_name, type_="foreignkey")
        op.drop_column(table_name, "shop_id")

    for constraint_name in ["uq_sales_shop_invoice_number", "uq_purchases_shop_purchase_number"]:
        try:
            op.drop_constraint(constraint_name, "sales" if "sales" in constraint_name else "purchases", type_="unique")
        except Exception:
            pass

    op.drop_index(op.f("ix_shops_code"), table_name="shops")
    op.drop_index(op.f("ix_shops_id"), table_name="shops")
    op.drop_table("shops")
