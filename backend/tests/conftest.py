"""Tests run against the real database inside Docker:  docker compose exec backend pytest
Every test registers fresh users, so tests never see each other's data."""
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import DATABASE_URL
from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        yield conn


class Api:
    """A logged-in user: api.post('/papers', json=...) etc. Fails loudly on unexpected status."""

    def __init__(self, client, name):
        self.client = client
        email = f"{name}-{uuid.uuid4().hex[:8]}@test.dev"
        r = client.post("/api/auth/register", json={"email": email, "name": name, "password": "secret123"})
        assert r.status_code == 201, r.text
        self.user = r.json()["user"]
        self.email = email
        self.headers = {"Authorization": f"Bearer {r.json()['token']}"}

    def call(self, method, path, expect=None, **kw):
        r = self.client.request(method, "/api" + path, headers=self.headers, **kw)
        if expect is not None:
            assert r.status_code == expect, f"{method} {path} -> {r.status_code}: {r.text}"
        return r

    def get(self, path, expect=200, **kw):
        return self.call("GET", path, expect, **kw).json()

    def post(self, path, expect=201, **kw):
        r = self.call("POST", path, expect, **kw)
        return r.json() if r.content else None

    def put(self, path, expect=200, **kw):
        return self.call("PUT", path, expect, **kw).json()

    def patch(self, path, expect=200, **kw):
        return self.call("PATCH", path, expect, **kw).json()

    def delete(self, path, expect=204, **kw):
        return self.call("DELETE", path, expect, **kw)


@pytest.fixture
def make_user(client):
    return lambda name="user": Api(client, name)
