import sqlite3
import os
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent / "data" / "accounting.db"
DB_PATH = Path(os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH))
DEFAULT_USER_ID = 1
DEFAULT_USERNAME = "default_user"
DEFAULT_EMAIL = "default@example.com"
DEFAULT_PASSWORD_HASH = "temporary_password_hash"
USER_PROFILE_COLUMNS = {
    "nickname": "TEXT NOT NULL DEFAULT ''",
    "language": "TEXT NOT NULL DEFAULT 'zh-CN'",
    "currency": "TEXT NOT NULL DEFAULT 'CNY'",
    "plan": "TEXT NOT NULL DEFAULT 'free'",
    "premium_until": "TIMESTAMP",
}


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        migrate_users_profile_columns(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO users (id, username, email, password_hash)
            VALUES (?, ?, ?, ?)
            """,
            (
                DEFAULT_USER_ID,
                DEFAULT_USERNAME,
                DEFAULT_EMAIL,
                DEFAULT_PASSWORD_HASH,
            ),
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL DEFAULT 1,
                date TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                note TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount >= 0),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, month),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        migrate_records_user_id(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_user_id ON records(user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_user_date ON records(user_id, date)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_budgets_user_month ON budgets(user_id, month)"
        )
        conn.commit()


def migrate_users_profile_columns(conn):
    columns = conn.execute("PRAGMA table_info(users)").fetchall()
    existing_columns = {column["name"] for column in columns}

    for column_name, column_definition in USER_PROFILE_COLUMNS.items():
        if column_name not in existing_columns:
            conn.execute(
                f"ALTER TABLE users ADD COLUMN {column_name} {column_definition}"
            )


def migrate_records_user_id(conn):
    columns = conn.execute("PRAGMA table_info(records)").fetchall()
    has_user_id = any(column["name"] == "user_id" for column in columns)
    if has_user_id:
        return

    conn.execute("ALTER TABLE records RENAME TO records_old")
    conn.execute(
        """
        CREATE TABLE records (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL DEFAULT 1,
            date TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
            category TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            note TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO records (
            id, user_id, date, type, category, amount, note, created_at
        )
        SELECT
            id, ?, date, type, category, amount, note, created_at
        FROM records_old
        """,
        (DEFAULT_USER_ID,),
    )
    conn.execute("DROP TABLE records_old")


def row_to_dict(row):
    return {
        "id": row["id"],
        "date": row["date"],
        "type": row["type"],
        "category": row["category"],
        "amount": row["amount"],
        "note": row["note"],
        "createdAt": row["created_at"],
    }
