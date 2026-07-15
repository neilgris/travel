// 每天卡片的照片墙：同天内拖拽调整顺序，异步提交，不刷新页面。
// .day-photos 是 flex-wrap 的横向照片墙（非纵向列表），判断插入位置要按 2D 最近距离，
// 不能照搬 entry-reorder.js 只看 y 坐标那一套。原生 HTML5 拖放，无第三方库。
(function () {
  "use strict";

  function closestThumb(zone, x, y) {
    const thumbs = [...zone.querySelectorAll(".photo-thumb:not(.dragging)")];
    let best = null;
    let bestDist = Infinity;
    for (const el of thumbs) {
      const box = el.getBoundingClientRect();
      const cx = box.left + box.width / 2;
      const cy = box.top + box.height / 2;
      const dist = Math.hypot(x - cx, y - cy);
      if (dist < bestDist) {
        bestDist = dist;
        best = { el, cx, box };
      }
    }
    return best;
  }

  function submitOrder(zone) {
    const order = [...zone.querySelectorAll(".photo-thumb")]
      .map((t) => Number(t.dataset.imageId));
    fetch(zone.dataset.reorderUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ order: order }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (!data.ok) throw new Error(data.error || "reorder failed");
      })
      .catch((err) => {
        console.error("照片排序保存失败：", err);
        alert("照片排序保存失败，请刷新页面后重试。");
      });
  }

  function initZone(zone) {
    let dragging = null;

    zone.addEventListener("dragstart", (e) => {
      const thumb = e.target.closest(".photo-thumb");
      if (!thumb || !zone.contains(thumb)) return;
      dragging = thumb;
      thumb.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });

    zone.addEventListener("dragend", () => {
      if (!dragging) return;
      dragging.classList.remove("dragging");
      dragging = null;
      submitOrder(zone);
    });

    zone.addEventListener("dragover", (e) => {
      if (!dragging) return;
      e.preventDefault();
      const closest = closestThumb(zone, e.clientX, e.clientY);
      if (!closest) {
        zone.appendChild(dragging);
        return;
      }
      const { el, cx, box } = closest;
      if (el === dragging) return;
      let before;
      if (e.clientY < box.top) before = true;
      else if (e.clientY > box.bottom) before = false;
      else before = e.clientX < cx;
      zone.insertBefore(dragging, before ? el : el.nextElementSibling);
    });
  }

  document.querySelectorAll(".day-photos").forEach(initZone);
})();
