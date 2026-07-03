from conftest import create_record, csrf_headers, login_as_new_user, logout_user, save_budget


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
    for value in ["", 0, -1, "abc", "NaN", "Infinity", "-Infinity", 1_000_000_000_000]:
        assert save_budget(client, "2026-06", value).status_code == 400


def test_budget_statuses(client):
    login_as_new_user(client, "alice", "alice@example.com")
    unset = client.get("/api/analytics?month=2026-06").get_json()
    assert unset["budget"]["amount"] == 0

    save_budget(client, "2026-06", 100)
    create_record(client, date="2026-06-01", record_type="expense", amount=120)
    over = client.get("/api/analytics?month=2026-06").get_json()
    assert over["budget"]["used"] == 120
    assert over["budget"]["percent"] == 120


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
