from conftest import csrf_token, login_as_new_user, login_user, logout_user, register_user


def test_register_success(client):
    response = register_user(client)
    assert response.status_code == 302


def test_duplicate_username_rejected(client):
    assert register_user(client).status_code == 302
    response = register_user(client, email="another@example.com")
    assert response.status_code == 400


def test_duplicate_email_case_insensitive_rejected(client):
    assert register_user(client, email="case@example.com").status_code == 302
    response = register_user(client, username="bob", email="CASE@EXAMPLE.COM")
    assert response.status_code == 400


def test_invalid_email_rejected(client):
    response = register_user(client, email="not-an-email")
    assert response.status_code == 400


def test_login_with_username_email_and_uppercase_email(client):
    assert register_user(client, username="CaseUser", email="case@example.com").status_code == 302
    assert login_user(client, "CaseUser").status_code == 302
    logout_user(client)
    assert login_user(client, "case@example.com").status_code == 302
    logout_user(client)
    assert login_user(client, " CASE@EXAMPLE.COM ").status_code == 302


def test_username_case_behavior_is_unchanged(client):
    assert register_user(client, username="CaseUser", email="case@example.com").status_code == 302
    response = login_user(client, "caseuser")
    assert response.status_code == 400


def test_wrong_password_and_missing_account_fail(client):
    assert register_user(client).status_code == 302
    assert login_user(client, "alice", "wrong-password").status_code == 400
    assert login_user(client, "missing", "password123").status_code == 400


def test_logout_requires_post(client):
    login_as_new_user(client, "alice", "alice@example.com")
    assert client.get("/logout").status_code == 405
    assert logout_user(client).status_code == 302


def test_protected_page_redirects_when_logged_out(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_password_change_invalidates_old_password(client):
    login_as_new_user(client, "alice", "alice@example.com")
    token = csrf_token(client, "/settings")
    response = client.post(
        "/settings",
        data={
            "csrf_token": token,
            "nickname": "Alice",
            "language": "zh-CN",
            "currency": "CNY",
            "current_password": "password123",
            "new_password": "newpassword123",
            "confirm_password": "newpassword123",
        },
    )
    assert response.status_code == 302
    logout_user(client)
    assert login_user(client, "alice", "password123").status_code == 400
    assert login_user(client, "alice", "newpassword123").status_code == 302


def test_settings_post_cannot_change_email(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    token = csrf_token(client, "/settings")
    response = client.post(
        "/settings",
        data={
            "csrf_token": token,
            "nickname": "Alice",
            "email": "attacker@example.com",
            "language": "zh-CN",
            "currency": "CNY",
        },
    )
    assert response.status_code == 302
    with app_module.get_connection() as conn:
        email = conn.execute(
            "SELECT email FROM users WHERE username = ?",
            ("alice",),
        ).fetchone()["email"]
    assert email == "alice@example.com"
