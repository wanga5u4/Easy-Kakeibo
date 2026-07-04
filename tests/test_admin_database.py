import sqlite3
import sys

from conftest import create_record, login_as_new_user


def test_init_db_adds_admin_fields_and_preserves_legacy_data(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE records (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            feedback_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            page_url TEXT NOT NULL DEFAULT '',
            contact TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO users (username, email, password_hash) VALUES ('legacy', 'legacy@example.com', 'hash')"
    )
    conn.execute(
        """
        INSERT INTO records (id, date, type, category, amount, note, created_at)
        VALUES ('r1', '2026-07-01', 'expense', 'food', 12, 'old', 1)
        """
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    sys.modules.pop("server", None)
    sys.modules.pop("database", None)
    import server

    server.init_db()
    with server.get_connection() as conn:
        user = conn.execute(
            """
            SELECT is_admin, vip_status, vip_expires_at, last_login_at, is_active
            FROM users
            WHERE username = 'legacy'
            """
        ).fetchone()
        assert user["is_admin"] == 0
        assert user["vip_status"] == "free"
        assert user["vip_expires_at"] is None
        assert user["last_login_at"] is None
        assert user["is_active"] == 1
        assert conn.execute("SELECT COUNT(*) FROM records WHERE id = 'r1'").fetchone()[0] == 1
        assert "admin_note" in {
            row["name"] for row in conn.execute("PRAGMA table_info(feedback)")
        }
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'admin_audit_logs'"
        ).fetchone()[0] == 1

    server.init_db()
    with server.get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE username = 'legacy'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM records WHERE id = 'r1'").fetchone()[0] == 1

    sys.modules.pop("server", None)
    sys.modules.pop("database", None)


def test_registration_defaults_new_user_to_non_admin_free(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    create_record(client)

    with app_module.get_connection() as conn:
        user = conn.execute(
            "SELECT is_admin, vip_status FROM users WHERE username = 'alice'"
        ).fetchone()
        assert user["is_admin"] == 0
        assert user["vip_status"] == "free"
        assert conn.execute(
            "SELECT COUNT(*) FROM records WHERE user_id = ?",
            (conn.execute("SELECT id FROM users WHERE username = 'alice'").fetchone()["id"],),
        ).fetchone()[0] == 1
