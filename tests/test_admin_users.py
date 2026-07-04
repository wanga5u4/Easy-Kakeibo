from conftest import csrf_token, login_as_new_user, login_user, logout_user
from test_admin_auth import make_admin


def user_id_for(app_module, username):
    with app_module.get_connection() as conn:
        return conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,),
        ).fetchone()["id"]


def setup_admin_and_users(app_module, client):
    login_as_new_user(client, "admin", "admin@example.com")
    make_admin(app_module, "admin")
    logout_user(client)
    login_as_new_user(client, "alice", "alice@example.com")
    logout_user(client)
    login_as_new_user(client, "bob", "bob@example.com")
    logout_user(client)
    with app_module.get_connection() as conn:
        conn.execute("UPDATE users SET vip_status = 'vip' WHERE username = 'bob'")
        conn.commit()
    assert login_user(client, "admin").status_code == 302


def post_vip(client, user_id, vip_status="vip", vip_expires_at="", note="test"):
    token = csrf_token(client, f"/admin/users/{user_id}")
    return client.post(
        f"/admin/users/{user_id}",
        data={
            "csrf_token": token,
            "vip_status": vip_status,
            "vip_expires_at": vip_expires_at,
            "admin_note": note,
        },
        follow_redirects=False,
    )


def test_user_list_search_filters_and_invalid_page(app_module, client):
    setup_admin_and_users(app_module, client)

    response = client.get("/admin/users?q=ali")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "alice" in page
    assert "bob" not in page
    assert "password_hash" not in page

    response = client.get("/admin/users?vip_status=vip")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "bob" in page
    assert "alice" not in page

    response = client.get("/admin/users?page=not-a-number")
    assert response.status_code == 200


def test_user_detail_missing_returns_404(app_module, client):
    setup_admin_and_users(app_module, client)
    assert client.get("/admin/users/9999").status_code == 404


def test_admin_can_update_and_cancel_vip_with_audit_log(app_module, client):
    setup_admin_and_users(app_module, client)
    alice_id = user_id_for(app_module, "alice")

    response = post_vip(
        client,
        alice_id,
        vip_status="vip",
        vip_expires_at="2026-12-31",
        note="trial",
    )
    assert response.status_code == 302
    with app_module.get_connection() as conn:
        user = conn.execute(
            "SELECT vip_status, vip_expires_at FROM users WHERE id = ?",
            (alice_id,),
        ).fetchone()
        assert user["vip_status"] == "vip"
        assert user["vip_expires_at"] == "2026-12-31"
        log = conn.execute(
            "SELECT old_value, new_value, note FROM admin_audit_logs WHERE target_user_id = ?",
            (alice_id,),
        ).fetchone()
        assert '"vip_status":"free"' in log["old_value"]
        assert '"vip_status":"vip"' in log["new_value"]
        assert log["note"] == "trial"

    response = post_vip(client, alice_id, vip_status="free", vip_expires_at="")
    assert response.status_code == 302
    with app_module.get_connection() as conn:
        user = conn.execute(
            "SELECT vip_status, vip_expires_at FROM users WHERE id = ?",
            (alice_id,),
        ).fetchone()
        assert user["vip_status"] == "free"
        assert user["vip_expires_at"] is None


def test_vip_update_validation_and_method(app_module, client):
    setup_admin_and_users(app_module, client)
    alice_id = user_id_for(app_module, "alice")

    assert post_vip(client, alice_id, vip_status="paid").status_code == 302
    assert post_vip(client, alice_id, vip_status="vip", vip_expires_at="2026/12/31").status_code == 302
    assert client.get(f"/admin/users/{alice_id}?vip_status=vip").status_code == 200

    with app_module.get_connection() as conn:
        user = conn.execute(
            "SELECT vip_status, vip_expires_at FROM users WHERE id = ?",
            (alice_id,),
        ).fetchone()
        assert user["vip_status"] == "free"
        assert user["vip_expires_at"] is None


def test_normal_user_cannot_post_vip_update(app_module, client):
    setup_admin_and_users(app_module, client)
    alice_id = user_id_for(app_module, "alice")
    logout_user(client)
    assert login_user(client, "alice").status_code == 302

    token = csrf_token(client, f"/admin/users/{alice_id}")
    response = client.post(
        f"/admin/users/{alice_id}",
        data={"csrf_token": token, "vip_status": "vip", "vip_expires_at": ""},
    )

    assert response.status_code == 403
