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

// —— 分类走势页：选一个维度（一级/二级/标签）看它逐年金额折线，点某年在右侧看当年 Top 消费 ——
// 左侧一栏平铺所有维度并各带累计金额：分类按「支出/收入 → 一级 → 二级」缩进列出，
// 标签单独一列表，两者用顶部按钮切换。
const TREND_LINE = '#e76f51';
const TREND_LINE_SEL = '#c1440e';  // 选中年份的高亮点

// 维度显示名：一级=图标+名；二级=图标+一级·名；标签=#名。
function expTrendLabel(d) {
  const icon = expIconPrefix(d.icon);
  if (d.type === 'tag') return icon + '#' + expEsc(d.name);
  if (d.type === 'cat2') return icon + expEsc(d.parent) + ' · ' + expEsc(d.name);
  return icon + expEsc(d.name);
}

// data: {years:[…], dimensions:[{key,type,kind,name,icon,parent,parent_key,total,amounts[],counts[]}], default_key}
function expTrends(data) {
  const el = id => document.getElementById(id);
  const sideList = el('trendSideList');
  const title = el('trendChartTitle'), tbody = el('trendTableBody');
  const topTitle = el('trendTopTitle'), topList = el('trendTopList');
  if (!sideList) return;

  const dims = data.dimensions;
  const byKey = Object.fromEntries(dims.map(d => [d.key, d]));
  const cat1s = dims.filter(d => d.type === 'cat1');
  const tags = dims.filter(d => d.type === 'tag');
  const childrenOf = {};  // 一级 key → [二级维度]
  dims.filter(d => d.type === 'cat2').forEach(d => (childrenOf[d.parent_key] ||= []).push(d));

  let curKey = null;  // setMode() 会在首次渲染前选中列表最上一项
  let mode = 'cat';  // 与模板里默认高亮的「分类」标签页保持一致
  let selYear = data.years[data.years.length - 1];  // 默认看最后一年

  // ---- 左侧维度列表 ----
  // extraClass 决定这一行的层级样式：'' 顶格；'trend-item-sub' 是真·下级（分类模式的二级，
  // 缩进且降一档字号/颜色）；'trend-item-nested' 只缩进不降级（标签模式组内的标签——它们
  // 跟未分组的标签是同一类东西，只是被归了组，不该显得低人一等）。
  function sideRow(d, extraClass) {
    const label = d.type === 'tag' ? '#' + expEsc(d.name) : expIconPrefix(d.icon) + expEsc(d.name);
    return `<button type="button" class="trend-item${extraClass ? ' ' + extraClass : ''}" data-key="${d.key}">
      <span class="trend-item-name">${label}</span>
      <span class="trend-item-amt">${expFmt0(d.total)}</span>
    </button>`;
  }

  // 连续同 group 的项归一段，段头是组名（tags 已按组聚好序，不用再排）
  function groupRuns(items, labelOf) {
    return items.reduce((runs, d) => {
      const label = labelOf(d);
      const last = runs[runs.length - 1];
      if (last && last.label === label) last.items.push(d);
      else runs.push({ label, items: [d] });
      return runs;
    }, []);
  }

  function renderSide() {
    if (mode === 'tag') {
      // 标签不挂在分类树上，分两级：一级分类（按金额推）→ 标签组（手工设的 group_name）→ 标签。
      // 未设标签组的直接挂在一级分类下、顶格（对应分类模式里的一级行）；有组的标签缩进一级。
      sideList.innerHTML = groupRuns(tags, d => d.group).map(run =>
        `<div class="trend-grp">${expIconPrefix(run.items[0].group_icon)}${expEsc(run.label)}</div>` +
        groupRuns(run.items, d => d.subgroup || '').map(sub =>
          (sub.label ? `<div class="trend-grp trend-grp-sub">${expEsc(sub.label)}</div>` : '') +
          sub.items.map(d => sideRow(d, sub.label ? 'trend-item-nested' : '')).join('')
        ).join('')
      ).join('') || '<p class="muted trend-side-empty">还没有用过标签。</p>';
    } else {
      // 一级下面紧跟它的二级；一级本身也可点（= 含其所有二级的合计）
      sideList.innerHTML = ['支出', '收入'].map(kind => {
        const items = cat1s.filter(d => d.kind === kind);
        if (!items.length) return '';
        return `<div class="trend-grp">${kind}</div>` + items.map(d =>
          sideRow(d, '') + (childrenOf[d.key] || []).map(sub => sideRow(sub, 'trend-item-sub')).join('')
        ).join('');
      }).join('');
    }
    markSide(true);
  }

  function markSide(scrollIntoView) {
    let sel = null;
    sideList.querySelectorAll('.trend-item').forEach(b => {
      const on = b.dataset.key === curKey;
      b.classList.toggle('is-sel', on);
      if (on) sel = b;
    });
    // 选中项可能在长列表里被卷到视野外（首屏默认项、切换维度类型时）。
    // 只滚侧栏这一个容器——用 scrollIntoView 会连整个页面一起滚上去。
    if (scrollIntoView && sel) {
      sideList.scrollTop = sel.offsetTop - sideList.offsetTop - sideList.clientHeight / 2 + sel.offsetHeight / 2;
    }
  }

  function setMode(next) {
    mode = next;
    document.querySelectorAll('.trend-mode-btn').forEach(b => b.classList.toggle('is-active', b.dataset.mode === mode));
    // 每次切换标签页都默认选中列表里最靠上的第一项
    const pool = mode === 'tag' ? tags : cat1s;
    if (pool[0]) curKey = pool[0].key;
    renderSide();
  }

  // ---- 折线图 ----
  const chart = new Chart(el('trendChart'), {
    type: 'line',
    data: {
      labels: data.years.map(y => y + '年'),
      datasets: [{
        data: [], borderColor: TREND_LINE, backgroundColor: 'rgba(231,111,81,0.12)',
        tension: 0.3, fill: true, pointHoverRadius: 7,
      }],
    },
    options: {
      // 点图上任意处：取最近的年份列（不必正好戳中圆点），选中该年
      onClick: evt => {
        const pts = chart.getElementsAtEventForMode(evt, 'index', { intersect: false }, true);
        if (pts.length) { selYear = data.years[pts[0].index]; renderAll(); }
      },
      plugins: {
        legend: { display: false },
        tooltip: { mode: 'index', intersect: false, callbacks: { label: i => ' ' + expFmt(i.raw) } },
      },
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, ticks: { callback: v => v.toLocaleString('zh-CN') } },
      },
    },
  });

  function yoyCell(cur, prev, i) {
    if (i === 0 || prev == null || prev === 0) return '<span class="muted">—</span>';
    const pct = (cur - prev) / prev * 100;
    const up = pct >= 0;
    return `<span style="color:${up ? TREND_LINE : '#2a9d8f'}">${up ? '+' : ''}${pct.toFixed(1)}%</span>`;
  }

  function renderChart(d, iSel) {
    const ds = chart.data.datasets[0];
    ds.data = d.amounts;
    ds.pointRadius = data.years.map((y, i) => i === iSel ? 7 : 4);
    ds.pointBackgroundColor = data.years.map((y, i) => i === iSel ? TREND_LINE_SEL : TREND_LINE);
    chart.update();
    title.textContent = expTrendLabel(d).trim() + ' · 逐年走势';
  }

  function renderTable(d) {
    tbody.innerHTML = data.years.map((y, i) => `<tr class="trend-row${y === selYear ? ' is-sel' : ''}" data-year="${y}">
      <td>${y}</td>
      <td class="num">${expFmt(d.amounts[i])}</td>
      <td class="num">${yoyCell(d.amounts[i], d.amounts[i - 1], i)}</td>
      <td class="num">${d.counts[i]}</td>
    </tr>`).join('');
  }

  // 当年 Top 50 消费：每次维度或年份变化时按需拉一段明细，下方多列自适应铺开
  let topReqId = 0;
  function renderTop(d, iSel) {
    const count = d.counts[iSel] || 0;
    topTitle.textContent = `${selYear} · ${expTrendLabel(d).trim()} · ${expFmt(d.amounts[iSel] || 0)} · 共 ${count} 笔`;
    const reqId = ++topReqId;
    topList.innerHTML = '<li class="cat-empty">加载中…</li>';
    fetch(`/expenses/trends/records?key=${encodeURIComponent(curKey)}&year=${selYear}`)
      .then(r => r.json())
      .then(j => {
        if (reqId !== topReqId) return;  // 快速连点，只认最后一次
        topList.innerHTML = expMillerRecords(j.records.map(r => ({ ...r, amount: +r.amount })), TREND_LINE);
      })
      .catch(() => { if (reqId === topReqId) topList.innerHTML = expMillerEmpty('加载失败'); });
  }

  function renderAll() {
    const d = byKey[curKey];
    const iSel = data.years.indexOf(selYear);
    renderChart(d, iSel);
    renderTable(d);
    renderTop(d, iSel);
  }

  // ---- 事件 ----
  document.querySelectorAll('.trend-mode-btn').forEach(btn => btn.addEventListener('click', () => {
    if (btn.dataset.mode === mode) return;
    setMode(btn.dataset.mode);
    renderAll();
  }));

  sideList.addEventListener('click', e => {
    const btn = e.target.closest('.trend-item[data-key]');
    if (!btn || btn.dataset.key === curKey) return;
    curKey = btn.dataset.key;
    markSide();
    renderAll();
  });

  tbody.addEventListener('click', e => {
    const row = e.target.closest('.trend-row[data-year]');
    if (row) { selYear = +row.dataset.year; renderAll(); }
  });

  setMode(mode);
  renderAll();
}
