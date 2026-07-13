# 旅游记录网站 ✈️

一个**纯私人**的本地旅游记录网站：记录每次旅行的行程、每天的吃/玩/购物/住宿/交通、花费、配图与日记。无账号、无多用户、本地单机运行。

首页是一个 3D 地球，用弧线展示所有旅程的行程路线；每个旅程有详情页（按天记录）和统计页（花费环图、按城市/按天、里程、Top 消费等）。

## 技术栈

Python + Flask + SQLite + Jinja2（服务端渲染）+ Chart.js（图表）+ Globe.gl/D3（首页地球）。图片存本地 `uploads/`，城市坐标自动地理编码。

## 如何运行

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python run.py        # 访问 http://localhost:8000
pytest -v            # 运行测试
```

数据库 `instance/travel.db` 首次启动自动创建；图片存 `uploads/`。
默认端口 8000（避开 macOS AirPlay 占用的 5000）；可用 `PORT=xxxx python run.py` 覆盖。

## 目录结构

```
app/
├── __init__.py        应用工厂 create_app
├── config.py          配置（SECRET_KEY、DB 路径，env 可覆盖）
├── extensions.py      db 等扩展实例
├── blueprints/        路由层（按功能分蓝图，只管 HTTP）
├── models/            数据层（SQLAlchemy 模型，只管数据）
├── services/          业务逻辑（无 HTTP，可独立测试）
├── templates/         Jinja2 模板
└── static/            style.css + form.js + 地球前端
run.py                 启动入口
tests/                 pytest，每个模块对应一个测试文件
instance/travel.db     SQLite（首次启动自动建，已 gitignore）
uploads/               图片（已 gitignore）
```

## 更多文档

给 Claude Code 协作用的项目入口、数据模型、设计决策等详见 [CLAUDE.md](CLAUDE.md)。
