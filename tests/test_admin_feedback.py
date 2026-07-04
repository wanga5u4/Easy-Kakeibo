from conftest import csrf_token, login_as_new_user, login_user, logout_user
from test_admin_auth import make_admin


def feedback_id_for(app_module, title):
    with app_module.get_connection() as conn:
        return conn.execute(
            "SELECT id FROM feedback WHERE title = ?",
            (title,),
        ).fetchone()["id"]


def submit_feedback(client, title="<script>alert(1)</script>", content="<b>bad</b>"):
    token = csrf_token(client, "/feedback")
    response = client.post(
        "/feedback",
        data={
            "csrf_token": token,
            "feedback_type": "feature",
            "title": title,
            "content": content,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302


def setup_admin_feedback(app_module, client):
    login_as_new_user(client, "admin", "admin@example.com")
    make_admin(app_module, "admin")
    logout_user(client)
    login_as_new_user(client, "alice", "alice@example.com")
    submit_feedback(client)
    logout_user(client)
    assert login_user(client, "admin").status_code == 302


def post_feedback_admin(client, feedback_id, status="reviewing", admin_note="checking"):
    token = csrf_token(client, f"/admin/feedback/{feedback_id}")
    return client.post(
        f"/admin/feedback/{feedback_id}",
        data={
            "csrf_token": token,
            "status": status,
            "admin_note": admin_note,
        },
        follow_redirects=False,
    )


def test_admin_feedback_list_filter_and_detail_escapes_html(app_module, client):
    setup_admin_feedback(app_module, client)
    feedback_id = feedback_id_for(app_module, "<script>alert(1)</script>")

    response = client.get("/admin/feedback?status=new")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<script>alert(1)</script>" not in page

    response = client.get(f"/admin/feedback/{feedback_id}")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "&lt;b&gt;bad&lt;/b&gt;" in page
    assert "<b>bad</b>" not in page


def test_admin_can_update_feedback_status_note_and_logs(app_module, client):
    setup_admin_feedback(app_module, client)
    feedback_id = feedback_id_for(app_module, "<script>alert(1)</script>")

    response = post_feedback_admin(
        client,
        feedback_id,
        status="resolved",
        admin_note="done",
    )
    assert response.status_code == 302

    with app_module.get_connection() as conn:
        row = conn.execute(
            "SELECT status, admin_note, title, content FROM feedback WHERE id = ?",
            (feedback_id,),
        ).fetchone()
        assert row["status"] == "resolved"
        assert row["admin_note"] == "done"
        assert row["title"] == "<script>alert(1)</script>"
        assert row["content"] == "<b>bad</b>"
        log = conn.execute(
            "SELECT old_value, new_value, note FROM admin_audit_logs WHERE target_feedback_id = ?",
            (feedback_id,),
        ).fetchone()
        assert '"status":"new"' in log["old_value"]
        assert '"status":"resolved"' in log["new_value"]
        assert log["note"] == "done"


def test_feedback_admin_validation_missing_and_normal_user_denied(app_module, client):
    setup_admin_feedback(app_module, client)
    feedback_id = feedback_id_for(app_module, "<script>alert(1)</script>")

    assert post_feedback_admin(client, feedback_id, status="bad").status_code == 302
    assert client.get("/admin/feedback/9999").status_code == 404
    logout_user(client)
    assert login_user(client, "alice").status_code == 302

    token = csrf_token(client, f"/admin/feedback/{feedback_id}")
    response = client.post(
        f"/admin/feedback/{feedback_id}",
        data={"csrf_token": token, "status": "closed", "admin_note": "nope"},
    )
    assert response.status_code == 403

    with app_module.get_connection() as conn:
        status = conn.execute(
            "SELECT status FROM feedback WHERE id = ?",
            (feedback_id,),
        ).fetchone()["status"]
        assert status == "new"
