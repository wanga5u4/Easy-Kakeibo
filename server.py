import time
import uuid
import os
from datetime import date
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_connection, init_db, row_to_dict

BASE_DIR = Path(__file__).parent

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

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


def validate_record_payload(data):
    errors = []

    date = data.get("date", "")
    if not date or len(date) != 10:
        errors.append("日期格式无效")

    record_type = data.get("type", "")
    if record_type not in ("income", "expense"):
        errors.append("类型必须是 income 或 expense")

    category = (data.get("category") or "").strip()
    if not category:
        errors.append("分类不能为空")

    try:
        amount = float(data.get("amount", 0))
        if amount <= 0:
            errors.append("金额必须大于 0")
    except (TypeError, ValueError):
        errors.append("金额格式无效")

    if errors:
        return None, errors

    return {
        "date": date,
        "type": record_type,
        "category": category,
        "amount": amount,
        "note": (data.get("note") or "").strip(),
    }, None


def validate_register_payload(form):
    errors = []
    username = (form.get("username") or "").strip()
    email = (form.get("email") or "").strip()
    password = form.get("password") or ""
    confirm_password = form.get("confirm_password") or ""

    if not username:
        errors.append("用户名不能为空")

    if not email:
        errors.append("邮箱不能为空")

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
    email = (form.get("email") or "").strip()
    language = (form.get("language") or "zh-CN").strip()
    currency = (form.get("currency") or "CNY").strip()
    current_password = form.get("current_password") or ""
    new_password = form.get("new_password") or ""
    confirm_password = form.get("confirm_password") or ""

    if len(nickname) > 30:
        errors.append("昵称不能超过 30 个字符")

    if not email:
        errors.append("邮箱不能为空")

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
        "email": email,
        "language": language,
        "currency": currency,
        "current_password": current_password,
        "new_password": new_password,
        "wants_password_change": wants_password_change,
    }, errors


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
        existing_email = conn.execute(
            "SELECT id FROM users WHERE email = ? AND id != ?",
            (form_data["email"], user["id"]),
        ).fetchone()
        if existing_email:
            errors.append("邮箱已被其他用户使用")

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
                    "email": form_data["email"],
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
                SET nickname = ?, email = ?, language = ?, currency = ?,
                    password_hash = ?
                WHERE id = ?
                """,
                (
                    form_data["nickname"],
                    form_data["email"],
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
                SET nickname = ?, email = ?, language = ?, currency = ?
                WHERE id = ?
                """,
                (
                    form_data["nickname"],
                    form_data["email"],
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
                "SELECT id FROM users WHERE email = ?",
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
                WHERE username = ? OR email = ?
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


@app.get("/logout")
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

    query = "SELECT * FROM records WHERE user_id = ?"
    params = [user_id]

    if record_type in ("income", "expense"):
        query += " AND type = ?"
        params.append(record_type)

    if month:
        query += " AND date LIKE ?"
        params.append(f"{month}%")

    query += " ORDER BY date DESC, created_at DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return jsonify([row_to_dict(row) for row in rows])


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

    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "预算金额格式无效"}), 400

    if amount < 0:
        return jsonify({"error": "预算金额不能小于 0"}), 400

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
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
