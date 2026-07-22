"""日常消费记账 .xls 导入：解析「支出」「收入」两个 sheet，自动补建分类/标签，
按自然键指纹去重写入。与 services/import_expense.py（旅程专用，需匹配 Trip 的 Day
与申报币种）语义不同，互不复用。设计见 docs/specs/2026-07-20-daily-expense-design.md。
"""
import datetime as dt
import hashlib
from collections import Counter
from decimal import Decimal
import xlrd

from app.extensions import db
from app.models.expense import ExpenseCategory, ExpenseTag, ExpenseRecord, guess_icon

SHEET_KINDS = {"支出": "支出", "收入": "收入"}


def _fingerprint(kind, date, cat1, cat2, amount, tag, note, seq):
    raw = f"{kind}|{date.isoformat()}|{cat1}|{cat2}|{amount}|{tag}|{note}|{seq}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def parse_rows(file_obj):
    """读取记账 App 导出的 .xls，返回原始行列表（不做入库判断）。
    file_obj: 任意有 .read() 的文件对象（Flask FileStorage 或 io.BytesIO）。
    """
    wb = xlrd.open_workbook(file_contents=file_obj.read())
    rows = []
    seq_counter = Counter()
    for sheet_name, kind in SHEET_KINDS.items():
        if sheet_name not in wb.sheet_names():
            continue
        sheet = wb.sheet_by_name(sheet_name)
        for r in range(1, sheet.nrows):
            values = sheet.row_values(r)
            date_raw = str(values[1]).strip()
            if not date_raw:
                continue
            date = dt.datetime.strptime(date_raw.split(" ")[0], "%Y-%m-%d").date()
            cat1 = str(values[2]).strip()
            cat2 = str(values[3]).strip()
            amount = Decimal(str(values[5]))
            tag = str(values[7]).strip()
            note = str(values[9]).strip()
            key = (kind, date, cat1, cat2, amount, tag, note)
            seq = seq_counter[key]
            seq_counter[key] += 1
            rows.append({
                "kind": kind, "date": date, "cat1": cat1, "cat2": cat2,
                "amount": amount, "tag": tag, "note": note,
                "fingerprint": _fingerprint(kind, date, cat1, cat2, amount, tag, note, seq),
            })
    return rows


def _get_or_create_category(cache, kind, cat1, cat2):
    """返回 (最终分类, 本次新建的分类行数 0/1/2)。"""
    top_key = (kind, None, cat1)
    top = cache.get(top_key)
    created = 0
    if top is None:
        top = ExpenseCategory.query.filter_by(kind=kind, parent_id=None, name=cat1).first()
        if top is None:
            top = ExpenseCategory(kind=kind, parent_id=None, name=cat1, icon=guess_icon(cat1))
            db.session.add(top)
            db.session.flush()
            created += 1
        cache[top_key] = top
    if not cat2:
        return top, created
    sub_key = (kind, top.id, cat2)
    sub = cache.get(sub_key)
    if sub is None:
        sub = ExpenseCategory.query.filter_by(kind=kind, parent_id=top.id, name=cat2).first()
        if sub is None:
            sub = ExpenseCategory(kind=kind, parent_id=top.id, name=cat2, icon=guess_icon(cat2))
            db.session.add(sub)
            db.session.flush()
            created += 1
        cache[sub_key] = sub
    return sub, created


def _get_or_create_tag(cache, name):
    if not name:
        return None, False
    tag = cache.get(name)
    if tag is not None:
        return tag, False
    tag = ExpenseTag.query.filter_by(name=name).first()
    created = tag is None
    if tag is None:
        tag = ExpenseTag(name=name)
        db.session.add(tag)
        db.session.flush()
    cache[name] = tag
    return tag, created


def import_rows(rows):
    """把 parse_rows 的结果写入数据库，按 fingerprint 去重。
    返回 {"created": N, "skipped": M, "new_categories": X, "new_tags": Y}。
    """
    existing_fps = {fp for (fp,) in db.session.query(ExpenseRecord.fingerprint)
                    .filter(ExpenseRecord.fingerprint.isnot(None)).all()}
    cat_cache, tag_cache = {}, {}
    created = skipped = new_categories = new_tags = 0
    for row in rows:
        if row["fingerprint"] in existing_fps:
            skipped += 1
            continue
        category, cat_created = _get_or_create_category(cat_cache, row["kind"], row["cat1"], row["cat2"])
        new_categories += cat_created
        tag, tag_created = _get_or_create_tag(tag_cache, row["tag"])
        if tag_created:
            new_tags += 1
        db.session.add(ExpenseRecord(
            kind=row["kind"], date=row["date"], category_id=category.id,
            tag_id=tag.id if tag else None, amount=row["amount"],
            note=row["note"] or None, source="import", fingerprint=row["fingerprint"],
        ))
        existing_fps.add(row["fingerprint"])
        created += 1
    db.session.commit()
    return {"created": created, "skipped": skipped,
            "new_categories": new_categories, "new_tags": new_tags}
