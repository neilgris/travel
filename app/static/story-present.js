/* 故事页放映壳：全屏 overlay + slide 编排 + 自动播放 + 3D 地球飞行过场。
   零后端：slides 从故事页 DOM 与 data-map JSON 拼装；three/globe.gl 进放映时才注入。
   设计见 docs/specs/2026-07-15-presentation-mode-design.md。 */
(function () {
  const btn = document.getElementById("story-present-btn");
  if (!btn) return;
  const VENDOR = btn.dataset.vendor;                     // /static/vendor/

  const mapEl = document.getElementById("story-map");
  let MAP = {};
  try { MAP = JSON.parse((mapEl && mapEl.dataset.map) || "{}"); } catch (e) { MAP = {}; }
  const CITIES = MAP.cities || [];
  const DAY_CITIES = MAP.day_cities || [];
  const ROUTE = MAP.route || [];

  // 按天下标反查城市（day_cities 只有坐标，名字从 cities 找）。
  const cityAt = (idx) => {
    const dc = DAY_CITIES[idx];
    if (!dc) return null;
    return CITIES.find((c) => c.lat === dc.lat && c.lng === dc.lng) || dc;
  };

  // ---------- slides 组装 ----------
  function buildSlides() {
    const sections = Array.from(document.querySelectorAll(".story-day[data-day-index]"));
    // 照片页/天上限：短旅程(≤7天)3页，长旅程2页；每页尽量 ≤4 张，超上限才多塞。
    const perDayCap = sections.length <= 7 ? 3 : 2;
    const slides = [{ type: "opening" }];
    let prevCity = null;
    sections.forEach((sec, idx) => {
      const city = cityAt(idx);
      if (idx > 0 && city && prevCity &&
          (city.lat !== prevCity.lat || city.lng !== prevCity.lng)) {
        slides.push({ type: "fly", from: prevCity, to: city, dayIndex: idx });
      }
      if (city) prevCity = city;

      const journal = sec.querySelector(".story-journal");
      const spend = sec.querySelector(".story-spend");
      slides.push({
        type: "day", dayIndex: idx,
        head: sec.querySelector(".story-day-head").innerHTML,
        journal: journal ? journal.innerHTML : "",
        spend: spend ? spend.innerHTML : "",
        compact: sec.classList.contains("story-day-slim"),
      });

      const photos = Array.from(sec.querySelectorAll(".story-photo")).map((p) => p.src);
      if (photos.length) {
        const pages = Math.min(perDayCap, Math.ceil(photos.length / 4));
        const per = Math.ceil(photos.length / pages);
        for (let i = 0; i < photos.length; i += per)
          slides.push({ type: "photos", dayIndex: idx, imgs: photos.slice(i, i + per) });
      }
    });
    slides.push({ type: "ending", days: sections.length });
    return slides;
  }

  // ---------- 节奏（毫秒）：正文按日记字数伸缩，结尾停住 ----------
  function durationOf(s) {
    if (s.type === "opening") return 5000;
    if (s.type === "fly") return 3200;
    if (s.type === "photos") return 5000;
    if (s.type === "ending") return Infinity;
    if (s.compact) return 3000;
    const chars = (s.journal || "").replace(/<[^>]*>/g, "").length;
    return Math.min(15000, 6000 + chars * 50);
  }

  // ---------- 3D 地球：进放映才注入 three/globe.gl，失败一律降级直切 ----------
  let world = null, globeReady = false, globePromise = null;
  function ensureGlobe() {
    if (!CITIES.length) return Promise.resolve();        // 全缺坐标：连库都不加载
    if (globePromise) return globePromise;
    globePromise = (async () => {
      try {
        // 与首页同款：ESM 引 three 挂 window.THREE，globe.gl(UMD) 复用同一实例。
        const THREE = await import(VENDOR + "three.module.js");
        window.THREE = window.THREE || Object.assign({}, THREE);
        await new Promise((res, rej) => {
          if (window.Globe) return res();
          const sc = document.createElement("script");
          sc.src = VENDOR + "globe.gl.min.js"; sc.onload = res; sc.onerror = rej;
          document.head.appendChild(sc);
        });
        world = Globe()
          .backgroundImageUrl(VENDOR + "night-sky.png")
          .globeImageUrl(VENDOR + "earth-blue-marble.jpg")
          .atmosphereColor("#5aa9ff").atmosphereAltitude(0.18)
          .pointsData(CITIES).pointLat("lat").pointLng("lng")
          .pointColor(() => "#ffe08a").pointAltitude(0.01).pointRadius(0.28)
          .arcsData([]).arcColor(() => "#e8792b").arcStroke(0.8)
          .arcAltitudeAutoScale(0.4)
          (globeLayer);
        world.controls().enabled = false;                // 演示不许拖球
        sizeGlobe();
        window.addEventListener("resize", sizeGlobe);
        globeReady = true;
      } catch (e) { globeReady = false; }
    })();
    return globePromise;
  }
  function sizeGlobe() {
    if (world) world.width(overlay.clientWidth).height(overlay.clientHeight);
  }

  function firstCity() {
    for (const dc of DAY_CITIES) if (dc) return dc;      // 第一个有坐标的天
    return CITIES[0] || null;
  }
  function openingFlight() {
    const c = firstCity();
    if (!c) return;
    world.arcsData([]);
    world.pointOfView({ lat: c.lat, lng: c.lng, altitude: 2.5 }, 0);
    world.pointOfView({ lat: c.lat, lng: c.lng, altitude: 0.9 }, 3500);
  }
  function flyTo(s) {
    // 单条弧线一次性画出（dash 一个周期 > 页时长，不会循环重画）。
    world.arcsData([{ startLat: s.from.lat, startLng: s.from.lng,
                      endLat: s.to.lat, endLng: s.to.lng }])
      .arcDashLength(1).arcDashGap(2).arcDashInitialGap(1).arcDashAnimateTime(3000);
    world.pointOfView({ lat: s.from.lat, lng: s.from.lng, altitude: 1.0 }, 0);
    world.pointOfView({ lat: s.to.lat, lng: s.to.lng, altitude: 1.0 }, 2800);
  }
  function endingView() {
    world.arcsData(ROUTE.map((r) => ({
      startLat: r.from.lat, startLng: r.from.lng,
      endLat: r.to.lat, endLng: r.to.lng,
    }))).arcDashLength(1).arcDashGap(0).arcDashInitialGap(0).arcDashAnimateTime(0);
    const v = viewOfAll();
    world.pointOfView({ lat: v.lat, lng: v.lng, altitude: v.alt }, 2000);
  }
  function viewOfAll() {
    // 包围盒中心 + 按跨度估高度（不处理跨经线 180°，YAGNI）。
    let latMin = 90, latMax = -90, lngMin = 180, lngMax = -180;
    CITIES.forEach((c) => {
      latMin = Math.min(latMin, c.lat); latMax = Math.max(latMax, c.lat);
      lngMin = Math.min(lngMin, c.lng); lngMax = Math.max(lngMax, c.lng);
    });
    const span = Math.max(latMax - latMin, lngMax - lngMin);
    return { lat: (latMin + latMax) / 2, lng: (lngMin + lngMax) / 2,
             alt: Math.max(0.5, Math.min(2.5, span / 40 + 0.4)) };
  }

  // ---------- overlay ----------
  let overlay, slideEl, globeLayer, minimapEl, minimap, hudCaption, hudBar, pausedEl;
  function buildOverlay() {
    overlay = document.createElement("div");
    overlay.className = "story-present";
    overlay.innerHTML =
      '<div class="sp-globe"></div>' +
      '<div class="sp-slide"></div>' +
      '<div class="sp-minimap"></div>' +
      '<div class="sp-caption"></div>' +
      '<div class="sp-paused">⏸</div>' +
      '<div class="sp-progress"><i></i></div>';
    document.body.appendChild(overlay);
    slideEl = overlay.querySelector(".sp-slide");
    globeLayer = overlay.querySelector(".sp-globe");
    minimapEl = overlay.querySelector(".sp-minimap");
    hudCaption = overlay.querySelector(".sp-caption");
    pausedEl = overlay.querySelector(".sp-paused");
    hudBar = overlay.querySelector(".sp-progress i");
    if (CITIES.length && window.STORY_MAP)
      minimap = STORY_MAP.render(minimapEl, MAP, { pad: 18 });
    overlay.addEventListener("click", () => next());
  }

  // ---------- slide 渲染 ----------
  function renderSlide(s) {
    minimapEl.style.display = s.type === "day" && minimap ? "" : "none";
    globeShow(s.type === "opening" || s.type === "fly" || s.type === "ending");
    let html = "";
    if (s.type === "opening") {
      const hero = document.querySelector(".story-hero");
      html = '<div class="sp-opening"><h1>' + hero.querySelector("h1").innerHTML + "</h1>" +
             "<p>" + hero.querySelector(".story-meta").innerHTML + "</p></div>";
    } else if (s.type === "day") {
      html = '<div class="sp-day' + (s.compact ? " sp-compact" : "") + '">' +
             "<h2>" + s.head + "</h2>" +
             (s.journal ? '<div class="sp-journal">' + s.journal + "</div>" : "") +
             (s.spend ? '<div class="sp-spend">' + s.spend + "</div>" : "") + "</div>";
      if (minimap) minimap.highlightDay(s.dayIndex);
    } else if (s.type === "photos") {
      html = '<div class="sp-photos sp-n' + Math.min(s.imgs.length, 6) + '">' +
             s.imgs.map((src) => '<img src="' + src + '" alt="">').join("") + "</div>";
    } else if (s.type === "ending") {
      const meta = document.querySelector(".story-meta").textContent;
      const km = (meta.match(/里程\s*([\d,]+)\s*km/) || [])[1];
      const cost = (meta.match(/总花费\s*(￥[\d.,]+)/) || [])[1];
      html = '<div class="sp-ending"><h2>' +
             document.querySelector(".story-hero h1").textContent + "</h2>" +
             "<p>" + s.days + " 天 · " + CITIES.length + " 城" +
             (km ? " · " + km + " km" : "") + (cost ? " · " + cost : "") + "</p>" +
             '<p class="sp-hint">↵ 重播 · Esc 退出</p></div>';
    }
    // fly 页无正文，只有地球层（Task 5 实现飞行）。
    slideEl.innerHTML = html;
    slideEl.classList.remove("sp-in");
    void slideEl.offsetWidth;                            // 重启入场动画
    slideEl.classList.add("sp-in");
    hudCaption.textContent = captionOf(s);
  }
  function captionOf(s) {
    const pos = (idx + 1) + "/" + slides.length;
    return s.dayIndex != null ? "Day " + (s.dayIndex + 1) + " · " + pos : pos;
  }

  // ---------- 播放引擎：rAF 主循环，elapsed 到点翻页 ----------
  let slides = [], idx = 0, active = false, paused = false;
  let elapsed = 0, lastT = 0, rafId = 0;

  function loop(t) {
    if (!active) return;
    rafId = requestAnimationFrame(loop);
    if (paused) { lastT = t; return; }
    elapsed += t - lastT; lastT = t;
    const d = durationOf(slides[idx]);
    const frac = d === Infinity ? 0 : Math.min(1, elapsed / d);
    hudBar.style.width = ((idx + frac) / slides.length * 100) + "%";  // 总进度
    if (elapsed >= d) next();
  }

  function show(i) {
    idx = Math.max(0, Math.min(slides.length - 1, i));
    elapsed = 0;
    renderSlide(slides[idx]);
    onSlideStart(slides[idx]);
  }
  function next() { if (idx < slides.length - 1) show(idx + 1); }
  function prev() { show(idx - 1); }
  function setPaused(p) {
    paused = p;
    pausedEl.style.display = paused ? "" : "none";
  }
  function onSlideStart(s) {
    if (s.type === "fly") {
      if (!globeReady) { show(idx + 1); return; }        // 降级：直切
      flyTo(s);
    }
    if (s.type === "opening" && globeReady) openingFlight();
    if (s.type === "ending" && globeReady) endingView();
  }
  function globeShow(on) {
    globeLayer.classList.toggle("sp-globe-on", !!on && globeReady);
  }

  // ---------- 光标：3 秒不动就藏 ----------
  let cursorTimer = 0;
  function wakeCursor() {
    overlay.classList.remove("sp-nocursor");
    clearTimeout(cursorTimer);
    cursorTimer = setTimeout(() => overlay.classList.add("sp-nocursor"), 3000);
  }

  function onKey(e) {
    if (e.key === "Escape") { exit(); return; }
    if (e.key === " ") { e.preventDefault(); setPaused(!paused); return; }
    if (e.key === "ArrowRight") next();
    if (e.key === "ArrowLeft") prev();
    if (e.key === "Enter" && slides[idx].type === "ending") show(0);
  }
  function onFsChange() {
    if (!document.fullscreenElement && active) exit();   // 系统 Esc 退全屏 → 一并退放映
  }

  async function start() {
    if (!overlay) buildOverlay();
    overlay.style.display = "";
    slides = buildSlides();
    active = true;
    document.addEventListener("keydown", onKey);
    document.addEventListener("fullscreenchange", onFsChange);
    if (overlay.requestFullscreen) overlay.requestFullscreen().catch(() => {});
    await ensureGlobe();                                 // 失败不阻塞，globeReady=false 走降级
    if (!active) return;                                 // 等待期间被 Esc 了
    show(0);
    setPaused(false);
    wakeCursor();
    overlay.addEventListener("mousemove", wakeCursor);
    lastT = performance.now();
    rafId = requestAnimationFrame(loop);
  }
  function exit() {
    if (!active) return;
    active = false;
    cancelAnimationFrame(rafId);
    clearTimeout(cursorTimer);
    overlay.removeEventListener("mousemove", wakeCursor);
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("fullscreenchange", onFsChange);
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    overlay.style.display = "none";
    // 回到当前天在故事页的位置。
    const s = slides[idx];
    const di = s && s.dayIndex != null ? s.dayIndex : 0;
    const target = document.querySelector('.story-day[data-day-index="' + di + '"]');
    if (target) target.scrollIntoView({ block: "start" });
  }

  btn.addEventListener("click", start);
})();
