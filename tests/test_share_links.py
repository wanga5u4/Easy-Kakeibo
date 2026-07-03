from datetime import datetime, timedelta, timezone

from conftest import create_record, csrf_token, login_as_new_user, login_user, logout_user


def post_share(client, **overrides):
    data = {
        "csrf_token": csrf_token(client, "/share"),
        "title": "July summary",
        "description": "Shared totals only.",
        "share_month": "2026-07",
        "include_income_summary": "1",
        "include_expense_summary": "1",
        "include_category_summary": "1",
        "expires_in": "7",
    }
    for key, value in overrides.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return client.post("/share", data=data, follow_redirects=False)


def post_share_action(client, link_id, action):
    return client.post(
        f"/share/{link_id}/{action}",
        data={"csrf_token": csrf_token(client, "/share")},
        follow_redirects=False,
    )


def get_share_links(app_module):
    with app_module.get_connection() as conn:
        return conn.execute(
            "SELECT * FROM share_links ORDER BY created_at DESC, id DESC"
        ).fetchall()


def set_share_expired(app_module, link_id):
    past = (
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    ).strftime("%Y-%m-%d %H:%M:%S")
    with app_module.get_connection() as conn:
        conn.execute(
            "UPDATE share_links SET expires_at = ? WHERE id = ?",
            (past, link_id),
        )
        conn.commit()


def user_id_for(app_module, username):
    with app_module.get_connection() as conn:
        return conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,),
        ).fetchone()["id"]


def test_share_management_requires_login(client):
    response = client.get("/share")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_logged_in_user_can_create_share_link(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")

    response = post_share(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/share")

    rows = get_share_links(app_module)
    assert len(rows) == 1
    assert rows[0]["user_id"] == user_id_for(app_module, "alice")
    assert rows[0]["share_month"] == "2026-07"
    assert rows[0]["is_active"] == 1
    assert rows[0]["view_count"] == 0


def test_share_token_unique_and_not_predictable(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert post_share(client, title="First").status_code == 302
    assert post_share(client, title="Second").status_code == 302

    rows = get_share_links(app_module)
    tokens = [row["token"] for row in rows]
    assert len(set(tokens)) == 2
    for row in rows:
        assert len(row["token"]) >= 40
        assert row["token"] != str(row["id"])
        assert row["token"] != row["share_month"]


def test_share_creation_validation(client):
    login_as_new_user(client, "alice", "alice@example.com")

    assert post_share(client, share_month="2026-13").status_code == 400
    assert post_share(
        client,
        include_income_summary=None,
        include_expense_summary=None,
        include_category_summary=None,
    ).status_code == 400
    assert post_share(client, title="A" * 101).status_code == 400
    assert post_share(client, description="A" * 301).status_code == 400
    assert post_share(client, expires_in="999").status_code == 400


def test_user_only_sees_own_share_links(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert post_share(client, title="Alice private link").status_code == 302
    logout_user(client)

    login_as_new_user(client, "bob", "bob@example.com")
    page = client.get("/share").get_data(as_text=True)
    assert "Alice private link" not in page
    assert "还没有创建分享链接。" in page


def test_user_cannot_disable_or_delete_another_users_link(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert post_share(client, title="Alice link").status_code == 302
    link = get_share_links(app_module)[0]
    logout_user(client)

    login_as_new_user(client, "bob", "bob@example.com")
    assert post_share_action(client, link["id"], "disable").status_code == 302
    assert post_share_action(client, link["id"], "delete").status_code == 302

    rows = get_share_links(app_module)
    assert len(rows) == 1
    assert rows[0]["id"] == link["id"]
    assert rows[0]["is_active"] == 1


def test_disabled_expired_and_deleted_links_do_not_render_public_page(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert post_share(client).status_code == 302
    disabled = get_share_links(app_module)[0]
    assert post_share_action(client, disabled["id"], "disable").status_code == 302
    assert client.get(f"/s/{disabled['token']}").status_code == 410

    assert post_share(client, title="Expired").status_code == 302
    expired = get_share_links(app_module)[0]
    set_share_expired(app_module, expired["id"])
    expired_page = client.get(f"/s/{expired['token']}")
    assert expired_page.status_code == 410
    assert "链接已过期".encode("utf-8") in expired_page.data

    assert post_share(client, title="Delete me").status_code == 302
    deleted = get_share_links(app_module)[0]
    assert post_share_action(client, deleted["id"], "delete").status_code == 302
    missing = client.get(f"/s/{deleted['token']}")
    assert missing.status_code == 404
    assert "链接不存在".encode("utf-8") in missing.data


def test_public_share_privacy_and_scope(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    create_record(client, date="2026-07-05", record_type="income", category="salary", amount=100, note="secret salary note")
    create_record(client, date="2026-07-06", record_type="expense", category="food", amount=40, note="secret food note")
    create_record(client, date="2026-08-06", record_type="expense", category="food", amount=999, note="wrong month")
    assert post_share(client, share_month="2026-07").status_code == 302
    token = get_share_links(app_module)[0]["token"]
    logout_user(client)

    login_as_new_user(client, "bob", "bob@example.com")
    create_record(client, date="2026-07-06", record_type="expense", category="travel", amount=777, note="bob secret")
    logout_user(client)

    page = client.get(f"/s/{token}?month=2026-08").get_data(as_text=True)
    assert "￥100.00" in page
    assert "￥40.00" in page
    assert "￥60.00" in page
    assert "￥999.00" not in page
    assert "￥777.00" not in page
    assert "alice@example.com" not in page
    assert "User ID" not in page
    assert "secret salary note" not in page
    assert "secret food note" not in page
    assert "bob secret" not in page
    assert "完整交易明细" in page


def test_public_share_escapes_user_input(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert post_share(
        client,
        title="<script>alert(1)</script>",
        description="<script>alert(2)</script>",
    ).status_code == 302
    token = get_share_links(app_module)[0]["token"]
    logout_user(client)

    page = client.get(f"/s/{token}").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<script>alert(2)</script>" not in page


def test_public_share_view_count_increments_only_for_valid_access(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert post_share(client).status_code == 302
    link = get_share_links(app_module)[0]
    logout_user(client)

    assert client.get(f"/s/{link['token']}").status_code == 200
    assert get_share_links(app_module)[0]["view_count"] == 1

    login_user(client, "alice")
    assert post_share_action(client, link["id"], "disable").status_code == 302
    logout_user(client)
    assert client.get(f"/s/{link['token']}").status_code == 410
    assert get_share_links(app_module)[0]["view_count"] == 1


def test_account_deletion_removes_feedback_and_share_links(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    alice_id = user_id_for(app_module, "alice")
    client.post(
        "/feedback",
        data={
            "csrf_token": csrf_token(client, "/feedback"),
            "feedback_type": "feature",
            "title": "Feature idea",
            "content": "Please add something useful.",
        },
    )
    assert post_share(client).status_code == 302

    response = client.post(
        "/settings/delete-account",
        data={
            "csrf_token": csrf_token(client, "/settings"),
            "delete_current_password": "password123",
            "delete_confirmation": "DELETE",
        },
    )
    assert response.status_code == 302

    with app_module.get_connection() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM feedback WHERE user_id = ?",
            (alice_id,),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM share_links WHERE user_id = ?",
            (alice_id,),
        ).fetchone()[0] == 0
