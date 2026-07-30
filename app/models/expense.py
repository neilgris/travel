import datetime as dt
from app.extensions import db

EXPENSE_KINDS = ["支出", "收入"]

# 库中一级分类为空时的 seed 数据：{kind: {一级名: [二级名, ...]}}。
# 从 myMoney 示例文件（2025 全年）实际出现的分类归拢而来。
# 二级分类只按「渠道/场景」分（超市市场 / 网购 / 商场、早餐 / 午餐 / 晚餐），
# 「买什么」交给标签（衣服鞋包、电子产品、烟酒茶…），两边不重复设同名维度。
DEFAULT_CATEGORIES = {
    "支出": {
        "食品酒水": ["早餐", "午餐", "晚餐", "甜品饮料", "零食熟食", "面包糕点"],
        "买买买买": ["超市市场", "网购", "商场"],
        "行车交通": ["私家车费用", "打车", "公共交通", "租车"],
        "休闲娱乐": ["旅游度假", "休闲玩乐", "电影音乐会", "运动健身", "景点门票", "个人护理"],
        "居家物业": ["房租", "水电煤气", "物业管理"],
        "医疗保健": ["公立医疗", "私立医疗", "药品费"],
        "金融保险": ["保险", "行权"],
        "学习进修": ["书报杂志", "培训进修"],
        "交流通讯": ["手机费", "上网费"],
        "其他杂项": ["其他支出"],
    },
    "收入": {
        "职业收入": ["工资收入", "奖金收入"],
        "其他收入": ["房租收入"],
    },
}

# 默认分类图标（一级 + 二级，按分类名匹配；seed 与展示各处的图标都来自这里）。
# 分类名互不重名，用一张扁平表即可。表里保留了若干已不在 seed 里的名字（导入 .xls 时
# 可能又冒出来，或手工新建时能自动配上图标），所以条目比 seed 多是正常的。
CATEGORY_ICONS = {
    # 一级
    "食品酒水": "🍜", "买买买买": "🛍️", "行车交通": "🚗", "休闲娱乐": "🎮",
    "居家物业": "🏠", "医疗保健": "💊", "金融保险": "💰", "学习进修": "📚",
    "交流通讯": "📱", "其他杂项": "🗂️", "职业收入": "💼", "其他收入": "💵",
    # 二级 · 食品酒水
    "早餐": "🍳", "午餐": "🍱", "晚餐": "🍲", "甜品饮料": "🍰",
    "零食熟食": "🍪", "面包糕点": "🥐", "烟酒茶": "🍶",
    # 二级 · 买买买买
    "超市市场": "🛒", "网购": "📦", "商场": "🏬", "日用品": "🧴",
    "衣服鞋包": "👗", "电子产品": "💻", "玩具": "🧸",
    # 二级 · 行车交通
    "私家车费用": "🚙", "打车": "🚕", "公共交通": "🚌", "租车": "🔑", "维修保养": "🔧",
    # 二级 · 休闲娱乐
    "旅游度假": "🏖️", "休闲玩乐": "🎉", "电影音乐会": "🎬",
    "运动健身": "🏋️", "景点门票": "🎫", "个人护理": "💇",
    # 二级 · 居家物业
    "房租": "🏘️", "水电煤气": "💡", "物业管理": "🏢",
    # 二级 · 医疗保健
    "公立医疗": "🏥", "私立医疗": "🩺", "药品费": "💊",
    # 二级 · 金融保险
    "保险": "🛡️", "行权": "📈",
    # 二级 · 学习进修
    "书报杂志": "📖", "培训进修": "🎓",
    # 二级 · 交流通讯
    "手机费": "📶", "上网费": "🌐",
    # 二级 · 其他杂项
    "其他支出": "🗃️", "充钱储值": "💳",
    # 一级 · 人情往来（导入常见但不在 seed 里的一级分类）
    "人情往来": "🧧",
    # 二级 · 人情往来 / 其他常见二级（导入数据里出现过、seed 未覆盖）
    "红包": "🧧", "孝敬家长": "🎁", "请客": "🍽️", "送礼": "🎁",
    "治疗费": "🏥", "保健费": "🩺", "美容费": "💅", "腐败聚会": "🍻", "座机费": "☎️", "代购": "🧳",
    "银行手续": "🏦", "公积金": "🏦",
    "经营所得": "💹", "礼金收入": "🧧", "中奖收入": "🎉", "其他": "➕",
}


def guess_icon(name):
    """按分类名猜一个 emoji；没有已知匹配时返回 None（由调用方决定是否留空）。"""
    return CATEGORY_ICONS.get(name)


class ExpenseCategory(db.Model):
    __tablename__ = "expense_category"
    __table_args__ = (
        db.UniqueConstraint("kind", "parent_id", "name", name="uq_expense_category_kind_parent_name"),
    )
    id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(db.ForeignKey("expense_category.id"))
    name = db.Column(db.String(50), nullable=False)
    kind = db.Column(db.String(4), nullable=False)
    icon = db.Column(db.String(8))
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    children = db.relationship("ExpenseCategory", backref=db.backref("parent", remote_side=[id]),
                               order_by="ExpenseCategory.sort_order, ExpenseCategory.id",
                               cascade="all, delete-orphan")

    @property
    def is_top_level(self):
        return self.parent_id is None

    @property
    def display_icon(self):
        """展示用图标：优先自己的图标，没有则借用一级分类的图标。"""
        return self.icon or (self.parent.icon if self.parent else None)

    def __repr__(self):
        return f"<ExpenseCategory {self.name}>"


class ExpenseTag(db.Model):
    __tablename__ = "expense_tag"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), nullable=False, unique=True)
    # 标签组（菜系/火锅/甜品饮品…）：标签不挂在分类树上，一级分类能按金额推出来，
    # 但「菜系 vs 火锅」这层是语义、数据里没有，只能手工指定。空 = 未分组，直接挂在一级分类下。
    # 列名不用 group——那是 SQL 保留字。
    group_name = db.Column(db.String(20))

    def __repr__(self):
        return f"<ExpenseTag {self.name}>"


class ExpenseRule(db.Model):
    """固定收支规则：每 interval_months 个月、在 1 号记一笔固定金额。

    一条规则 = 一个金额 + 一段时间。房租涨价就给旧规则填上 end_month、另开一条新的，
    不在单条规则里塞多段金额区间——查询和展示都简单，代价只是规则条数多几行。
    """
    __tablename__ = "expense_rule"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    kind = db.Column(db.String(4), nullable=False)
    category_id = db.Column(db.ForeignKey("expense_category.id"), nullable=False)
    tag_id = db.Column(db.ForeignKey("expense_tag.id"))
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    # 间隔月数：1=每月，3=每季度，12=每年。相位由 start_month 决定（起始 2 月 + 间隔 3
    # → 2/5/8/11 月），所以不需要单独存「哪几个月」。
    interval_months = db.Column(db.Integer, nullable=False, default=1)
    # 起止都存当月 1 号——记录本来就固定落 1 号，两边对齐省掉来回换算。end_month 含当月，
    # 留空 = 一直有效。
    start_month = db.Column(db.Date, nullable=False)
    end_month = db.Column(db.Date)
    note = db.Column(db.Text)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=lambda: dt.datetime.now(dt.timezone.utc))

    category = db.relationship("ExpenseCategory")
    tag = db.relationship("ExpenseTag")

    @property
    def interval_label(self):
        if self.interval_months == 1:
            return "每月"
        if self.interval_months == 12:
            return "每年"
        return f"每 {self.interval_months} 个月"

    def __repr__(self):
        return f"<ExpenseRule {self.name} {self.amount}/{self.interval_months}月>"


class ExpenseRecord(db.Model):
    __tablename__ = "expense_record"
    __table_args__ = (
        db.Index("ix_expense_record_kind_date", "kind", "date"),
        # 一条规则同一天只可能有一笔，自动补记的幂等由数据库兜底。SQLite 里 NULL != NULL，
        # 所以手工/导入记录（rule_id 为空）互不影响。
        db.UniqueConstraint("rule_id", "date", name="uq_expense_record_rule_date"),
    )
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(4), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    category_id = db.Column(db.ForeignKey("expense_category.id"), nullable=False, index=True)
    tag_id = db.Column(db.ForeignKey("expense_tag.id"), index=True)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    note = db.Column(db.Text)
    source = db.Column(db.String(8), nullable=False, default="manual")
    fingerprint = db.Column(db.String(40), unique=True)
    # 由哪条固定收支规则生成；手工与导入的记录留空。
    rule_id = db.Column(db.ForeignKey("expense_rule.id"), index=True)
    created_at = db.Column(db.DateTime, default=lambda: dt.datetime.now(dt.timezone.utc))

    category = db.relationship("ExpenseCategory")
    tag = db.relationship("ExpenseTag")
    rule = db.relationship("ExpenseRule")

    def __repr__(self):
        return f"<ExpenseRecord {self.kind} {self.date} {self.amount}>"


def seed_default_categories():
    """库中一级分类为空时写入默认分类树；已有数据则不动。"""
    if ExpenseCategory.query.filter_by(parent_id=None).first():
        return
    for kind, tree in DEFAULT_CATEGORIES.items():
        for order1, (name1, children) in enumerate(tree.items()):
            top = ExpenseCategory(name=name1, kind=kind, sort_order=order1,
                                  icon=CATEGORY_ICONS.get(name1))
            db.session.add(top)
            db.session.flush()
            for order2, name2 in enumerate(children):
                db.session.add(ExpenseCategory(name=name2, kind=kind, parent_id=top.id, sort_order=order2,
                                               icon=CATEGORY_ICONS.get(name2)))
    db.session.commit()


# 标签组：走势页左栏把同一个一级分类下的标签再分一层，主要是「食品酒水」下几十个吃的标签
# 需要（菜系 / 火锅 / 甜品饮品…）。顺序即展示顺序。
TAG_GROUPS = ["中餐菜系", "火锅", "异国料理", "甜品饮品", "便餐小食"]

# 首次填充用的猜测规则：先按名字精确命中，再按后缀兜底。只在「一个标签组都还没设过」时跑
# 一次，之后完全以手工设置为准——猜错的（快餐/海鲜这类）在分类管理页改一下就固定了。
_TAG_GROUP_GUESS = {
    "日料": "异国料理", "西餐": "异国料理", "东南亚餐": "异国料理", "韩餐": "异国料理",
    "快餐": "便餐小食", "小吃": "便餐小食", "轻食": "便餐小食", "主食": "便餐小食",
    "烧烤": "便餐小食", "食堂": "便餐小食", "海鲜": "中餐菜系",
    "蛋糕": "甜品饮品", "咖啡": "甜品饮品", "奶茶": "甜品饮品", "酒吧": "甜品饮品",
    "冰激凌": "甜品饮品", "甜品": "甜品饮品", "果汁": "甜品饮品", "瓶装饮料": "甜品饮品",
}


def guess_tag_group(name):
    """按标签名猜它属于哪个标签组；猜不出返回 None（留空 = 未分组）。"""
    if name in _TAG_GROUP_GUESS:
        return _TAG_GROUP_GUESS[name]
    if name.endswith("火锅"):
        return "火锅"
    if name.endswith("菜"):
        return "中餐菜系"
    return None


def seed_tag_groups():
    """所有标签都还没设过分组时，按 guess_tag_group 预填一遍；已有任一分组则不动。
    与 seed_default_categories 同一套路：只兜首次，不覆盖手工结果。"""
    if ExpenseTag.query.filter(ExpenseTag.group_name.isnot(None)).first():
        return
    changed = False
    for tag in ExpenseTag.query.all():
        group = guess_tag_group(tag.name)
        if group:
            tag.group_name = group
            changed = True
    if changed:
        db.session.commit()
