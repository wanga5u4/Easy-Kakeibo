from conftest import login_as_new_user


def test_support_page_accessible_without_login(client):
    response = client.get("/support")

    assert response.status_code == 200
    assert "支持 Easy Kakeibo".encode("utf-8") in response.data
    assert 'href="/support"'.encode("utf-8") in response.data
    assert "支持与计划".encode("utf-8") in response.data
    assert b"Premium" not in response.data


def test_support_page_accessible_when_logged_in(client):
    login_as_new_user(client, "alice", "alice@example.com")

    response = client.get("/support")

    assert response.status_code == 200
    assert "支持 Easy Kakeibo".encode("utf-8") in response.data
    assert "欢迎，alice".encode("utf-8") in response.data


def test_support_page_language_switch_to_japanese(client):
    response = client.get("/support?lang=ja")

    assert response.status_code == 200
    assert "Easy Kakeibo をサポート".encode("utf-8") in response.data
    assert "サポートと予定".encode("utf-8") in response.data


def test_legacy_vip_and_premium_redirect_to_support(client):
    for path in ("/vip", "/premium"):
        response = client.get(path)

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/support")


def test_support_page_has_responsive_layout_markers(client):
    response = client.get("/support")

    assert response.status_code == 200
    assert b'<meta name="viewport"' in response.data
    assert b"row g-4" in response.data
    assert b"col-lg-4" in response.data
    assert b"col-lg-8" in response.data
