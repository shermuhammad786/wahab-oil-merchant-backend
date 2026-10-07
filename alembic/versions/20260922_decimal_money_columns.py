"""Convert legacy float money columns to fixed-precision decimals."""

from alembic import op
import sqlalchemy as sa


revision = "20260922_decimal_money_columns"
down_revision = "20260922_sync_contracts"
branch_labels = None
depends_on = None


money = sa.Numeric(18, 2)


def upgrade() -> None:
    op.alter_column("customers", "credit_limit", existing_type=sa.Float(), type_=money, existing_nullable=False)
    op.alter_column("customers", "opening_balance", existing_type=sa.Float(), type_=money, existing_nullable=False)
    op.alter_column("suppliers", "opening_balance", existing_type=sa.Float(), type_=money, existing_nullable=False)


def downgrade() -> None:
    op.alter_column("suppliers", "opening_balance", existing_type=money, type_=sa.Float(), existing_nullable=False)
    op.alter_column("customers", "opening_balance", existing_type=money, type_=sa.Float(), existing_nullable=False)
    op.alter_column("customers", "credit_limit", existing_type=money, type_=sa.Float(), existing_nullable=False)
