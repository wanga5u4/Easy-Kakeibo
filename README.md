# 简易记账系统

Flask 多用户记账系统，使用原生 SQLite 持久化数据。

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

## 数据库初始化

应用启动时会执行幂等 `init_db()`，会创建缺失的表和字段，不会清空已有用户、账目或预算。

也可以手动检查初始化：

```bash
python -c "from database import init_db; init_db(); print('ok')"
```

## 生产启动

生产环境请关闭 Debug，并通过 WSGI 服务器运行：

```bash
export APP_ENV=production
export SECRET_KEY=replace-with-a-long-random-secret
gunicorn --workers 2 --bind 127.0.0.1:8000 server:app
```

生产环境建议放在 Nginx/Caddy 等反向代理之后，并启用 HTTPS。

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
- 用户设置和会员展示页
