// 每天卡片的「+ 添加照片」拖拽区：把「照片」App 拖出的图（含 HEIC）异步上传。
// 走已有的 add_day_images 端点（带 X-Requested-With → 返回 JSON），成功后就地插进
// 当天的 .day-photos，不刷新页面。原生 API，无第三方库。保留原文件选择表单作兜底。
(function () {
  "use strict";

  function thumbFor(img) {
    // 与 detail.html 里 .photo-thumb 结构保持一致；删除交互由 photo-delete.js 委托处理。
    const span = document.createElement("span");
    span.className = "photo-thumb";
    span.draggable = true;
    span.dataset.imageId = img.id;

    const el = document.createElement("img");
    el.className = "thumb";
    el.draggable = false;
    el.src = img.url;

    const form = document.createElement("form");
    form.method = "post";
    form.className = "photo-del-form";
    form.action = img.delete_url;

    const btn = document.createElement("button");
    btn.type = "submit";
    btn.className = "photo-del";
    btn.title = "删除照片";
    btn.textContent = "×";

    form.appendChild(btn);
    span.appendChild(el);
    span.appendChild(form);
    return span;
  }

  function upload(zone, files) {
    const images = [...files].filter((f) => f.type.startsWith("image/") || /\.(heic|heif)$/i.test(f.name));
    if (!images.length) return;
    const gallery = zone.closest(".card").querySelector(".day-photos");
    const fd = new FormData();
    images.forEach((f) => fd.append("images", f, f.name));

    zone.classList.add("uploading");
    fetch(zone.dataset.uploadUrl, {
      method: "POST",
      headers: { "X-Requested-With": "XMLHttpRequest" },
      body: fd,
    })
      .then((r) => r.json())
      .then((data) => {
        if (!data.ok) throw new Error(data.error || "upload failed");
        data.images.forEach((img) => gallery.appendChild(thumbFor(img)));
      })
      .catch((err) => {
        console.error("照片上传失败：", err);
        alert("照片上传失败，请重试。");
      })
      .finally(() => zone.classList.remove("uploading"));
  }

  function initZone(zone) {
    ["dragenter", "dragover"].forEach((type) =>
      zone.addEventListener(type, (e) => {
        e.preventDefault();
        zone.classList.add("dragover");
      })
    );
    ["dragleave", "dragend"].forEach((type) =>
      zone.addEventListener(type, (e) => {
        // 只有真正离开拖拽区（而非移到子元素上）才取消高亮。
        if (type === "dragleave" && zone.contains(e.relatedTarget)) return;
        zone.classList.remove("dragover");
      })
    );
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("dragover");
      if (e.dataTransfer && e.dataTransfer.files.length) {
        upload(zone, e.dataTransfer.files);
      }
    });
  }

  document.querySelectorAll(".photo-drop").forEach(initZone);
})();
