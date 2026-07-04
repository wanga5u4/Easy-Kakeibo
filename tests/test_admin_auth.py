from conftest import csrf_token, login_as_new_user, login_user


ADMIN_PATHS = (
    "/admin",
    "/admin/users",
    "/admin/users/1",
    "/admin/feedback",
    "/admin/feedback/1",
    "/admin/audit-logs",
)


def make_admin(app_module, username="alice"):
    with app_module.get_connection() as conn:
        conn.execute("UPDATE users SET is_admin = 1 WHERE username = ?", (username,))
        conn.commit()


def test_admin_requires_login(client):
    response = client.get("/admin")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert "next=/admin" in response.headers["Location"]


def test_normal_user_cannot_enter_admin_routes(client):
    login_as_new_user(client, "alice", "alice@example.com")

    for path in ADMIN_PATHS:
        assert client.get(path).status_code == 403


def test_admin_can_enter_dashboard(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    make_admin(app_module)

    response = client.get("/admin")

    assert response.status_code == 200
    assert "管理后台".encode("utf-8") in response.data


def test_admin_navigation_visible_only_to_admin(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    normal_page = client.get("/dashboard").get_data(as_text=True)
    assert "管理后台" not in normal_page

    make_admin(app_module)
    admin_page = client.get("/dashboard").get_data(as_text=True)
    assert "管理后台" in admin_page
    assert 'href="/admin/"' in admin_page


def test_admin_post_requires_csrf(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    make_admin(app_module)

    response = client.post(
        "/admin/users/1",
        data={"vip_status": "vip", "vip_expires_at": ""},
    )
    assert response.status_code == 400

    token = csrf_token(client, "/admin/users/1")
    response = client.post(
        "/admin/users/1",
        data={"csrf_token": token, "vip_status": "vip", "vip_expires_at": ""},
    )
    assert response.status_code == 302
