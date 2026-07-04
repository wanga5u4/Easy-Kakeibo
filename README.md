# Easy Kakeibo 简易记账系统

当前版本：v0.6.1

Easy Kakeibo 是一个基于 Flask 和 SQLite 的多用户个人记账系统，适合小范围自托管使用。项目当前重点是收入/支出记录、预算、统计图表、中日双语界面，以及 v0.6 引入的多货币记录和汇率换算能力。

v0.6.1 是 v0.6 多货币功能的稳定收尾版，主要补全文档、自动测试、CI 和发布前回归准备；不包含大型新功能。

## 主要功能

- 用户注册、登录、POST 退出登录
- 多用户数据隔离，普通用户只能访问自己的记录、预算、反馈和分享链接
- 收入和支出记录：添加、查看、编辑、删除
- 按类型和月份筛选记录
- 服务器端分页，每页 10/20/50 条
- 月度预算保存和更新，预算进度与状态提示
- 仪表盘月度收入、支出、结余概览
- 统计页面：支出分类占比、最近六个月收支趋势
- 公开首页和演示图表
- 支持与计划页面
- 登录用户反馈提交和最近反馈状态查看
- 月度汇总公开分享链接，不暴露完整交易明细
- `/health` 健康检查接口
- SQLite 数据库初始化、幂等迁移和备份脚本

## 多语言支持

当前界面语言：

- 简体中文：`zh_CN`
- 日文：`ja`

项目使用 Flask-Babel 管理翻译，提交翻译时需要同步 `messages.pot`、`translations/*/LC_MESSAGES/messages.po` 和编译后的 `messages.mo`。

当前没有英文界面选项；代码中的英文仅作为部分内部标识、依赖名称或开发语境使用。

## 多货币功能

当前启用的记账货币：

- JPY 日元，0 位小数
- CNY 人民币，2 位小数

多货币规则：

- 每个用户有自己的默认货币 `base_currency_code`
- 新建记录可以选择 JPY 或 CNY
- 当记录币种和默认货币不同时，需要手动输入汇率
- 系统保存原始金额、原始币种、汇率、折算金额和记录创建时的默认货币
- 修改用户默认货币不会改写历史记录
- 统计和仪表盘会优先使用历史记录保存的汇率；跨默认货币展示时，会使用该用户最近保存的汇率进行估算
- 缺少可用汇率的记录不会计入当前汇总，并会返回提示信息
- 汇率按用户隔离，不同用户之间不会共享

当前没有接入外部实时汇率接口，测试也不依赖外部网络。

## 技术栈

- Python 3.12
- Flask
- Flask-Babel
- Flask-Limiter
- SQLite
- Jinja2
- Bootstrap 5
- Chart.js
- pytest
- Gunicorn
- Caddy 或其他反向代理

## 项目目录结构

```text
.github/workflows/        GitHub Actions 自动测试配置
server.py                 Flask 应用入口、路由、安全中间件和 API
database.py               SQLite 初始化、迁移、连接和行序列化
currency.py               多货币金额、汇率、格式化工具
templates/                Jinja2 页面模板
static/css/               样式文件
static/js/                页面 JavaScript
translations/             Babel 翻译文件和编译文件
tests/                    pytest 自动化测试
scripts/backup_database.py SQLite 备份脚本
scripts/list_feedback.py  反馈查看脚本
deploy/                   systemd 和 Caddy 部署示例
data/                     默认 SQLite 数据库目录，不提交 Git
logs/                     默认日志目录，不提交 Git
backups/                  默认备份目录，不提交 Git
requirements.txt          运行依赖
requirements-dev.txt      测试/开发依赖
.env.example              环境变量示例
```

当前仓库没有真实截图目录。README 不引用伪造截图；首页使用静态演示图表展示产品形态。

## 本地运行

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
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export APP_ENV=development
export SECRET_KEY=dev-only-local-secret
python server.py
```

访问：

```text
http://127.0.0.1:5000
```

## 环境变量

参考 `.env.example`。不要提交真实 `.env`。

| 变量 | 说明 |
| --- | --- |
| `APP_ENV` | `development`、`testing` 或 `production` |
| `SECRET_KEY` | Flask 会话密钥；生产环境必须设置随机长字符串 |
| `DATABASE_PATH` | SQLite 数据库路径，默认 `data/accounting.db` |
| `SESSION_COOKIE_SECURE` | HTTPS 生产环境建议设为 `true` |
| `RATELIMIT_STORAGE_URI` | Flask-Limiter 存储，默认 `memory://` |
| `LOG_DIR` | 生产日志目录，默认 `logs` |
| `LOG_LEVEL` | 日志级别，默认 `INFO` |
| `BACKUP_DIR` | 数据库备份目录，默认 `backups` |
| `BACKUP_RETENTION_DAYS` | 备份保留天数，默认 `14` |
| `GUNICORN_BIND` | Gunicorn 监听地址，默认 `127.0.0.1:8000` |
| `GUNICORN_WORKERS` | Gunicorn worker 数；SQLite 小规模使用建议为 `1` |
| `GUNICORN_TIMEOUT` | Gunicorn 超时时间，默认 `30` |

生成生产 `SECRET_KEY`：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 数据库初始化

应用启动时会执行幂等 `init_db()`，自动创建缺失的表、字段和索引，不会清空已有用户、账目、预算、反馈或分享链接。

也可以手动初始化：

```bash
python -c "from database import init_db; init_db(); print('ok')"
```

当前主要数据表：

- `users`：用户账号、语言、默认货币和资料设置
- `records`：收入/支出记录及多货币金额字段
- `budgets`：用户月度预算
- `feedback`：登录用户反馈
- `share_links`：月度汇总公开分享链接
- `user_exchange_rates`：用户最近使用的汇率

## 自动测试

安装依赖：

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

运行测试：

```bash
python -m pytest -q
```

测试会为每个用例创建临时 SQLite 数据库，并通过环境变量设置测试数据库路径，不读取生产 `.env`，不访问生产数据库，也不调用外部汇率接口。

如果 Windows 当前临时目录不可写，可以把 pytest 临时目录放在项目目录内：

```powershell
New-Item -ItemType Directory -Force .tmp | Out-Null
python -m pytest -q --basetemp .tmp\pytest-basetemp -p no:cacheprovider
```

## GitHub Actions

自动测试配置位于 `.github/workflows/tests.yml`。

触发条件：

- 任意 `push`
- 针对 `master` 的 `pull_request`

CI 行为：

- 使用 Ubuntu
- 使用 Python 3.12
- 安装 `requirements.txt` 和 `requirements-dev.txt`
- 设置 `APP_ENV=testing`
- 设置临时 `SECRET_KEY`
- 将 `DATABASE_PATH`、`LOG_DIR`、`BACKUP_DIR` 指向 GitHub runner 临时目录
- 执行 `python -m pytest -q`

CI 不读取生产 `.env`，不连接生产数据库，不执行部署、Tag 或 Release 操作。

## 生产部署结构

推荐结构：

```text
Internet
  -> Caddy/Nginx HTTPS 反向代理
  -> Gunicorn 127.0.0.1:8000
  -> Flask app
  -> SQLite data/accounting.db
```

部署示例文件：

- `deploy/accounting.service.example`：systemd 服务示例
- `deploy/Caddyfile.example`：Caddy 反向代理示例
- `gunicorn.conf.py`：Gunicorn 配置

生产启动示例：

```bash
export APP_ENV=production
export SECRET_KEY=replace-with-generated-random-value
gunicorn -c gunicorn.conf.py server:app
```

部署后建议执行：

```bash
python -c "from database import init_db; init_db(); print('ok')"
pytest
curl http://127.0.0.1:8000/health
```

不要把 Flask 开发服务器直接暴露到公网。

## 数据库备份

手动备份：

```bash
python scripts/backup_database.py
```

脚本会：

- 读取 `DATABASE_PATH`
- 将备份写入 `BACKUP_DIR`
- 使用 SQLite backup API 复制数据库
- 按 `BACKUP_RETENTION_DAYS` 清理过期备份

cron 示例：

```cron
0 3 * * * cd /opt/accounting-system && . /opt/accounting-system/venv/bin/activate && python scripts/backup_database.py >> /opt/accounting-system/logs/backup.log 2>&1
```

恢复前请先停止服务，并保留当前数据库副本：

```bash
sudo systemctl stop accounting
cp data/accounting.db data/accounting.before-restore.db
cp backups/accounting-YYYY-MM-DD-HHMMSS.db data/accounting.db
python -c "import sqlite3; conn=sqlite3.connect('data/accounting.db'); print(conn.execute('PRAGMA integrity_check').fetchone()[0])"
sudo systemctl start accounting
curl https://example.com/health
```

## 国际化维护

更新用户可见文案后执行：

```bash
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations -l zh_CN
pybabel update -i messages.pot -d translations -l ja
python scripts/fill_translations.py
pybabel compile -d translations
```

需要提交：

- `messages.pot`
- `translations/zh_CN/LC_MESSAGES/messages.po`
- `translations/zh_CN/LC_MESSAGES/messages.mo`
- `translations/ja/LC_MESSAGES/messages.po`
- `translations/ja/LC_MESSAGES/messages.mo`

## 当前限制

- 仅启用 JPY 和 CNY 两种货币
- 汇率需要用户手动输入，没有实时汇率 API
- 当前没有英文界面
- 当前没有 CSV 导出功能
- 当前没有全文搜索功能
- 预算支持保存和更新，当前没有单独删除预算接口
- 没有管理员后台；反馈由服务器管理员通过脚本查看
- 没有支付、订阅、第三方登录、OCR、AI 自动记账、App 或小程序
- SQLite 适合小规模使用；高并发或多人重度使用前应评估数据库方案
- 深色模式当前保持停用状态

## 后续开发计划

- CSV 导出
- 更细的搜索和筛选能力
- 手机端体验优化
- 预算提醒
- 周报/月报
- 数据恢复流程完善
- 更多货币支持
- 更完整的国际化
- 在明确需求后再评估 PostgreSQL、管理员后台或其他大型能力

## 安全提醒

- 不提交 `.env`
- 不提交 SQLite 数据库、备份文件或日志
- 不在公网开启 Debug
- 生产环境必须设置随机 `SECRET_KEY`
- 生产环境建议启用 HTTPS，并设置安全 Cookie
- 生产前备份 `data/accounting.db`
- 不在 README、issue、日志或截图中暴露服务器 IP、邮箱密码、API 密钥、用户数据或生产路径敏感信息
- 公开分享链接只应包含月度汇总，不应展示完整交易明细或个人敏感信息

## License

当前仓库尚未包含 `LICENSE` 文件，许可证状态未声明。公开发布前建议明确选择并提交许可证文件。
