import io
import xlwt

HEADER = ["交易类型", "日期", "一级分类", "二级分类", "支出账户",
          "金额", "成员", "商家", "项目", "备注"]


def make_expense_xls_bytes(expense_rows=None, income_rows=None):
    """按记账 App 导出格式生成内存 .xls，含「支出」「收入」两个 sheet。
    每行 dict: date/cat1/cat2/amount，可选 merchant/note/account/member。
    """
    wb = xlwt.Workbook()
    for sheet_name, kind, rows in (("支出", "支出", expense_rows or []),
                                    ("收入", "收入", income_rows or [])):
        sheet = wb.add_sheet(sheet_name)
        for c, h in enumerate(HEADER):
            sheet.write(0, c, h)
        for r, row in enumerate(rows, start=1):
            sheet.write(r, 0, kind)
            sheet.write(r, 1, row["date"])
            sheet.write(r, 2, row["cat1"])
            sheet.write(r, 3, row["cat2"])
            sheet.write(r, 4, row.get("account", "现金"))
            sheet.write(r, 5, row["amount"])
            sheet.write(r, 6, row.get("member", ""))
            sheet.write(r, 7, row.get("merchant", ""))
            sheet.write(r, 8, row.get("project", ""))
            sheet.write(r, 9, row.get("note", ""))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
