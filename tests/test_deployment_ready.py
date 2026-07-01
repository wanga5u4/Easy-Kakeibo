import os
import sqlite3
import time
from datetime import datetime, timedelta

from conftest import csrf_token, fresh_server, register_user


def test_health_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "database": "ok"}


def test_health_database_failure_hides_sensitive_details(app_module, client, monkeypatch):
    def broken_connection():
        raise RuntimeError("boom /tmp/secret/accounting.db traceback")

    monkeypatch.setattr(app_module, "get_connection", broken_connection)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.get_json() == {"status": "error", "database": "unavailable"}
    assert b"secret" not in response.data
    assert b"traceback" not in response.data.lower()


def test_login_post_rate_limit_blocks_excess_attempts(client):
    token = csrf_token(client, "/login")
    statuses = [
        client.post(
            "/login",
            data={"csrf_token": token, "account": "missing", "password": "password123"},
        ).status_code
        for _ in range(6)
    ]

    assert statuses[:5] == [400, 400, 400, 400, 400]
    assert statuses[5] == 429
    assert b"{" not in client.post(
        "/login",
        data={"csrf_token": token, "account": "missing", "password": "password123"},
    ).data[:1]


def test_register_post_rate_limit_blocks_excess_attempts(client):
    token = csrf_token(client, "/register")
    statuses = []
    for index in range(6):
        response = client.post(
            "/register",
            data={
                "csrf_token": token,
                "username": f"user{index}",
                "email": f"user{index}@example.com",
                "password": "password123",
                "confirm_password": "password123",
            },
        )
        statuses.append(response.status_code)

    assert statuses[:5] == [302, 302, 302, 302, 302]
    assert statuses[5] == 429


def test_login_get_is_not_rate_limited(client):
    for _ in range(8):
        assert client.get("/login").status_code == 200


def test_security_headers_on_normal_page(client):
    response = client.get("/login")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "Permissions-Policy" in response.headers
    assert "Content-Security-Policy" in response.headers


def test_hsts_only_for_https_production(tmp_path, monkeypatch):
    testing_server = fresh_server(tmp_path, monkeypatch, app_env="testing")
    assert "Strict-Transport-Security" not in testing_server.app.test_client().get("/login").headers

    production_server = fresh_server(tmp_path, monkeypatch, app_env="production", secret_key="prod-secret")
    production_client = production_server.app.test_client()
    assert "Strict-Transport-Security" not in production_client.get("/login").headers
    assert "Strict-Transport-Security" in production_client.get(
        "/login",
        headers={"X-Forwarded-Proto": "https"},
    ).headers


def test_rate_limit_state_does_not_pollute_next_app(tmp_path, monkeypatch):
    first_server = fresh_server(tmp_path, monkeypatch)
    first_client = first_server.app.test_client()
    token = csrf_token(first_client, "/login")
    for _ in range(6):
        first_client.post(
            "/login",
            data={"csrf_token": token, "account": "missing", "password": "password123"},
        )

    second_server = fresh_server(tmp_path, monkeypatch)
    second_client = second_server.app.test_client()
    token = csrf_token(second_client, "/login")
    response = second_client.post(
        "/login",
        data={"csrf_token": token, "account": "missing", "password": "password123"},
    )
    assert response.status_code == 400


def test_register_helper_still_works_after_limiter(client):
    assert register_user(client).status_code == 302


def make_database(path):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO sample (name) VALUES ('ok')")
        conn.commit()


def test_backup_creates_readable_database(tmp_path, monkeypatch):
    from scripts import backup_database

    db_path = tmp_path / "source.db"
    backup_dir = tmp_path / "backups"
    make_database(db_path)
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))

    backup_path = backup_database.create_backup(now=datetime(2026, 7, 1, 3, 0, 0))

    assert backup_path.exists()
    assert backup_path.name == "accounting-2026-07-01-030000.db"
    with sqlite3.connect(backup_path) as conn:
        assert conn.execute("SELECT name FROM sample").fetchone()[0] == "ok"


def test_backup_cleanup_deletes_only_expired_backups(tmp_path):
    from scripts import backup_database

    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    expired = backup_dir / "accounting-2026-06-01-030000.db"
    recent = backup_dir / "accounting-2026-06-30-030000.db"
    keep = backup_dir / "accounting-2026-05-01-030000.db"
    for path in [expired, recent, keep]:
        path.write_text("backup", encoding="utf-8")

    old_time = time.time() - 30 * 24 * 60 * 60
    os.utime(expired, (old_time, old_time))
    os.utime(keep, (old_time, old_time))

    deleted = backup_database.cleanup_old_backups(
        backup_dir,
        retention_days=14,
        keep_path=keep,
        now=datetime.now(),
    )

    assert expired in deleted
    assert not expired.exists()
    assert recent.exists()
    assert keep.exists()


def test_backup_missing_database_returns_failure(tmp_path, monkeypatch):
    from scripts import backup_database

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "missing.db"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))

    assert backup_database.main() == 1


def test_backup_does_not_delete_newly_created_backup(tmp_path, monkeypatch):
    from scripts import backup_database

    db_path = tmp_path / "source.db"
    backup_dir = tmp_path / "backups"
    make_database(db_path)
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("BACKUP_DIR", str(backup_dir))
    monkeypatch.setenv("BACKUP_RETENTION_DAYS", "0")

    backup_path = backup_database.create_backup(now=datetime.now() - timedelta(days=30))

    assert backup_path.exists()
