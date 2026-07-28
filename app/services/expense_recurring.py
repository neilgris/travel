"""固定收支的自动补记。

项目是本地手动启动、没有常驻进程的应用，真·定时任务在关机期间照样漏。所以这里不做调度，
改成「水位线补记」：规则记着从哪个月开始、每几个月一笔，每次进日常消费模块时把从起始月到
本月之间还缺的记录一次性补齐。关机三个月再打开，三笔一起补上，结果与天天开着一样。

幂等由 expense_record 的 (rule_id, date) 唯一约束兜底，跑多少遍都不会重复。
"""
import datetime as dt

from app.extensions import db
from app.models.expense import ExpenseRecord, ExpenseRule


def _month_start(d):
    return dt.date(d.year, d.month, 1)


def _add_months(d, months):
    """在某月 1 号上加 months 个月，仍返回 1 号。"""
    total = d.year * 12 + (d.month - 1) + months
    return dt.date(total // 12, total % 12 + 1, 1)


def due_dates(rule, today=None):
    """规则到今天为止该记的所有日期（都是当月 1 号，按 interval_months 步进）。

    截止到「今天所在月」与 end_month 里较早的那个，两者都含当月。相位由 start_month 决定：
    起始 2 月 + 间隔 3 个月 → 2/5/8/11 月。
    """
    today = today or dt.date.today()
    last = _month_start(today)
    if rule.end_month and rule.end_month < last:
        last = _month_start(rule.end_month)
    step = max(1, rule.interval_months or 1)

    dates = []
    cur = _month_start(rule.start_month)
    while cur <= last:
        dates.append(cur)
        cur = _add_months(cur, step)
    return dates


def next_due(rule, today=None):
    """下一笔会落在哪天；规则已过结束月则返回 None。"""
    today = today or dt.date.today()
    step = max(1, rule.interval_months or 1)
    dates = due_dates(rule, today)
    nxt = _add_months(dates[-1], step) if dates else _month_start(rule.start_month)
    if rule.end_month and nxt > _month_start(rule.end_month):
        return None
    return nxt


def materialize(rule, today=None):
    """补齐这条规则名下缺失的记录，返回新建的那些（已提交）。

    只比对同一 rule_id 下已有的日期——规则不去猜「这个月你是不是已经手工记过一笔房租」，
    因为误判会造成静默漏记，而多出来的记录在流水里一眼可见、随手可删。
    """
    wanted = due_dates(rule, today)
    if not wanted:
        return []

    existing = {d for (d,) in db.session.query(ExpenseRecord.date)
                .filter(ExpenseRecord.rule_id == rule.id)}
    created = []
    for date in wanted:
        if date in existing:
            continue
        record = ExpenseRecord(kind=rule.kind, date=date, category_id=rule.category_id,
                               tag_id=rule.tag_id, amount=rule.amount, note=rule.note,
                               source="auto", rule_id=rule.id)
        db.session.add(record)
        created.append(record)
    if created:
        db.session.commit()
    return created


def run_all(today=None):
    """把所有启用的规则补一遍，返回新建条数。"""
    return sum(len(materialize(rule, today))
               for rule in ExpenseRule.query.filter_by(active=True))


_LAST_RUN_KEY = "_RECURRING_LAST_RUN"


def run_if_stale(app, today=None):
    """同一天只补一次——挂在请求钩子上，别让每个请求都扫一遍规则表。

    水位线存在 app.config 里而不是模块全局，这样测试里每个 app 实例各算各的。
    """
    today = today or dt.date.today()
    if app.config.get(_LAST_RUN_KEY) == today:
        return 0
    app.config[_LAST_RUN_KEY] = today
    return run_all(today)


def preview(rule, today=None):
    """规则生效后会新增多少条、覆盖哪段时间——建规则前给用户看一眼，别闷头写库。"""
    wanted = due_dates(rule, today)
    existing = set()
    if rule.id:
        existing = {d for (d,) in db.session.query(ExpenseRecord.date)
                    .filter(ExpenseRecord.rule_id == rule.id)}
    missing = [d for d in wanted if d not in existing]
    return {
        "count": len(missing),
        "first": missing[0] if missing else None,
        "last": missing[-1] if missing else None,
        "total": rule.amount * len(missing) if missing else 0,
    }
