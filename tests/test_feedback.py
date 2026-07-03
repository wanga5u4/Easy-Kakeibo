from conftest import csrf_token, login_as_new_user, logout_user


def post_feedback(client, **overrides):
    data = {
        "csrf_token": csrf_token(client, "/feedback"),
        "feedback_type": "bug",
        "title": "Bug title",
        "content": "Something is not working.",
        "page_url": "/records",
        "contact": "alice@example.com",
    }
    data.update(overrides)
    return client.post("/feedback", data=data, follow_redirects=False)


def user_id_for(app_module, username):
    with app_module.get_connection() as conn:
        return conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,),
        ).fetchone()["id"]


def feedback_rows(app_module):
    with app_module.get_connection() as conn:
        return conn.execute(
            "SELECT * FROM feedback ORDER BY created_at DESC, id DESC"
        ).fetchall()


def test_feedback_requires_login(client):
    response = client.get("/feedback")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]

    token = csrf_token(client, "/login")
    response = client.post(
        "/feedback",
        data={
            "csrf_token": token,
            "feedback_type": "bug",
            "title": "Bug title",
            "content": "Something is broken.",
        },
    )
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_logged_in_user_can_access_and_submit_feedback(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")

    response = client.get("/feedback")
    assert response.status_code == 200
    assert "反馈与建议".encode("utf-8") in response.data

    response = post_feedback(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/feedback")

    rows = feedback_rows(app_module)
    assert len(rows) == 1
    assert rows[0]["feedback_type"] == "bug"
    assert rows[0]["status"] == "new"

    client.get("/feedback")
    assert len(feedback_rows(app_module)) == 1


def test_feedback_validation_errors(client):
    login_as_new_user(client, "alice", "alice@example.com")

    assert post_feedback(client, title="").status_code == 400
    assert post_feedback(client, content="").status_code == 400
    assert post_feedback(client, title="A" * 101).status_code == 400
    assert post_feedback(client, content="A" * 2001).status_code == 400
    assert post_feedback(client, feedback_type="invalid").status_code == 400
    assert post_feedback(client, page_url="A" * 201).status_code == 400
    assert post_feedback(client, contact="A" * 121).status_code == 400


def test_feedback_user_id_comes_from_session(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    alice_id = user_id_for(app_module, "alice")
    logout_user(client)

    login_as_new_user(client, "bob", "bob@example.com")
    bob_id = user_id_for(app_module, "bob")

    response = post_feedback(client, user_id=str(alice_id), title="Bob feedback")
    assert response.status_code == 302

    rows = feedback_rows(app_module)
    assert rows[0]["user_id"] == bob_id
    assert rows[0]["user_id"] != alice_id


def test_users_only_see_own_recent_feedback(app_module, client):
    login_as_new_user(client, "alice", "alice@example.com")
    post_feedback(client, title="Alice private feedback")
    logout_user(client)

    login_as_new_user(client, "bob", "bob@example.com")
    page = client.get("/feedback").get_data(as_text=True)
    assert "Alice private feedback" not in page
    assert "你还没有提交过反馈。" in page


def test_recent_feedback_limited_to_10_and_descending(client):
    login_as_new_user(client, "alice", "alice@example.com")
    for index in range(12):
        response = post_feedback(
            client,
            title=f"Feedback {index:02d}",
            content=f"Content for feedback {index:02d}",
        )
        assert response.status_code == 302

    page = client.get("/feedback").get_data(as_text=True)
    assert "Feedback 11" in page
    assert "Feedback 10" in page
    assert "Feedback 01" not in page
    assert "Feedback 00" not in page
    assert page.index("Feedback 11") < page.index("Feedback 10")


def test_feedback_html_is_escaped(client):
    login_as_new_user(client, "alice", "alice@example.com")
    response = post_feedback(
        client,
        title="<script>alert(1)</script>",
        content="<script>alert(2)</script> details",
    )
    assert response.status_code == 302

    page = client.get("/feedback").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<script>alert(2)</script>" not in page
