"""日常消费记账 .xls 导入：解析「支出」「收入」两个 sheet，自动补建分类/标签，
按自然键指纹去重写入。与 services/import_expense.py（旅程专用，需匹配 Trip 的 Day
与申报币种）语义不同，互不复用。设计见 docs/specs/2026-07-20-daily-expense-design.md。
"""
import datetime as dt
import hashlib
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
import xlrd

from app.extensions import db
from app.models.expense import ExpenseCategory, ExpenseTag, ExpenseRecord, guess_icon

SHEET_KINDS = {"支出": "支出", "收入": "收入"}


def natural_amount(amount):
    """金额归一化——**所有**算指纹的入口都必须过这一道，否则同一笔钱在不同入口
    算出来的指纹不一样：导入时拿到的是 xls 里的 float（18.1），手工填表拿到的是
    表单字符串（'18.50'），从库里读出来的是 Numeric(12,2)（Decimal('18.10')），
    直接塞进 f-string 是三种写法。
    先按库里的精度定死到两位（>2 位的源数据入库时本来就会被舍成两位），再走一趟
    float 去掉尾随 0——后面这步是为了跟历史指纹保持兼容，别让老库整批失效。"""
    quantized = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal(str(float(quantized)))


def natural_key(kind, date, cat1, cat2, amount, tag_name, note):
    """一条记录的自然键（归一化后的七元组）。导入解析、手工增改、批量改、重刷指纹
    都从这里拿 key，保证「同一条记录换个入口写进去，指纹还是同一个」。"""
    return (kind, date, cat1 or "", cat2 or "", natural_amount(amount), tag_name or "", note or "")


def record_natural_key(record, category, tag):
    """ORM 记录 → 自然键。category/tag 要显式传进来而不是读 record.category/record.tag：
    调用方往往刚改完 category_id/tag_id 还没 flush，这时关系属性拿到的还是旧值。"""
    if category.parent_id is None:
        cat1, cat2 = category.name, ""
    else:
        cat1, cat2 = category.parent.name, category.name
    return natural_key(record.kind, record.date, cat1, cat2, record.amount,
                       tag.name if tag else "", record.note)


def fingerprint_of(key, seq):
    """自然键 + 组内序号 → 指纹。seq 用来区分「同一天同分类同金额同备注」的多笔
    真实消费（一天喝两杯一样的奶茶），不是冲突兜底。"""
    kind, date, cat1, cat2, amount, tag, note = key
    raw = f"{kind}|{date.isoformat()}|{cat1}|{cat2}|{amount}|{tag}|{note}|{seq}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def next_free_fingerprint(key, exclude_id=None):
    """给单条记录找一个还没被占用的指纹：seq 从 0 起找库里第一个空位
    （exclude_id 排除记录自己，避免编辑时跟自己的旧指纹撞上）。"""
    seq = 0
    while True:
        fp = fingerprint_of(key, seq)
        query = ExpenseRecord.query.filter_by(fingerprint=fp)
        if exclude_id is not None:
            query = query.filter(ExpenseRecord.id != exclude_id)
        if query.first() is None:
            return fp
        seq += 1


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
            key = natural_key(kind, date, cat1, cat2, amount, tag, note)
            seq = seq_counter[key]
            seq_counter[key] += 1
            rows.append({
                "kind": kind, "date": date, "cat1": cat1, "cat2": cat2,
                "amount": amount, "tag": tag, "note": note,
                "fingerprint": fingerprint_of(key, seq),
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


def _plan_group(key, group):
    """给同一自然键的一组记录分配指纹，返回 {record.id: fingerprint}。

    **不变量**：同一自然键的 N 条记录，指纹正好占满 seq 0..N-1 这个集合——谁占哪个
    不重要，重要的是集合是满的。导入时文件里第 k 条同款记录算的是 seq=k 的指纹，只要
    集合是满的就一定能对上。所以这里只动真正错的：指纹已经落在本组集合里的原样留着，
    剩下的补空位；既避免无意义的重排，也避免组内互换指纹撞 UNIQUE 约束。"""
    slots = [fingerprint_of(key, seq) for seq in range(len(group))]
    planned, taken, pending = {}, set(), []
    for r in group:
        if r.fingerprint in slots and r.fingerprint not in taken:
            taken.add(r.fingerprint)
            planned[r.id] = r.fingerprint
        else:
            pending.append(r)
    for r, fp in zip(pending, [fp for fp in slots if fp not in taken]):
        planned[r.id] = fp
    return planned


def _write_fingerprints(records, planned):
    """把规划好的指纹落库，返回实际改动的条数。
    先把要改的一律清成 NULL、flush，再写新值：组内两条互换指纹时中间态会撞 UNIQUE
    约束。SQLite 里多个 NULL 可以并存，清空是安全的中转。"""
    changed = [r for r in records if planned[r.id] != r.fingerprint]
    for r in changed:
        r.fingerprint = None
    db.session.flush()
    for r in changed:
        r.fingerprint = planned[r.id]
    db.session.commit()
    return len(changed)


def compact_fingerprints_around(record):
    """把跟 record 同自然键的那一组重新排满 seq 0..N-1。删记录之后调用（传删掉的那条
    的字段快照），补上它留下的空洞——不补的话，以后导入只含这笔一次的账单会算出空着的
    seq=0、认不出来，又插一条重复的。
    record 可以是已经从 session 里删掉的对象，这里只读它的字段值。"""
    siblings = (ExpenseRecord.query
                .filter_by(kind=record.kind, date=record.date, category_id=record.category_id,
                           tag_id=record.tag_id, note=record.note)
                .filter(ExpenseRecord.amount == record.amount)
                .order_by(ExpenseRecord.id).all())
    if not siblings:
        return 0
    survivor = siblings[0]
    key = record_natural_key(survivor, survivor.category, survivor.tag)
    return _write_fingerprints(siblings, _plan_group(key, siblings))


def refresh_all_fingerprints():
    """按当前分类/标签/字段值给库里所有记录重新算一遍 fingerprint（含手工记录，原来没有
    fingerprint 的也会补上）。用于分类改名、标签合并之后让去重指纹跟数据对齐；也用于把
    创建/编辑时才开始写 fingerprint 的老手工记录一次性补齐。
    返回 {"total": N, "changed": M}；只改真正错的，所以连刷两次第二次必然是 0。"""
    records = ExpenseRecord.query.order_by(ExpenseRecord.id).all()
    groups = {}
    for r in records:
        groups.setdefault(record_natural_key(r, r.category, r.tag), []).append(r)

    planned = {}
    for key, group in groups.items():
        planned.update(_plan_group(key, group))
    return {"total": len(records), "changed": _write_fingerprints(records, planned)}


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
