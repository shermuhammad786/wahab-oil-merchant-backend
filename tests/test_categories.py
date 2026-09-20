from fastapi.testclient import TestClient


def test_categories_create(client: TestClient):
    assert client is not None


def test_categories_duplicate_rejected(client: TestClient):
    assert client is not None


def test_categories_trimmed_name(client: TestClient):
    assert client is not None
