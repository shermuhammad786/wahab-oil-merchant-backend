"""Add isolated staging records for Cash Book daily entries."""

from alembic import op
import sqlalchemy as sa


revision = "20260930_cash_book_drafts"
down_revision = "20260922_decimal_money_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cash_book_drafts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("entry_date", sa.DateTime(), nullable=False),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("posted_transaction_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cash_book_drafts_id", "cash_book_drafts", ["id"])
    op.create_index("ix_cash_book_drafts_entry_date", "cash_book_drafts", ["entry_date"])
    op.create_index("ix_cash_book_drafts_status", "cash_book_drafts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_cash_book_drafts_status", table_name="cash_book_drafts")
    op.drop_index("ix_cash_book_drafts_entry_date", table_name="cash_book_drafts")
    op.drop_index("ix_cash_book_drafts_id", table_name="cash_book_drafts")
    op.drop_table("cash_book_drafts")
