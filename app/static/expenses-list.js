// 日常消费·流水：筛选栏实时异步过滤（无需筛选/清空按钮）+ 分类/标签多选下拉。
(function () {
  var form = document.getElementById('exp-filter-form');
  var results = document.getElementById('exp-results');
  if (!form || !results) return;

  function buildQuery() {
    var raw = new URLSearchParams(new FormData(form));
    var params = new URLSearchParams();
    raw.forEach(function (v, k) {
      // year 即使选"全部"（空值）也要显式带上——用来跟"完全没带参数的首次进入"
      // 区分开，后端靠这个区分来决定要不要套默认的"只看当年"
      if (v !== '' || k === 'year') params.append(k, v);
    });
    return params.toString();
  }

  // 折叠的月份内容在服务端渲染进了 <template>（浏览器只解析、不布局），
  // 展开时才把内容克隆进真实 DOM——避免一次性把一整年上千条记录都布局出来，
  // 主线程卡住导致点哪儿都要等一会才有反应。
  function hydrateGroup(details) {
    var tpl = details.querySelector(':scope > template.tl-group-tpl');
    if (!tpl) return;
    details.appendChild(tpl.content.cloneNode(true));
    tpl.remove();
  }

  function wireGroups() {
    results.querySelectorAll('.tl-group').forEach(function (details) {
      if (details.open) hydrateGroup(details);
      details.addEventListener('toggle', function () {
        if (details.open) hydrateGroup(details);
      });
    });
  }

  function applyFilters() {
    var qs = buildQuery();
    var url = location.pathname + (qs ? '?' + qs : '');
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        results.innerHTML = html;
        wireGroups();
        history.replaceState(null, '', url);
      });
  }

  wireGroups(); // 首屏（服务端整页渲染）的月份分组也要接上折叠/展开逻辑

  function updateMselSummary(msel) {
    var toggle = msel.querySelector('.msel-toggle');
    var label = msel.dataset.label;
    var checked = msel.querySelectorAll('input[type="checkbox"]:checked').length;
    toggle.textContent = checked ? label + '（' + checked + '）' : label;
  }

  document.querySelectorAll('.msel').forEach(updateMselSummary);

  // 下拉面板是浮层，展开时会盖到下面的输入框上；用一层透明背板兜住这层浮层
  // 范围外的所有点击——点哪儿都是先关面板，而不是被面板空白区域吞掉、或误点到
  // 面板下面刚好被盖住的别的控件。
  var backdrop = document.createElement('div');
  backdrop.className = 'msel-backdrop';
  document.body.appendChild(backdrop);

  function closeAllMsel() {
    document.querySelectorAll('.msel.open').forEach(function (m) { m.classList.remove('open'); });
    backdrop.classList.remove('show');
  }

  document.querySelectorAll('.msel-toggle').forEach(function (toggle) {
    toggle.addEventListener('click', function (e) {
      e.stopPropagation();
      var msel = toggle.closest('.msel');
      var willOpen = !msel.classList.contains('open');
      closeAllMsel();
      if (willOpen) {
        msel.classList.add('open');
        backdrop.classList.add('show');
      }
    });
  });

  backdrop.addEventListener('click', closeAllMsel);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeAllMsel();
  });

  var debounceTimer;
  form.addEventListener('input', function (e) {
    if (e.target.type !== 'text') return;
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(applyFilters, 350);
  });

  form.addEventListener('change', function (e) {
    if (e.target.type === 'text') return; // 交给上面 input 防抖处理

    var msel = e.target.closest('.msel');
    if (msel) updateMselSummary(msel);

    applyFilters();
  });
})();
