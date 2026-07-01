import datetime as dt
from decimal import Decimal
import xlrd

CATEGORY_MAP = {
    "旅游餐饮费": "吃饭",
    "旅游买买买": "购物",
    "旅游娱乐费": "游玩",
    "旅游交通费": "交通",
    "旅游住宿费": "住宿",
    "其他消费": "其他消费",
}

ACCOUNT_CURRENCY_MAP = {
    "现金": "CNY",
    "港币": "HKD",
    "美元": "USD",
    "日元": "JPY",
}


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
