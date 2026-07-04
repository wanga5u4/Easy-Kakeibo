import sqlite3
import os
import logging
from pathlib import Path

from currency import (
    DEFAULT_BASE_CURRENCY,
    amount_to_minor_units_rounded,
    format_money_minor,
    minor_units_to_api_number,
)

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
    "base_currency_code": f"TEXT NOT NULL DEFAULT '{DEFAULT_BASE_CURRENCY}'",
    "plan": "TEXT NOT NULL DEFAULT 'free'",
    "premium_until": "TIMESTAMP",
}
USER_ADMIN_COLUMNS = {
    "is_admin": "INTEGER NOT NULL DEFAULT 0 CHECK(is_admin IN (0, 1))",
    "vip_status": "TEXT NOT NULL DEFAULT 'free' CHECK(vip_status IN ('free', 'vip'))",
    "vip_expires_at": "TIMESTAMP",
    "last_login_at": "TIMESTAMP",
    "is_active": "INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1))",
}
RECORD_MULTI_CURRENCY_COLUMNS = {
    "original_amount_minor": "INTEGER NOT NULL DEFAULT 0",
    "currency_code": f"TEXT NOT NULL DEFAULT '{DEFAULT_BASE_CURRENCY}'",
    "exchange_rate": "TEXT NOT NULL DEFAULT '1'",
    "converted_amount_minor": "INTEGER NOT NULL DEFAULT 0",
    "base_currency_code": f"TEXT NOT NULL DEFAULT '{DEFAULT_BASE_CURRENCY}'",
    "rate_date": "TEXT",
    "rate_source": "TEXT NOT NULL DEFAULT 'migration'",
}
BUDGET_MULTI_CURRENCY_COLUMNS = {
    "amount_minor": "INTEGER NOT NULL DEFAULT 0",
    "currency_code": f"TEXT NOT NULL DEFAULT '{DEFAULT_BASE_CURRENCY}'",
}
FEEDBACK_TYPES = ("bug", "feature", "question", "other")
FEEDBACK_STATUSES = ("new", "reviewing", "resolved", "closed")
FEEDBACK_ADMIN_COLUMNS = {
    "admin_note": "TEXT NOT NULL DEFAULT ''",
}
LOGGER = logging.getLogger(__name__)


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
        migrate_users_admin_columns(conn)
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                feedback_type TEXT NOT NULL CHECK(feedback_type IN ('bug', 'feature', 'question', 'other')),
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                page_url TEXT NOT NULL DEFAULT '',
                contact TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new', 'reviewing', 'resolved', 'closed')),
                admin_note TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS share_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                share_month TEXT NOT NULL,
                include_income_summary INTEGER NOT NULL DEFAULT 1 CHECK(include_income_summary IN (0, 1)),
                include_expense_summary INTEGER NOT NULL DEFAULT 1 CHECK(include_expense_summary IN (0, 1)),
                include_category_summary INTEGER NOT NULL DEFAULT 1 CHECK(include_category_summary IN (0, 1)),
                expires_at TIMESTAMP,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_viewed_at TIMESTAMP,
                view_count INTEGER NOT NULL DEFAULT 0 CHECK(view_count >= 0),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_exchange_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                from_currency_code TEXT NOT NULL,
                to_currency_code TEXT NOT NULL,
                rate TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, from_currency_code, to_currency_code),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_user_id INTEGER NOT NULL,
                target_user_id INTEGER,
                target_feedback_id INTEGER,
                action TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        migrate_feedback_admin_columns(conn)
        migrate_records_user_id(conn)
        migrate_records_multi_currency(conn)
        migrate_budgets_multi_currency(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_user_id ON records(user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_user_date ON records(user_id, date)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_user_base_month ON records(user_id, base_currency_code, date)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_budgets_user_month ON budgets(user_id, month)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_feedback_user_id ON feedback(user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_feedback_created_at ON feedback(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_vip_status ON users(vip_status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_is_admin ON users(is_admin)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_created_at ON admin_audit_logs(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_admin_user_id ON admin_audit_logs(admin_user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_target_user_id ON admin_audit_logs(target_user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_target_feedback_id ON admin_audit_logs(target_feedback_id)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_share_links_token ON share_links(token)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_share_links_user_id ON share_links(user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_share_links_created_at ON share_links(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_exchange_rates_user_id ON user_exchange_rates(user_id)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_exchange_rates_direction ON user_exchange_rates(user_id, from_currency_code, to_currency_code)"
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


def migrate_users_admin_columns(conn):
    add_missing_columns(conn, "users", USER_ADMIN_COLUMNS)


def migrate_feedback_admin_columns(conn):
    add_missing_columns(conn, "feedback", FEEDBACK_ADMIN_COLUMNS)


def get_table_columns(conn, table_name):
    return {
        column["name"]
        for column in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def add_missing_columns(conn, table_name, column_definitions):
    existing_columns = get_table_columns(conn, table_name)
    for column_name, column_definition in column_definitions.items():
        if column_name not in existing_columns:
            conn.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
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


def migrate_records_multi_currency(conn):
    add_missing_columns(conn, "records", RECORD_MULTI_CURRENCY_COLUMNS)

    pending_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM records
        WHERE original_amount_minor <= 0 OR converted_amount_minor <= 0
        """
    ).fetchone()[0]
    if not pending_count:
        return

    LOGGER.info("Starting records multi-currency migration: rows=%s", pending_count)
    rows = conn.execute(
        """
        SELECT r.id, r.user_id, r.amount, u.base_currency_code
        FROM records r
        LEFT JOIN users u ON u.id = r.user_id
        WHERE r.original_amount_minor <= 0 OR r.converted_amount_minor <= 0
        """
    ).fetchall()
    migrated = 0
    for row in rows:
        base_currency_code = row["base_currency_code"] or DEFAULT_BASE_CURRENCY
        try:
            amount_minor = amount_to_minor_units_rounded(
                row["amount"],
                base_currency_code,
            )
        except Exception:
            base_currency_code = DEFAULT_BASE_CURRENCY
            amount_minor = amount_to_minor_units_rounded(row["amount"], base_currency_code)
        conn.execute(
            """
            UPDATE records
            SET original_amount_minor = ?,
                currency_code = ?,
                exchange_rate = '1',
                converted_amount_minor = ?,
                base_currency_code = ?,
                rate_date = NULL,
                rate_source = 'migration'
            WHERE id = ?
            """,
            (
                amount_minor,
                base_currency_code,
                amount_minor,
                base_currency_code,
                row["id"],
            ),
        )
        migrated += 1
    LOGGER.info("Completed records multi-currency migration: rows=%s", migrated)


def migrate_budgets_multi_currency(conn):
    add_missing_columns(conn, "budgets", BUDGET_MULTI_CURRENCY_COLUMNS)
    rows = conn.execute(
        """
        SELECT id, amount
        FROM budgets
        WHERE amount_minor <= 0 AND amount > 0
        """
    ).fetchall()
    if rows:
        LOGGER.info("Starting budgets currency migration: rows=%s", len(rows))
    for row in rows:
        amount_minor = amount_to_minor_units_rounded(
            row["amount"],
            DEFAULT_BASE_CURRENCY,
        )
        conn.execute(
            """
            UPDATE budgets
            SET amount_minor = ?, currency_code = ?
            WHERE id = ?
            """,
            (amount_minor, DEFAULT_BASE_CURRENCY, row["id"]),
        )
    if rows:
        LOGGER.info("Completed budgets currency migration: rows=%s", len(rows))


def row_to_dict(row):
    original_currency = row["currency_code"]
    base_currency = row["base_currency_code"]
    original_amount = minor_units_to_api_number(
        row["original_amount_minor"],
        original_currency,
    )
    converted_amount = minor_units_to_api_number(
        row["converted_amount_minor"],
        base_currency,
    )
    return {
        "id": row["id"],
        "date": row["date"],
        "type": row["type"],
        "category": row["category"],
        "amount": original_amount,
        "original_amount": original_amount,
        "original_amount_minor": row["original_amount_minor"],
        "currency_code": original_currency,
        "exchange_rate": row["exchange_rate"],
        "converted_amount": converted_amount,
        "converted_amount_minor": row["converted_amount_minor"],
        "base_currency_code": base_currency,
        "formatted_original_amount": format_money_minor(
            row["original_amount_minor"],
            original_currency,
        ),
        "formatted_converted_amount": format_money_minor(
            row["converted_amount_minor"],
            base_currency,
        ),
        "rate_date": row["rate_date"],
        "rate_source": row["rate_source"],
        "note": row["note"],
        "createdAt": row["created_at"],
    }
