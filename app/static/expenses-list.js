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

  // 返回 promise：记一笔保存后要等列表重刷完，才能判断新记录有没有落进当前筛选。
  function applyFilters() {
    var qs = buildQuery();
    var url = location.pathname + (qs ? '?' + qs : '');
    return fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        results.innerHTML = html;
        wireGroups();
        updateBulkCount();
        history.replaceState(null, '', url);
      });
  }

  // 批量操作栏：面板本体在 list.html 里、#exp-results 外面（默认隐藏，点头部按钮才展开），
  // 不会被筛选刷新时的 innerHTML 替换掉，所以监听只用在首屏挂一次；"当前筛选 N 条"这行
  // 文字每次筛选刷新后要从结果区里的隐藏计数器（#exp-total-count）同步过来。
  // 目标范围永远是"当前筛选栏筛出来的所有记录"，不是勾选出来的一部分——提交时把筛选栏
  // 当前值（跟 applyFilters 用的是同一份 buildQuery）连同 field/value 一起发给后端，
  // 后端用同一套筛选逻辑圈定范围，保证跟页面上看到的结果完全一致。
  var bulkBar = document.getElementById('exp-bulk-bar');
  var bulkToggle = document.getElementById('exp-bulk-toggle');

  function updateBulkCount() {
    if (!bulkBar) return;
    var carrier = results.querySelector('#exp-total-count');
    var count = carrier ? carrier.dataset.count : '0';
    bulkBar.querySelector('.exp-bulk-count').textContent = '当前筛选 ' + count + ' 条';
  }

  function updateBulkApplyState() {
    if (!bulkBar) return;
    var field = bulkBar.querySelector('.exp-bulk-field').value;
    bulkBar.querySelectorAll('.exp-bulk-value').forEach(function (el) {
      el.hidden = el.dataset.for !== field;
    });
    var applyBtn = bulkBar.querySelector('.exp-bulk-apply');
    if (field === 'category') {
      applyBtn.disabled = !bulkBar.querySelector('.exp-bulk-category').value;
    } else if (field === 'tag') {
      applyBtn.disabled = false; // 标签留空 = 清空标签，是合法操作
    } else {
      applyBtn.disabled = true;
    }
  }

  function openBulkBar() {
    bulkBar.hidden = false;
    bulkToggle.setAttribute('aria-expanded', 'true');
  }

  function closeBulkBar() {
    bulkBar.hidden = true;
    bulkToggle.setAttribute('aria-expanded', 'false');
  }

  function wireBulkBar() {
    if (!bulkBar) return;
    updateBulkCount();
    updateBulkApplyState();
    bulkBar.querySelector('.exp-bulk-field').addEventListener('change', updateBulkApplyState);
    var catSel = bulkBar.querySelector('.exp-bulk-category');
    if (catSel) catSel.addEventListener('change', updateBulkApplyState);

    bulkBar.querySelector('.exp-bulk-apply').addEventListener('click', function () {
      var field = bulkBar.querySelector('.exp-bulk-field').value;
      var value, valueLabel;
      if (field === 'category') {
        var sel = bulkBar.querySelector('.exp-bulk-category');
        value = sel.value;
        valueLabel = sel.selectedOptions[0].textContent;
      } else {
        value = bulkBar.querySelector('.exp-bulk-tag').value.trim();
        valueLabel = value || '（清空标签）';
      }
      var label = field === 'category' ? '分类' : '标签';
      var countText = bulkBar.querySelector('.exp-bulk-count').textContent;
      if (!confirm(countText + '，确定把它们的' + label + '都改成 ' + valueLabel + ' 吗？此操作不可撤销。')) return;

      var params = new URLSearchParams(buildQuery());
      params.set('field', field);
      params.set('value', value);
      var applyBtn = bulkBar.querySelector('.exp-bulk-apply');
      applyBtn.disabled = true;
      fetch(bulkBar.dataset.url, {
        method: 'POST', body: params,
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.ok) {
            applyFilters();
          } else {
            alert(data.error || '操作失败');
          }
          applyBtn.disabled = false; // 无论成功失败都要解锁——期望是每次点击都再批量修改一遍当前筛选
        })
        .catch(function () {
          alert('网络错误，请重试');
          applyBtn.disabled = false;
        });
    });

    if (bulkToggle) {
      bulkToggle.addEventListener('click', function () {
        if (bulkBar.hidden) openBulkBar(); else closeBulkBar();
      });
    }
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
  wireBulkBar(); // 批量操作栏本体不会被筛选刷新替换，监听只需要在首屏挂一次
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

  // 记一笔：列表页原地展开一行录入表单，异步保存后按当前筛选重刷列表。
  // 「再记一笔」= 保存当前这条但表单原样留着，改几个字段就能接着记下一条。
  var newCard = document.getElementById('exp-new-card');
  var newForm = document.getElementById('exp-new-form');
  var newToggle = document.getElementById('exp-new-toggle');

  function findInResults(recordId) {
    // 折叠着的月份还躺在 <template> 里没进 DOM，也要一起找——否则刚记的这条只是
    // 落在了折叠分组里，却被误报成"不在当前筛选范围内"。
    var sel = '[data-record-id="' + recordId + '"]';
    if (results.querySelector(sel)) return true;
    var tpls = results.querySelectorAll('template.tl-group-tpl');
    for (var i = 0; i < tpls.length; i++) {
      if (tpls[i].content.querySelector(sel)) return true;
    }
    return false;
  }

  function showNewFormMsg(text, isError) {
    var el = newForm.querySelector('.exp-inline-error');
    el.textContent = text;
    el.classList.toggle('exp-inline-msg', !isError);
    el.hidden = !text;
  }

  function openNewForm() {
    newCard.hidden = false;
    newToggle.setAttribute('aria-expanded', 'true');
    renderInlineCat1(newForm);
    newForm.querySelector('.exp-inline-amount').focus();
  }

  function closeNewForm() {
    newCard.hidden = true;
    newToggle.setAttribute('aria-expanded', 'false');
    showNewFormMsg('', false);
  }

  function submitNewRecord(keepOpen) {
    if (!newForm.reportValidity()) return; // 「再记一笔」是 type=button，不走浏览器自带校验
    showNewFormMsg('', false);
    var btns = newForm.querySelectorAll('button');
    function setDisabled(v) { btns.forEach(function (b) { b.disabled = v; }); }
    setDisabled(true);
    fetch(newForm.dataset.createUrl, {
      method: 'POST', body: new FormData(newForm),
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        setDisabled(false);
        if (!data.ok) {
          showNewFormMsg(data.error || '保存失败', true);
          return;
        }
        applyFilters().then(function () {
          if (!findInResults(data.id)) {
            showNewFormMsg('已保存，但这条不在当前筛选范围内，列表里看不到。', false);
          }
        });
        if (keepOpen) {
          var amount = newForm.querySelector('.exp-inline-amount');
          amount.focus();
          amount.select();
        } else {
          closeNewForm();
        }
      })
      .catch(function () {
        setDisabled(false);
        showNewFormMsg('网络错误，请重试', true);
      });
  }

  if (newForm && newToggle) {
    newToggle.addEventListener('click', function () {
      if (newCard.hidden) openNewForm(); else closeNewForm();
    });
    newForm.addEventListener('submit', function (e) {
      e.preventDefault();
      submitNewRecord(false);
    });
    newForm.addEventListener('click', function (e) {
      if (e.target.closest('[data-save-again]')) submitNewRecord(true);
      else if (e.target.closest('[data-new-cancel]')) closeNewForm();
    });
    newForm.addEventListener('change', function (e) {
      if (e.target.classList.contains('exp-inline-kind')) renderInlineCat1(newForm);
      else if (e.target.classList.contains('exp-inline-cat1')) renderInlineCat2(newForm);
    });
  }

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
