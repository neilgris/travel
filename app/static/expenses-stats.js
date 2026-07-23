// 月度/年度/总览三页共用的图表工具：调色板、金额格式化、甜甜圈工厂。
// 三页的分类占比甜甜圈配置完全一样，抽到这里一处维护。
const EXP_PALETTE = ['#e76f51', '#2a9d8f', '#e9c46a', '#4a9fc9', '#9b8cb5', '#b0a99f', '#f4a261', '#606c38'];

Chart.defaults.font.family = "system-ui, -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif";

const expFmt = v => '￥' + v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const expFmt0 = v => '￥' + Math.round(v).toLocaleString('zh-CN');

// data: [{category, total}]。canvasId 指向一个 <canvas>。
function expMakeDonut(canvasId, data) {
  return new Chart(document.getElementById(canvasId), {
    type: 'doughnut',
    data: {
      labels: data.map(c => c.category),
      datasets: [{
        data: data.map(c => c.total),
        backgroundColor: data.map((c, i) => EXP_PALETTE[i % EXP_PALETTE.length]),
        borderWidth: 2, borderColor: '#fff', hoverOffset: 10,
      }],
    },
    options: {
      maintainAspectRatio: false,
      cutout: '64%',
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: i => {
          const total = data.reduce((a, c) => a + c.total, 0);
          const pct = total ? (i.raw / total * 100).toFixed(1) : 0;
          return ` ${i.label}  ${expFmt(i.raw)}  (${pct}%)`;
        } } },
      },
    },
  });
}

// —— 分类明细 / 标签榜共用的 Miller 列小工具 ——
const expEsc = s => (s == null ? '' : String(s)).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

// 一列里的一行。栏窄、金额长（动辄七位数），故标题独占一行、金额落到副行右侧，
// 避免标题被挤成「居…」。clickable 可选中（右向展开），active 高亮当前选中，› 提示可展开。
function expMillerItem(c, title, meta, amount, barPct, { active = false, clickable = false, idx = null } = {}) {
  return `<li class="cat-item${clickable ? ' cat-item--click' : ''}${active ? ' cat-item--active' : ''}"${idx != null ? ` data-idx="${idx}"` : ''}>
    <span class="top-bar" style="background:${c}"></span>
    <span class="cat-item-body">
      <span class="cat-item-head">
        <span class="top-title">${title}</span>
        ${clickable ? '<span class="cat-caret">›</span>' : ''}
      </span>
      <span class="cat-item-sub">
        <span class="top-meta">${meta || ''}</span>
        <span class="top-amount">${expFmt(amount)}</span>
      </span>
      ${barPct != null ? `<span class="mini-bar"><i style="width:${Math.min(barPct, 100)}%;background:${c}"></i></span>` : ''}
    </span>
  </li>`;
}
const expMillerEmpty = txt => `<li class="cat-empty">${txt}</li>`;

// 单笔记录栏（分类明细最右栏 / 标签榜右栏共用）：按金额降序渲染成一列。
function expMillerRecords(recs, c) {
  const max = recs.length ? recs[0].amount : 0;
  return recs.map(r => {
    const title = expEsc(r.note || r.category);
    const meta = `${r.date} · ${expEsc(r.category)}${r.tag ? ' · #' + expEsc(r.tag) : ''}`;
    return expMillerItem(c, title, meta, r.amount, max ? r.amount / max * 100 : 0, {});
  }).join('') || expMillerEmpty('暂无记录');
}

// 榜项左栏标题里的图标前缀（有则 "icon "，无则空）。
const expIconPrefix = icon => (icon ? expEsc(icon) + ' ' : '');

// 一级分类榜 / 二级分类榜 / 标签榜共用的两栏 Miller 列：左栏排行（固定常驻），点某项右栏出
// 它名下的单笔支出 Top N。三个榜只有左栏一行的标题/副文不同，用 fmt(entry)->{title,meta} 注入。
function expBoard(mountId, data, fmt) {
  const el = document.getElementById(mountId);
  if (!el) return;
  const color = i => EXP_PALETTE[i % EXP_PALETTE.length];

  el.innerHTML = `<div class="cat-miller">
    <ul class="cat-col cat-col--l1" data-col="item"></ul>
    <ul class="cat-col cat-col--l3" data-col="rec"></ul>
  </div>`;
  const colItem = el.querySelector('[data-col="item"]');
  const colRec = el.querySelector('[data-col="rec"]');
  let sel = data.length ? 0 : null;  // 进来默认选中金额第一项，右栏不空

  function renderItems() {
    const max = data.length ? data[0].total : 0;
    colItem.innerHTML = data.map((d, i) => {
      const { title, meta } = fmt(d);
      return expMillerItem(color(i), title, meta, d.total, max ? d.total / max * 100 : 0,
                           { active: i === sel, clickable: d.records.length > 0, idx: i });
    }).join('') || expMillerEmpty('暂无数据');
  }

  function renderRecs() {
    if (sel == null) { colRec.innerHTML = expMillerEmpty('← 选择左侧'); return; }
    colRec.innerHTML = expMillerRecords(data[sel].records, color(sel));
  }

  colItem.addEventListener('click', e => {
    const li = e.target.closest('.cat-item--click[data-idx]');
    if (!li) return;
    sel = +li.dataset.idx;
    renderItems(); renderRecs();
  });

  renderItems(); renderRecs();
}

// 三个榜的左栏行格式化器（title = 标题，meta = 副文）。
function expFmtCat1(d) {  // 一级分类榜：图标 + 名称 / 占比（+同比涨跌上色）
  let meta = `占 ${d.pct.toFixed(1)}%`;
  if (d.yoy_pct != null) {
    const up = d.yoy_pct >= 0;
    meta += ` · <span style="color:${up ? '#e76f51' : '#2a9d8f'}">同比${up ? '+' : ''}${d.yoy_pct.toFixed(1)}%</span>`;
  }
  return { title: expIconPrefix(d.icon) + expEsc(d.name), meta };
}
function expFmtCat2(d) {  // 二级分类榜：图标 + 名称 / 所属一级 · 占比
  return { title: expIconPrefix(d.icon) + expEsc(d.name), meta: `${expEsc(d.parent)} · 占 ${d.pct.toFixed(1)}%` };
}
function expFmtTag(d) {  // 标签榜：#标签 / N 笔
  return { title: '#' + expEsc(d.tag), meta: `${d.count} 笔` };
}
