# 日常消费 —— 设计文档

> 状态快照：数据模型、页面、统计口径的权威来源。第四版「日常消费」模块。
> 参考数据：记账 App 导出的 `myMoney-2.xls`（2025 全年，支出 1384 条 + 收入 19 条）。

## 1. 这是什么

在既有的旅游记录网站里新增一个**与旅程互不相干**的模块：记录日常收支流水，并按月/年做统计分析。

顶栏左上角由单一品牌变成**两个模块入口**（`✈ 旅行记录` / `💰 日常消费`），右侧子菜单随当前模块切换。两个模块各自独立，数据层零外键关联。

**不做**（YAGNI）：预算、账户与余额、多币种、成员/项目、附件图片、与旅程花费打通。

## 2. 数据来源与列映射

导入文件为记账 App 导出的 `.xls`，两个 sheet（`支出` / `收入`），列结构相同：

| xls 列 | 处理 |
|---|---|
| 交易类型 | → `record.kind`（也决定分类树走哪个分支） |
| 日期 | → `record.date`，**时分秒丢弃，只记到日** |
| 一级分类 | → `expense_category`（`parent_id IS NULL`）按名查/建 |
| 二级分类 | → `expense_category`（parent = 上面那条）按名查/建 → `record.category_id` |
| 支出账户 / 收入账户 | **丢弃**（示例数据全是「现金」） |
| 金额 | → `record.amount` |
| 成员 | **丢弃** |
| 商家 | → `expense_tag` 按名查/建 → `record.tag_id`（空值不建标签，留 NULL） |
| 项目 | **丢弃**（全空） |
| 备注 | → `record.note` |

「商家」列实际内容是「超市 / 停车缴费 / 充电 / 京鲁菜 / 咖啡 / 衣服鞋包」这类**标签语义**而非真实商户名，因此建成标签表而不是第三级分类——它并不严格从属二级分类（如「充电」挂在「私家车费用」下）。

## 3. 数据模型

三张新表，与旅程模块（Trip / Day / City / Person …）**无任何外键**。

### 3.1 `expense_category` 消费分类（自关联两级树）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | Integer | PK | |
| `parent_id` | Integer | FK → `expense_category.id`, NULL | **NULL = 一级**；非空 = 二级，指向其一级 |
| `name` | String(50) | NOT NULL | 「食品酒水」「午餐」 |
| `kind` | String(4) | NOT NULL | `支出` / `收入`；二级必须与父级一致 |
| `icon` | String(8) | NULL | emoji，列表与图表图例用 |
| `sort_order` | Integer | NOT NULL, default 0 | 同层手动排序 |

- 唯一约束：`UNIQUE(kind, parent_id, name)`——同父下不重名；不同一级下可有同名二级
- 索引：`parent_id`
- 关系：`children`（自关联，按 `sort_order` 排序），`parent`（backref）
- **仅两层**：建/改二级时校验 `parent.parent_id IS NULL`
- **删除策略**：分类下有子分类或有流水 → 禁止删除，提示先迁移；不做级联删除

### 3.2 `expense_tag` 标签

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | Integer | PK | |
| `name` | String(30) | NOT NULL, UNIQUE | 「超市」「停车缴费」「京鲁菜」 |

- 全局唯一，不分收支，无层级
- **删除策略**：仍被流水引用 → 禁止删除
- 展示排序按「使用次数」动态计算，不存字段

### 3.3 `expense_record` 流水（主表）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | Integer | PK | |
| `kind` | String(4) | NOT NULL | `支出` / `收入`。冗余自 category，写入时校验一致——为免 join 直接筛选 |
| `date` | Date | NOT NULL | 只到日 |
| `category_id` | Integer | FK → `expense_category.id`, NOT NULL | 通常指向二级；只有一级的条目可直接指一级。一级经 `category.parent` 反查 |
| `tag_id` | Integer | FK → `expense_tag.id`, NULL | 一条流水最多一个标签 |
| `amount` | Numeric(12,2) | NOT NULL | **一律存正数**，正负由 `kind` 决定；Python 侧 `Decimal` |
| `note` | Text | NULL | 备注（「山姆」「muji」「北投停车」） |
| `source` | String(8) | NOT NULL, default `manual` | `manual` / `import` |
| `fingerprint` | String(40) | NULL, UNIQUE | 导入去重指纹；手动录入为 NULL（SQLite 允许多 NULL 并存） |
| `created_at` | DateTime | NOT NULL, default now | 同日多条的稳定排序依据 |

- 索引：`(kind, date)`、`date`、`category_id`、`tag_id`
- 默认排序：`ORDER BY date DESC, created_at DESC`

### 3.4 关联关系

```
expense_category ──┐ 自关联 parent_id (NULL = 一级)
      │ 1          └─< children (二级)
      │ N
expense_record
      │ N
      │ 1
expense_tag
```

- `ExpenseCategory 1 ─ N ExpenseRecord`（一条流水一个分类）
- `ExpenseCategory 1 ─ N ExpenseCategory`（一级下挂二级，仅两层）
- `ExpenseTag 1 ─ N ExpenseRecord`（标签可空）

### 3.5 默认分类树

`DEFAULT_CATEGORIES` 常量，库中分类为空时 seed；导入遇到未知分类自动补建。

```
支出  食品酒水 → 早餐 / 午餐 / 晚餐 / 甜品饮料 / 零食熟食 / 面包糕点 / 烟酒茶
      买买买买 → 超市市场 / 网购 / 商场 / 日用品 / 衣服鞋包 / 电子产品 / 玩具
      行车交通 → 私家车费用 / 打车 / 公共交通 / 租车 / 维修保养
      休闲娱乐 → 旅游度假 / 休闲玩乐 / 电影音乐会 / 运动健身 / 景点门票
      居家物业 → 房租 / 水电煤气 / 物业管理
      医疗保健 → 治疗费 / 药品费
      金融保险 → 保险 / 行权
      学习进修 → 书报杂志 / 培训进修
      交流通讯 → 手机费 / 上网费
      其他杂项 → 其他支出
收入  职业收入 → 工资收入 / 奖金收入
      其他收入 → 房租收入
```

## 4. 导入与去重

指纹（写入 `fingerprint`，唯一索引）：

```
sha1("kind|date|一级分类|二级分类|金额|商家|备注|同键序号")
```

「同键序号」= 同一份文件内该自然键第几次出现（0,1,2…），用于区分「同天同金额同备注」的两笔真实消费。效果：

- 同一份文件重复导入 → 全部命中、全部跳过
- 两份有重叠的文件 → 重叠部分只保留一份
- 手动录入的条目 `fingerprint` 为 NULL，不参与去重，导入不会覆盖它们

导入完成后展示摘要：**新增 N 条 / 跳过 M 条 / 新建分类 X 个 / 新建标签 Y 个**。

按示例文件跑一遍的预期：1384 条支出 + 19 条收入，标签 36 个。

## 5. 分层与文件

```
app/models/expense.py            ExpenseCategory / ExpenseTag / ExpenseRecord + DEFAULT_CATEGORIES
app/services/expense_import.py   解析两个 sheet → 查建分类/标签 → 指纹去重写入 → 返回统计
app/services/expense_stats.py    月度、年度、整体统计、分类走势聚合 + 共用聚合小工具（一级/二级分类、标签排行；纯查询，无 HTTP）
app/blueprints/expenses.py       url_prefix=/expenses
app/templates/expenses/          list / form / monthly / yearly / overview / trends / import / categories .html
                                 _list_results / _item_row / _inline_edit_form（流水行内编辑片段）
                                 _stats_macros.html（月/年/总览共用 KPI·环图·排行榜宏）
app/static/expenses-stats.js     月/年/总览/走势共用图表工具（调色板、金额格式化、环图工厂、走势控制器）
```

既有的 `app/services/import_expense.py` 是**旅程专用**的（要匹配 Trip 的 Day 与申报币种），语义不同，本模块另起 `expense_import.py`，不改动它。

## 6. 页面

| 路由 | 内容 |
|---|---|
| `GET /expenses/` | 流水列表：按月分组 + 吸顶月份标题与当月小计（复用旅程列表的分组样式）；筛选 年月 / 收支 / 一级·二级分类 / 标签（含「空」= 筛无标签记录）/ 备注关键词。点击某行原地下拉成表单、异步保存不刷新页面 |
| `GET,POST /expenses/new`<br>`GET,POST /expenses/<id>/edit`<br>`POST /expenses/<id>/delete` | 单条增删改：日期、收支、分类（一级联动二级）、金额、标签（单选下拉，可新建）、备注。`edit` 带 `X-Requested-With` 时返回行内编辑片段（GET）或更新后的行 JSON（POST），供流水页异步编辑 |
| `GET /expenses/monthly?ym=YYYY-MM` | 当月仪表盘 |
| `GET /expenses/yearly?year=YYYY` | 年度分析 |
| `GET /expenses/overview` | 整体统计：跨全部年份的对比看板 |
| `GET /expenses/trends` | 分类走势：选一个维度（一级/二级分类或标签）看逐年金额折线，点某年在下方多列看当年 Top 50 消费 |
| `GET /expenses/trends/records?key=&year=` | 走势页右侧数据源：某维度某年金额最高的前 50 笔（内部 XHR，按需拉取） |
| `GET,POST /expenses/import` | 上传 `.xls`，写入后展示结果摘要；页内含危险操作区：`POST /expenses/clear` 清空全部或按年清空流水 |
| `GET,POST /expenses/categories` | 分类树增删改排序 + 标签管理 |

## 7. 统计口径

**月度概览**（`/expenses/monthly`）

- 当月总支出、总收入、结余（= 收入 − 支出）、日均支出（总支出 ÷ 当月天数）
- 环比：与上月总支出对比（金额差 + 百分比；上月为 0 时不显示百分比）
- 一级分类榜（一级占比环图 + 两栏榜）、二级分类榜、标签榜（三个榜同构，见下）
- 每日支出柱状图（当月每一天，无消费为 0）
- Top 10 单笔支出

**年度分析**（`/expenses/yearly`）

- 12 个月支出/收入双折线（当年未过完时只画到当前月，避免曲线砸到 0）
- 一级分类榜（一级占比环图 + 两栏榜；一级行附同比涨跌上色，与上一年同分类对比，上一年无数据则不显示同比）、二级分类榜、标签榜（三个榜同构，见下）
- 全年总支出（带同比）/总收入/结余（带结余率）/月均/日均/支出笔数
- 洞察条：消费最高月 / 最低月 / 最大单笔 / 有消费天数
- 月均、日均口径：完整过去年份按 12 月 / 当年实际天数（含闰年）；当年按已过月份 / 已过天数，避免被稀释

**整体统计**（`/expenses/overview`）——跨全部年份的对比看板

- 累计 KPI：累计支出/收入/结余（带结余率）/年均支出/日均支出/支出笔数
- 洞察条：记账跨度 / 消费最高年 / 最低年 / 最大单笔
- 逐年支出与收入双折线
- ⭐ 分类构成逐年变化：堆叠柱状图，每年一柱、柱内按一级分类分段；单独上色上限 7 类，其余并入「其他」段
- 全时段一级分类榜（一级占比环图 + 两栏榜）、二级分类榜、标签榜（三个榜同构，见下）
- 逐年明细表：年份 / 支出 / 收入 / 结余 / 结余率 / 支出同比（涨红降绿）——排在三个榜之后、页尾
- 口径：年均 = 累计支出 ÷ 有支出的年数；结余率 = 累计结余 ÷ 累计收入；年份区间按首末记录连续填满

**分类走势**（`/expenses/trends`）——单维度的逐年走势 + 当年 Top 消费

- 选一个维度：分类模式下一级联动二级（二级下拉含「整个〔一级〕」= 看一级合计），或标签模式可输入联想；分类树含支出与收入两类，标签跨两类汇总
- 满宽折线画该维度逐年金额（X 轴为全量记账跨度 first_year..last_year，某年无消费画 0；各维度共用一条时间轴），默认选中累计金额最高的维度
- 逐年明细表：年份 / 金额 / 同比（涨红降绿，客户端由序列算）/ 笔数，行可点选年份
- 点折线上任意年份（或点明细表某行）→ 下方按金额**从左到右、从上到下**多列（列宽 300px 自适应，宽屏约 3 列）展示该维度当年 **Top 50** 单笔，标题带当年金额与总笔数
- 服务端 `trend_stats()` 一次算好所有维度逐年金额/笔数序列内联为 JSON，纯前端切换；当年 Top 50 明细由 `trend_year_records()` 经 `/trends/records` 按需拉取（避免把上万条明细塞进页面）

**三个排行榜：一级分类榜 / 二级分类榜 / 标签榜**（三页共用，显示顺序即此）

- 都是**两栏 Miller 列，同一套列样式与渲染工具**（`expBoard` + `expMillerItem` / `expMillerRecords`）：**左栏排行**（固定常驻，金额降序），点某项 → **右栏该项名下单笔支出 Top 15**（按金额降序，显示日期/分类/标签/备注）。进页面默认选中金额第一项，右栏不空。
- **一级分类榜**：所有一级，副文 占比（年度页附同比涨跌上色）；左栏顶部居中放一级占比环图。名下单笔跨其所有二级。
- **二级分类榜**：所有真正的二级**跨一级全局排序**（不按一级分组），副文 所属一级 · 占总比；直接挂在一级、无二级的记录跳过。
- **标签榜**：所有标签，副文 笔数；没打标签的记录跳过。
- 每行标题独占一行、金额落副行右侧（窄栏里七位数金额才不挤没标题）；一项的单笔沿用该项调色板色；窄屏整栏横向滚动。
- 服务端 `category_level1_board` / `category_level2_board` / `tag_drilldown` 各算好整棵内联为 JSON，纯前端交互。

金额一律 `Decimal`，两位四舍五入，仅人民币。

## 8. 导航

`base.html` 顶栏左侧改为两个模块入口，当前模块高亮；右侧子菜单按 `request.blueprint` 切换：

- **旅行记录**：旅程 / 足迹 / 创建 / 设置
- **日常消费**：流水 / 月度 / 年度 / 总览 / 走势 / 导入 / 分类

## 9. 测试

TDD，`tests/` 与模块一一对应：

- `tests/test_expense_models.py`——两级约束、删除策略、唯一约束
- `tests/test_expense_import.py`——列映射、日期截断、分类/标签自动建、指纹去重（重复导入零新增）
- `tests/test_expense_stats.py`——月度/年度各项口径、环比同比边界（除零、无上期数据）
- `tests/test_expenses_blueprint.py`——列表筛选（含空标签）、增删改（含行内异步编辑）、清空全部/按年、导入流程

## 10. 数据库

新表由 `db.create_all()` 首次启动自动创建，不触碰既有表，无需迁移（见 DECISIONS D19）。动手前备份 `instance/travel.db`。
