import time
import uuid
import os
import secrets
import math
import re
from datetime import date, datetime
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_connection, init_db, row_to_dict

BASE_DIR = Path(__file__).parent

app = Flask(__name__, static_folder="static", static_url_path="/static")
APP_ENV = os.environ.get("APP_ENV", "development").lower()
secret_key = os.environ.get("SECRET_KEY")

if APP_ENV == "production" and not secret_key:
    raise RuntimeError(
        "SECRET_KEY is required in production. "
        "Set it as an environment variable before starting the application."
    )

if not secret_key:
    secret_key = "development-only-secret-key-change-me"
    print(
        "WARNING: Using a development SECRET_KEY. "
        "Set SECRET_KEY before deploying this application."
    )

app.config["SECRET_KEY"] = secret_key
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=APP_ENV == "production",
)
init_db()

LANGUAGE_OPTIONS = {
    "zh-CN": "简体中文",
    "en-US": "English",
}
CURRENCY_OPTIONS = {
    "CNY": "人民币 CNY",
    "USD": "美元 USD",
    "JPY": "日元 JPY",
    "EUR": "欧元 EUR",
}

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
ALLOWED_PER_PAGE = {10, 20, 50}
DEFAULT_PER_PAGE = 10
MEMBERSHIP_PLANS = {
    "free": {
        "name": "免费版",
        "price": "￥0",
        "features": ["多用户记账", "基础收支统计", "每月预算", "分类占比图"],
        "limits": ["高级统计、导出和 AI 分析暂未开放"],
    },
    "premium": {
        "name": "Premium",
        "price": "敬请期待",
        "features": ["高级统计", "数据导出", "自定义分类", "多账本", "AI 财务分析"],
        "limits": ["当前版本仅展示能力，不接入真实支付"],
    },
}


def normalize_email(value):
    return (value or "").strip().lower()


def is_valid_email(value):
    email = normalize_email(value)
    if not email or " " in email:
        return False
    if len(email) > 254:
        return False
    return bool(EMAIL_RE.match(email))


def parse_record_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_positive_amount(value, max_value=1_000_000_000):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(amount):
        return None
    if amount <= 0 or amount > max_value:
        return None
    return round(amount, 2)


def parse_pagination_args():
    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    if page < 1:
        page = 1

    try:
        per_page = int(request.args.get("per_page", DEFAULT_PER_PAGE))
    except (TypeError, ValueError):
        per_page = DEFAULT_PER_PAGE
    if per_page not in ALLOWED_PER_PAGE:
        per_page = DEFAULT_PER_PAGE

    return page, per_page


def validate_record_payload(data):
    errors = []

    parsed_date = parse_record_date(data.get("date", ""))
    if not parsed_date:
        errors.append("日期格式无效")

    record_type = data.get("type", "")
    if record_type not in ("income", "expense"):
        errors.append("类型必须是 income 或 expense")

    category = (data.get("category") or "").strip()
    if not category:
        errors.append("分类不能为空")

    amount = parse_positive_amount(data.get("amount"))
    if amount is None:
        errors.append("金额格式无效")

    if errors:
        return None, errors

    return {
        "date": parsed_date.isoformat(),
        "type": record_type,
        "category": category,
        "amount": amount,
        "note": (data.get("note") or "").strip(),
    }, None


def validate_register_payload(form):
    errors = []
    username = (form.get("username") or "").strip()
    email = normalize_email(form.get("email"))
    password = form.get("password") or ""
    confirm_password = form.get("confirm_password") or ""

    if not username:
        errors.append("用户名不能为空")

    if not email:
        errors.append("邮箱不能为空")
    elif not is_valid_email(email):
        errors.append("邮箱格式无效")

    if len(password) < 8:
        errors.append("密码至少需要 8 位")

    if password != confirm_password:
        errors.append("两次输入的密码不一致")

    return {
        "username": username,
        "email": email,
        "password": password,
    }, errors


def validate_login_payload(form):
    errors = []
    account = (form.get("account") or "").strip()
    password = form.get("password") or ""

    if not account:
        errors.append("用户名或邮箱不能为空")

    if not password:
        errors.append("密码不能为空")

    return {
        "account": account,
        "password": password,
    }, errors


def validate_settings_payload(form):
    errors = []
    nickname = (form.get("nickname") or "").strip()
    language = (form.get("language") or "zh-CN").strip()
    currency = (form.get("currency") or "CNY").strip()
    current_password = form.get("current_password") or ""
    new_password = form.get("new_password") or ""
    confirm_password = form.get("confirm_password") or ""

    if len(nickname) > 30:
        errors.append("昵称不能超过 30 个字符")

    if language not in LANGUAGE_OPTIONS:
        errors.append("语言选项无效")

    if currency not in CURRENCY_OPTIONS:
        errors.append("货币选项无效")

    wants_password_change = any([current_password, new_password, confirm_password])
    if wants_password_change:
        if not current_password:
            errors.append("请输入当前密码")
        if len(new_password) < 8:
            errors.append("新密码至少需要 8 位")
        if new_password != confirm_password:
            errors.append("两次输入的新密码不一致")

    return {
        "nickname": nickname,
        "language": language,
        "currency": currency,
        "current_password": current_password,
        "new_password": new_password,
        "wants_password_change": wants_password_change,
    }, errors


def wants_json_response():
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


def get_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf_token():
    expected_token = session.get("_csrf_token")
    provided_token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
    return bool(expected_token and provided_token and secrets.compare_digest(expected_token, provided_token))


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": get_csrf_token}


@app.before_request
def protect_csrf():
    if request.method not in UNSAFE_METHODS:
        return None
    if validate_csrf_token():
        return None
    if wants_json_response():
        return jsonify({"ok": False, "error": "CSRF validation failed"}), 400
    return render_template(
        "message.html",
        active_page="",
        title="安全验证失败",
        message="请求已过期或安全验证失败，请刷新页面后重试。",
        action_url=url_for("index"),
        action_text="返回首页",
    ), 400


def render_error_response(status_code, message):
    if wants_json_response():
        return jsonify({"ok": False, "error": message}), status_code
    return render_template(
        "message.html",
        active_page="",
        title=f"{status_code} 错误",
        message=message,
        action_url=url_for("index"),
        action_text="返回首页",
    ), status_code


@app.errorhandler(400)
def handle_bad_request(error):
    return render_error_response(400, "请求无效，请检查输入后重试。")


@app.errorhandler(403)
def handle_forbidden(error):
    return render_error_response(403, "没有权限执行此操作。")


@app.errorhandler(404)
def handle_not_found(error):
    return render_error_response(404, "页面或资源不存在。")


@app.errorhandler(500)
def handle_server_error(error):
    return render_error_response(500, "服务器暂时无法处理请求，请稍后重试。")


def get_current_user_id():
    return session.get("user_id")


def get_current_user():
    user_id = get_current_user_id()
    if not user_id:
        return None

    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, username, email, password_hash, nickname, language,
                   currency, plan, premium_until, created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()


def user_has_feature(user, feature):
    if not user:
        return False
    if user["plan"] == "premium":
        return True
    return feature in {"basic_accounting", "basic_statistics", "monthly_budget"}


def require_login_json():
    if not get_current_user_id():
        return jsonify({"error": "请先登录"}), 401
    return None


def require_login_page():
    if not get_current_user_id():
        return redirect(url_for("login"))
    return None


def current_month():
    return date.today().strftime("%Y-%m")


def normalize_month(value):
    month = (value or "").strip()
    if not month:
        return current_month()
    if len(month) == 7 and month[4] == "-" and month[:4].isdigit() and month[5:].isdigit():
        month_num = int(month[5:])
        if 1 <= month_num <= 12:
            return month
    return None


def month_shift(month, offset):
    year = int(month[:4])
    month_num = int(month[5:]) + offset
    while month_num < 1:
        year -= 1
        month_num += 12
    while month_num > 12:
        year += 1
        month_num -= 12
    return f"{year:04d}-{month_num:02d}"


def get_budget_status(amount, used):
    if amount <= 0:
        return "未设置预算"
    percent = used / amount * 100
    if percent >= 100:
        return "已超出预算"
    if percent >= 80:
        return "预算即将用完"
    return "预算正常"


@app.context_processor
def inject_user_context():
    return {"current_user_profile": get_current_user()}


@app.route("/")
def index():
    if get_current_user_id():
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.get("/dashboard")
def dashboard():
    login_redirect = require_login_page()
    if login_redirect:
        return login_redirect
    return render_template("dashboard.html", active_page="dashboard")


@app.get("/records")
def records_page():
    login_redirect = require_login_page()
    if login_redirect:
        return login_redirect
    return render_template("records.html", active_page="records")


@app.get("/records/add")
def add_record_page():
    login_redirect = require_login_page()
    if login_redirect:
        return login_redirect
    return render_template("record_form.html", active_page="records", record_id=None)


@app.get("/records/<record_id>/edit")
def edit_record_page(record_id):
    login_redirect = require_login_page()
    if login_redirect:
        return login_redirect

    user_id = get_current_user_id()
    with get_connection() as conn:
        record = conn.execute(
            "SELECT id FROM records WHERE id = ? AND user_id = ?",
            (record_id, user_id),
        ).fetchone()

    if not record:
        return render_template(
            "message.html",
            active_page="records",
            title="记录不存在",
            message="这条记录不存在，或不属于当前登录用户。",
            action_url=url_for("records_page"),
            action_text="返回记录列表",
        ), 404

    return render_template("record_form.html", active_page="records", record_id=record_id)


@app.get("/statistics")
def statistics_page():
    login_redirect = require_login_page()
    if login_redirect:
        return login_redirect
    return render_template("statistics.html", active_page="statistics")


@app.get("/budgets")
def budgets_page():
    login_redirect = require_login_page()
    if login_redirect:
        return login_redirect
    return render_template("budgets.html", active_page="budgets")


@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    login_redirect = require_login_page()
    if login_redirect:
        return login_redirect

    user = get_current_user()
    if request.method == "GET":
        return render_template(
            "settings.html",
            active_page="settings",
            user=user,
            language_options=LANGUAGE_OPTIONS,
            currency_options=CURRENCY_OPTIONS,
            errors=[],
        )

    form_data, errors = validate_settings_payload(request.form)

    with get_connection() as conn:
        if form_data["wants_password_change"] and not check_password_hash(
            user["password_hash"],
            form_data["current_password"],
        ):
            errors.append("当前密码不正确")

        if errors:
            updated_user = dict(user)
            updated_user.update(
                {
                    "nickname": form_data["nickname"],
                    "language": form_data["language"],
                    "currency": form_data["currency"],
                }
            )
            return render_template(
                "settings.html",
                active_page="settings",
                user=updated_user,
                language_options=LANGUAGE_OPTIONS,
                currency_options=CURRENCY_OPTIONS,
                errors=errors,
            ), 400

        if form_data["wants_password_change"]:
            conn.execute(
                """
                UPDATE users
                SET nickname = ?, language = ?, currency = ?, password_hash = ?
                WHERE id = ?
                """,
                (
                    form_data["nickname"],
                    form_data["language"],
                    form_data["currency"],
                    generate_password_hash(form_data["new_password"]),
                    user["id"],
                ),
            )
        else:
            conn.execute(
                """
                UPDATE users
                SET nickname = ?, language = ?, currency = ?
                WHERE id = ?
                """,
                (
                    form_data["nickname"],
                    form_data["language"],
                    form_data["currency"],
                    user["id"],
                ),
            )
        conn.commit()

    flash("设置已保存", "success")
    return redirect(url_for("settings_page"))


@app.get("/premium")
def premium_page():
    login_redirect = require_login_page()
    if login_redirect:
        return login_redirect

    user = get_current_user()
    return render_template(
        "premium.html",
        active_page="premium",
        user=user,
        plans=MEMBERSHIP_PLANS,
        has_premium_features=user_has_feature(user, "advanced_statistics"),
    )


@app.get("/api/me")
def current_user():
    user_id = session.get("user_id")
    username = session.get("username")

    return jsonify(
        {
            "loggedIn": bool(user_id),
            "userId": user_id,
            "username": username,
        }
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", errors=[], form={})

    form_data, errors = validate_register_payload(request.form)

    with get_connection() as conn:
        if form_data["username"]:
            existing_username = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                (form_data["username"],),
            ).fetchone()
            if existing_username:
                errors.append("用户名已存在")

        if form_data["email"]:
            existing_email = conn.execute(
                "SELECT id FROM users WHERE lower(email) = lower(?)",
                (form_data["email"],),
            ).fetchone()
            if existing_email:
                errors.append("邮箱已存在")

        if errors:
            return render_template(
                "register.html",
                errors=errors,
                form=form_data,
            ), 400

        password_hash = generate_password_hash(form_data["password"])
        conn.execute(
            """
            INSERT INTO users (username, email, password_hash)
            VALUES (?, ?, ?)
            """,
            (
                form_data["username"],
                form_data["email"],
                password_hash,
            ),
        )
        conn.commit()

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", errors=[], form={})

    form_data, errors = validate_login_payload(request.form)

    user = None
    if not errors:
        with get_connection() as conn:
            user = conn.execute(
                """
                SELECT id, username, password_hash
                FROM users
                WHERE username = ? OR lower(email) = lower(?)
                """,
                (form_data["account"], form_data["account"]),
            ).fetchone()

        if not user or not check_password_hash(
            user["password_hash"],
            form_data["password"],
        ):
            errors.append("用户名/邮箱或密码错误")

    if errors:
        return render_template(
            "login.html",
            errors=errors,
            form=form_data,
        ), 400

    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]

    return redirect(url_for("dashboard"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/api/records")
def list_records():
    login_error = require_login_json()
    if login_error:
        return login_error

    user_id = get_current_user_id()
    record_type = request.args.get("type", "all")
    month = request.args.get("month", "").strip()
    page, per_page = parse_pagination_args()

    where_parts = ["user_id = ?"]
    params = [user_id]

    if record_type in ("income", "expense"):
        where_parts.append("type = ?")
        params.append(record_type)

    if month:
        where_parts.append("date LIKE ?")
        params.append(f"{month}%")

    where_sql = " AND ".join(where_parts)

    with get_connection() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM records WHERE {where_sql}",
            params,
        ).fetchone()[0]
        total_pages = max(math.ceil(total / per_page), 1)
        if page > total_pages:
            page = total_pages

        offset = (page - 1) * per_page
        rows = conn.execute(
            f"""
            SELECT *
            FROM records
            WHERE {where_sql}
            ORDER BY date DESC, created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()

    return jsonify(
        {
            "items": [row_to_dict(row) for row in rows],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages if total else 0,
                "has_prev": page > 1,
                "has_next": total > page * per_page,
            },
        }
    )


@app.get("/api/records/<record_id>")
def get_record(record_id):
    login_error = require_login_json()
    if login_error:
        return login_error

    user_id = get_current_user_id()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM records WHERE id = ? AND user_id = ?",
            (record_id, user_id),
        ).fetchone()

    if not row:
        return jsonify({"error": "记录不存在"}), 404

    return jsonify(row_to_dict(row))


@app.get("/api/summary")
def get_summary():
    login_error = require_login_json()
    if login_error:
        return login_error

    user_id = get_current_user_id()
    month = normalize_month(request.args.get("month"))
    if not month:
        return jsonify({"error": "月份格式无效"}), 400

    with get_connection() as conn:
        income = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM records
            WHERE user_id = ? AND type = 'income' AND date LIKE ?
            """,
            (user_id, f"{month}%"),
        ).fetchone()[0]
        expense = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM records
            WHERE user_id = ? AND type = 'expense' AND date LIKE ?
            """,
            (user_id, f"{month}%"),
        ).fetchone()[0]

    return jsonify(
        {
            "month": month,
            "totalIncome": income,
            "totalExpense": expense,
            "balance": income - expense,
        }
    )


@app.get("/api/analytics")
def get_analytics():
    login_error = require_login_json()
    if login_error:
        return login_error

    user_id = get_current_user_id()
    month = normalize_month(request.args.get("month"))
    if not month:
        return jsonify({"error": "月份格式无效"}), 400

    trend_months = [month_shift(month, offset) for offset in range(-5, 1)]

    with get_connection() as conn:
        income = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM records
            WHERE user_id = ? AND type = 'income' AND date LIKE ?
            """,
            (user_id, f"{month}%"),
        ).fetchone()[0]
        expense = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0)
            FROM records
            WHERE user_id = ? AND type = 'expense' AND date LIKE ?
            """,
            (user_id, f"{month}%"),
        ).fetchone()[0]
        category_rows = conn.execute(
            """
            SELECT category, COALESCE(SUM(amount), 0) AS amount
            FROM records
            WHERE user_id = ? AND type = 'expense' AND date LIKE ?
            GROUP BY category
            ORDER BY amount DESC
            """,
            (user_id, f"{month}%"),
        ).fetchall()
        trend_rows = conn.execute(
            """
            SELECT substr(date, 1, 7) AS month, type, COALESCE(SUM(amount), 0) AS amount
            FROM records
            WHERE user_id = ? AND substr(date, 1, 7) BETWEEN ? AND ?
            GROUP BY substr(date, 1, 7), type
            """,
            (user_id, trend_months[0], trend_months[-1]),
        ).fetchall()
        budget_row = conn.execute(
            """
            SELECT amount
            FROM budgets
            WHERE user_id = ? AND month = ?
            """,
            (user_id, month),
        ).fetchone()

    category_total = sum(row["amount"] for row in category_rows)
    categories = [
        {
            "category": row["category"],
            "amount": row["amount"],
            "percent": round(row["amount"] / category_total * 100, 1)
            if category_total
            else 0,
        }
        for row in category_rows
    ]

    trend_map = {
        trend_month: {"month": trend_month, "income": 0, "expense": 0, "balance": 0}
        for trend_month in trend_months
    }
    for row in trend_rows:
        trend_map[row["month"]][row["type"]] = row["amount"]
    for item in trend_map.values():
        item["balance"] = item["income"] - item["expense"]

    budget_amount = budget_row["amount"] if budget_row else 0
    budget_percent = round(expense / budget_amount * 100, 1) if budget_amount else 0
    budget_remaining = budget_amount - expense if budget_amount else 0

    return jsonify(
        {
            "month": month,
            "totalIncome": income,
            "totalExpense": expense,
            "balance": income - expense,
            "categories": categories,
            "trend": list(trend_map.values()),
            "budget": {
                "amount": budget_amount,
                "used": expense,
                "remaining": budget_remaining,
                "percent": budget_percent,
                "status": get_budget_status(budget_amount, expense),
            },
        }
    )


@app.post("/api/budget")
def save_budget():
    login_error = require_login_json()
    if login_error:
        return login_error

    user_id = get_current_user_id()
    data = request.get_json(silent=True) or {}
    month = normalize_month(data.get("month"))
    if not month:
        return jsonify({"error": "月份格式无效"}), 400

    amount = parse_positive_amount(data.get("amount"))
    if amount is None:
        return jsonify({"error": "预算金额格式无效"}), 400

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO budgets (user_id, month, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, month)
            DO UPDATE SET amount = excluded.amount, updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, month, amount),
        )
        conn.commit()

    return jsonify({"month": month, "amount": amount})


@app.post("/api/records")
def create_record():
    login_error = require_login_json()
    if login_error:
        return login_error

    user_id = get_current_user_id()
    payload, errors = validate_record_payload(request.get_json(silent=True) or {})
    if errors:
        return jsonify({"error": errors[0], "errors": errors}), 400

    record_id = str(uuid.uuid4())
    created_at = int(time.time() * 1000)

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO records (
                id, user_id, date, type, category, amount, note, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                user_id,
                payload["date"],
                payload["type"],
                payload["category"],
                payload["amount"],
                payload["note"],
                created_at,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM records WHERE id = ? AND user_id = ?",
            (record_id, user_id),
        ).fetchone()

    return jsonify(row_to_dict(row)), 201


@app.put("/api/records/<record_id>")
def update_record(record_id):
    login_error = require_login_json()
    if login_error:
        return login_error

    user_id = get_current_user_id()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT * FROM records WHERE id = ? AND user_id = ?",
            (record_id, user_id),
        ).fetchone()

    if not existing:
        return jsonify({"error": "记录不存在"}), 404

    payload, errors = validate_record_payload(
        request.get_json(silent=True) or {}
    )
    if errors:
        return jsonify({"error": errors[0], "errors": errors}), 400

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE records
            SET date = ?, type = ?, category = ?, amount = ?, note = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                payload["date"],
                payload["type"],
                payload["category"],
                payload["amount"],
                payload["note"],
                record_id,
                user_id,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM records WHERE id = ? AND user_id = ?",
            (record_id, user_id),
        ).fetchone()

    return jsonify(row_to_dict(row))


@app.delete("/api/records/<record_id>")
def delete_record(record_id):
    login_error = require_login_json()
    if login_error:
        return login_error

    user_id = get_current_user_id()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM records WHERE id = ? AND user_id = ?",
            (record_id, user_id),
        ).fetchone()
        if not existing:
            return jsonify({"error": "记录不存在"}), 404

        conn.execute(
            "DELETE FROM records WHERE id = ? AND user_id = ?",
            (record_id, user_id),
        )
        conn.commit()

    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=APP_ENV == "development",
    )
