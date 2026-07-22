import datetime as dt
from app.extensions import db

EXPENSE_KINDS = ["支出", "收入"]

# 库中一级分类为空时的 seed 数据：{kind: {一级名: [二级名, ...]}}。
# 从 myMoney 示例文件（2025 全年）实际出现的分类归拢而来。
DEFAULT_CATEGORIES = {
    "支出": {
        "食品酒水": ["早餐", "午餐", "晚餐", "甜品饮料", "零食熟食", "面包糕点", "烟酒茶"],
        "买买买买": ["超市市场", "网购", "商场", "日用品", "衣服鞋包", "电子产品", "玩具"],
        "行车交通": ["私家车费用", "打车", "公共交通", "租车", "维修保养"],
        "休闲娱乐": ["旅游度假", "休闲玩乐", "电影音乐会", "运动健身", "景点门票"],
        "居家物业": ["房租", "水电煤气", "物业管理"],
        "医疗保健": ["治疗费", "药品费"],
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
# 一级/二级分类名互不重名，用一张扁平表即可；"维修保养" 在行车交通/居家物业下重复出现，
# 图标合用同一个也说得通，故不按父级区分。
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
    "运动健身": "🏋️", "景点门票": "🎫",
    # 二级 · 居家物业
    "房租": "🏘️", "水电煤气": "💡", "物业管理": "🏢",
    # 二级 · 医疗保健
    "治疗费": "🏥", "药品费": "💊",
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
    "保健费": "🩺", "美容费": "💅", "腐败聚会": "🍻", "座机费": "☎️", "代购": "🧳",
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

    def __repr__(self):
        return f"<ExpenseTag {self.name}>"


class ExpenseRecord(db.Model):
    __tablename__ = "expense_record"
    __table_args__ = (
        db.Index("ix_expense_record_kind_date", "kind", "date"),
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
    created_at = db.Column(db.DateTime, default=lambda: dt.datetime.now(dt.timezone.utc))

    category = db.relationship("ExpenseCategory")
    tag = db.relationship("ExpenseTag")

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
