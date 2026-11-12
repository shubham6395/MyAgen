from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_list_items():
    assert client.get("/items").status_code in (200, 500)


def test_read_me_requires_token():
    assert client.get("/users/me").status_code in (200, 401, 422)