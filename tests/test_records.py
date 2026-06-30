from conftest import create_record, csrf_headers, login_as_new_user, logout_user


def test_add_edit_delete_record(client):
    login_as_new_user(client, "alice", "alice@example.com")
    created = create_record(client, note="  lunch  ")
    assert created.status_code == 201
    record = created.get_json()
    assert record["note"] == "lunch"

    updated = client.put(
        f"/api/records/{record['id']}",
        json={
            "date": "2026-06-16",
            "type": "income",
            "category": "salary",
            "amount": 1000.55,
            "note": "pay",
        },
        headers=csrf_headers(client),
    )
    assert updated.status_code == 200
    assert updated.get_json()["type"] == "income"

    deleted = client.delete(f"/api/records/{record['id']}", headers=csrf_headers(client))
    assert deleted.status_code == 200
    assert client.get(f"/api/records/{record['id']}").status_code == 404


def test_record_date_validation(client):
    login_as_new_user(client, "alice", "alice@example.com")
    for value in ["2026-02-30", "2026-13-01", "abcdefghij", ""]:
        assert create_record(client, date=value).status_code == 400
    assert create_record(client, date="2028-02-29").status_code == 201


def test_record_amount_validation(client):
    login_as_new_user(client, "alice", "alice@example.com")
    for value in ["", 0, -1, "abc", "NaN", "Infinity", "-Infinity", 1_000_000_001]:
        assert create_record(client, amount=value).status_code == 400
    assert create_record(client, amount=10).status_code == 201
    assert create_record(client, amount=10.23).status_code == 201


def test_record_type_and_category_validation(client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert create_record(client, record_type="transfer").status_code == 400
    assert create_record(client, category="   ").status_code == 400


def test_user_data_isolation_for_records_and_statistics(client):
    login_as_new_user(client, "alice", "alice@example.com")
    a_record = create_record(client, record_type="expense", amount=10, note="alice expense").get_json()
    create_record(client, record_type="income", amount=100, note="alice income")
    logout_user(client)

    login_as_new_user(client, "bob", "bob@example.com")
    b_record = create_record(client, record_type="expense", amount=70, note="bob expense").get_json()

    records = client.get("/api/records").get_json()["items"]
    assert {item["id"] for item in records} == {b_record["id"]}
    summary = client.get("/api/summary?month=2026-06").get_json()
    assert summary["totalExpense"] == 70
    assert summary["totalIncome"] == 0

    assert client.get(f"/api/records/{a_record['id']}").status_code == 404
    assert client.put(
        f"/api/records/{a_record['id']}",
        json={"date": "2026-06-01", "type": "expense", "category": "food", "amount": 5},
        headers=csrf_headers(client),
    ).status_code == 404
    assert client.delete(f"/api/records/{a_record['id']}", headers=csrf_headers(client)).status_code == 404


def test_api_ignores_forged_user_id(client):
    login_as_new_user(client, "alice", "alice@example.com")
    created = create_record(client, extra={"user_id": 999}).get_json()
    assert client.get(f"/api/records/{created['id']}").status_code == 200
    logout_user(client)

    login_as_new_user(client, "bob", "bob@example.com")
    assert client.get(f"/api/records/{created['id']}").status_code == 404
