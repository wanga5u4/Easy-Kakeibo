import os
import sqlite3
import subprocess
import sys


def run_set_admin(tmp_path, *args):
    db_path = tmp_path / "set-admin.db"
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_PATH": str(db_path),
            "APP_ENV": "testing",
            "SECRET_KEY": "test-secret",
        }
    )
    result = subprocess.run(
        [sys.executable, "scripts/set_admin.py", *args],
        cwd=os.getcwd(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return db_path, result


def test_set_admin_script_reports_missing_user(tmp_path):
    _, result = run_set_admin(tmp_path, "missing")

    assert result.returncode == 1
    assert "was not found" in result.stderr


def test_set_admin_script_grants_and_removes_admin(tmp_path):
    db_path = tmp_path / "set-admin.db"
    with sqlite3.connect(db_path) as conn:
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
            INSERT INTO users (username, email, password_hash)
            VALUES ('alice', 'alice@example.com', 'hash')
            """
        )
        conn.commit()

    db_path, grant = run_set_admin(tmp_path, "alice")
    assert grant.returncode == 0
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT is_admin FROM users WHERE username = 'alice'"
        ).fetchone()[0] == 1

    _, remove = run_set_admin(tmp_path, "alice", "--remove")
    assert remove.returncode == 0
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT is_admin FROM users WHERE username = 'alice'"
        ).fetchone()[0] == 0
