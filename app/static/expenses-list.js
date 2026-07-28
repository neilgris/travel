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

  // 筛选栏"收支"切换时，"分类"下拉里只留对应收支类型的分类可选——
  // 已勾选但不属于当前收支类型的分类会被自动取消勾选。
  var catMsel = document.getElementById('exp-cat-msel');
  function filterCategoryMsel() {
    if (!catMsel) return;
    var kind = form.querySelector('select[name="kind"]').value;
    var changed = false;
    catMsel.querySelectorAll('.msel-opt').forEach(function (opt) {
      var match = !kind || opt.dataset.kind === kind;
      opt.hidden = !match;
      if (!match) {
        var cb = opt.querySelector('input[type="checkbox"]');
        if (cb.checked) { cb.checked = false; changed = true; }
      }
    });
    updateMselSummary(catMsel);
    return changed;
  }

  wireGroups(); // 首屏（服务端整页渲染）的月份分组也要接上折叠/展开逻辑
  filterCategoryMsel(); // 首屏按当前"收支"筛选值同步一次分类下拉的可选项

  // 点一行流水，原地下拉成编辑表单，保存/取消都不刷新页面。
  // EXP_CATEGORIES 由 list.html 内联注入（一级+二级分类树，含图标）。
  function renderInlineCat1(form) {
    var kindSel = form.querySelector('.exp-inline-kind');
    var cat1Sel = form.querySelector('.exp-inline-cat1');
    var kind = kindSel.value;
    cat1Sel.innerHTML = '';
    (typeof EXP_CATEGORIES !== 'undefined' ? EXP_CATEGORIES : []).filter(function (c) {
      return c.kind === kind;
    }).forEach(function (c) {
      var opt = document.createElement('option');
      opt.value = c.id; opt.textContent = (c.icon || '') + ' ' + c.name;
      cat1Sel.appendChild(opt);
    });
    if (kind === form.dataset.curKind && form.dataset.curCat1) cat1Sel.value = form.dataset.curCat1;
    renderInlineCat2(form);
  }

  function renderInlineCat2(form) {
    var kindSel = form.querySelector('.exp-inline-kind');
    var cat1Sel = form.querySelector('.exp-inline-cat1');
    var cat2Sel = form.querySelector('.exp-inline-cat2');
    var top = (typeof EXP_CATEGORIES !== 'undefined' ? EXP_CATEGORIES : []).find(function (c) {
      return String(c.id) === cat1Sel.value;
    });
    cat2Sel.innerHTML = '';
    if (top) {
      var self = document.createElement('option');
      self.value = top.id; self.textContent = '（不细分）';
      cat2Sel.appendChild(self);
      top.children.forEach(function (sub) {
        var opt = document.createElement('option');
        opt.value = sub.id; opt.textContent = (sub.icon ? sub.icon + ' ' : '') + sub.name;
        cat2Sel.appendChild(opt);
      });
    }
    if (kindSel.value === form.dataset.curKind && form.dataset.curCat2) cat2Sel.value = form.dataset.curCat2;
  }

  function openInlineEdit(li) {
    var trigger = li.querySelector('.tl-main');
    if (!trigger) return;
    fetch(trigger.href, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        var tpl = document.createElement('template');
        tpl.innerHTML = html.trim();
        var formLi = tpl.content.firstElementChild;
        formLi._originalLi = li;
        li.replaceWith(formLi);
        renderInlineCat1(formLi.querySelector('.exp-inline-form'));
      });
  }

  function closeInlineEdit(formLi) {
    if (formLi._originalLi) formLi.replaceWith(formLi._originalLi);
  }

  function submitInlineEdit(form) {
    var formLi = form.closest('.exp-item-editing');
    var errorEl = form.querySelector('.exp-inline-error');
    errorEl.hidden = true;
    var submitBtn = form.querySelector('button[type="submit"]');
    submitBtn.disabled = true;
    fetch(form.dataset.editUrl, {
      method: 'POST', body: new FormData(form),
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          var tpl = document.createElement('template');
          tpl.innerHTML = data.html.trim();
          formLi.replaceWith(tpl.content.firstElementChild);
        } else {
          errorEl.textContent = data.error || '保存失败';
          errorEl.hidden = false;
          submitBtn.disabled = false;
        }
      })
      .catch(function () {
        errorEl.textContent = '网络错误，请重试';
        errorEl.hidden = false;
        submitBtn.disabled = false;
      });
  }

  results.addEventListener('click', function (e) {
    var cancelBtn = e.target.closest('[data-cancel]');
    if (cancelBtn) {
      closeInlineEdit(cancelBtn.closest('.exp-item-editing'));
      return;
    }
    var trigger = e.target.closest('.tl-main');
    if (!trigger) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return; // 允许新标签页打开等默认行为
    var li = trigger.closest('.exp-item');
    if (!li || li.classList.contains('exp-item-editing')) return;
    e.preventDefault();
    openInlineEdit(li);
  });

  results.addEventListener('change', function (e) {
    var form = e.target.closest('.exp-inline-form');
    if (!form) return;
    if (e.target.classList.contains('exp-inline-kind')) renderInlineCat1(form);
    else if (e.target.classList.contains('exp-inline-cat1')) renderInlineCat2(form);
  });

  results.addEventListener('submit', function (e) {
    var editForm = e.target.closest('.exp-inline-form');
    if (editForm) {
      e.preventDefault();
      submitInlineEdit(editForm);
      return;
    }
    var delForm = e.target.closest('.exp-del-form');
    if (delForm) {
      e.preventDefault();
      if (!confirm('删除这条记录？')) return;
      fetch(delForm.action, {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.ok) applyFilters();
          else alert('删除失败');
        })
        .catch(function () { alert('网络错误，请重试'); });
    }
  });

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

    if (e.target.name === 'kind') filterCategoryMsel();

    var msel = e.target.closest('.msel');
    if (msel) updateMselSummary(msel);

    applyFilters();
  });
})();
