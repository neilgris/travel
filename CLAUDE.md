# CLAUDE.md — 旅游记录网站

> 新会话先读这里。本文件是项目入口，指向其它文档。

## 这是什么

一个**纯私人**的本地旅游记录网站：记录每次旅行的行程、每天的吃/玩/购物/住宿/交通、花费、配图与日记。无账号、无多用户、本地单机运行。

## 文档地图

| 文档 | 用途 |
|------|------|
| **本文件 CLAUDE.md** | 项目概览、技术栈、如何运行、目录结构、约定 |
| [docs/specs/2026-06-30-travel-journal-design.md](docs/specs/2026-06-30-travel-journal-design.md) | 需求与设计（数据模型、页面、统计的权威来源） |
| [DECISIONS.md](DECISIONS.md) | 关键决策流水账（为什么这样选） |
| [ROADMAP.md](ROADMAP.md) | 版本里程碑与功能清单（活文档，上线勾选，未完成项可随时捡起） |
| [docs/plans/2026-06-30-travel-journal-v1.md](docs/plans/2026-06-30-travel-journal-v1.md) | 第一版实现计划（13 个 TDD 任务） |

## 技术栈

Python + Flask + SQLite + Jinja2（服务端渲染）+ Chart.js（图表）。图片存本地 `uploads/`，城市坐标自动地理编码。

## 数据模型（速览）

```
Trip 旅程 ──1:N── Leg 行程段 (有序: 出发城市→到达城市 + 出行方式)
   │                 └──> City 城市 (复用, 含经纬度)
   ├──1:N── Day 某天 (日期, 所在城市, 日记)
   │            ├──1:N── Entry 记录 (类别/标题/金额/币种)
   │            ├──1:N── DayImage 当天配图
   │            └──> City
   ├──M:N── Person 同行人 (复用: 姓名, 照片)
   └──1:N── TripCurrency (币种, 汇率: 1人民币=?外币)
```

- Trip 的城市/出行方式由 **Leg 推导**，不单独存（无 TripCity 表）。
- Leg 与 Day 不直接关联，通过 City 间接相连。
- Entry 类别：吃饭 / 游玩 / 购物 / 住宿 / 交通。
- 花费换算：`人民币 = 外币 ÷ 汇率`。

详见设计文档第 3 节。

## 目录结构

```
app/
├── __init__.py        应用工厂 create_app
├── config.py          配置（SECRET_KEY、DB 路径，env 可覆盖）
├── extensions.py      db 等扩展实例
├── blueprints/        路由层（按功能分蓝图，只管 HTTP）
│   ├── main.py        默认入口 `/`（重定向到日常消费）、地球首页 `/travel`、uploads 静态
│   ├── trips.py       旅程 CRUD、详情、统计、记录录入
│   └── settings.py    同行人 / 城市管理
├── models/            数据层（SQLAlchemy 模型，只管数据）
│   ├── city.py        City
│   ├── person.py      Person
│   ├── trip.py        Trip / Leg / TripCurrency / TripPerson
│   └── day.py         Day / Entry / DayImage
├── services/          业务逻辑（无 HTTP，可独立测试）
│   ├── geocoding.py   城市坐标地理编码（Nominatim）
│   ├── exchange.py    实时汇率查询（open.er-api.com）
│   ├── stats.py       花费换算与单旅程统计
│   ├── distance.py    旅程里程（行程段城市间 haversine 直线距离累加）
│   ├── uploads.py     图片上传保存
│   ├── import_expense.py  记账 .xls 解析与匹配（导入用）
│   ├── expense_recurring.py 固定收支水位线补记（进模块时把缺的月份补到今天）
│   └── globe.py       首页地球数据（Leg→弧线 + 城市点）
├── templates/         Jinja2 模板（trips/ settings/ + base.html + home.html 地球页）
└── static/            style.css + form.js + 地球前端（globe-home 控制器 / globe-gl 写实·卫星 / globe-d3 矢量）；vendor/ 离线 Globe.gl·three·d3·topojson·地球贴图·地形·矢量详情层（land-50m/admin1/lakes/rivers 放大懒加载；卫星瓦片走 Esri，联网）
run.py                 启动入口
tests/                 pytest，每个模块对应一个测试文件
instance/travel.db     SQLite（首次启动自动建，已 gitignore）
uploads/               图片（已 gitignore）；trips/{trip_id}/ 存旅程配图、people/ 存同行人照片
```

## 约定

- **TDD**：先写失败测试再实现；`tests/` 与模块一一对应。
- **分层**：路由进 `blueprints/`，业务逻辑进 `services/`，`models/` 只管数据；蓝图里不写复杂逻辑。
- **金额**：一律 `Decimal`，换算 `人民币 = 外币 ÷ 汇率`，两位四舍五入。
- **图片**：存 `uploads/`，按归属分目录——旅程配图落 `uploads/trips/{trip_id}/`，同行人照片落 `uploads/people/`；库里只存相对路径（含子目录）。
- **文档**：改动按下方「文档同步纪律」与 [DECISIONS.md](DECISIONS.md) D6 的规则同步。

## 版本

- **第一版**：记录流程 + 单旅程统计；旅程页仅列表概要。
- **第二版（已上线）**：首页 3D 地球路线展示（Globe.gl，用 Leg + City 坐标画弧线）。见 [docs/specs/2026-07-08-globe-home-design.md](docs/specs/2026-07-08-globe-home-design.md)。
- **第三版（进行中）**：回顾·统计·分享——旅程故事页、那年今日、人生足迹、年度报告、演示模式、静态导出等。清单与进度见 [ROADMAP.md](ROADMAP.md)。

## 如何运行

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python run.py        # 访问 http://localhost:8000
pytest -v            # 运行测试
```

数据库 `instance/travel.db` 首次启动自动创建；图片存 `uploads/`。
默认端口 8000（避开 macOS AirPlay 占用的 5000）；可用 `PORT=xxxx python run.py` 覆盖。

## 文档同步纪律 ⚠️

文档分四类，更新规则由「类型」决定，**不是每份每次都改**（完整版见 [DECISIONS.md](DECISIONS.md) D6）：

| 文档 | 类型 | 何时更新 |
|------|------|----------|
| 设计文档 spec | 状态快照 | 改**数据模型/页面/统计/需求**时同步；上线/删**功能**时改「功能总览」节 |
| 本文件 CLAUDE.md | 入口/地图 | 改**结构/技术栈/怎么跑**时 |
| DECISIONS.md | 追加日志 | 有**新取舍/踩坑**时**追加**（不改旧条目） |
| ROADMAP.md | 活清单 | **版本规划变化**时改；功能**上线**时勾选；只记做什么，不记怎么做 |
| docs/plans/* | 一次性 | 计划做完即归档，**不再维护** |

> 改 bug / 调样式 / 加测试 → 只靠 commit message 记录，**不碰文档**。
> 一次迭代合并前自检：对照上表，该动的动了、不该动的别动。
