// 每天卡片的照片删除：确认后异步提交（带 X-Requested-With），成功就地移除缩略图，不刷新页面。
// 用事件委托挂在 document 上，同时覆盖服务端渲染的缩略图和 photo-drop.js 动态插入的缩略图。
(function () {
  "use strict";

  document.addEventListener("submit", (e) => {
    const form = e.target.closest(".photo-del-form");
    if (!form) return;
    e.preventDefault();
    if (!confirm("删除这张照片？此操作不可恢复。")) return;

    const thumb = form.closest(".photo-thumb");
    fetch(form.action, {
      method: "POST",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then((r) => r.json())
      .then((data) => {
        if (!data.ok) throw new Error(data.error || "delete failed");
        if (thumb) thumb.remove();
      })
      .catch((err) => {
        console.error("照片删除失败：", err);
        alert("照片删除失败，请刷新页面后重试。");
      });
  });
})();
