import json
import math
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for, g
from flask_babel import gettext as _

from .decorators import admin_required


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

ADMIN_PER_PAGE = 20
ADMIN_MAX_PER_PAGE = 50
VIP_STATUSES = ("free", "vip")
ADMIN_FILTERS = ("all", "yes", "no")
FEEDBACK_STATUSES = ("new", "reviewing", "resolved", "closed")
FEEDBACK_STATUS_FILTERS = ("all",) + FEEDBACK_STATUSES
USER_SORTS = ("created_desc", "created_asc")
TIME_SORTS = ("created_desc", "created_asc")


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def timestamp_now():
    return utc_now().strftime("%Y-%m-%d %H:%M:%S")


def db_connection():
    from database import get_connection

    return get_connection()


def parse_page():
    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        return 1
    return max(page, 1)


def pagination(total, page, per_page=ADMIN_PER_PAGE):
    total_pages = max(math.ceil(total / per_page), 1) if total else 0
    if total_pages and page > total_pages:
        page = total_pages
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "offset": (page - 1) * per_page,
        "has_prev": page > 1,
        "has_next": bool(total_pages and page < total_pages),
    }


def query_args_without_page():
    args = request.args.to_dict(flat=True)
    args.pop("page", None)
    return args


def feedback_type_labels():
    return {
        "bug": _("Bug 报告"),
        "feature": _("功能建议"),
        "question": _("使用问题"),
        "other": _("其他"),
    }


def feedback_status_labels():
    return {
        "new": _("新建"),
        "reviewing": _("处理中"),
        "resolved": _("已解决"),
        "closed": _("已关闭"),
    }


def vip_status_labels():
    return {
        "free": _("免费版"),
        "vip": _("VIP 测试权限"),
    }


def admin_filter_labels():
    return {
        "all": _("全部"),
        "yes": _("管理员"),
        "no": _("普通用户"),
    }


def account_status_label(user):
    return _("启用") if user["is_active"] else _("停用")


def truncate_text(value, length=80):
    text = value or ""
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "..."


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_audit_log(
    conn,
    action,
    old_value=None,
    new_value=None,
    note="",
    target_user_id=None,
    target_feedback_id=None,
):
    conn.execute(
        """
        INSERT INTO admin_audit_logs (
            admin_user_id, target_user_id, target_feedback_id,
            action, old_value, new_value, note, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            g.admin_user["id"],
            target_user_id,
            target_feedback_id,
            action,
            compact_json(old_value) if old_value is not None else None,
            compact_json(new_value) if new_value is not None else None,
            note.strip()[:500] if note else None,
            timestamp_now(),
        ),
    )


def parse_vip_expires_at(value):
    text = (value or "").strip()
    if not text:
        return None, None
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None, _("VIP 到期时间格式无效，请使用 YYYY-MM-DD。")
    return parsed.isoformat(), None


def get_user_or_404(conn, user_id):
    user = conn.execute(
        """
        SELECT id, username, email, nickname, language, currency, base_currency_code,
               plan, premium_until, created_at, is_admin, vip_status, vip_expires_at,
               last_login_at, is_active
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()
    if not user:
        abort(404)
    return user


def get_feedback_or_404(conn, feedback_id):
    feedback = conn.execute(
        """
        SELECT f.id, f.user_id, f.feedback_type, f.title, f.content, f.page_url,
               f.contact, f.status, f.admin_note, f.created_at, f.updated_at,
               u.username
        FROM feedback f
        LEFT JOIN users u ON u.id = f.user_id
        WHERE f.id = ?
        """,
        (feedback_id,),
    ).fetchone()
    if not feedback:
        abort(404)
    return feedback


@admin_bp.get("")
@admin_bp.get("/")
@admin_required
def dashboard():
    today = utc_now().date().isoformat()
    seven_days_ago = (utc_now() - timedelta(days=6)).date().isoformat()
    with db_connection() as conn:
        stats = {
            "total_users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "today_users": conn.execute(
                "SELECT COUNT(*) FROM users WHERE date(created_at) = ?",
                (today,),
            ).fetchone()[0],
            "week_users": conn.execute(
                "SELECT COUNT(*) FROM users WHERE date(created_at) >= ?",
                (seven_days_ago,),
            ).fetchone()[0],
            "vip_users": conn.execute(
                "SELECT COUNT(*) FROM users WHERE vip_status = 'vip'"
            ).fetchone()[0],
            "total_feedback": conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0],
            "open_feedback": conn.execute(
                "SELECT COUNT(*) FROM feedback WHERE status IN ('new', 'reviewing')"
            ).fetchone()[0],
        }
        recent_users = conn.execute(
            """
            SELECT id, username, created_at, vip_status
            FROM users
            ORDER BY created_at DESC, id DESC
            LIMIT 8
            """
        ).fetchall()
        recent_feedback = conn.execute(
            """
            SELECT f.id, f.feedback_type, f.title, f.content, f.status, f.created_at,
                   u.username
            FROM feedback f
            LEFT JOIN users u ON u.id = f.user_id
            ORDER BY f.created_at DESC, f.id DESC
            LIMIT 8
            """
        ).fetchall()

    return render_template(
        "admin/dashboard.html",
        active_page="admin_dashboard",
        stats=stats,
        recent_users=recent_users,
        recent_feedback=recent_feedback,
        feedback_type_labels=feedback_type_labels(),
        feedback_status_labels=feedback_status_labels(),
        vip_status_labels=vip_status_labels(),
        truncate_text=truncate_text,
    )


@admin_bp.get("/users")
@admin_required
def users():
    page = parse_page()
    search = (request.args.get("q") or "").strip()[:80]
    vip_status = (request.args.get("vip_status") or "all").strip()
    admin_filter = (request.args.get("is_admin") or "all").strip()
    sort = (request.args.get("sort") or "created_desc").strip()
    if vip_status not in ("all",) + VIP_STATUSES:
        vip_status = "all"
    if admin_filter not in ADMIN_FILTERS:
        admin_filter = "all"
    if sort not in USER_SORTS:
        sort = "created_desc"

    where = []
    params = []
    if search:
        where.append("username LIKE ?")
        params.append(f"%{search}%")
    if vip_status != "all":
        where.append("vip_status = ?")
        params.append(vip_status)
    if admin_filter != "all":
        where.append("is_admin = ?")
        params.append(1 if admin_filter == "yes" else 0)

    where_sql = " WHERE " + " AND ".join(where) if where else ""
    order_sql = "created_at ASC, id ASC" if sort == "created_asc" else "created_at DESC, id DESC"

    with db_connection() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM users{where_sql}", params).fetchone()[0]
        pager = pagination(total, page)
        rows = conn.execute(
            f"""
            SELECT id, username, created_at, last_login_at, language, currency,
                   base_currency_code, vip_status, vip_expires_at, is_active, is_admin
            FROM users
            {where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
            """,
            params + [pager["per_page"], pager["offset"]],
        ).fetchall()

    return render_template(
        "admin/users.html",
        active_page="admin_users",
        users=rows,
        filters={
            "q": search,
            "vip_status": vip_status,
            "is_admin": admin_filter,
            "sort": sort,
        },
        pagination=pager,
        query_args=query_args_without_page(),
        vip_status_labels=vip_status_labels(),
        admin_filter_labels=admin_filter_labels(),
        account_status_label=account_status_label,
    )


@admin_bp.route("/users/<int:user_id>", methods=["GET", "POST"])
@admin_required
def user_detail(user_id):
    with db_connection() as conn:
        user = get_user_or_404(conn, user_id)

        if request.method == "POST":
            vip_status = (request.form.get("vip_status") or "").strip()
            vip_expires_at, date_error = parse_vip_expires_at(
                request.form.get("vip_expires_at")
            )
            note = (request.form.get("admin_note") or "").strip()
            if vip_status not in VIP_STATUSES:
                flash(_("VIP 状态无效。"), "error")
                return redirect(url_for("admin.user_detail", user_id=user_id))
            if date_error:
                flash(date_error, "error")
                return redirect(url_for("admin.user_detail", user_id=user_id))

            old_value = {
                "vip_status": user["vip_status"],
                "vip_expires_at": user["vip_expires_at"],
            }
            new_value = {
                "vip_status": vip_status,
                "vip_expires_at": vip_expires_at,
            }
            conn.execute(
                """
                UPDATE users
                SET vip_status = ?, vip_expires_at = ?
                WHERE id = ?
                """,
                (vip_status, vip_expires_at, user_id),
            )
            if old_value != new_value:
                write_audit_log(
                    conn,
                    "vip_test_permission_updated",
                    old_value=old_value,
                    new_value=new_value,
                    note=note,
                    target_user_id=user_id,
                )
            conn.commit()
            flash(_("VIP 测试权限已更新。"), "success")
            return redirect(url_for("admin.user_detail", user_id=user_id))

        audit_logs = conn.execute(
            """
            SELECT l.*, u.username AS admin_username
            FROM admin_audit_logs l
            LEFT JOIN users u ON u.id = l.admin_user_id
            WHERE l.target_user_id = ?
              AND l.action = 'vip_test_permission_updated'
            ORDER BY l.created_at DESC, l.id DESC
            LIMIT 10
            """,
            (user_id,),
        ).fetchall()

    return render_template(
        "admin/user_detail.html",
        active_page="admin_users",
        user=user,
        audit_logs=audit_logs,
        vip_status_labels=vip_status_labels(),
        account_status_label=account_status_label,
    )


@admin_bp.get("/feedback")
@admin_required
def feedback():
    page = parse_page()
    status = (request.args.get("status") or "all").strip()
    sort = (request.args.get("sort") or "created_desc").strip()
    if status not in FEEDBACK_STATUS_FILTERS:
        status = "all"
    if sort not in TIME_SORTS:
        sort = "created_desc"
    where = ""
    params = []
    if status != "all":
        where = " WHERE f.status = ?"
        params.append(status)
    order_sql = "f.created_at ASC, f.id ASC" if sort == "created_asc" else "f.created_at DESC, f.id DESC"

    with db_connection() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM feedback f{where}",
            params,
        ).fetchone()[0]
        pager = pagination(total, page)
        rows = conn.execute(
            f"""
            SELECT f.id, f.feedback_type, f.title, f.content, f.status,
                   f.created_at, u.username
            FROM feedback f
            LEFT JOIN users u ON u.id = f.user_id
            {where}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
            """,
            params + [pager["per_page"], pager["offset"]],
        ).fetchall()

    return render_template(
        "admin/feedback.html",
        active_page="admin_feedback",
        feedback_items=rows,
        filters={"status": status, "sort": sort},
        pagination=pager,
        query_args=query_args_without_page(),
        feedback_type_labels=feedback_type_labels(),
        feedback_status_labels=feedback_status_labels(),
        truncate_text=truncate_text,
    )


@admin_bp.route("/feedback/<int:feedback_id>", methods=["GET", "POST"])
@admin_required
def feedback_detail(feedback_id):
    with db_connection() as conn:
        feedback_item = get_feedback_or_404(conn, feedback_id)
        if request.method == "POST":
            status = (request.form.get("status") or "").strip()
            admin_note = (request.form.get("admin_note") or "").strip()
            if status not in FEEDBACK_STATUSES:
                flash(_("反馈状态无效。"), "error")
                return redirect(url_for("admin.feedback_detail", feedback_id=feedback_id))
            if len(admin_note) > 2000:
                flash(_("管理员备注不能超过 2000 个字符。"), "error")
                return redirect(url_for("admin.feedback_detail", feedback_id=feedback_id))

            old_value = {
                "status": feedback_item["status"],
                "admin_note": feedback_item["admin_note"],
            }
            new_value = {
                "status": status,
                "admin_note": admin_note,
            }
            conn.execute(
                """
                UPDATE feedback
                SET status = ?, admin_note = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, admin_note, timestamp_now(), feedback_id),
            )
            if old_value != new_value:
                write_audit_log(
                    conn,
                    "feedback_management_updated",
                    old_value=old_value,
                    new_value=new_value,
                    note=admin_note,
                    target_user_id=feedback_item["user_id"],
                    target_feedback_id=feedback_id,
                )
            conn.commit()
            flash(_("反馈处理状态已更新。"), "success")
            return redirect(url_for("admin.feedback_detail", feedback_id=feedback_id))

        audit_logs = conn.execute(
            """
            SELECT l.*, u.username AS admin_username
            FROM admin_audit_logs l
            LEFT JOIN users u ON u.id = l.admin_user_id
            WHERE l.target_feedback_id = ?
            ORDER BY l.created_at DESC, l.id DESC
            LIMIT 10
            """,
            (feedback_id,),
        ).fetchall()

    return render_template(
        "admin/feedback_detail.html",
        active_page="admin_feedback",
        feedback_item=feedback_item,
        audit_logs=audit_logs,
        feedback_type_labels=feedback_type_labels(),
        feedback_status_labels=feedback_status_labels(),
    )


@admin_bp.get("/audit-logs")
@admin_required
def audit_logs():
    page = parse_page()
    with db_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM admin_audit_logs").fetchone()[0]
        pager = pagination(total, page, ADMIN_MAX_PER_PAGE)
        rows = conn.execute(
            """
            SELECT l.*, au.username AS admin_username, tu.username AS target_username
            FROM admin_audit_logs l
            LEFT JOIN users au ON au.id = l.admin_user_id
            LEFT JOIN users tu ON tu.id = l.target_user_id
            ORDER BY l.created_at DESC, l.id DESC
            LIMIT ? OFFSET ?
            """,
            (pager["per_page"], pager["offset"]),
        ).fetchall()

    return render_template(
        "admin/audit_logs.html",
        active_page="admin_audit_logs",
        audit_logs=rows,
        pagination=pager,
        query_args=query_args_without_page(),
    )
