from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.base import Base
from app.models.shop import Shop
from app.models.category import Category
from app.models.customer import Customer
from app.models.product import Product
from app.models.stock import StockMovement
from app.models.supplier import Supplier
from app.models.user import User
from app.models.sales import Sale, SaleItem
from app.models.purchases import Purchase, PurchaseItem
from app.models.payment import CustomerPayment, SupplierPayment
from app.models.ledger import CustomerLedgerEntry, SupplierLedgerEntry
from app.models.expense import Expense
from app.models.bank import BankAccount, BankTransaction
from app.models.cash_credit import CashCreditPerson, CashCreditTransaction
from app.models.cash_book import CashBookDraft, CashDayClose, CashTransaction
from app.models.returns import SaleReturn, SaleReturnItem, PurchaseReturn, PurchaseReturnItem
from app.models.settings import AppSetting

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
