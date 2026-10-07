#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_token, hash_password
from app.db.base import Base
from app.db.session import engine
import app.models
from app.models import Customer, Shop, User
from app.main import app


settings = get_settings()
TARGET_DATABASE = "wahab_oil_merchant"
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"}


def ensure_safe_target() -> None:
    url = engine.url
    if (
        (url.host or "").lower() not in ALLOWED_HOSTS
        or url.database != TARGET_DATABASE
        or settings.APP_ENV.lower() != "development"
    ):
        raise SystemExit(
            "Refusing reset: expected APP_ENV=development and "
            f"localhost/{TARGET_DATABASE}; configured target is "
            f"APP_ENV={settings.APP_ENV}, {url.host}/{url.database}."
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Drop and rebuild the local WOM database with exactly two shops and admins."
    )
    parser.add_argument("--confirm-reset", action="store_true", help="Required destructive confirmation flag.")
    return parser


def database_identity(db_engine: Engine) -> dict[str, Any]:
    with db_engine.connect() as connection:
        row = connection.execute(
            text("SELECT DATABASE() AS database_name, @@hostname AS server_host, @@port AS server_port")
        ).mappings().one()
        current_revision = MigrationContext.configure(connection).get_current_revision()
    return {**row, "current_revision": current_revision}


def drop_all_tables(db_engine: Engine) -> list[str]:
    with db_engine.connect() as connection:
        inspector = inspect(connection)
        tables = inspector.get_table_names()
        views = inspector.get_view_names()
        preparer = db_engine.dialect.identifier_preparer
        connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
        try:
            for view_name in views:
                connection.exec_driver_sql(f"DROP VIEW IF EXISTS {preparer.quote(view_name)}")
            for table_name in tables:
                connection.exec_driver_sql(f"DROP TABLE IF EXISTS {preparer.quote(table_name)}")
        finally:
            connection.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")
        return tables


def generate_credentials(label: str) -> tuple[str, str]:
    slug = label.lower().replace(" ", ".")
    return f"{slug}@local.test", secrets.token_urlsafe(18)


def admin_credentials() -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    specs = [
        ("SHOP-WOM", "Wahab Oil Merchant", "WOM_ADMIN_LOGIN", "WOM_ADMIN_PASSWORD"),
        ("SHOP-AH", "Abdul Haq", "ABDUL_HAQ_ADMIN_LOGIN", "ABDUL_HAQ_ADMIN_PASSWORD"),
    ]
    users: list[dict[str, str]] = []
    generated: dict[str, dict[str, str]] = {}
    configured_fields = settings.model_fields_set
    for shop_id, name, login_field, password_field in specs:
        login_is_set = login_field in configured_fields and bool(getattr(settings, login_field))
        password_is_set = password_field in configured_fields and bool(getattr(settings, password_field))
        default_email, default_password = generate_credentials(name)
        email = getattr(settings, login_field) if login_is_set else default_email
        password = getattr(settings, password_field) if password_is_set else default_password
        if not login_is_set or not password_is_set:
            generated[shop_id] = {"email": email, "password": password}
        users.append({"shop_id": shop_id, "name": f"{name} Admin", "email": email, "password": password})
    return users, generated


def seed_minimal_data(db_engine: Engine) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    shop_specs = [
        ("SHOP-WOM", "Wahab Oil Merchant", "WOM"),
        ("SHOP-AH", "Abdul Haq", "AH"),
    ]
    user_specs, generated = admin_credentials()
    with Session(db_engine) as session:
        allowed_shop_ids = {shop_id for shop_id, _, _ in shop_specs}
        for shop_id, name, code in shop_specs:
            shop = session.get(Shop, shop_id)
            if shop is None:
                shop = Shop(id=shop_id, name=name, code=code, is_active=True)
                session.add(shop)
            else:
                shop.name = name
                shop.code = code
                shop.is_active = True
        for shop in session.scalars(select(Shop)).all():
            if shop.id not in allowed_shop_ids:
                session.delete(shop)
        session.flush()
        for spec in user_specs:
            session.add(User(
                id=f"USR-{spec['shop_id']}",
                name=spec["name"],
                email=spec["email"],
                password_hash=hash_password(spec["password"]),
                role="admin",
                shop_id=spec["shop_id"],
                is_active=True,
            ))
        session.commit()
    credentials = {spec["shop_id"]: {"email": spec["email"], "password": spec["password"]} for spec in user_specs}
    return credentials, generated


def verify_schema_and_counts(db_engine: Engine) -> dict[str, Any]:
    inspector = inspect(db_engine)
    physical_tables = set(inspector.get_table_names())
    expected_tables = set(Base.metadata.tables)
    stale_tables = sorted(physical_tables - expected_tables - {"alembic_version"})
    missing_tables = sorted(expected_tables - physical_tables)
    if stale_tables or missing_tables:
        raise RuntimeError(f"Schema table mismatch; stale={stale_tables}, missing={missing_tables}")

    missing_shop_columns = sorted(
        table_name
        for table_name, table in Base.metadata.tables.items()
        if "shop_id" in table.c and "shop_id" not in {column["name"] for column in inspector.get_columns(table_name)}
    )
    if missing_shop_columns:
        raise RuntimeError(f"Missing shop_id columns: {missing_shop_columns}")

    with db_engine.connect() as connection:
        row_counts = {
            table_name: connection.execute(text(f"SELECT COUNT(*) FROM {db_engine.dialect.identifier_preparer.quote(table_name)}")).scalar_one()
            for table_name in sorted(expected_tables)
        }
        shops = connection.execute(text("SELECT id, name, code, is_active FROM shops ORDER BY id")).mappings().all()
        users = connection.execute(text("SELECT id, shop_id, email, role, is_active FROM users ORDER BY shop_id")).mappings().all()
        null_shop_users = connection.execute(text("SELECT COUNT(*) FROM users WHERE shop_id IS NULL")).scalar_one()
        current_revision = MigrationContext.configure(connection).get_current_revision()

    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    head_revision = script.get_current_head()
    if current_revision != head_revision:
        raise RuntimeError(f"Alembic revision mismatch: current={current_revision}, head={head_revision}")
    if row_counts.get("shops") != 2 or row_counts.get("users") != 2 or null_shop_users:
        raise RuntimeError(f"Unexpected seed counts: shops={row_counts.get('shops')}, users={row_counts.get('users')}, null_shop_users={null_shop_users}")
    nonempty_business = {name: count for name, count in row_counts.items() if name not in {"shops", "users"} and count}
    if nonempty_business:
        raise RuntimeError(f"Business tables are not empty: {nonempty_business}")
    return {
        "physical_tables": sorted(physical_tables),
        "row_counts": row_counts,
        "shops": [dict(row) for row in shops],
        "users": [dict(row) for row in users],
        "stale_tables": stale_tables,
        "current_revision": current_revision,
        "head_revision": head_revision,
    }


def verify_logins_and_isolation(credentials: dict[str, dict[str, str]], db_engine: Engine) -> dict[str, Any]:
    tokens: dict[str, str] = {}
    with TestClient(app) as client:
        for shop_id, login in credentials.items():
            response = client.post("/api/v1/auth/login", json={**login, "shop_id": shop_id})
            if response.status_code != 200:
                raise RuntimeError(f"Login failed for {shop_id}: HTTP {response.status_code}")
            token = response.json()["access_token"]
            if decode_token(token).get("shop_id") != shop_id:
                raise RuntimeError(f"JWT shop_id mismatch for {shop_id}")
            profile = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            if profile.status_code != 200 or profile.json().get("shop_id") != shop_id:
                raise RuntimeError(f"/auth/me shop mismatch for {shop_id}")
            tokens[shop_id] = token

        wom_login = credentials["SHOP-WOM"]
        wrong_shop = client.post("/api/v1/auth/login", json={**wom_login, "shop_id": "SHOP-AH"})
        if wrong_shop.status_code != 401:
            raise RuntimeError(f"Wrong-shop login should return 401, got {wrong_shop.status_code}")

        smoke_customer_id = f"CUS-SMOKE-{uuid4().hex}"
        try:
            with Session(db_engine) as session:
                session.add(Customer(id=smoke_customer_id, shop_id="SHOP-WOM", name="Isolation Smoke", status="Active"))
                session.commit()
            wom_result = client.get(
                f"/api/v1/customers/{smoke_customer_id}",
                headers={"Authorization": f"Bearer {tokens['SHOP-WOM']}"},
            )
            ah_result = client.get(
                f"/api/v1/customers/{smoke_customer_id}",
                headers={"Authorization": f"Bearer {tokens['SHOP-AH']}"},
            )
            if wom_result.status_code != 200 or ah_result.status_code != 404:
                raise RuntimeError(f"Customer isolation failed: WOM={wom_result.status_code}, AH={ah_result.status_code}")
        finally:
            with Session(db_engine) as session:
                session.execute(delete(Customer).where(Customer.id == smoke_customer_id))
                session.commit()
    return {"login_status": 200, "wrong_shop_status": 401, "wom_jwt_shop_id": "SHOP-WOM", "ah_jwt_shop_id": "SHOP-AH"}


def main() -> None:
    args = build_parser().parse_args()
    ensure_safe_target()
    identity = database_identity(engine)
    if identity["database_name"] != TARGET_DATABASE:
        raise SystemExit(f"Refusing reset: server reports database {identity['database_name']!r}.")
    print(f"Verified target: host={engine.url.host}, database={identity['database_name']}, environment={settings.APP_ENV}")
    print(f"Current Alembic revision: {identity['current_revision']}")
    if not args.confirm_reset:
        print("Reset requires --confirm-reset. No destructive action taken.")
        return

    os.chdir(ROOT)
    dropped_tables = drop_all_tables(engine)
    alembic_config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(alembic_config, "head")
    credentials, generated = seed_minimal_data(engine)
    login_results = verify_logins_and_isolation(credentials, engine)
    verification = verify_schema_and_counts(engine)

    print("\nRESET VERIFICATION")
    print(f"Old tables removed: {len(dropped_tables)}")
    print(f"Latest schema recreated: yes ({verification['current_revision']})")
    print(f"Shops: {verification['row_counts']['shops']}; users: {verification['row_counts']['users']}")
    print(f"Business tables with non-zero rows: none")
    print(f"Stale legacy tables: {', '.join(verification['stale_tables']) or 'none'}")
    print(f"WOM login and JWT: PASS ({login_results['wom_jwt_shop_id']})")
    print(f"Abdul Haq login and JWT: PASS ({login_results['ah_jwt_shop_id']})")
    print("Wrong-shop login: PASS (HTTP 401)")
    print("WOM/AH customer isolation and cleanup: PASS")
    if generated:
        print("\nGenerated development credentials (shown once):")
        for shop_id, login in generated.items():
            print(f"{shop_id}: email={login['email']} password={login['password']}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
        raise
