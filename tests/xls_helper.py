import io
import xlwt

HEADER = ["交易类型", "日期", "一级分类", "二级分类", "支出账户",
          "金额", "成员", "商家", "项目", "备注"]


def make_xls_bytes(rows, sheet_name="支出"):
    """按记账 App 导出格式生成一个内存 .xls，供测试上传/解析用。
    rows: 每项 dict，需含 date/category/account/amount/note，其余列可省略。
    """
    wb = xlwt.Workbook()
    sheet = wb.add_sheet(sheet_name)
    for c, h in enumerate(HEADER):
        sheet.write(0, c, h)
    for r, row in enumerate(rows, start=1):
        sheet.write(r, 0, "支出")
        sheet.write(r, 1, row["date"])
        sheet.write(r, 2, row["category"])
        sheet.write(r, 3, row.get("subcategory", ""))
        sheet.write(r, 4, row["account"])
        sheet.write(r, 5, row["amount"])
        sheet.write(r, 6, row.get("member", ""))
        sheet.write(r, 7, row.get("merchant", ""))
        sheet.write(r, 8, row.get("project", ""))
        sheet.write(r, 9, row["note"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
