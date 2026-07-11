import datetime as dt
from decimal import Decimal
import xlrd

from app.models.day import COMMON_CURRENCIES

CATEGORY_MAP = {
    "旅游餐饮费": "吃饭",
    "旅游买买买": "购物",
    "旅游娱乐费": "游玩",
    "旅游交通费": "交通",
    "旅游住宿费": "住宿",
    "其他消费": "其他消费",
}

# 记账文件「账户/币种」列的中文 → ISO 币种码。
# 主表由 COMMON_CURRENCIES（币种码 ↔ 中文名 的权威来源）自动生成，避免这里再手维护一份
# 容易漏（曾漏掉欧元/瑞士法郎等）；再补现金/人民币与几个常见口语别名。
ACCOUNT_CURRENCY_MAP = {zh: code for code, zh, _flag in COMMON_CURRENCIES}
ACCOUNT_CURRENCY_MAP.update({
    "现金": "CNY", "人民币": "CNY",
    "美金": "USD",
    "港元": "HKD",
    "澳门币": "MOP",
    "新币": "SGD", "新加坡币": "SGD",
    "台币": "TWD", "新臺幣": "TWD",
    "韩币": "KRW", "韩元": "KRW",
    "澳大利亚元": "AUD",
    "加拿大元": "CAD",
    "阿联酋迪拉姆": "AED",
})


def parse_rows(file_obj):
    """读取记账 App 导出的 .xls（第一个 sheet），返回原始行列表（不做匹配判断）。
    file_obj: 任意有 .read() 的文件对象（Flask FileStorage 或 io.BytesIO）。
    """
    wb = xlrd.open_workbook(file_contents=file_obj.read())
    sheet = wb.sheet_by_index(0)
    rows = []
    for r in range(1, sheet.nrows):
        values = sheet.row_values(r)
        if str(values[0]).strip() != "支出":
            continue
        date_raw = str(values[1]).strip()
        if not date_raw:
            continue
        date = dt.datetime.strptime(date_raw.split(" ")[0], "%Y-%m-%d").date()
        rows.append({
            "date": date,
            "category_raw": str(values[2]).strip(),
            "account_raw": str(values[4]).strip(),
            "amount": Decimal(str(values[5])),
            "title": str(values[9]).strip()[:200],
        })
    return rows


def match_row(trip, row):
    """把一行原始数据匹配到 Entry 所需字段。
    返回 (matched, resolved)；resolved 里已解析对的字段给具体值，
    没对上的字段为 None，供待确认页面渲染对应的下拉框。
    """
    day = next((d for d in trip.days if d.date == row["date"]), None)
    category = CATEGORY_MAP.get(row["category_raw"])
    currency_code = ACCOUNT_CURRENCY_MAP.get(row["account_raw"])
    if currency_code and currency_code != "CNY":
        declared = {c.currency_code for c in trip.currencies}
        if currency_code not in declared:
            currency_code = None
    matched = day is not None and category is not None and currency_code is not None
    return matched, {
        "day_id": day.id if day else None,
        "date": row["date"],
        "category": category,
        "currency_code": currency_code,
        "amount": row["amount"],
        "title": row["title"],
    }
