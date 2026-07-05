from conftest import create_record, csrf_headers, csrf_token, login_as_new_user, logout_user, save_budget


def set_profile_currency(client, currency_code, language="zh-CN", nickname=""):
    return client.post(
        "/settings/profile",
        data={
            "csrf_token": csrf_token(client, "/settings"),
            "nickname": nickname,
            "language": language,
            "currency": currency_code,
        },
        follow_redirects=False,
    )


def test_create_and_update_budget_without_duplicates(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert save_budget(client, "2026-06", 1000).status_code == 200
    assert save_budget(client, "2026-06", 1200).status_code == 200
    with app_module.get_connection() as conn:
        rows = conn.execute("SELECT amount FROM budgets WHERE month = '2026-06'").fetchall()
    assert len(rows) == 1
    assert rows[0]["amount"] == 1200


def test_budget_is_user_isolated(client):
    login_as_new_user(client, "alice", "alice@example.com")
    save_budget(client, "2026-06", 100)
    logout_user(client)
    login_as_new_user(client, "bob", "bob@example.com")
    save_budget(client, "2026-06", 500)
    data = client.get("/api/analytics?month=2026-06").get_json()
    assert data["budget"]["amount"] == 500


def test_invalid_budget_amounts_rejected(client):
    login_as_new_user(client, "alice", "alice@example.com")
    for value in ["", -1, "abc", "NaN", "Infinity", "-Infinity", 1_000_000_000_000]:
        assert save_budget(client, "2026-06", value).status_code == 400


def test_zero_budget_is_saved_and_usage_stays_finite(client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert save_budget(client, "2026-06", 0).status_code == 200
    data = client.get("/api/analytics?month=2026-06").get_json()
    assert data["budget"]["amount"] == 0
    assert data["budget"]["used"] == 0
    assert data["budget"]["percent"] == 0


def test_budget_statuses(client):
    login_as_new_user(client, "alice", "alice@example.com")
    unset = client.get("/api/analytics?month=2026-06").get_json()
    assert unset["budget"]["amount"] == 0

    save_budget(client, "2026-06", 100)
    create_record(client, date="2026-06-01", record_type="expense", amount=120)
    over = client.get("/api/analytics?month=2026-06").get_json()
    assert over["budget"]["used"] == 120
    assert over["budget"]["percent"] == 120
    assert over["budget"]["formatted_over_budget"]


def test_new_budget_uses_cny_default_currency(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert set_profile_currency(client, "CNY").status_code == 302

    page = client.get("/budgets").get_data(as_text=True)
    assert 'id="budgetCurrencyLabel">CNY<' in page

    empty = client.get("/api/analytics?month=2026-08").get_json()
    assert empty["budget"]["currency_code"] == "CNY"
    assert save_budget(client, "2026-08", "1500.25").status_code == 200

    with app_module.get_connection() as conn:
        row = conn.execute(
            "SELECT amount, currency_code FROM budgets WHERE month = '2026-08'"
        ).fetchone()
    assert row["amount"] == 1500.25
    assert row["currency_code"] == "CNY"


def test_jpy_default_currency_saves_jpy_budget(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert save_budget(client, "2026-08", "1500").status_code == 200

    with app_module.get_connection() as conn:
        currency_code = conn.execute(
            "SELECT currency_code FROM budgets WHERE month = '2026-08'"
        ).fetchone()["currency_code"]
    assert currency_code == "JPY"


def test_existing_budget_keeps_currency_after_default_changes(client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert save_budget(client, "2026-07", "3000").status_code == 200
    assert set_profile_currency(client, "CNY").status_code == 302

    july = client.get("/api/analytics?month=2026-07").get_json()
    august = client.get("/api/analytics?month=2026-08").get_json()

    assert july["budget"]["currency_code"] == "JPY"
    assert august["budget"]["currency_code"] == "CNY"


def test_legacy_budget_without_currency_falls_back_to_user_default(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert set_profile_currency(client, "CNY").status_code == 302
    assert save_budget(client, "2026-09", "800.50").status_code == 200

    with app_module.get_connection() as conn:
        conn.execute(
            "UPDATE budgets SET currency_code = '', amount_minor = 0 WHERE month = '2026-09'"
        )
        conn.commit()

    data = client.get("/api/analytics?month=2026-09").get_json()
    assert data["budget"]["currency_code"] == "CNY"
    assert data["budget"]["amount"] == 800.5


def test_budget_rejects_unknown_currency_code(client):
    login_as_new_user(client, "alice", "alice@example.com")
    response = client.post(
        "/api/budget",
        json={"month": "2026-06", "amount": "100", "currency_code": "USD"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 400



def test_user_cannot_modify_other_user_budget(client):
    login_as_new_user(client, "alice", "alice@example.com")
    save_budget(client, "2026-06", 100)
    logout_user(client)
    login_as_new_user(client, "bob", "bob@example.com")
    save_budget(client, "2026-06", 500)
    logout_user(client)

    login_as_new_user(client, "alice2", "alice2@example.com")
    data = client.get("/api/analytics?month=2026-06").get_json()
    assert data["budget"]["amount"] == 0
