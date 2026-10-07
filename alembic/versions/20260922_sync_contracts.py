"""Synchronize active API contracts with the current frontend."""

from alembic import op
import sqlalchemy as sa


revision = "20260922_sync_contracts"
down_revision = "20260919_final_phase2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("expenses", sa.Column("reference", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("expenses", "reference")