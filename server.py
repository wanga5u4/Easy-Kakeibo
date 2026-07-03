import time
import uuid
import os
import secrets
import math
import re
import logging
import hashlib
from datetime import date, datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlparse, urljoin

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_babel import Babel, gettext as _
from flask_limiter import Limiter
from flask_limiter.errors import RateLimitExceeded
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_connection, init_db, row_to_dict

BASE_DIR = Path(__file__).parent

app = Flask(__name__, static_folder="static", static_url_path="/static")
APP_ENV = os.environ.get("APP_ENV", "development").lower()
IS_PRODUCTION = APP_ENV == "production"
secret_key = os.environ.get("SECRET_KEY")

if IS_PRODUCTION and not secret_key:
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
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", str(IS_PRODUCTION)).lower()
    in {"1", "true", "yes", "on"},
    BABEL_DEFAULT_LOCALE="zh_CN",
    BABEL_TRANSLATION_DIRECTORIES=str(BASE_DIR / "translations"),
)


def setup_logging():
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if IS_PRODUCTION:
        log_dir = Path(os.environ.get("LOG_DIR", "logs"))
        if not log_dir.is_absolute():
            log_dir = BASE_DIR / log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "accounting.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    app.logger.handlers.clear()
    app.logger.propagate = True
    app.logger.setLevel(log_level)


setup_logging()
app.logger.info("Application starting")
app.logger.info("Runtime environment: %s", APP_ENV)

try:
    init_db()
    app.logger.info("Database initialized successfully")
except Exception:
    app.logger.exception("Database initialization failed")
    raise

RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
if IS_PRODUCTION and RATELIMIT_STORAGE_URI == "memory://":
    app.logger.warning(
        "RATELIMIT_STORAGE_URI is memory:// in production; use Redis for multi-process deployments."
    )

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=RATELIMIT_STORAGE_URI,
)

LANGUAGE_OPTIONS = {
    "zh_CN": "简体中文",
    "ja": "日本語",
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
LOCALE_ALIASES = {"zh-CN": "zh_CN", "zh": "zh_CN", "ja-JP": "ja"}
ACCOUNT_DELETION_CONFIRMATION = "DELETE"
FEEDBACK_TYPES = ("bug", "feature", "question", "other")
FEEDBACK_STATUSES = ("new", "reviewing", "resolved", "closed")
SHARE_EXPIRATION_DAYS = {"1": 1, "7": 7, "30": 30, "forever": None}
SHARE_TOKEN_BYTES = 32
USER_OWNED_TABLES = ("records", "budgets", "feedback", "share_links")


def normalize_locale(value):
    locale = (value or "").strip()
    locale = LOCALE_ALIASES.get(locale, locale.replace("-", "_"))
    return locale if locale in LANGUAGE_OPTIONS else None


def get_language_options():
    return {"zh_CN": _("简体中文"), "ja": _("日本語")}


def get_currency_options():
    return {
        "CNY": _("人民币 CNY"),
        "USD": _("美元 USD"),
        "JPY": _("日元 JPY"),
        "EUR": _("欧元 EUR"),
    }


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


def get_locale():
    lang = normalize_locale(request.args.get("lang"))
    if lang:
        session["lang"] = lang
        return lang

    lang = normalize_locale(session.get("lang"))
    if lang:
        return lang

    user = get_current_user()
    if user:
        lang = normalize_locale(user["language"])
        if lang:
            session["lang"] = lang
            return lang

    return app.config["BABEL_DEFAULT_LOCALE"]


babel = Babel(app, locale_selector=get_locale)


def normalize_email(value):
    return (value or "").strip().lower()


def anonymize_account(value):
    normalized = (value or "").strip().lower().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()[:16]


def is_safe_redirect_target(target):
    if not target:
        return False
    try:
        host_url = urlparse(request.host_url)
        resolved = urlparse(urljoin(request.host_url, target))
    except ValueError:
        return False
    return (
        resolved.scheme in {"http", "https"}
        and resolved.scheme == host_url.scheme
        and resolved.netloc == host_url.netloc
    )


def default_language_redirect():
    if get_current_user_id():
        return url_for("dashboard")
    return url_for("index")


def get_safe_next_url():
    target = request.values.get("next", "").strip()
    if not is_safe_redirect_target(target):
        return ""
    return target


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
        errors.append(_("日期格式无效"))

    record_type = data.get("type", "")
    if record_type not in ("income", "expense"):
        errors.append(_("类型必须是 income 或 expense"))

    category = (data.get("category") or "").strip()
    if not category:
        errors.append(_("分类不能为空"))

    amount = parse_positive_amount(data.get("amount"))
    if amount is None:
        errors.append(_("金额格式无效"))

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
        errors.append(_("用户名不能为空"))

    if not email:
        errors.append(_("邮箱不能为空"))
    elif not is_valid_email(email):
        errors.append(_("邮箱格式无效"))

    if len(password) < 8:
        errors.append(_("密码至少需要 8 位"))

    if password != confirm_password:
        errors.append(_("两次输入的密码不一致"))

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
        errors.append(_("用户名或邮箱不能为空"))

    if not password:
        errors.append(_("密码不能为空"))

    return {
        "account": account,
        "password": password,
    }, errors


def validate_settings_payload(form):
    errors = []
    nickname = (form.get("nickname") or "").strip()
    language = normalize_locale(form.get("language")) or "zh_CN"
    currency = (form.get("currency") or "CNY").strip()
    current_password = form.get("current_password") or ""
    new_password = form.get("new_password") or ""
    confirm_password = form.get("confirm_password") or ""

    if len(nickname) > 30:
        errors.append(_("昵称不能超过 30 个字符"))

    if language not in LANGUAGE_OPTIONS:
        errors.append(_("语言选项无效"))

    if currency not in CURRENCY_OPTIONS:
        errors.append(_("货币选项无效"))

    wants_password_change = any([current_password, new_password, confirm_password])
    if wants_password_change:
        if not current_password:
            errors.append(_("请输入当前密码"))
        if len(new_password) < 8:
            errors.append(_("新密码至少需要 8 位"))
        if new_password != confirm_password:
            errors.append(_("两次输入的新密码不一致"))

    return {
        "nickname": nickname,
        "language": language,
        "currency": currency,
        "current_password": current_password,
        "new_password": new_password,
        "wants_password_change": wants_password_change,
    }, errors


def validate_account_deletion_payload(form, user):
    errors = []
    current_password = form.get("delete_current_password") or ""
    confirmation_text = (form.get("delete_confirmation") or "").strip()

    if not current_password:
        errors.append(_("请输入当前密码"))
    elif not check_password_hash(user["password_hash"], current_password):
        errors.append(_("当前密码不正确"))

    if confirmation_text != ACCOUNT_DELETION_CONFIRMATION:
        errors.append(_("确认文字错误，请输入 DELETE"))

    return errors


def get_feedback_type_labels():
    return {
        "bug": _("Bug 报告"),
        "feature": _("功能建议"),
        "question": _("使用问题"),
        "other": _("其他"),
    }


def get_feedback_status_labels():
    return {
        "new": _("新建"),
        "reviewing": _("处理中"),
        "resolved": _("已解决"),
        "closed": _("已关闭"),
    }


def get_share_status(link):
    if not link["is_active"]:
        return "inactive"
    if is_share_expired(link):
        return "expired"
    return "active"


def get_share_status_labels():
    return {
        "active": _("有效"),
        "inactive": _("已停用"),
        "expired": _("已过期"),
    }


def truncate_text(value, length=120):
    text = value or ""
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "..."


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def validate_feedback_payload(form):
    errors = []
    feedback_type = (form.get("feedback_type") or "").strip()
    title = (form.get("title") or "").strip()
    content = (form.get("content") or "").strip()
    page_url = (form.get("page_url") or "").strip()
    contact = (form.get("contact") or "").strip()

    if feedback_type not in FEEDBACK_TYPES:
        errors.append(_("反馈类型无效"))
    if not title:
        errors.append(_("标题不能为空"))
    elif not 2 <= len(title) <= 100:
        errors.append(_("标题长度需要在 2 到 100 个字符之间"))
    if not content:
        errors.append(_("详细内容不能为空"))
    elif not 5 <= len(content) <= 2000:
        errors.append(_("详细内容长度需要在 5 到 2000 个字符之间"))
    if len(page_url) > 200:
        errors.append(_("当前页面不能超过 200 个字符"))
    if len(contact) > 120:
        errors.append(_("联系方式不能超过 120 个字符"))

    return {
        "feedback_type": feedback_type,
        "title": title,
        "content": content,
        "page_url": page_url,
        "contact": contact,
    }, errors


def get_recent_feedback(conn, user_id):
    return conn.execute(
        """
        SELECT id, feedback_type, title, content, status, created_at
        FROM feedback
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 10
        """,
        (user_id,),
    ).fetchall()


def validate_share_payload(form):
    errors = []
    share_month = normalize_month(form.get("share_month"))
    title = (form.get("title") or "").strip()
    description = (form.get("description") or "").strip()
    expires_in = (form.get("expires_in") or "7").strip()
    include_income = 1 if form.get("include_income_summary") == "1" else 0
    include_expense = 1 if form.get("include_expense_summary") == "1" else 0
    include_category = 1 if form.get("include_category_summary") == "1" else 0

    if not share_month:
        errors.append(_("月份格式无效"))
    if not title and share_month:
        title = _("%(month)s 收支概览", month=share_month)
    if not title:
        errors.append(_("分享标题不能为空"))
    elif len(title) > 100:
        errors.append(_("分享标题不能超过 100 个字符"))
    if len(description) > 300:
        errors.append(_("分享说明不能超过 300 个字符"))
    if not any([include_income, include_expense, include_category]):
        errors.append(_("请至少选择一项分享内容"))
    if expires_in not in SHARE_EXPIRATION_DAYS:
        errors.append(_("有效期无效"))

    expires_at = None
    if expires_in in SHARE_EXPIRATION_DAYS and SHARE_EXPIRATION_DAYS[expires_in] is not None:
        expires_at = (
            utc_now() + timedelta(days=SHARE_EXPIRATION_DAYS[expires_in])
        ).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "title": title,
        "description": description,
        "share_month": share_month or "",
        "include_income_summary": include_income,
        "include_expense_summary": include_expense,
        "include_category_summary": include_category,
        "expires_at": expires_at,
        "expires_in": expires_in,
    }, errors


def generate_unique_share_token(conn):
    for _ in range(5):
        token = secrets.token_urlsafe(SHARE_TOKEN_BYTES)
        exists = conn.execute(
            "SELECT 1 FROM share_links WHERE token = ?",
            (token,),
        ).fetchone()
        if not exists:
            return token
    raise RuntimeError("unable to generate unique share token")


def parse_db_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def is_share_expired(link):
    expires_at = parse_db_timestamp(link["expires_at"])
    return bool(expires_at and expires_at <= utc_now())


def get_month_totals(conn, user_id, month):
    rows = conn.execute(
        """
        SELECT type, COALESCE(SUM(amount), 0) AS amount
        FROM records
        WHERE user_id = ? AND date LIKE ?
        GROUP BY type
        """,
        (user_id, f"{month}%"),
    ).fetchall()
    totals = {"income": 0, "expense": 0}
    for row in rows:
        totals[row["type"]] = row["amount"]
    totals["balance"] = totals["income"] - totals["expense"]
    return totals


def get_category_summary(conn, user_id, month, record_type):
    rows = conn.execute(
        """
        SELECT category, COALESCE(SUM(amount), 0) AS amount
        FROM records
        WHERE user_id = ? AND type = ? AND date LIKE ?
        GROUP BY category
        ORDER BY amount DESC
        """,
        (user_id, record_type, f"{month}%"),
    ).fetchall()
    total = sum(row["amount"] for row in rows)
    return [
        {
            "category": row["category"],
            "amount": row["amount"],
            "percent": round(row["amount"] / total * 100, 1) if total else 0,
        }
        for row in rows
    ]


def get_public_share_summary(conn, user_id, month):
    totals = get_month_totals(conn, user_id, month)
    return {
        "month": month,
        "totalIncome": totals["income"],
        "totalExpense": totals["expense"],
        "balance": totals["balance"],
        "incomeCategories": get_category_summary(conn, user_id, month, "income"),
        "expenseCategories": get_category_summary(conn, user_id, month, "expense"),
    }


def delete_user_account(user_id):
    conn = get_connection()
    try:
        conn.execute("BEGIN")
        for table_name in USER_OWNED_TABLES:
            conn.execute(f"DELETE FROM {table_name} WHERE user_id = ?", (user_id,))
        deleted = conn.execute("DELETE FROM users WHERE id = ?", (user_id,)).rowcount
        if deleted != 1:
            raise RuntimeError("current user no longer exists")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def wants_json_response():
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


def is_secure_request():
    return request.is_secure or request.headers.get("X-Forwarded-Proto", "").lower() == "https"


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "font-src 'self' data: https://cdn.jsdelivr.net; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'",
    )
    if IS_PRODUCTION and is_secure_request():
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    return response


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
        return jsonify({"ok": False, "error": _("安全验证失败，请刷新页面后重试。")}), 400
    return render_template(
        "message.html",
        active_page="",
        title=_("安全验证失败"),
        message=_("请求已过期或安全验证失败，请刷新页面后重试。"),
        action_url=url_for("index"),
        action_text=_("返回首页"),
    ), 400


def render_error_response(status_code, message):
    if wants_json_response():
        return jsonify({"ok": False, "error": message}), status_code
    return render_template(
        "message.html",
        active_page="",
        title=_("%(status_code)s 错误", status_code=status_code),
        message=message,
        action_url=url_for("index"),
        action_text=_("返回首页"),
    ), status_code


@app.errorhandler(400)
def handle_bad_request(error):
    return render_error_response(400, _("请求无效，请检查输入后重试。"))


@app.errorhandler(403)
def handle_forbidden(error):
    return render_error_response(403, _("没有权限执行此操作。"))


@app.errorhandler(404)
def handle_not_found(error):
    return render_error_response(404, _("页面或资源不存在。"))


@app.errorhandler(500)
def handle_server_error(error):
    app.logger.error(
        "Unhandled exception",
        exc_info=getattr(error, "original_exception", error),
    )
    return render_error_response(500, _("服务器暂时无法处理请求，请稍后重试。"))


@app.errorhandler(RateLimitExceeded)
def handle_rate_limit(error):
    app.logger.warning(
        "Rate limit triggered: path=%s method=%s remote_addr=%s",
        request.path,
        request.method,
        get_remote_address(),
    )
    message = _("请求过于频繁，请稍后再试。")
    if wants_json_response():
        return jsonify({"ok": False, "error": message}), 429
    return render_template(
        "message.html",
        active_page="",
        title=_("请求过于频繁"),
        message=message,
        action_url=url_for("login") if request.path == "/login" else url_for("register"),
        action_text=_("返回后重试"),
    ), 429


def require_login_json():
    if not get_current_user_id():
        return jsonify({"error": _("请先登录")}), 401
    return None


def require_login_page():
    if not get_current_user_id():
        next_url = request.full_path.rstrip("?")
        return redirect(url_for("login", next=next_url))
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
        return _("未设置预算")
    percent = used / amount * 100
    if percent >= 100:
        return _("已超出预算")
    if percent >= 80:
        return _("预算即将用完")
    return _("预算正常")


@app.context_processor
def inject_user_context():
    current_language = str(get_locale())
    return {
        "current_user_profile": get_current_user(),
        "current_language": current_language,
        "language_options": get_language_options(),
        "js_i18n": {
            "requestFailed": _("请求失败，请稍后重试"),
            "categories": {
                "income": [_("工资"), _("奖金"), _("理财"), _("兼职"), _("其他收入")],
                "expense": [_("餐饮"), _("交通"), _("购物"), _("住房"), _("娱乐"), _("医疗"), _("教育"), _("其他支出")],
            },
            "typeLabels": {"income": _("收入"), "expense": _("支出")},
            "dateFormat": _("%(year)s年%(month)s月%(day)s日"),
            "used": _("已用 %(amount)s"),
            "remaining": _("%(status)s，剩余 %(amount)s"),
            "edit": _("编辑"),
            "delete": _("删除"),
            "noNote": _("—"),
            "pagination": _("第 %(page)s / %(total_pages)s 页，共 %(total)s 条"),
            "recordDeleted": _("记录已删除"),
            "deleteFailed": _("删除失败：%(message)s"),
            "recordUpdated": _("记录已更新"),
            "recordAdded": _("记录已添加"),
            "budgetSaved": _("预算已保存"),
            "income": _("收入"),
            "expense": _("支出"),
            "linkCopied": _("链接已复制"),
            "copyManually": _("复制失败，请手动复制链接。"),
            "confirmDeleteShareLink": _("确定要删除这个分享链接吗？此操作无法撤销。"),
        },
    }


@app.get("/set-language/<language>")
def set_language(language):
    selected_language = normalize_locale(language)
    if selected_language:
        session["lang"] = selected_language
    if is_safe_redirect_target(request.referrer):
        return redirect(request.referrer)
    return redirect(default_language_redirect())


@app.route("/")
def index():
    return render_template("index.html", active_page="home")


@app.get("/health")
def health():
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception:
        app.logger.exception("Health check database failed")
        return jsonify({"status": "error", "database": "unavailable"}), 503
    return jsonify({"status": "ok", "database": "ok"})


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
            title=_("记录不存在"),
            message=_("这条记录不存在，或不属于当前登录用户。"),
            action_url=url_for("records_page"),
            action_text=_("返回记录列表"),
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


@app.route("/feedback", methods=["GET", "POST"])
def feedback_page():
    login_redirect = require_login_page()
    if login_redirect:
        return login_redirect

    user_id = get_current_user_id()
    form = {
        "feedback_type": "bug",
        "title": "",
        "content": "",
        "page_url": (request.args.get("page") or "")[:200],
        "contact": "",
    }
    errors = []

    if request.method == "POST":
        form, errors = validate_feedback_payload(request.form)
        if not errors:
            try:
                with get_connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO feedback (
                            user_id, feedback_type, title, content, page_url, contact
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            form["feedback_type"],
                            form["title"],
                            form["content"],
                            form["page_url"],
                            form["contact"],
                        ),
                    )
                    conn.commit()
                flash(_("反馈已提交，感谢你的帮助。"), "success")
                return redirect(url_for("feedback_page"))
            except Exception:
                app.logger.error("Feedback submission failed: user_id=%s", user_id, exc_info=True)
                errors.append(_("反馈提交失败，请稍后重试。"))

    with get_connection() as conn:
        recent_feedback = get_recent_feedback(conn, user_id)

    return render_template(
        "feedback.html",
        active_page="feedback",
        errors=errors,
        form=form,
        recent_feedback=recent_feedback,
        feedback_type_labels=get_feedback_type_labels(),
        feedback_status_labels=get_feedback_status_labels(),
        truncate_text=truncate_text,
    ), 400 if errors else 200


@app.route("/share", methods=["GET", "POST"])
def share_page():
    login_redirect = require_login_page()
    if login_redirect:
        return login_redirect

    user_id = get_current_user_id()
    form = {
        "title": "",
        "description": "",
        "share_month": current_month(),
        "include_income_summary": 1,
        "include_expense_summary": 1,
        "include_category_summary": 1,
        "expires_in": "7",
    }
    errors = []

    if request.method == "POST":
        form, errors = validate_share_payload(request.form)
        if not errors:
            try:
                with get_connection() as conn:
                    token = generate_unique_share_token(conn)
                    conn.execute(
                        """
                        INSERT INTO share_links (
                            user_id, token, title, description, share_month,
                            include_income_summary, include_expense_summary,
                            include_category_summary, expires_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            token,
                            form["title"],
                            form["description"],
                            form["share_month"],
                            form["include_income_summary"],
                            form["include_expense_summary"],
                            form["include_category_summary"],
                            form["expires_at"],
                        ),
                    )
                    share_link_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    conn.commit()
                app.logger.info("Share link created: share_link_id=%s user_id=%s", share_link_id, user_id)
                flash(_("分享链接已创建。"), "success")
                return redirect(url_for("share_page"))
            except Exception:
                app.logger.error("Share link creation failed: user_id=%s", user_id, exc_info=True)
                errors.append(_("分享链接创建失败，请稍后重试。"))

    with get_connection() as conn:
        share_links = conn.execute(
            """
            SELECT id, token, title, share_month, expires_at, is_active,
                   created_at, view_count
            FROM share_links
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()

    public_links = {
        link["id"]: url_for("public_share_page", token=link["token"], _external=True)
        for link in share_links
    }

    return render_template(
        "share.html",
        active_page="share",
        errors=errors,
        form=form,
        share_links=share_links,
        public_links=public_links,
        share_status_labels=get_share_status_labels(),
        get_share_status=get_share_status,
        current_month=current_month(),
    ), 400 if errors else 200


def update_own_share_link(link_id, updates):
    user_id = get_current_user_id()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM share_links WHERE id = ? AND user_id = ?",
            (link_id, user_id),
        ).fetchone()
        if not existing:
            return False
        updates(conn)
        conn.commit()
    return True


@app.post("/share/<int:link_id>/disable")
def disable_share_link(link_id):
    def updates(conn):
        conn.execute(
            "UPDATE share_links SET is_active = 0 WHERE id = ? AND user_id = ?",
            (link_id, get_current_user_id()),
        )

    login_redirect = require_login_page()
    if login_redirect:
        return login_redirect
    if update_own_share_link(link_id, updates):
        app.logger.info("Share link disabled: share_link_id=%s", link_id)
        flash(_("分享链接已停用。"), "success")
    else:
        flash(_("分享链接不存在。"), "error")
    return redirect(url_for("share_page"))


@app.post("/share/<int:link_id>/enable")
def enable_share_link(link_id):
    def updates(conn):
        conn.execute(
            "UPDATE share_links SET is_active = 1 WHERE id = ? AND user_id = ?",
            (link_id, get_current_user_id()),
        )

    login_redirect = require_login_page()
    if login_redirect:
        return login_redirect
    if update_own_share_link(link_id, updates):
        app.logger.info("Share link enabled: share_link_id=%s", link_id)
        flash(_("分享链接已启用。"), "success")
    else:
        flash(_("分享链接不存在。"), "error")
    return redirect(url_for("share_page"))


@app.post("/share/<int:link_id>/delete")
def delete_share_link(link_id):
    def updates(conn):
        conn.execute(
            "DELETE FROM share_links WHERE id = ? AND user_id = ?",
            (link_id, get_current_user_id()),
        )

    login_redirect = require_login_page()
    if login_redirect:
        return login_redirect
    if update_own_share_link(link_id, updates):
        app.logger.info("Share link deleted: share_link_id=%s", link_id)
        flash(_("分享链接已删除。"), "success")
    else:
        flash(_("分享链接不存在。"), "error")
    return redirect(url_for("share_page"))


@app.get("/s/<token>")
def public_share_page(token):
    with get_connection() as conn:
        link = conn.execute(
            """
            SELECT id, user_id, token, title, description, share_month,
                   include_income_summary, include_expense_summary,
                   include_category_summary, expires_at, is_active,
                   created_at, view_count
            FROM share_links
            WHERE token = ?
            """,
            (token,),
        ).fetchone()

        if not link:
            return render_template(
                "public_share_status.html",
                title=_("链接不存在"),
                message=_("这个分享链接不存在或已被删除。"),
            ), 404
        if not link["is_active"]:
            return render_template(
                "public_share_status.html",
                title=_("链接已停用"),
                message=_("这个分享链接已停用。"),
            ), 410
        if is_share_expired(link):
            return render_template(
                "public_share_status.html",
                title=_("链接已过期"),
                message=_("这个分享链接已过期。"),
            ), 410

        summary = get_public_share_summary(conn, link["user_id"], link["share_month"])
        conn.execute(
            """
            UPDATE share_links
            SET view_count = view_count + 1, last_viewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (link["id"],),
        )
        conn.commit()

    return render_template(
        "public_share.html",
        link=link,
        summary=summary,
    )


@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    login_redirect = require_login_page()
    if login_redirect:
        return login_redirect

    user = get_current_user()
    if not user:
        session.clear()
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template(
            "settings.html",
            active_page="settings",
            user=user,
            language_options=get_language_options(),
            currency_options=get_currency_options(),
            errors=[],
        )

    form_data, errors = validate_settings_payload(request.form)

    with get_connection() as conn:
        if form_data["wants_password_change"] and not check_password_hash(
            user["password_hash"],
            form_data["current_password"],
        ):
            errors.append(_("当前密码不正确"))

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
                language_options=get_language_options(),
                currency_options=get_currency_options(),
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

    session["lang"] = form_data["language"]
    flash(_("设置已保存"), "success")
    return redirect(url_for("settings_page"))


@app.post("/settings/delete-account")
def delete_account():
    login_redirect = require_login_page()
    if login_redirect:
        return login_redirect

    user = get_current_user()
    if not user:
        session.clear()
        flash(_("请重新登录后再试"), "error")
        return redirect(url_for("login"))

    errors = validate_account_deletion_payload(request.form, user)
    if errors:
        app.logger.warning("Account deletion rejected: user_id=%s", user["id"])
        for error in errors:
            flash(error, "error")
        return redirect(url_for("settings_page"))

    try:
        delete_user_account(user["id"])
    except Exception:
        app.logger.error("Account deletion failed: user_id=%s", user["id"], exc_info=True)
        flash(_("账号注销失败，请稍后重试。"), "error")
        return redirect(url_for("settings_page"))

    app.logger.info("Account deletion succeeded: user_id=%s", user["id"])
    session.clear()
    flash(_("账号已注销"), "success")
    return redirect(url_for("register"))


@app.get("/support")
def support_page():
    return render_template("support.html", active_page="support")


@app.get("/premium")
@app.get("/vip")
def legacy_support_redirect():
    return redirect(url_for("support_page"), code=302)


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
@limiter.limit("5 per hour", methods=["POST"])
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
                errors.append(_("用户名已存在"))

        if form_data["email"]:
            existing_email = conn.execute(
                "SELECT id FROM users WHERE lower(email) = lower(?)",
                (form_data["email"],),
            ).fetchone()
            if existing_email:
                errors.append(_("邮箱已存在"))

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

    app.logger.info("Registration succeeded: username=%s", form_data["username"])
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute; 30 per hour", methods=["POST"])
def login():
    next_url = get_safe_next_url()
    if request.method == "GET":
        return render_template("login.html", errors=[], form={}, next_url=next_url)

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
            errors.append(_("用户名/邮箱或密码错误"))

    if errors:
        app.logger.warning(
            "Login failed: account_hash=%s remote_addr=%s",
            anonymize_account(form_data["account"]),
            get_remote_address(),
        )
        return render_template(
            "login.html",
            errors=errors,
            form=form_data,
            next_url=next_url,
        ), 400

    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]

    app.logger.info("Login succeeded: user_id=%s username=%s", user["id"], user["username"])
    if next_url:
        return redirect(next_url)
    return redirect(url_for("dashboard"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


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
        return jsonify({"error": _("记录不存在")}), 404

    return jsonify(row_to_dict(row))


@app.get("/api/summary")
def get_summary():
    login_error = require_login_json()
    if login_error:
        return login_error

    user_id = get_current_user_id()
    month = normalize_month(request.args.get("month"))
    if not month:
        return jsonify({"error": _("月份格式无效")}), 400

    with get_connection() as conn:
        totals = get_month_totals(conn, user_id, month)

    return jsonify(
        {
            "month": month,
            "totalIncome": totals["income"],
            "totalExpense": totals["expense"],
            "balance": totals["balance"],
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
        return jsonify({"error": _("月份格式无效")}), 400

    trend_months = [month_shift(month, offset) for offset in range(-5, 1)]

    with get_connection() as conn:
        totals = get_month_totals(conn, user_id, month)
        categories = get_category_summary(conn, user_id, month, "expense")
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

    trend_map = {
        trend_month: {"month": trend_month, "income": 0, "expense": 0, "balance": 0}
        for trend_month in trend_months
    }
    for row in trend_rows:
        trend_map[row["month"]][row["type"]] = row["amount"]
    for item in trend_map.values():
        item["balance"] = item["income"] - item["expense"]

    budget_amount = budget_row["amount"] if budget_row else 0
    budget_percent = round(totals["expense"] / budget_amount * 100, 1) if budget_amount else 0
    budget_remaining = budget_amount - totals["expense"] if budget_amount else 0

    return jsonify(
        {
            "month": month,
            "totalIncome": totals["income"],
            "totalExpense": totals["expense"],
            "balance": totals["balance"],
            "categories": categories,
            "trend": list(trend_map.values()),
            "budget": {
                "amount": budget_amount,
                "used": totals["expense"],
                "remaining": budget_remaining,
                "percent": budget_percent,
                "status": get_budget_status(budget_amount, totals["expense"]),
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
        return jsonify({"error": _("月份格式无效")}), 400

    amount = parse_positive_amount(data.get("amount"))
    if amount is None:
        return jsonify({"error": _("预算金额格式无效")}), 400

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
        return jsonify({"error": _("记录不存在")}), 404

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
            return jsonify({"error": _("记录不存在")}), 404

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
