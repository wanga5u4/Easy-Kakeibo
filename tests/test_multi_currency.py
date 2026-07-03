import importlib
import sqlite3
import sys

from conftest import (
    create_record,
    csrf_headers,
    csrf_token,
    fresh_server,
    login_as_new_user,
    logout_user,
    save_budget,
)


def set_base_currency(client, currency_code, language="zh-CN"):
    return client.post(
        "/settings",
        data={
            "csrf_token": csrf_token(client, "/settings"),
            "nickname": "",
            "language": language,
            "currency": currency_code,
        },
        follow_redirects=False,
    )


def test_jpy_user_adds_jpy_and_cny_records(client):
    login_as_new_user(client, "alice", "alice@example.com")

    same = create_record(client, amount="1000", extra={"currency_code": "JPY"}).get_json()
    assert same["currency_code"] == "JPY"
    assert same["base_currency_code"] == "JPY"
    assert same["exchange_rate"] == "1"
    assert same["converted_amount"] == 1000
    assert same["rate_source"] == "same_currency"

    converted = create_record(
        client,
        amount="100.50",
        extra={
            "currency_code": "CNY",
            "exchange_rate": "21.277",
            "converted_amount": 999999,
        },
    )
    assert converted.status_code == 201
    row = converted.get_json()
    assert row["currency_code"] == "CNY"
    assert row["base_currency_code"] == "JPY"
    assert row["converted_amount"] == 2138
    assert row["rate_source"] == "manual"


def test_cny_user_adds_jpy_and_cny_records(client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert set_base_currency(client, "CNY").status_code == 302

    jpy = create_record(
        client,
        amount="1000",
        extra={"currency_code": "JPY", "exchange_rate": "0.047"},
    ).get_json()
    assert jpy["base_currency_code"] == "CNY"
    assert jpy["converted_amount"] == 47

    cny = create_record(
        client,
        amount="100.50",
        extra={"currency_code": "CNY"},
    ).get_json()
    assert cny["exchange_rate"] == "1"
    assert cny["converted_amount"] == 100.5


def test_create_record_rejects_invalid_currency_amount_and_rates(client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert create_record(client, amount="10.5", extra={"currency_code": "JPY"}).status_code == 400
    assert create_record(client, amount="10.555", extra={"currency_code": "CNY", "exchange_rate": "1"}).status_code == 400
    assert create_record(client, amount="10", extra={"currency_code": "USD"}).status_code == 400
    for rate in ["", "0", "-1", "abc", "NaN", "Infinity", "1e-3"]:
        assert create_record(
            client,
            amount="10.50",
            extra={"currency_code": "CNY", "exchange_rate": rate},
        ).status_code == 400
    assert create_record(client, amount="1000000000000", extra={"currency_code": "JPY"}).status_code == 400


def test_edit_record_preserves_rate_on_note_only_and_recalculates_on_amount_change(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    record = create_record(
        client,
        amount="100.00",
        extra={"currency_code": "CNY", "exchange_rate": "20"},
    ).get_json()

    note_only = client.put(
        f"/api/records/{record['id']}",
        json={
            "date": record["date"],
            "type": record["type"],
            "category": record["category"],
            "amount": "100.00",
            "currency_code": "CNY",
            "exchange_rate": "20",
            "note": "new note",
        },
        headers=csrf_headers(client),
    ).get_json()
    assert note_only["exchange_rate"] == "20"
    assert note_only["converted_amount"] == 2000

    changed = client.put(
        f"/api/records/{record['id']}",
        json={
            "date": record["date"],
            "type": record["type"],
            "category": record["category"],
            "amount": "200.00",
            "currency_code": "CNY",
            "exchange_rate": "20",
            "note": "new note",
        },
        headers=csrf_headers(client),
    ).get_json()
    assert changed["converted_amount"] == 4000

    assert set_base_currency(client, "CNY").status_code == 302
    after_setting_change = client.get(f"/api/records/{record['id']}").get_json()
    assert after_setting_change["base_currency_code"] == "JPY"


def test_user_cannot_edit_other_users_record(client):
    login_as_new_user(client, "alice", "alice@example.com")
    record = create_record(client, amount="100").get_json()
    logout_user(client)
    login_as_new_user(client, "bob", "bob@example.com")
    assert client.put(
        f"/api/records/{record['id']}",
        json={"date": "2026-06-01", "type": "expense", "category": "food", "amount": "5"},
        headers=csrf_headers(client),
    ).status_code == 404


def test_statistics_use_converted_amount_and_filter_base_currency(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    create_record(client, date="2026-06-01", record_type="expense", category="food", amount="1000")
    create_record(
        client,
        date="2026-06-02",
        record_type="income",
        category="salary",
        amount="100.00",
        extra={"currency_code": "CNY", "exchange_rate": "20"},
    )
    with app_module.get_connection() as conn:
        conn.execute(
            "UPDATE records SET base_currency_code = 'CNY' WHERE type = 'expense'"
        )
        conn.commit()

    data = client.get("/api/analytics?month=2026-06").get_json()
    assert data["currencyCode"] == "JPY"
    assert data["totalIncome"] == 2000
    assert data["totalExpense"] == 1000
    assert data["balance"] == 1000
    assert data["missingRateCount"] == 0


def test_budget_currency_and_usage_filtering(client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert save_budget(client, "2026-06", "3000").status_code == 200
    create_record(client, date="2026-06-01", record_type="expense", amount="1000")
    create_record(
        client,
        date="2026-06-02",
        record_type="expense",
        amount="100.00",
        extra={"currency_code": "CNY", "exchange_rate": "20"},
    )
    data = client.get("/api/analytics?month=2026-06").get_json()
    assert data["budget"]["currency_code"] == "JPY"
    assert data["budget"]["used"] == 3000
    assert data["budget"]["remaining"] == 0

    assert set_base_currency(client, "CNY").status_code == 302
    data_after_change = client.get("/api/analytics?month=2026-06").get_json()
    assert data_after_change["budget"]["currency_code"] == "JPY"


def test_old_database_records_migrate_idempotently(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
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
            CREATE TABLE budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, month)
            )
            """
        )
        conn.execute(
            "INSERT INTO records (id, date, type, category, amount, note, created_at) VALUES ('old', '2026-06-01', 'expense', 'food', 12.5, '', 1)"
        )
        conn.commit()

    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    sys.modules.pop("server", None)
    sys.modules.pop("database", None)
    server = importlib.import_module("server")
    server.init_db()

    with server.get_connection() as conn:
        first = conn.execute("SELECT * FROM records WHERE id = 'old'").fetchone()
        assert first["user_id"] == 1
        assert first["currency_code"] == "JPY"
        assert first["base_currency_code"] == "JPY"
        assert first["exchange_rate"] == "1"
        assert first["converted_amount_minor"] == first["original_amount_minor"]
        assert first["rate_source"] == "migration"
        original_minor = first["original_amount_minor"]

    server.init_db()
    with server.get_connection() as conn:
        second = conn.execute("SELECT * FROM records WHERE id = 'old'").fetchone()
        assert second["original_amount_minor"] == original_minor
        assert conn.execute(
            "SELECT COUNT(*) FROM user_exchange_rates"
        ).fetchone()[0] == 0


def test_latest_exchange_rate_table_updates_by_user_and_direction(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    create_record(
        client,
        amount="100.00",
        extra={"currency_code": "CNY", "exchange_rate": "20"},
    )
    create_record(
        client,
        amount="100.00",
        extra={"currency_code": "CNY", "exchange_rate": "20.5"},
    )

    direct = client.get("/api/exchange-rate/latest?from=CNY&to=JPY").get_json()
    assert direct["found"] is True
    assert direct["rate"] == "20.5"
    assert direct["source"] == "direct"

    inverse = client.get("/api/exchange-rate/latest?from=JPY&to=CNY").get_json()
    assert inverse["found"] is True
    assert inverse["source"] == "inverse"
    assert inverse["rate"].startswith("0.048780")

    with app_module.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM user_exchange_rates WHERE user_id = ?",
            (2,),
        ).fetchall()
        assert len(rows) == 1

    logout_user(client)
    login_as_new_user(client, "bob", "bob@example.com")
    missing_for_bob = client.get("/api/exchange-rate/latest?from=CNY&to=JPY").get_json()
    assert missing_for_bob["found"] is False


def test_latest_exchange_rate_rejects_invalid_inputs_and_failed_save_does_not_update(client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert client.get("/api/exchange-rate/latest?from=USD&to=JPY").status_code == 400
    assert create_record(
        client,
        amount="100.00",
        extra={"currency_code": "CNY", "exchange_rate": "bad"},
    ).status_code == 400
    missing = client.get("/api/exchange-rate/latest?from=CNY&to=JPY").get_json()
    assert missing["found"] is False


def test_edit_note_does_not_update_latest_rate_but_rate_change_does(client):
    login_as_new_user(client, "alice", "alice@example.com")
    record = create_record(
        client,
        amount="100.00",
        extra={"currency_code": "CNY", "exchange_rate": "20"},
    ).get_json()

    client.put(
        f"/api/records/{record['id']}",
        json={
            "date": record["date"],
            "type": record["type"],
            "category": record["category"],
            "amount": "100.00",
            "currency_code": "CNY",
            "exchange_rate": "20",
            "note": "note only",
        },
        headers=csrf_headers(client),
    )
    assert client.get("/api/exchange-rate/latest?from=CNY&to=JPY").get_json()["rate"] == "20"

    changed = client.put(
        f"/api/records/{record['id']}",
        json={
            "date": record["date"],
            "type": record["type"],
            "category": record["category"],
            "amount": "100.00",
            "currency_code": "CNY",
            "exchange_rate": "21",
            "note": "changed rate",
        },
        headers=csrf_headers(client),
    )
    assert changed.status_code == 200
    assert client.get("/api/exchange-rate/latest?from=CNY&to=JPY").get_json()["rate"] == "21"


def test_default_currency_and_language_are_independent(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert set_base_currency(client, "JPY", language="zh-CN").status_code == 302
    assert set_base_currency(client, "CNY", language="zh-CN").status_code == 302
    assert set_base_currency(client, "JPY", language="ja").status_code == 302
    assert set_base_currency(client, "CNY", language="ja").status_code == 302

    with app_module.get_connection() as conn:
        row = conn.execute(
            "SELECT language, base_currency_code FROM users WHERE username = 'alice'"
        ).fetchone()
        assert row["language"] == "ja"
        assert row["base_currency_code"] == "CNY"

    client.get("/set-language/zh_CN")
    with app_module.get_connection() as conn:
        row = conn.execute(
            "SELECT language, base_currency_code FROM users WHERE username = 'alice'"
        ).fetchone()
        assert row["language"] == "ja"
        assert row["base_currency_code"] == "CNY"


def test_record_form_copy_is_user_friendly_in_chinese_and_japanese(client):
    login_as_new_user(client, "alice", "alice@example.com")

    chinese = client.get("/records/add?lang=zh_CN").get_data(as_text=True)
    assert "金额" in chinese
    assert "币种" in chinese
    assert "换算汇率" in chinese
    assert "换算结果" in chinese
    assert "原始金额" not in chinese
    assert "原始币种" not in chinese
    assert "汇率方向固定" not in chinese

    japanese = client.get("/records/add?lang=ja").get_data(as_text=True)
    assert "金額" in japanese
    assert "通貨" in japanese
    assert "換算レート" in japanese
    assert "換算結果" in japanese
    assert "元の金額" not in japanese


def test_dashboard_uses_recent_rate_for_current_default_currency_without_modifying_history(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    historical = create_record(
        client,
        date="2026-06-01",
        record_type="expense",
        amount="1000",
        extra={"currency_code": "JPY"},
    ).get_json()
    assert set_base_currency(client, "CNY").status_code == 302
    create_record(
        client,
        date="2026-06-02",
        record_type="expense",
        amount="1000",
        extra={"currency_code": "JPY", "exchange_rate": "0.047"},
    )

    data = client.get("/api/analytics?month=2026-06").get_json()
    assert data["currencyCode"] == "CNY"
    assert data["totalExpense"] == 94
    assert data["estimatedCount"] == 1
    assert data["estimatedRateNotice"]

    with app_module.get_connection() as conn:
        original = conn.execute(
            "SELECT * FROM records WHERE id = ?",
            (historical["id"],),
        ).fetchone()
        assert original["base_currency_code"] == "JPY"
        assert original["exchange_rate"] == "1"
        assert original["converted_amount_minor"] == 1000


def test_missing_recent_rate_is_not_counted_and_reports_notice(client):
    login_as_new_user(client, "alice", "alice@example.com")
    create_record(
        client,
        date="2026-06-01",
        record_type="expense",
        amount="1000",
        extra={"currency_code": "JPY"},
    )
    assert set_base_currency(client, "CNY").status_code == 302

    data = client.get("/api/analytics?month=2026-06").get_json()
    assert data["totalExpense"] == 0
    assert data["missingRateCount"] == 1
    assert data["missingRateNotice"]
    assert data["missingRateDirections"][0]["from_currency_code"] == "JPY"
    assert data["missingRateDirections"][0]["to_currency_code"] == "CNY"


def test_budget_uses_recent_rate_and_skips_missing_rates(client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert save_budget(client, "2026-06", "3000").status_code == 200
    create_record(client, date="2026-06-01", record_type="expense", amount="1000")
    create_record(
        client,
        date="2026-06-02",
        record_type="expense",
        amount="100.00",
        extra={"currency_code": "CNY", "exchange_rate": "20"},
    )
    data = client.get("/api/analytics?month=2026-06").get_json()
    assert data["budget"]["used"] == 3000

    create_record(client, date="2026-07-01", record_type="expense", amount="1000", extra={"currency_code": "JPY"})
    assert set_base_currency(client, "CNY").status_code == 302
    assert save_budget(client, "2026-07", "500.00").status_code == 200
    july = client.get("/api/analytics?month=2026-07").get_json()
    assert july["budget"]["used"] == 50
    assert july["budget"]["budgetEstimatedCount"] == 1

    logout_user(client)
    login_as_new_user(client, "bob", "bob@example.com")
    create_record(client, date="2026-08-01", record_type="expense", amount="1000", extra={"currency_code": "JPY"})
    assert set_base_currency(client, "CNY").status_code == 302
    assert save_budget(client, "2026-08", "500.00").status_code == 200
    august = client.get("/api/analytics?month=2026-08").get_json()
    assert august["budget"]["used"] == 0
    assert august["budget"]["budgetMissingRateCount"] == 1
