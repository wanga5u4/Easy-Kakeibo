import importlib
import hashlib
import logging
import sys

import pytest

from conftest import csrf_headers, csrf_token, fresh_server, login_as_new_user, login_user, register_user


def test_form_csrf_required_and_valid_token_works(client):
    token = csrf_token(client, "/register")
    ok = client.post(
        "/register",
        data={
            "csrf_token": token,
            "username": "alice",
            "email": "alice@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert ok.status_code == 302

    missing = client.post(
        "/login",
        data={"account": "alice", "password": "password123"},
    )
    assert missing.status_code == 400

    bad = client.post(
        "/login",
        data={"csrf_token": "bad-token", "account": "alice", "password": "password123"},
    )
    assert bad.status_code == 400


def test_json_csrf_required_for_post_put_delete(client):
    register_user(client)
    login_user(client)
    ok = client.post(
        "/api/records",
        json={"date": "2026-06-01", "type": "expense", "category": "food", "amount": 10},
        headers=csrf_headers(client),
    )
    assert ok.status_code == 201
    record_id = ok.get_json()["id"]

    missing_post = client.post(
        "/api/records",
        json={"date": "2026-06-01", "type": "expense", "category": "food", "amount": 10},
    )
    assert missing_post.status_code == 400
    assert missing_post.get_json()["ok"] is False

    assert client.put(f"/api/records/{record_id}", json={}).status_code == 400
    assert client.delete(f"/api/records/{record_id}").status_code == 400


def test_old_token_invalid_after_login(client):
    register_user(client)
    old_token = csrf_token(client, "/login")
    response = client.post(
        "/login",
        data={"csrf_token": old_token, "account": "alice", "password": "password123"},
    )
    assert response.status_code == 302
    response = client.post(
        "/api/budget",
        json={"month": "2026-06", "amount": 100},
        headers={"X-CSRFToken": old_token},
    )
    assert response.status_code == 400


def test_get_requests_do_not_require_csrf(client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert client.get("/dashboard").status_code == 200
    assert client.get("/api/records").status_code == 200


def test_static_and_sensitive_files(app_module):
    client = app_module.app.test_client()
    assert client.get("/static/css/styles.css").status_code == 200
    for path in ["/server.py", "/database.py", "/data/accounting.db", "/requirements.txt", "/.env", "/.git/config"]:
        assert client.get(path).status_code in {404, 405}


def test_production_requires_secret_key(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "prod.db"))
    sys.modules.pop("server", None)
    sys.modules.pop("database", None)
    with pytest.raises(RuntimeError):
        importlib.import_module("server")


def test_production_and_development_cookie_config(tmp_path, monkeypatch):
    prod = fresh_server(tmp_path, monkeypatch, app_env="production", secret_key="prod-secret")
    assert prod.app.debug is False
    assert prod.app.config["SESSION_COOKIE_SECURE"] is True
    assert prod.app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert prod.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"

    dev = fresh_server(tmp_path, monkeypatch, app_env="development", secret_key="dev-secret")
    assert dev.app.config["SESSION_COOKIE_SECURE"] is False
    assert dev.app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert dev.app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


def test_language_switch_allows_same_origin_referrer(client):
    response = client.get(
        "/set-language/ja",
        headers={"Referer": "http://localhost/dashboard?month=2026-06"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "http://localhost/dashboard?month=2026-06"


def test_language_switch_rejects_external_referrer(client):
    response = client.get(
        "/set-language/ja",
        headers={"Referer": "https://evil.example/phish"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_language_switch_uses_safe_default_without_referrer(client):
    response = client.get("/set-language/ja")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_language_switch_invalid_language_does_not_change_session_and_redirects_safely(client):
    with client.session_transaction() as sess:
        sess["lang"] = "zh_CN"

    response = client.get(
        "/set-language/not-a-locale",
        headers={"Referer": "//evil.example/phish"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    with client.session_transaction() as sess:
        assert sess["lang"] == "zh_CN"


def test_language_switch_without_referrer_returns_dashboard_when_logged_in(client):
    login_as_new_user(client, "alice", "alice@example.com")

    response = client.get("/set-language/ja")

    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"


def test_login_failure_log_masks_account_and_password(client, caplog):
    register_user(client, username="alice", email="alice@example.com", password="password123")
    token = csrf_token(client, "/login")
    account = " Alice@Example.com "
    password = "wrong-password"
    expected_hash = hashlib.sha256(account.strip().lower().encode("utf-8")).hexdigest()[:16]

    with caplog.at_level(logging.WARNING):
        response = client.post(
            "/login",
            data={"csrf_token": token, "account": account, "password": password},
        )

    assert response.status_code == 400
    assert expected_hash in caplog.text
    assert "Alice@Example.com" not in caplog.text
    assert "alice@example.com" not in caplog.text
    assert password not in caplog.text
