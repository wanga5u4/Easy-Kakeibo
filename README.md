# 简易记账系统

Flask 多用户记账系统，使用原生 SQLite 持久化数据。

## 项目结构

```text
server.py              Flask 应用入口和路由
database.py            SQLite 初始化、迁移和连接
templates/             Jinja2 页面模板
static/css/            样式文件
static/js/             页面 JavaScript
tests/                 pytest 自动化测试
data/                  默认 SQLite 数据库目录，不提交 Git
requirements.txt       生产依赖
requirements-dev.txt   测试/开发依赖
.env.example           环境变量示例
```

## 本地启动

Windows PowerShell:

```powershell
cd D:\accounting-system
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
$env:APP_ENV="development"
$env:SECRET_KEY="dev-only-local-secret"
python server.py
```

Linux/macOS:

```bash
cd /path/to/accounting-system
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export APP_ENV=development
export SECRET_KEY=dev-only-local-secret
python server.py
```

访问：http://127.0.0.1:5000

## SECRET_KEY

生产环境必须设置随机 `SECRET_KEY`，不要使用示例值。

生成方式：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

环境变量示例见 `.env.example`。不要提交真实 `.env`。

## 数据库路径

默认数据库路径为 `data/accounting.db`。不设置 `DATABASE_PATH` 时，开发和生产环境都会继续使用这个默认路径。

自动化测试通过临时 `DATABASE_PATH` 使用 pytest 临时数据库，不读取、不修改、也不删除正式 `data/accounting.db`。

## 数据库初始化

应用启动时会执行幂等 `init_db()`，会创建缺失的表和字段，不会清空已有用户、账目、预算、反馈或分享链接。

也可以手动检查初始化：

```bash
python -c "from database import init_db; init_db(); print('ok')"
```

## 生产启动

生产环境请关闭 Debug，并通过 WSGI 服务器运行：

```bash
export APP_ENV=production
export SECRET_KEY=replace-with-a-long-random-secret
gunicorn -c gunicorn.conf.py server:app
```

生产环境建议放在 Nginx/Caddy 等反向代理之后，并启用 HTTPS。

## Ubuntu 部署

以下示例使用占位域名、用户和路径。请将 `example.com`、`your-user`、`/opt/accounting-system` 替换为实际值。域名需要提前解析到服务器公网 IP。

1. 安装系统依赖

```bash
sudo apt update
sudo apt install -y git python3 python3-venv caddy ufw
```

2. 克隆仓库

```bash
sudo mkdir -p /opt/accounting-system
sudo chown your-user:your-user /opt/accounting-system
git clone https://example.com/your/accounting-system.git /opt/accounting-system
cd /opt/accounting-system
```

3. 创建虚拟环境并安装依赖

```bash
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

4. 创建 `.env`

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

编辑 `.env`，至少设置：

```env
APP_ENV=production
SECRET_KEY=replace-with-generated-random-value
DATABASE_PATH=data/accounting.db
SESSION_COOKIE_SECURE=true
RATELIMIT_STORAGE_URI=memory://
LOG_DIR=logs
LOG_LEVEL=INFO
BACKUP_DIR=backups
BACKUP_RETENTION_DAYS=14
GUNICORN_BIND=127.0.0.1:8000
GUNICORN_WORKERS=1
GUNICORN_TIMEOUT=30
```

生产环境必须使用随机且足够长的 `SECRET_KEY`，不要提交真实 `.env`。如果有 Redis，建议把 `RATELIMIT_STORAGE_URI` 改成类似 `redis://127.0.0.1:6379/0`。
当前 SQLite 小范围朋友测试阶段推荐使用 1 个 Gunicorn worker，降低并发写入锁冲突和进程内限流不一致的风险。未来迁移 PostgreSQL，或接入 Redis 等共享限流存储并完成并发验证后，再按服务器资源增加 worker 数。

5. 初始化数据库

```bash
mkdir -p data logs backups
python -c "from database import init_db; init_db(); print('ok')"
```

当前主要数据表：

- `users`：用户账号、语言、货币和资料设置
- `records`：当前用户的收入/支出记录
- `budgets`：当前用户的月度预算
- `feedback`：登录用户提交的反馈与建议
- `share_links`：登录用户创建的月度汇总公开分享链接

新增表和索引由 `init_db()` 自动创建；部署新版本后执行一次上面的初始化命令即可完成迁移。

## 用户反馈

登录后访问 `/feedback` 可以提交反馈与建议。反馈字段包括类型、标题、详细内容、当前页面和联系方式；`user_id` 只来自登录 session，表单里伪造的 `user_id` 会被忽略。

反馈保存在 `feedback` 表中，普通用户只能看到自己最近 10 条反馈和当前状态，不能修改状态，也不能查看其他用户的反馈。

本版本不提供公开管理员后台。服务器管理员可在终端查看反馈：

```bash
python scripts/list_feedback.py
python scripts/list_feedback.py --status new
python scripts/list_feedback.py --limit 20
```

脚本只输出反馈 ID、用户 ID、类型、标题、状态、创建时间、联系方式和内容摘要，不输出密码或密码哈希。

## 分享链接

登录后访问 `/share` 可以创建和管理分享链接。公开链接形如 `/s/<token>`，不需要登录即可查看。

第一版公开范围仅包括：

- 指定月份收入总额
- 指定月份支出总额
- 指定月份结余
- 收入/支出分类汇总
- 用户填写的分享标题和说明

公开页面不会展示登录邮箱、用户 ID、真实姓名、密码信息、联系方式、预算、反馈内容、单笔交易备注或完整交易明细。公开统计实时按 `share_links.user_id` 和 `share_links.share_month` 计算，URL 查询参数不能改变分享月份或分享范围。

分享链接 token 使用 `secrets.token_urlsafe(32)` 生成，并存入 `share_links.token` 唯一索引。用户只能管理自己的链接；停用、启用和删除都使用 POST。停用或过期后公开页面立即不可用，删除后公开地址返回不存在。

管理页提供复制链接按钮；如果浏览器或本地 HTTP 环境不支持 Clipboard API，仍可手动选中输入框中的公开链接。

6. 运行测试

```bash
pytest
```

7. 测试 Gunicorn

```bash
gunicorn -c gunicorn.conf.py server:app
curl http://127.0.0.1:8000/health
```

确认返回 `{"database":"ok","status":"ok"}` 后停止前台进程。

8. 安装 systemd 服务

```bash
sudo cp deploy/accounting.service.example /etc/systemd/system/accounting.service
sudo editor /etc/systemd/system/accounting.service
sudo systemctl daemon-reload
sudo systemctl enable accounting
sudo systemctl start accounting
sudo systemctl status accounting
```

服务示例默认使用普通用户运行，并只给 `data`、`logs`、`backups` 写权限。不要使用 root 运行应用。

9. 配置 Caddy

```bash
sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo editor /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy 会自动申请和续期 HTTPS 证书。Flask/Gunicorn 只监听 `127.0.0.1`，公网只开放 `80` 和 `443`，不要把 Flask 开发服务器直接暴露到互联网。

10. 配置 UFW

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

11. 检查健康状态

```bash
curl https://example.com/health
```

12. 配置每日数据库备份

先手动运行一次：

```bash
cd /opt/accounting-system
. venv/bin/activate
python scripts/backup_database.py
```

再添加 cron：

```bash
crontab -e
```

示例每天 03:00 执行：

```cron
0 3 * * * cd /opt/accounting-system && . /opt/accounting-system/venv/bin/activate && python scripts/backup_database.py >> /opt/accounting-system/logs/backup.log 2>&1
```

13. 查看日志

```bash
sudo journalctl -u accounting -f
tail -f /opt/accounting-system/logs/accounting.log
tail -f /opt/accounting-system/logs/backup.log
```

14. 更新项目标准流程

```bash
cd /opt/accounting-system
git fetch --all
git checkout main
git pull --ff-only
. venv/bin/activate
pip install -r requirements.txt
python -c "from database import init_db; init_db(); print('ok')"
pytest
sudo systemctl restart accounting
curl https://example.com/health
```

15. 数据库恢复方法

恢复前先停止服务并保留当前数据库副本：

```bash
sudo systemctl stop accounting
cp data/accounting.db data/accounting.before-restore.db
cp backups/accounting-YYYY-MM-DD-HHMMSS.db data/accounting.db
python -c "import sqlite3; conn=sqlite3.connect('data/accounting.db'); conn.execute('PRAGMA integrity_check'); print('ok')"
sudo systemctl start accounting
curl https://example.com/health
```

确认恢复正常后，再按备份策略清理旧文件。

## 运行测试

Windows PowerShell:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
pytest
```

Linux/macOS:

```bash
. .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
pytest
```

测试会为每个用例创建临时 SQLite 数据库，并通过真实 CSRF Token 提交表单和 API 请求。

如果当前机器的默认临时目录不可写，可以把 pytest 临时目录放到项目目录：

```powershell
New-Item -ItemType Directory -Force tmp_pytest | Out-Null
$env:TMP=(Resolve-Path tmp_pytest).Path
$env:TEMP=$env:TMP
python -m pytest --basetemp tmp_pytest\basetemp -p no:cacheprovider
```

## 国际化

项目使用 Flask-Babel。更新用户可见文案后执行：

```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations -l zh_CN
pybabel update -i messages.pot -d translations -l ja
python scripts/fill_translations.py
pybabel compile -d translations
```

需要提交 `messages.pot`、对应语言的 `messages.po` 和编译后的 `messages.mo`。

## 安全提醒

- 不提交 `.env`
- 不提交数据库文件或备份
- 不在公网使用 Debug
- 生产环境必须设置随机 `SECRET_KEY`
- 生产环境建议启用 HTTPS
- 部署前备份 `data/accounting.db`

## 主要功能

- 用户注册、登录、POST 退出登录
- 用户数据隔离
- 添加、查看、编辑、删除账目
- 类型和月份筛选
- 服务器端分页
- 本月收入、本月支出、本月结余
- 每月预算、预算进度条和状态提示
- 支出分类占比图
- 最近六个月收支趋势图
- 用户设置和支持与后续更新计划页
- 反馈与建议提交、最近反馈状态查看
- 月度汇总分享链接管理和公开只读分享页
