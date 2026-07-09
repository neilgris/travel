// 每日消费记录：同一天内拖拽调整顺序，异步提交，不刷新页面。
// 原生 HTML5 拖放，无第三方库。每个 .entry-list 是一天的记录容器。
(function () {
  "use strict";

  function afterElement(list, y) {
    // 在鼠标 y 坐标处，找到应插在其“之前”的行（离下沿最近且在其上方的那个）。
    const rows = [...list.querySelectorAll(".entry-row:not(.dragging)")];
    let closest = { offset: -Infinity, el: null };
    for (const row of rows) {
      const box = row.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > closest.offset) {
        closest = { offset, el: row };
      }
    }
    return closest.el;
  }

  function submitOrder(list) {
    const order = [...list.querySelectorAll(".entry-row")]
      .map((r) => Number(r.dataset.entryId));
    fetch(list.dataset.reorderUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ order: order }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (!data.ok) throw new Error(data.error || "reorder failed");
      })
      .catch((err) => {
        console.error("排序保存失败：", err);
        alert("排序保存失败，请刷新页面后重试。");
      });
  }

  function initList(list) {
    let dragging = null;

    list.addEventListener("dragstart", (e) => {
      const row = e.target.closest(".entry-row");
      if (!row || !list.contains(row)) return;
      dragging = row;
      row.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });

    list.addEventListener("dragend", () => {
      if (!dragging) return;
      dragging.classList.remove("dragging");
      dragging = null;
      submitOrder(list);
    });

    list.addEventListener("dragover", (e) => {
      if (!dragging) return;
      e.preventDefault();
      const ref = afterElement(list, e.clientY);
      if (ref == null) {
        list.appendChild(dragging);
      } else if (ref !== dragging) {
        list.insertBefore(dragging, ref);
      }
    });
  }

  document.querySelectorAll(".entry-list").forEach(initList);
})();
