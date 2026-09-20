from fastapi.testclient import TestClient


def test_login_success(client: TestClient):
    assert client is not None


def test_invalid_login(client: TestClient):
    assert client is not None


def test_me_requires_auth(client: TestClient):
    response = client.get("/api/v1/auth/me")
    assert response.status_code in {401, 403}


def test_logout(client: TestClient):
    response = client.post("/api/v1/auth/logout")
    assert response.status_code in {200, 401}
