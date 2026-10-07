from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.main import app
from app.db.session import get_db
from app.models.shop import Shop


TEST_DB_NAME = "wahab_oil_merchant_test"
settings = get_settings()


@pytest.fixture(scope="session")
def engine():
    admin_url = f"mysql+pymysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}"
    admin_engine = create_engine(admin_url, pool_pre_ping=True)

    with admin_engine.begin() as conn:
        conn.exec_driver_sql(f"DROP DATABASE IF EXISTS `{TEST_DB_NAME}`")
        conn.exec_driver_sql(f"CREATE DATABASE `{TEST_DB_NAME}`")

    engine = create_engine(
        f"mysql+pymysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{TEST_DB_NAME}",
        pool_pre_ping=True,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()
    admin_engine.dispose()


@pytest.fixture()
def db_session(engine):
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    session.info["shop_id"] = "SHOP-WOM"
    if session.get(Shop, "SHOP-WOM") is None:
        session.add(Shop(id="SHOP-WOM", name="Wahab Oil Merchant", code="WOM"))
        session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
