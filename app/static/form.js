// 旅程表单：行程段 / 币种动态增删 + 选币种实时取汇率。
(function () {
  function renumberLegs() {
    document.querySelectorAll('#legs input[name="leg_seq"]').forEach(function (el, i) {
      el.value = i + 1;
    });
  }

  function addRow(containerId, templateId) {
    var tpl = document.getElementById(templateId);
    var container = document.getElementById(containerId);
    if (!tpl || !container) return;
    container.appendChild(tpl.content.cloneNode(true));
    renumberLegs();
  }

  function clearRow(row) {
    row.querySelectorAll('input').forEach(function (i) {
      if (i.type !== 'hidden') i.value = '';
    });
    row.querySelectorAll('select').forEach(function (s) { s.selectedIndex = 0; });
  }

  function fetchRate(select) {
    var code = select.value;
    var rateInput = select.closest('.cur-row').querySelector('input[name="cur_rate"]');
    if (!code || !rateInput) return;
    fetch('/trips/exchange-rate?code=' + encodeURIComponent(code))
      .then(function (r) { return r.json(); })
      .then(function (data) { if (data.rate) rateInput.value = data.rate; })
      .catch(function () { /* 离线/失败时静默，用户可手填 */ });
  }

  document.addEventListener('click', function (e) {
    var add = e.target.closest('[data-add]');
    if (add) {
      addRow(add.dataset.add, add.dataset.template);
      return;
    }
    var del = e.target.closest('.row-del');
    if (del) {
      var row = del.closest('.leg-row, .cur-row');
      if (!row) return;
      var container = row.parentElement;
      if (container.children.length > 1) {
        row.remove();
      } else {
        clearRow(row); // 至少保留一行，清空而非删除
      }
      renumberLegs();
    }
  });

  document.addEventListener('change', function (e) {
    if (e.target.matches('select[name="cur_code"]')) fetchRate(e.target);
  });
})();
