from conftest import csrf_token, login_as_new_user, login_user, logout_user
from test_admin_auth import make_admin


def submit_feedback(client, title, status="new"):
    token = csrf_token(client, "/feedback")
    response = client.post(
        "/feedback",
        data={
            "csrf_token": token,
            "feedback_type": "bug",
            "title": title,
            "content": "Feedback body",
        },
    )
    assert response.status_code == 302


def test_admin_dashboard_statistics(app_module, client):
    login_as_new_user(client, "admin", "admin@example.com")
    make_admin(app_module, "admin")
    logout_user(client)
    login_as_new_user(client, "alice", "alice@example.com")
    submit_feedback(client, "Alice new feedback")
    logout_user(client)
    login_as_new_user(client, "bob", "bob@example.com")
    submit_feedback(client, "Bob resolved feedback")
    logout_user(client)

    with app_module.get_connection() as conn:
        conn.execute("UPDATE users SET created_at = '2026-07-04 10:00:00' WHERE username = 'alice'")
        conn.execute("UPDATE users SET created_at = '2026-07-01 10:00:00' WHERE username = 'bob'")
        conn.execute("UPDATE users SET created_at = '2026-06-01 10:00:00' WHERE username = 'admin'")
        conn.execute("UPDATE users SET vip_status = 'vip' WHERE username = 'bob'")
        conn.execute("UPDATE feedback SET status = 'resolved' WHERE title = 'Bob resolved feedback'")
        conn.commit()

    assert login_user(client, "admin").status_code == 302
    response = client.get("/admin")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "用户总数" in page
    assert "VIP 测试用户数" in page
    assert "未处理反馈数" in page
    assert "Alice new feedback" in page
    assert "Bob resolved feedback" in page
    assert "alice" in page
    assert "bob" in page
