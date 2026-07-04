from conftest import csrf_token, login_as_new_user, login_user, logout_user
from test_admin_auth import make_admin


def test_audit_logs_are_admin_only_and_render_missing_targets(app_module, client):
    login_as_new_user(client, "admin", "admin@example.com")
    make_admin(app_module, "admin")
    logout_user(client)
    login_as_new_user(client, "alice", "alice@example.com")
    logout_user(client)

    assert login_user(client, "admin").status_code == 302
    with app_module.get_connection() as conn:
        admin_id = conn.execute(
            "SELECT id FROM users WHERE username = 'admin'"
        ).fetchone()["id"]
        alice_id = conn.execute(
            "SELECT id FROM users WHERE username = 'alice'"
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO admin_audit_logs (
                admin_user_id, target_user_id, action, old_value, new_value, note
            )
            VALUES (?, ?, 'vip_test_permission_updated', '{"vip_status":"free"}', '{"vip_status":"vip"}', 'manual')
            """,
            (admin_id, alice_id),
        )
        conn.execute("DELETE FROM users WHERE id = ?", (alice_id,))
        conn.commit()

    response = client.get("/admin/audit-logs")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "vip_test_permission_updated" in page
    assert "用户不存在" in page
    assert "password_hash" not in page
    assert "SECRET_KEY" not in page


def test_audit_logs_normal_user_forbidden(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    response = client.get("/admin/audit-logs")
    assert response.status_code == 403


def test_feedback_get_request_does_not_modify_status(app_module, client):
    login_as_new_user(client, "admin", "admin@example.com")
    make_admin(app_module, "admin")
    token = csrf_token(client, "/feedback")
    client.post(
        "/feedback",
        data={
            "csrf_token": token,
            "feedback_type": "bug",
            "title": "No GET mutation",
            "content": "Feedback body",
        },
    )
    feedback_id = None
    with app_module.get_connection() as conn:
        feedback_id = conn.execute(
            "SELECT id FROM feedback WHERE title = 'No GET mutation'"
        ).fetchone()["id"]

    response = client.get(f"/admin/feedback/{feedback_id}?status=closed")
    assert response.status_code == 200
    with app_module.get_connection() as conn:
        status = conn.execute(
            "SELECT status FROM feedback WHERE id = ?",
            (feedback_id,),
        ).fetchone()["status"]
        assert status == "new"
