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
      return;
    }
  });

  // 行程段：同 detail.html 消费记录一致的原生拖放，纯前端调整 DOM 顺序，
  // 提交时 leg_seq 已按 renumberLegs 重排，无需再问服务端。
  (function initLegDrag() {
    var legs = document.getElementById('legs');
    if (!legs) return;
    var dragging = null;

    function afterElement(y) {
      var rows = Array.prototype.filter.call(
        legs.querySelectorAll('.leg-row'),
        function (r) { return r !== dragging; }
      );
      var closest = { offset: -Infinity, el: null };
      rows.forEach(function (row) {
        var box = row.getBoundingClientRect();
        var offset = y - box.top - box.height / 2;
        if (offset < 0 && offset > closest.offset) closest = { offset: offset, el: row };
      });
      return closest.el;
    }

    legs.addEventListener('dragstart', function (e) {
      var row = e.target.closest('.leg-row');
      if (!row || !legs.contains(row)) return;
      dragging = row;
      row.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    });

    legs.addEventListener('dragend', function () {
      if (!dragging) return;
      dragging.classList.remove('dragging');
      dragging = null;
      renumberLegs();
    });

    legs.addEventListener('dragover', function (e) {
      if (!dragging) return;
      e.preventDefault();
      var ref = afterElement(e.clientY);
      if (ref == null) {
        legs.appendChild(dragging);
      } else if (ref !== dragging) {
        legs.insertBefore(dragging, ref);
      }
    });
  })();

  document.addEventListener('change', function (e) {
    if (e.target.matches('select[name="cur_code"]')) fetchRate(e.target);
    if (e.target.matches('.leg-city-pick')) {
      // 行程段城市：下拉只是快速填充，选完把值塞进旁边的文本框，自己复位。
      var field = e.target.closest('.leg-city-field');
      var input = field && field.querySelector('input');
      if (input && e.target.value) input.value = e.target.value;
      e.target.selectedIndex = 0;
    }
  });
})();
