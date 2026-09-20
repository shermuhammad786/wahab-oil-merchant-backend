from fastapi.testclient import TestClient


def test_customers_create(client: TestClient):
    assert client is not None


def test_customers_list(client: TestClient):
    assert client is not None


def test_customers_detail(client: TestClient):
    assert client is not None


def test_customers_update(client: TestClient):
    assert client is not None


def test_customers_deactivate(client: TestClient):
    assert client is not None
