from conftest import create_record, login_as_new_user, logout_user


def test_records_pagination_pages_and_totals(client):
    login_as_new_user(client, "alice", "alice@example.com")
    for day in range(1, 13):
        create_record(client, date=f"2026-06-{day:02d}", amount=day)

    page1 = client.get("/api/records?page=1&per_page=10").get_json()
    page2 = client.get("/api/records?page=2&per_page=10").get_json()
    assert len(page1["items"]) == 10
    assert len(page2["items"]) == 2
    assert page1["pagination"]["total"] == 12
    assert page1["pagination"]["total_pages"] == 2
    assert page1["pagination"]["has_prev"] is False
    assert page1["pagination"]["has_next"] is True
    assert page2["pagination"]["has_prev"] is True
    assert page2["pagination"]["has_next"] is False
    assert page1["items"][0]["date"] == "2026-06-12"


def test_invalid_pagination_args_fallback(client):
    login_as_new_user(client, "alice", "alice@example.com")
    for day in range(1, 4):
        create_record(client, date=f"2026-06-{day:02d}")
    data = client.get("/api/records?page=bad&per_page=bad").get_json()
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["per_page"] == 10
    data = client.get("/api/records?page=-5&per_page=999").get_json()
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["per_page"] == 10


def test_allowed_per_page_values(client):
    login_as_new_user(client, "alice", "alice@example.com")
    for day in range(1, 31):
        create_record(client, date=f"2026-06-{day:02d}")
    assert len(client.get("/api/records?per_page=10").get_json()["items"]) == 10
    assert len(client.get("/api/records?per_page=20").get_json()["items"]) == 20
    assert len(client.get("/api/records?per_page=50").get_json()["items"]) == 30


def test_type_and_month_filter_pagination(client):
    login_as_new_user(client, "alice", "alice@example.com")
    for day in range(1, 8):
        create_record(client, date=f"2026-06-{day:02d}", record_type="expense")
    for day in range(1, 6):
        create_record(client, date=f"2026-05-{day:02d}", record_type="income")

    expense = client.get("/api/records?type=expense&page=1&per_page=10").get_json()
    june = client.get("/api/records?month=2026-06&page=1&per_page=10").get_json()
    assert expense["pagination"]["total"] == 7
    assert all(item["type"] == "expense" for item in expense["items"])
    assert june["pagination"]["total"] == 7
    assert all(item["date"].startswith("2026-06") for item in june["items"])


def test_pagination_is_user_isolated_and_empty_is_reasonable(client):
    login_as_new_user(client, "alice", "alice@example.com")
    create_record(client)
    logout_user(client)
    login_as_new_user(client, "bob", "bob@example.com")
    data = client.get("/api/records?page=1&per_page=10").get_json()
    assert data["items"] == []
    assert data["pagination"]["total"] == 0
    assert data["pagination"]["total_pages"] == 0
