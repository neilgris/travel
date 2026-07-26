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
// 选择器是联动式：一级→二级两级下拉，或标签可输入联想；维度太多时不再挤在一个长下拉里。
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
  const cat1Sel = el('trendCat1'), cat2Sel = el('trendCat2');
  const tagInput = el('trendTagInput'), tagList = el('trendTagList');
  const title = el('trendChartTitle'), tbody = el('trendTableBody');
  const topTitle = el('trendTopTitle'), topList = el('trendTopList');
  if (!cat1Sel) return;

  const dims = data.dimensions;
  const byKey = Object.fromEntries(dims.map(d => [d.key, d]));
  const cat1s = dims.filter(d => d.type === 'cat1');
  const tags = dims.filter(d => d.type === 'tag');
  const tagByName = Object.fromEntries(tags.map(d => [d.name, d]));
  const childrenOf = {};  // 一级 key → [二级维度]
  dims.filter(d => d.type === 'cat2').forEach(d => (childrenOf[d.parent_key] ||= []).push(d));

  let curKey = data.default_key;
  let selYear = data.years[data.years.length - 1];  // 默认看最后一年

  // ---- 填充选择器 ----
  cat1Sel.innerHTML = [['支出', '支出'], ['收入', '收入']].map(([kind, label]) => {
    const items = cat1s.filter(d => d.kind === kind);
    if (!items.length) return '';
    return `<optgroup label="${label}">` +
      items.map(d => `<option value="${d.key}">${expTrendLabel(d)}</option>`).join('') + '</optgroup>';
  }).join('');
  tagList.innerHTML = tags.map(d => `<option value="${expEsc(d.name)}">`).join('');

  function fillCat2(cat1Key) {
    const parent = byKey[cat1Key];
    const kids = childrenOf[cat1Key] || [];
    cat2Sel.innerHTML = `<option value="${cat1Key}">整个「${expEsc(parent.name)}」</option>` +
      kids.map(d => `<option value="${d.key}">${expIconPrefix(d.icon)}${expEsc(d.name)}</option>`).join('');
  }

  function setMode(mode) {
    document.querySelectorAll('.trend-mode-btn').forEach(b => b.classList.toggle('is-active', b.dataset.mode === mode));
    document.querySelectorAll('[data-mode-panel]').forEach(p => { p.hidden = p.dataset.modePanel !== mode; });
  }

  // 根据 curKey 把选择器 UI 摆到对应位置（首次进入 & 切模式时用）
  function syncPickers() {
    const d = byKey[curKey];
    if (d.type === 'tag') {
      setMode('tag');
      tagInput.value = d.name;
    } else {
      setMode('cat');
      const cat1Key = d.type === 'cat2' ? d.parent_key : d.key;
      cat1Sel.value = cat1Key;
      fillCat2(cat1Key);
      cat2Sel.value = d.key;
    }
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
    const mode = btn.dataset.mode;
    setMode(mode);
    if (mode === 'tag') { curKey = (tagByName[tagInput.value] || tags[0]).key; tagInput.value = byKey[curKey].name; }
    else { curKey = cat2Sel.value || cat1Sel.value || cat1s[0].key; }
    renderAll();
  }));
  cat1Sel.addEventListener('change', () => { fillCat2(cat1Sel.value); curKey = cat1Sel.value; renderAll(); });
  cat2Sel.addEventListener('change', () => { curKey = cat2Sel.value; renderAll(); });
  tagInput.addEventListener('change', () => {
    const d = tagByName[tagInput.value];
    if (d) { curKey = d.key; renderAll(); }
  });
  tbody.addEventListener('click', e => {
    const row = e.target.closest('.trend-row[data-year]');
    if (row) { selYear = +row.dataset.year; renderAll(); }
  });

  syncPickers();
  renderAll();
}
