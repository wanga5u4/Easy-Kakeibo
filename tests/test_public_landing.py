from urllib.parse import parse_qs, urlparse

from conftest import csrf_token, login_as_new_user, login_user, register_user


def test_landing_page_accessible_without_login(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "轻松记录每一笔收支".encode("utf-8") in response.data
    assert 'href="/login"'.encode("utf-8") in response.data
    assert 'href="/register"'.encode("utf-8") in response.data


def test_landing_page_accessible_when_logged_in(client):
    login_as_new_user(client, "alice", "alice@example.com")

    response = client.get("/")

    assert response.status_code == 200
    assert "进入仪表盘".encode("utf-8") in response.data
    assert 'href="/records"'.encode("utf-8") in response.data


def test_dashboard_requires_login_and_returns_after_login(client):
    response = client.get("/dashboard")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    location = urlparse(response.headers["Location"])
    assert parse_qs(location.query)["next"] == ["/dashboard"]

    register_user(client)
    token = csrf_token(client, "/login?next=/dashboard")
    response = client.post(
        "/login?next=/dashboard",
        data={"csrf_token": token, "account": "alice", "password": "password123"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"


def test_login_default_redirects_to_dashboard_and_rejects_external_next(client):
    register_user(client)

    response = login_user(client)
    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"

    token = csrf_token(client, "/login?next=https://evil.example/phish")
    response = client.post(
        "/login?next=https://evil.example/phish",
        data={"csrf_token": token, "account": "alice", "password": "password123"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"


def test_navbar_logged_out_and_logged_in_states(client):
    logged_out = client.get("/")

    assert "登录".encode("utf-8") in logged_out.data
    assert "注册".encode("utf-8") in logged_out.data
    assert "退出登录".encode("utf-8") not in logged_out.data

    login_as_new_user(client, "alice", "alice@example.com")
    logged_in = client.get("/dashboard")

    assert "仪表盘".encode("utf-8") in logged_in.data
    assert "退出登录".encode("utf-8") in logged_in.data
    assert 'href="/login"'.encode("utf-8") not in logged_in.data
    assert 'href="/register"'.encode("utf-8") not in logged_in.data


def test_support_remains_public(client):
    response = client.get("/support")

    assert response.status_code == 200
    assert "支持 Easy Kakeibo".encode("utf-8") in response.data


def test_landing_page_renders_chinese_and_japanese(client):
    chinese = client.get("/?lang=zh-CN")
    japanese = client.get("/?lang=ja")

    assert chinese.status_code == 200
    assert "轻松记录每一笔收支".encode("utf-8") in chinese.data
    assert japanese.status_code == 200
    assert "収支をかんたんに記録".encode("utf-8") in japanese.data


def test_existing_user_data_pages_still_require_login(client):
    for path in ("/dashboard", "/records", "/records/add", "/statistics", "/budgets", "/settings"):
        response = client.get(path)
        assert response.status_code == 302
        assert urlparse(response.headers["Location"]).path == "/login"

    for path in ("/api/records", "/api/summary", "/api/analytics"):
        response = client.get(path)
        assert response.status_code == 401


def test_no_redirect_loop_for_public_and_auth_entry_points(client):
    for path in ("/", "/login", "/register", "/support"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 200


def test_landing_template_static_assets_resolve(client):
    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/static/css/styles.css"'.encode("utf-8") in response.data
    assert 'src="/static/js/common.js"'.encode("utf-8") in response.data
    assert b"https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" in response.data


def test_landing_dark_mode_theme_styles_are_present(client):
    page = client.get("/")
    css = client.get("/static/css/styles.css")

    assert page.status_code == 200
    assert b"sticky-top" not in page.data
    assert css.status_code == 200
    stylesheet = css.get_data(as_text=True)
    assert "--text-primary: #f4f7fc" in stylesheet
    assert "--text-secondary: #c4cede" in stylesheet
    assert "--text-muted: #94a3b8" in stylesheet
    assert "--surface: #172033" in stylesheet
    assert "--surface-secondary: #1d2940" in stylesheet
    assert "--border-color: #34445e" in stylesheet
    assert ".text-muted" in stylesheet
    assert "color: var(--text-muted) !important" in stylesheet
