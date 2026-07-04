from conftest import login_user, register_user


def test_successful_login_updates_last_login_at(app_module, client):
    assert register_user(client, "alice", "alice@example.com").status_code == 302

    with app_module.get_connection() as conn:
        assert conn.execute(
            "SELECT last_login_at FROM users WHERE username = 'alice'"
        ).fetchone()["last_login_at"] is None

    assert login_user(client, "alice").status_code == 302

    with app_module.get_connection() as conn:
        assert conn.execute(
            "SELECT last_login_at FROM users WHERE username = 'alice'"
        ).fetchone()["last_login_at"] is not None


def test_failed_login_does_not_update_last_login_at(app_module, client):
    assert register_user(client, "alice", "alice@example.com").status_code == 302

    assert login_user(client, "alice", "wrong-password").status_code == 400

    with app_module.get_connection() as conn:
        assert conn.execute(
            "SELECT last_login_at FROM users WHERE username = 'alice'"
        ).fetchone()["last_login_at"] is None
