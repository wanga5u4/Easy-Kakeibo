from conftest import login_as_new_user


DONATION_IMAGE = "wechat-donation.jpg"
RECENT_VERSIONS = ("v0.6.2", "v0.6.1", "v0.6.0", "v0.5.2")
OLDER_VERSIONS = ("v0.5.1", "v0.5.0", "v0.4.0")


def test_support_page_accessible_without_login(client):
    response = client.get("/support")

    assert response.status_code == 200
    assert "支持 Easy Kakeibo".encode("utf-8") in response.data
    assert 'href="/support"'.encode("utf-8") in response.data
    assert "支持与计划".encode("utf-8") in response.data
    assert b"Premium" not in response.data


def test_support_page_shows_wechat_donation_for_public_users(client):
    response = client.get("/support")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "微信赞赏" in page
    assert "请使用微信扫一扫" in page
    assert f"/static/images/{DONATION_IMAGE}" in page
    assert "赞助预留区域" not in page
    assert "支付成功" not in page
    assert "我已支付" not in page
    assert "赞助完成" not in page
    assert "以下记录来自当前仓库 Git 提交记录和 README 中已有功能描述。" not in page


def test_support_page_groups_version_history(client):
    response = client.get("/support")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    for version in RECENT_VERSIONS:
        assert version in page
    assert '<details class="version-history-older mt-3">' in page
    assert "<summary>" in page
    assert "查看更早版本" in page
    older_section = page.split('<details class="version-history-older mt-3">', 1)[1]
    older_section = older_section.split("</details>", 1)[0]
    for version in OLDER_VERSIONS:
        assert version in older_section


def test_support_page_shows_project_status(client):
    response = client.get("/support")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "当前版本 v0.6.2" in page
    assert "免费测试中" in page
    assert "Easy Kakeibo 仍在持续开发中" in page
    assert "当前版本：" in page
    assert "项目状态：" in page
    assert "最后更新：" in page
    assert "2026年7月" in page


def test_support_page_keeps_feedback_and_share_entry_logic(client):
    response = client.get("/support")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'href="/login?next=/feedback"' in page
    assert 'href="/share"' not in page
    assert "报告使用问题，或告诉我们你希望加入的功能。" in page
    assert "可以复制链接分享给朋友" in page
    assert "通过微信赞赏支持服务器、域名和持续开发。" in page


def test_support_page_accessible_when_logged_in(client):
    login_as_new_user(client, "alice", "alice@example.com")

    response = client.get("/support")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "支持 Easy Kakeibo" in page
    assert "欢迎，alice" in page
    assert 'href="/feedback"' in page
    assert 'href="/share"' in page


def test_feedback_and_share_routes_still_require_login(client):
    feedback_response = client.get("/feedback")
    share_response = client.get("/share")

    assert feedback_response.status_code == 302
    assert "/login" in feedback_response.headers["Location"]
    assert share_response.status_code == 302
    assert "/login" in share_response.headers["Location"]


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
