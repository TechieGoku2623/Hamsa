from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from hamsa.main import create_app
from hamsa.seed import DEMO_OWNER_PHONE, seed


@pytest.fixture
def make_client(tmp_path):
    clients = []

    def _make(llm=None, seeded=True) -> TestClient:
        url = f"sqlite+aiosqlite:///{tmp_path}/t{len(clients)}.db"
        app = create_app(url, llm=llm)
        if seeded:
            asyncio.run(seed(app.state.db))
            asyncio.run(app.state.db.engine.dispose())
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        return c

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()


def login(client: TestClient, phone: str, name: str = "", token: str | None = None) -> dict:
    r = client.post("/api/auth/otp/request", json={"phone": phone})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = client.post("/api/auth/otp/verify", json={"phone": phone, "code": r.json()["dev_code"], "display_name": name}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def owner(client: TestClient) -> dict:
    return login(client, DEMO_OWNER_PHONE)


JWK = {"kty": "EC", "crv": "P-256", "x": "f83OJ3D2xF1Bg8vub9tLe1gHMzV76e8Tus9uPHvRVEU", "y": "x_FEzRu9m36HLN_tue659LNpXW6pCyStikYjKIWI5a0"}
