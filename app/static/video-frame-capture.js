// 「+ 添加照片」区选中的视频：本地用 <video>+<canvas> 截一帧存成 JPEG，视频本身不上传、不落盘。
// photo-drop.js 把混在一起的视频挑出来后派 qclaw:videos-picked 过来，这里逐个弹窗让用户定格，
// 截出的帧再经 qclaw:upload-files 回给 photo-drop.js 走正常上传。
// 视频来源只能是「选择文件」或从 Finder 拖入：macOS「照片」App 拖视频只给 JPEG 封面帧，拿不到原片。
(function () {
  "use strict";

  // 微调步长：多数手机视频 30fps，0.04 秒约一帧多一点，够用来卡表情/动作。
  const STEP = 0.04;

  function openCapture(file, zone, index, total, done) {
    const video = document.createElement("video");
    video.src = URL.createObjectURL(file);
    video.controls = true;
    video.playsInline = true;
    video.muted = true;
    video.preload = "auto";
    // 不自动播放：停在第一帧等你挑，否则画面在动、点哪一帧全凭手速。
    // 但只加载不播的话浏览器不会解码首帧，此时 drawImage 画出来是全黑的，
    // 所以轻推一下进度逼它把第一帧解出来。
    video.addEventListener(
      "loadeddata",
      () => {
        if (video.currentTime === 0) video.currentTime = 0.001;
      },
      { once: true }
    );

    const hint = document.createElement("p");
    hint.className = "video-frame-hint";
    const which = total > 1 ? `（第 ${index + 1}/${total} 个视频）` : "";
    hint.textContent = `${file.name}${which}：播放或拖动进度条找到画面，用 ◀ ▶ 微调到满意的一帧`;

    const clock = document.createElement("span");
    clock.className = "video-frame-clock";
    const showTime = () => {
      clock.textContent = `${video.currentTime.toFixed(2)}s / ${(video.duration || 0).toFixed(2)}s`;
    };
    video.addEventListener("loadedmetadata", showTime);
    video.addEventListener("timeupdate", showTime);
    video.addEventListener("seeked", showTime);

    // 微调时先暂停，否则刚跳过去就被播放冲走。
    function step(delta) {
      video.pause();
      const t = Math.min(Math.max(video.currentTime + delta, 0), video.duration || 0);
      video.currentTime = t;
    }

    const prevBtn = document.createElement("button");
    prevBtn.type = "button";
    prevBtn.className = "btn btn-sm btn-ghost";
    prevBtn.textContent = "◀";
    prevBtn.title = "往前微调一帧";
    prevBtn.addEventListener("click", () => step(-STEP));

    const nextBtn = document.createElement("button");
    nextBtn.type = "button";
    nextBtn.className = "btn btn-sm btn-ghost";
    nextBtn.textContent = "▶";
    nextBtn.title = "往后微调一帧";
    nextBtn.addEventListener("click", () => step(STEP));

    const captureBtn = document.createElement("button");
    captureBtn.type = "button";
    captureBtn.className = "btn btn-sm";
    captureBtn.textContent = "截取这一帧";

    const skipBtn = document.createElement("button");
    skipBtn.type = "button";
    skipBtn.className = "btn btn-sm btn-ghost";
    skipBtn.textContent = total > 1 && index < total - 1 ? "跳过这个" : "取消";

    const actions = document.createElement("div");
    actions.className = "video-frame-actions";
    actions.appendChild(prevBtn);
    actions.appendChild(nextBtn);
    actions.appendChild(clock);
    actions.appendChild(captureBtn);
    actions.appendChild(skipBtn);

    const box = document.createElement("div");
    box.className = "video-frame-box";
    box.appendChild(video);
    box.appendChild(hint);
    box.appendChild(actions);

    const overlay = document.createElement("div");
    overlay.className = "video-frame-modal";
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    function close() {
      URL.revokeObjectURL(video.src);
      overlay.remove();
      done();
    }

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close();
    });
    skipBtn.addEventListener("click", close);

    captureBtn.addEventListener("click", () => {
      // 还没解出画面就截会得到一张全黑图，宁可让用户等一下。
      if (!video.videoWidth || video.readyState < 2) {
        alert("视频还没加载好，稍等一下再截。");
        return;
      }
      const canvas = document.createElement("canvas");
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext("2d").drawImage(video, 0, 0);
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            alert("截取失败，请重试。");
            return;
          }
          const base = file.name.replace(/\.[^.]+$/, "") || "frame";
          const frame = new File([blob], `${base}-${Date.now()}.jpg`, { type: "image/jpeg" });
          zone.dispatchEvent(new CustomEvent("qclaw:upload-files", { detail: { files: [frame] } }));
          close();
        },
        "image/jpeg",
        0.92
      );
    });
  }

  // 一次拖进来多个视频就排队，一个处理完（截取或跳过）再弹下一个。
  function runQueue(zone, videos) {
    let i = 0;
    (function next() {
      if (i >= videos.length) return;
      openCapture(videos[i], zone, i, videos.length, () => {
        i += 1;
        next();
      });
    })();
  }

  document.querySelectorAll(".photo-drop").forEach((zone) => {
    zone.addEventListener("qclaw:videos-picked", (e) => {
      if (e.detail && e.detail.files && e.detail.files.length) {
        runQueue(zone, e.detail.files);
      }
    });
  });
})();
