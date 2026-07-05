import logging

from werkzeug.security import check_password_hash

from conftest import (
    create_record,
    csrf_token,
    login_as_new_user,
    login_user,
    logout_user,
    register_user,
    save_budget,
)


def post_settings(client, nickname="", language="zh-CN", currency="CNY", extra=None):
    data = {
        "csrf_token": csrf_token(client, "/settings"),
        "nickname": nickname,
        "language": language,
        "currency": currency,
    }
    if extra:
        data.update(extra)
    return client.post("/settings/profile", data=data, follow_redirects=False)


def post_password_settings(
    client,
    current_password="password123",
    new_password="new-password123",
    confirm_password="new-password123",
):
    return client.post(
        "/settings/password",
        data={
            "csrf_token": csrf_token(client, "/settings"),
            "current_password": current_password,
            "new_password": new_password,
            "confirm_password": confirm_password,
        },
        follow_redirects=False,
    )


def post_delete_account(
    client,
    password="password123",
    confirmation="DELETE",
    extra=None,
    follow_redirects=False,
):
    data = {
        "csrf_token": csrf_token(client, "/settings"),
        "delete_current_password": password,
        "delete_confirmation": confirmation,
    }
    if extra:
        data.update(extra)
    return client.post(
        "/settings/delete-account",
        data=data,
        follow_redirects=follow_redirects,
    )


def count_rows(app_module, table_name, user_id=None):
    with app_module.get_connection() as conn:
        if user_id is None:
            return conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        return conn.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]


def user_id_for(app_module, username):
    with app_module.get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    return row["id"]


def test_delete_account_requires_login_and_post(app_module, client):
    token = csrf_token(client, "/login")
    response = client.post(
        "/settings/delete-account",
        data={
            "csrf_token": token,
            "delete_current_password": "password123",
            "delete_confirmation": "DELETE",
        },
    )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    login_as_new_user(client, "alice", "alice@example.com")
    alice_id = user_id_for(app_module, "alice")
    create_record(client)
    assert client.get("/settings/delete-account").status_code == 405
    assert count_rows(app_module, "users") == 2
    assert count_rows(app_module, "records", alice_id) == 1


def test_delete_account_rejects_wrong_password_and_confirmation(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    alice_id = user_id_for(app_module, "alice")
    create_record(client)
    save_budget(client)

    wrong_password = post_delete_account(client, password="wrong-password")
    assert wrong_password.status_code == 302
    assert count_rows(app_module, "users") == 2
    assert count_rows(app_module, "records", alice_id) == 1
    assert count_rows(app_module, "budgets", alice_id) == 1

    wrong_confirmation = post_delete_account(client, confirmation="注销账号")
    assert wrong_confirmation.status_code == 302
    assert count_rows(app_module, "users") == 2
    assert count_rows(app_module, "records", alice_id) == 1
    assert count_rows(app_module, "budgets", alice_id) == 1


def test_delete_account_removes_only_current_user_data_and_clears_session(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    alice_id = user_id_for(app_module, "alice")
    create_record(client, note="alice data")
    save_budget(client, month="2026-06", amount=100)
    logout_user(client)

    login_as_new_user(client, "bob", "bob@example.com")
    bob_id = user_id_for(app_module, "bob")
    create_record(client, note="bob data")
    save_budget(client, month="2026-06", amount=500)

    response = post_delete_account(
        client,
        extra={"user_id": str(alice_id)},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/register")
    with client.session_transaction() as sess:
        assert "user_id" not in sess
        assert "username" not in sess

    with app_module.get_connection() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM users WHERE id = ?",
            (bob_id,),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM records WHERE user_id = ?",
            (bob_id,),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM budgets WHERE user_id = ?",
            (bob_id,),
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM users WHERE id = ?",
            (alice_id,),
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM records WHERE user_id = ?",
            (alice_id,),
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM budgets WHERE user_id = ?",
            (alice_id,),
        ).fetchone()[0] == 1

    assert login_user(client, "bob", "password123").status_code == 400
    assert login_user(client, "alice", "password123").status_code == 302


def test_delete_account_rolls_back_when_user_delete_fails(app_module, client, monkeypatch):
    login_as_new_user(client, "alice", "alice@example.com")
    alice_id = user_id_for(app_module, "alice")
    create_record(client)
    save_budget(client)
    original_get_connection = app_module.get_connection

    class FailingConnection:
        def __init__(self):
            self.conn = original_get_connection()

        def execute(self, sql, params=()):
            if sql.strip().startswith("DELETE FROM users"):
                raise RuntimeError("delete failed")
            return self.conn.execute(sql, params)

        def commit(self):
            return self.conn.commit()

        def rollback(self):
            return self.conn.rollback()

        def close(self):
            return self.conn.close()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self.close()

    monkeypatch.setattr(app_module, "get_connection", FailingConnection)

    response = post_delete_account(client)

    assert response.status_code == 302
    assert count_rows(app_module, "users") == 2
    assert count_rows(app_module, "records", alice_id) == 1
    assert count_rows(app_module, "budgets", alice_id) == 1


def test_delete_account_logs_do_not_include_plaintext_password(client, caplog):
    login_as_new_user(client, "alice", "alice@example.com")
    with caplog.at_level(logging.WARNING):
        response = post_delete_account(client, password="wrong-password")

    assert response.status_code == 302
    assert "wrong-password" not in caplog.text
    assert "password123" not in caplog.text


def test_settings_page_labels_profile_fields_and_removes_plan_card(client):
    login_as_new_user(client, "alice", "alice@example.com")

    response = client.get("/settings")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "用户名" in text
    assert "alice" in text
    assert "邮箱" in text
    assert "alice@example.com" in text
    assert "昵称将用于页面中的欢迎信息和账户显示。" in text
    assert "当前套餐" not in text
    assert "当前账号使用的套餐与权益状态。" not in text
    assert ">free<" not in text


def test_settings_page_does_not_repeat_email_when_username_is_email(client):
    register_user(client, username="same@example.com", email="same@example.com")
    assert login_user(client, "same@example.com").status_code == 302

    text = client.get("/settings").get_data(as_text=True)

    assert "登录邮箱" in text
    assert 'id="login_email"' in text
    assert 'id="email"' not in text
    assert "该邮箱用于登录，暂不支持在此页面修改。" in text


def test_settings_password_fields_are_not_prefilled(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    with app_module.get_connection() as conn:
        password_hash = conn.execute(
            "SELECT password_hash FROM users WHERE username = 'alice'"
        ).fetchone()["password_hash"]

    text = client.get("/settings").get_data(as_text=True)

    assert 'name="current_password" value=' not in text
    assert 'name="new_password" value=' not in text
    assert 'name="confirm_password" value=' not in text
    assert password_hash not in text


def test_settings_forms_submit_independent_fields(client):
    login_as_new_user(client, "alice", "alice@example.com")
    text = client.get("/settings").get_data(as_text=True)

    profile_form = text.split('action="/settings/profile"', 1)[1].split("</form>", 1)[0]
    password_form = text.split('action="/settings/password"', 1)[1].split("</form>", 1)[0]

    assert "current_password" not in profile_form
    assert "new_password" not in profile_form
    assert "confirm_password" not in profile_form
    assert 'name="nickname"' not in password_form
    assert 'name="language"' not in password_form
    assert 'name="currency"' not in password_form


def test_profile_updates_do_not_require_or_change_password(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    with app_module.get_connection() as conn:
        before_hash = conn.execute(
            "SELECT password_hash FROM users WHERE username = 'alice'"
        ).fetchone()["password_hash"]

    assert post_settings(client, currency="CNY").status_code == 302
    assert post_settings(client, language="ja", currency="CNY").status_code == 302
    assert post_settings(client, nickname="小明", language="ja", currency="CNY").status_code == 302

    with app_module.get_connection() as conn:
        row = conn.execute(
            "SELECT nickname, language, base_currency_code, password_hash FROM users WHERE username = 'alice'"
        ).fetchone()

    assert row["nickname"] == "小明"
    assert row["language"] == "ja"
    assert row["base_currency_code"] == "CNY"
    assert row["password_hash"] == before_hash


def test_password_form_validation_errors_do_not_change_hash(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    with app_module.get_connection() as conn:
        before_hash = conn.execute(
            "SELECT password_hash FROM users WHERE username = 'alice'"
        ).fetchone()["password_hash"]

    empty = post_password_settings(client, current_password="", new_password="", confirm_password="")
    wrong_current = post_password_settings(client, current_password="wrong-password")
    mismatch = post_password_settings(client, new_password="new-password123", confirm_password="another-password")

    assert empty.status_code == 400
    assert wrong_current.status_code == 400
    assert mismatch.status_code == 400
    assert "当前密码错误" in wrong_current.get_data(as_text=True)
    assert "两次输入的密码不一致" in mismatch.get_data(as_text=True)
    with app_module.get_connection() as conn:
        after_hash = conn.execute(
            "SELECT password_hash FROM users WHERE username = 'alice'"
        ).fetchone()["password_hash"]
    assert after_hash == before_hash


def test_password_form_updates_only_password_hash(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert post_settings(client, nickname="小明", language="ja", currency="CNY").status_code == 302

    response = post_password_settings(client)
    assert response.status_code == 302

    with app_module.get_connection() as conn:
        row = conn.execute(
            "SELECT nickname, language, base_currency_code, password_hash FROM users WHERE username = 'alice'"
        ).fetchone()

    assert row["nickname"] == "小明"
    assert row["language"] == "ja"
    assert row["base_currency_code"] == "CNY"
    assert row["password_hash"] != "new-password123"
    assert check_password_hash(row["password_hash"], "new-password123")
    logout_user(client)
    assert login_user(client, "alice", "password123").status_code == 400
    assert login_user(client, "alice", "new-password123").status_code == 302


def test_nickname_save_empty_fallback_and_nav_priority(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")

    assert post_settings(client, nickname="  小明  ").status_code == 302
    dashboard = client.get("/dashboard").get_data(as_text=True)
    assert "欢迎，小明" in dashboard
    assert "欢迎，alice" not in dashboard
    assert login_user(client, "alice", "password123").status_code == 302

    assert post_settings(client, nickname="   ").status_code == 302
    dashboard = client.get("/dashboard").get_data(as_text=True)
    assert "欢迎，alice" in dashboard
    with app_module.get_connection() as conn:
        nickname = conn.execute(
            "SELECT nickname FROM users WHERE username = ?",
            ("alice",),
        ).fetchone()["nickname"]
    assert nickname == ""


def test_nickname_too_long_fails_and_forged_user_id_is_ignored(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    logout_user(client)
    login_as_new_user(client, "bob", "bob@example.com")
    bob_id = user_id_for(app_module, "bob")
    logout_user(client)

    login_user(client, "alice")
    response = post_settings(client, nickname="A" * 31, extra={"user_id": str(bob_id)})
    assert response.status_code == 400

    ok = post_settings(client, nickname="Alice", extra={"user_id": str(bob_id)})
    assert ok.status_code == 302

    with app_module.get_connection() as conn:
        rows = {
            row["username"]: row["nickname"]
            for row in conn.execute("SELECT username, nickname FROM users")
        }
    assert rows["alice"] == "Alice"
    assert rows["bob"] == ""
