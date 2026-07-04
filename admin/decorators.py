from functools import wraps

from flask import abort, g, redirect, request, session, url_for


def _safe_admin_next():
    next_url = request.full_path.rstrip("?")
    if not next_url.startswith("/") or next_url.startswith("//"):
        return ""
    return next_url


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("login", next=_safe_admin_next()))

        from database import get_connection

        with get_connection() as conn:
            user = conn.execute(
                """
                SELECT id, username, is_admin, is_active
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()

        if not user:
            session.clear()
            return redirect(url_for("login", next=_safe_admin_next()))
        if not user["is_active"] or not user["is_admin"]:
            abort(403)

        g.admin_user = user
        return view_func(*args, **kwargs)

    return wrapped
