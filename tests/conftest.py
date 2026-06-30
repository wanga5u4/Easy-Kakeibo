import sys

import pytest


def fresh_server(tmp_path, monkeypatch, app_env="testing", secret_key="test-secret"):
    db_path = tmp_path / "accounting-test.db"
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("SECRET_KEY", secret_key)
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    sys.modules.pop("server", None)
    sys.modules.pop("database", None)
    import server

    server.app.config.update(TESTING=True)
    return server


@pytest.fixture()
def app_module(tmp_path, monkeypatch):
    server = fresh_server(tmp_path, monkeypatch)
    yield server
    sys.modules.pop("server", None)
    sys.modules.pop("database", None)


@pytest.fixture()
def client(app_module):
    return app_module.app.test_client()


def csrf_token(client, path="/login"):
    client.get(path)
    with client.session_transaction() as sess:
        return sess["_csrf_token"]


def csrf_headers(client, path="/dashboard"):
    return {"X-CSRFToken": csrf_token(client, path)}


def register_user(client, username="alice", email="alice@example.com", password="password123"):
    token = csrf_token(client, "/register")
    return client.post(
        "/register",
        data={
            "csrf_token": token,
            "username": username,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
        follow_redirects=False,
    )


def login_user(client, account="alice", password="password123"):
    token = csrf_token(client, "/login")
    return client.post(
        "/login",
        data={"csrf_token": token, "account": account, "password": password},
        follow_redirects=False,
    )


def logout_user(client):
    token = csrf_token(client, "/dashboard")
    return client.post("/logout", data={"csrf_token": token}, follow_redirects=False)


def create_record(
    client,
    date="2026-06-15",
    record_type="expense",
    category="food",
    amount=12.5,
    note="lunch",
    extra=None,
):
    payload = {
        "date": date,
        "type": record_type,
        "category": category,
        "amount": amount,
        "note": note,
    }
    if extra:
        payload.update(extra)
    return client.post("/api/records", json=payload, headers=csrf_headers(client))


def save_budget(client, month="2026-06", amount=1000):
    return client.post(
        "/api/budget",
        json={"month": month, "amount": amount},
        headers=csrf_headers(client),
    )


def login_as_new_user(client, username, email, password="password123"):
    response = register_user(client, username, email, password)
    assert response.status_code == 302
    response = login_user(client, username, password)
    assert response.status_code == 302
