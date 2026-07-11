// 旅程表单：行程段 / 币种动态增删 + 选币种实时取汇率。
(function () {
  function renumberLegs() {
    document.querySelectorAll('#legs input[name="leg_seq"]').forEach(function (el, i) {
      el.value = i + 1;
    });
  }

  // 行程段城市二级选择（国家→城市）：cityGroups[''] 是未分类城市。
  var cityGroups = {};
  try {
    var dataEl = document.getElementById('city-groups-data');
    if (dataEl) cityGroups = JSON.parse(dataEl.textContent);
  } catch (e) { cityGroups = {}; }

  function fillCitySelect(citySelect, country, keepValue) {
    var names = country === '__none__' ? (cityGroups[''] || []) : (cityGroups[country] || []);
    citySelect.innerHTML = '<option value="">城市</option>';
    names.forEach(function (name) {
      var opt = document.createElement('option');
      opt.value = name; opt.textContent = name;
      if (name === keepValue) opt.selected = true;
      citySelect.appendChild(opt);
    });
  }

  function syncNewMode(countrySelect, citySelect, newInput) {
    var isNew = countrySelect.value === '__new__';
    citySelect.hidden = isNew;
    citySelect.disabled = isNew;
    newInput.hidden = !isNew;
    newInput.disabled = !isNew;
    if (isNew) newInput.focus();
  }

  function initCityPicker(picker) {
    var countrySelect = picker.querySelector('.leg-country');
    var citySelect = picker.querySelector('.leg-city');
    var newInput = picker.querySelector('.leg-city-new');
    if (!countrySelect || !citySelect || !newInput) return;
    if (countrySelect.value) {
      fillCitySelect(citySelect, countrySelect.value, citySelect.dataset.selected || '');
    }
    syncNewMode(countrySelect, citySelect, newInput);
  }

  function addRow(containerId, templateId) {
    var tpl = document.getElementById(templateId);
    var container = document.getElementById(containerId);
    if (!tpl || !container) return;
    container.appendChild(tpl.content.cloneNode(true));
    renumberLegs();
    var last = container.lastElementChild;
    if (last) last.querySelectorAll('.leg-city-picker').forEach(initCityPicker);
  }

  function clearRow(row) {
    row.querySelectorAll('input').forEach(function (i) {
      if (i.type !== 'hidden') i.value = '';
    });
    row.querySelectorAll('select').forEach(function (s) { s.selectedIndex = 0; });
    row.querySelectorAll('.leg-city-picker').forEach(function (picker) {
      var countrySelect = picker.querySelector('.leg-country');
      var citySelect = picker.querySelector('.leg-city');
      var newInput = picker.querySelector('.leg-city-new');
      citySelect.innerHTML = '<option value="">城市</option>';
      syncNewMode(countrySelect, citySelect, newInput);
    });
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
    if (e.target.matches('.leg-country')) {
      var picker = e.target.closest('.leg-city-picker');
      var citySelect = picker.querySelector('.leg-city');
      var newInput = picker.querySelector('.leg-city-new');
      fillCitySelect(citySelect, e.target.value, '');
      syncNewMode(e.target, citySelect, newInput);
    }
  });

  document.querySelectorAll('.leg-city-picker').forEach(initCityPicker);
})();
