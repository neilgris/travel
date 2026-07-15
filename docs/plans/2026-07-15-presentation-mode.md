# 全屏演示模式 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给故事页加放映壳：全屏、自动翻页、换城市时 3D 地球沿路线飞行过场。

**Architecture:** 纯前端壳（方案 A）——slides 由 JS 从故事页现有 DOM 与 `data-map` JSON 拼装，零后端改动、无新路由；three/globe.gl 进放映时才懒加载。设计权威来源：[docs/specs/2026-07-15-presentation-mode-design.md](../specs/2026-07-15-presentation-mode-design.md)。

**Tech Stack:** Jinja2 模板（只加一个按钮）、原生 JS、d3（复用故事页 2D 小地图）、Globe.gl + three（vendor 已有，离线）。

## Global Constraints

- **零后端改动**：不改 models/services/blueprints；模板只加放映按钮。
- **前端不写测试**（项目惯例）；pytest 只为模板按钮的出现/不出现各加一条。
- JS/CSS 注释用中文，风格对齐现有 `story-map.js` / `story.css`。
- vendor 资产全离线复用：`three.module.js`、`globe.gl.min.js`、`earth-blue-marble.jpg`、`night-sky.png`。
- 分支：`feat/presentation-mode`；commit message 末尾加 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。
- 每个 Task 结束都要 `pytest -v` 全绿（防止壳改坏现有故事页断言）。

---

### Task 1: 放映按钮入口（TDD）

**Files:**
- Modify: `app/templates/trips/story.html`（hero 区）
- Modify: `app/static/story.css`（按钮样式）
- Test: `tests/test_story.py`

**Interfaces:**
- Produces: `#story-present-btn` 按钮（有 Day 才渲染），带 `data-vendor` 属性 = `/static/vendor/`，后续任务的 JS 靠它拿懒加载基址。

- [ ] **Step 0: 建分支**

```bash
git checkout -b feat/presentation-mode
```

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_story.py` 末尾）

```python
def test_story_page_has_present_button(client, app):
    from app.extensions import db
    with app.app_context():
        t = Trip(title="t", start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 1))
        t.days = [Day(date=dt.date(2026, 1, 1), diary="日记")]
        db.session.add(t)
        db.session.commit()
        tid = t.id
    body = client.get(f"/trips/{tid}/story").get_data(as_text=True)
    assert "story-present-btn" in body   # 有 Day：显示放映按钮


def test_story_page_no_present_button_without_days(client, app):
    from app.extensions import db
    with app.app_context():
        t = Trip(title="空行", start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 1))
        db.session.add(t)
        db.session.commit()
        tid = t.id
    body = client.get(f"/trips/{tid}/story").get_data(as_text=True)
    assert "story-present-btn" not in body   # 无 Day：不渲染
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_story.py -v -k present_button`
Expected: 2 FAILED（`story-present-btn` not in body）

- [ ] **Step 3: 改模板**

`app/templates/trips/story.html` 中，把 hero 里现有的：

```html
  <a class="story-back" href="{{ url_for('trips.detail', trip_id=trip.id) }}">← 返回详情</a>
```

替换为：

```html
  <div class="story-actions">
    {% if story.days %}
    <button type="button" id="story-present-btn" class="story-present-btn"
            data-vendor="{{ url_for('static', filename='vendor') }}/">▶ 放映</button>
    {% endif %}
    <a class="story-back" href="{{ url_for('trips.detail', trip_id=trip.id) }}">← 返回详情</a>
  </div>
```

- [ ] **Step 4: 改样式**

`app/static/story.css` 中，把现有 `.story-back` 两条规则替换为（胶囊样式共享给按钮）：

```css
.story-actions { position: absolute; top: 0; right: 0; display: flex; gap: 8px; }
.story-back, .story-present-btn {
  font-size: .85rem; color: #888; text-decoration: none; padding: 5px 12px;
  border: 1px solid #ddd; border-radius: 14px; background: none; cursor: pointer;
  font-family: inherit; transition: color .15s, border-color .15s, background .15s; }
.story-back:hover, .story-present-btn:hover {
  color: #b8955a; border-color: #b8955a; background: #faf7f0; }
```

（`.story-back` 原来的 `position: absolute; top: 0; right: 0;` 移到 `.story-actions` 上了。）

- [ ] **Step 5: 跑测试确认通过**

Run: `pytest -v`
Expected: 全部 PASS（含新增 2 条；`test_story_route_is_readonly` 仍过——button 不是 form）

- [ ] **Step 6: Commit**

```bash
git add app/templates/trips/story.html app/static/story.css tests/test_story.py
git commit -m "feat: 故事页加放映按钮入口

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: story-map.js 抽出可复用 render()

**Files:**
- Modify: `app/static/story-map.js`（整文件重构，行为不变）

**Interfaces:**
- Produces: `window.STORY_MAP.render(el, data, opts)` → 返回 `{ highlight(name), highlightDay(idx) }` 或 `null`（无坐标城市时）。`opts.pad` 控制投影内边距（默认 40）。放映壳的小地图靠它再渲染一份实例。
- 故事页原行为（左栏地图 + 滚动联动 + 灯箱）不变。

- [ ] **Step 1: 重构**

`app/static/story-map.js` 整文件替换为：

```js
/* 故事页客户端：2D 小地图(d3 等距投影贴合旅程) + 滚动高亮 + 照片灯箱。
   离线依赖：d3、topojson、static/vendor/land-50m.json。
   render() 挂在 window.STORY_MAP 上，放映壳（story-present.js）复用它渲染角落小地图。 */
(function () {
  function render(el, data, opts) {
    opts = opts || {};
    const cities = data.cities || [];
    const route = data.route || [];
    const dayCities = data.day_cities || [];
    if (!cities.length) {
      el.innerHTML = '<p style="padding:1rem;color:#888">暂无坐标</p>';
      return null;
    }

    const w = el.clientWidth || 400;
    const h = el.clientHeight || 520;
    const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${w} ${h}`);

    // 用旅程城市点算包围盒，等距圆柱投影 fitExtent 贴合（区域旅程也看得清）。
    const feat = { type: "FeatureCollection", features: cities.map((c) => ({
      type: "Feature", geometry: { type: "Point", coordinates: [c.lng, c.lat] } })) };
    const projection = d3.geoEquirectangular();
    const pad = opts.pad == null ? 40 : opts.pad;
    projection.fitExtent([[pad, pad], [w - pad, h - pad]], feat);
    const path = d3.geoPath(projection);

    d3.json("/static/vendor/land-50m.json").then((topo) => {
      const land = topojson.feature(topo, topo.objects.land);
      svg.insert("path", ":first-child").datum(land)
        .attr("d", path).attr("fill", "#d7dee6").attr("stroke", "#c2ccd6");
    });

    // 路线：大圆弧线。
    svg.append("g").selectAll("path.route").data(route).join("path")
      .attr("class", "route")
      .attr("d", (r) => path({ type: "LineString",
        coordinates: [[r.from.lng, r.from.lat], [r.to.lng, r.to.lat]] }))
      .attr("fill", "none").attr("stroke", "#e8792b").attr("stroke-width", 2)
      .attr("stroke-linecap", "round").attr("opacity", 0.8);

    // 城市点 + 名字。
    const g = svg.append("g");
    g.selectAll("circle.city-dot").data(cities).join("circle")
      .attr("class", "city-dot")
      .attr("data-city", (c) => c.name)
      .attr("cx", (c) => projection([c.lng, c.lat])[0])
      .attr("cy", (c) => projection([c.lng, c.lat])[1])
      .attr("r", 4).attr("fill", "#5a6472");
    g.selectAll("text.city-label").data(cities).join("text")
      .attr("class", "city-label")
      .attr("x", (c) => projection([c.lng, c.lat])[0] + 6)
      .attr("y", (c) => projection([c.lng, c.lat])[1] + 4)
      .attr("font-size", 11).attr("fill", "#333").text((c) => c.name);

    // 高亮：指定城市点变色放大；highlightDay 按天下标经 day_cities 反查城市。
    const dots = svg.selectAll("circle.city-dot");
    function highlight(name) {
      dots.classed("is-active", (c) => c.name === name)
          .attr("r", (c) => (c.name === name ? 7 : 4));
    }
    function highlightDay(idx) {
      const dc = dayCities[idx];
      if (!dc) { highlight(null); return; }
      const city = cities.find((c) => c.lat === dc.lat && c.lng === dc.lng);
      highlight(city ? city.name : null);
    }
    return { highlight, highlightDay };
  }
  window.STORY_MAP = { render };

  // ---------- 故事页初始化：左栏地图 + 滚动联动 ----------
  const mapEl = document.getElementById("story-map");
  if (mapEl) {
    let data;
    try { data = JSON.parse(mapEl.dataset.map || "{}"); } catch (e) { data = {}; }
    const map = render(mapEl, data);
    if (map) {
      const sections = document.querySelectorAll(".story-day[data-day-index]");
      const io = new IntersectionObserver((entries) => {
        const vis = entries.filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (!vis) return;
        map.highlightDay(+vis.target.dataset.dayIndex);
      }, { rootMargin: "-45% 0px -45% 0px" });
      sections.forEach((s) => io.observe(s));
    }
  }

  // ---------- 照片灯箱 ----------
  initLightbox();
  function initLightbox() {
    const photos = Array.from(document.querySelectorAll(".story-photo"));
    if (!photos.length) return;
    const box = document.createElement("div");
    box.className = "story-lightbox";
    box.innerHTML =
      '<button class="story-lb-nav story-lb-prev" aria-label="上一张">‹</button>' +
      '<img alt="">' +
      '<button class="story-lb-nav story-lb-next" aria-label="下一张">›</button>';
    document.body.appendChild(box);
    const img = box.querySelector("img");
    let i = 0;
    const show = (n) => { i = (n + photos.length) % photos.length; img.src = photos[i].src; };
    photos.forEach((p, n) => p.addEventListener("click", () => { show(n); box.classList.add("open"); }));
    box.querySelector(".story-lb-prev").addEventListener("click", (e) => { e.stopPropagation(); show(i - 1); });
    box.querySelector(".story-lb-next").addEventListener("click", (e) => { e.stopPropagation(); show(i + 1); });
    box.addEventListener("click", () => box.classList.remove("open"));
    document.addEventListener("keydown", (e) => {
      if (!box.classList.contains("open")) return;
      if (e.key === "Escape") box.classList.remove("open");
      if (e.key === "ArrowLeft") show(i - 1);
      if (e.key === "ArrowRight") show(i + 1);
    });
  }
})();
```

- [ ] **Step 2: 手动验证故事页没坏**

启动 `python run.py`，开 `http://localhost:8000/trips/1/story`：
- 左栏地图正常渲染（陆地/路线/城市点/城市名）。
- 滚动右栏，当天城市点仍放大变橙。
- 点照片弹灯箱，←/→/Esc 正常。

- [ ] **Step 3: 跑测试 + Commit**

Run: `pytest -v` → 全 PASS

```bash
git add app/static/story-map.js
git commit -m "refactor: story-map 抽出可复用 render()，供放映壳小地图复用

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: 放映壳骨架（overlay + slides 组装 + 手动翻页 + 照片拼贴）

**Files:**
- Create: `app/static/story-present.js`
- Modify: `app/templates/trips/story.html`（scripts 块加一行）
- Modify: `app/static/story.css`（放映壳样式）

**Interfaces:**
- Consumes: `#story-present-btn`（Task 1）、`window.STORY_MAP.render`（Task 2）、故事页 DOM（`.story-day` / `.story-hero` / `data-map`）。
- Produces: slide 数据结构 `{type: "opening"|"day"|"photos"|"fly"|"ending", ...}` 与 `show(i)/next()/prev()/exit()`；Task 4 的播放引擎、Task 5 的地球都挂在这些点上。本任务结束时：点放映 → 全屏、→/←/点击翻页、Esc 退出；`fly` 页暂为直切占位（渲染为空，立即可跳）。

- [ ] **Step 1: 模板加载脚本**

`app/templates/trips/story.html` 的 `{% block scripts %}` 里，`story-map.js` 那行之后加：

```html
<script src="{{ url_for('static', filename='story-present.js') }}"></script>
```

- [ ] **Step 2: 创建 `app/static/story-present.js`**

```js
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

  // ---------- 导航（Task 4 挂自动播放） ----------
  let slides = [], idx = 0, active = false;
  function show(i) {
    idx = Math.max(0, Math.min(slides.length - 1, i));
    resetTimer();
    renderSlide(slides[idx]);
    onSlideStart(slides[idx]);
  }
  function next() { if (idx < slides.length - 1) show(idx + 1); }
  function prev() { show(idx - 1); }
  // 占位：Task 4 覆写计时；Task 5 覆写地球行为。
  function resetTimer() {}
  function onSlideStart(s) {
    if (s.type === "fly") show(idx + 1);                 // 地球未接入前：过场直切
  }
  function globeShow() {}

  function onKey(e) {
    if (e.key === "Escape") { exit(); return; }
    if (e.key === "ArrowRight") next();
    if (e.key === "ArrowLeft") prev();
    if (e.key === "Enter" && slides[idx].type === "ending") show(0);
  }
  function onFsChange() {
    if (!document.fullscreenElement && active) exit();   // 系统 Esc 退全屏 → 一并退放映
  }

  function start() {
    if (!overlay) buildOverlay();
    overlay.style.display = "";
    slides = buildSlides();
    active = true;
    document.addEventListener("keydown", onKey);
    document.addEventListener("fullscreenchange", onFsChange);
    if (overlay.requestFullscreen) overlay.requestFullscreen().catch(() => {});
    show(0);
  }
  function exit() {
    if (!active) return;
    active = false;
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
```

- [ ] **Step 3: 放映壳样式**（追加到 `app/static/story.css` 末尾）

```css
/* ---------- 放映壳（story-present.js 动态挂载） ---------- */
.story-present { position: fixed; inset: 0; z-index: 200; background: #0c0e12; color: #f2efe8; }
.story-present.sp-nocursor { cursor: none; }
.sp-globe { position: absolute; inset: 0; opacity: 0; transition: opacity .8s; pointer-events: none; }
.sp-globe.sp-globe-on { opacity: 1; }
.sp-slide { position: absolute; inset: 0; display: flex; align-items: center;
            justify-content: center; padding: 4vw; box-sizing: border-box; }
.sp-slide.sp-in > * { animation: sp-fade .7s ease both; }
@keyframes sp-fade { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; } }

.sp-opening, .sp-ending { text-align: center; }
.sp-opening h1, .sp-ending h2 { font-size: 3.2rem; margin: 0 0 1rem; }
.sp-opening p, .sp-ending p { color: #cfc9bc; font-size: 1.2rem; }
.sp-hint { opacity: .6; font-size: .95rem !important; margin-top: 2rem; }

.sp-day { max-width: 60rem; width: 100%; }
.sp-day h2 { font-size: 2.4rem; margin: 0 0 1.5rem; }
.sp-day .story-day-n { color: #d9b06c; }
.sp-journal { font-family: Georgia, "Songti SC", serif; font-size: 1.5rem; line-height: 2;
              max-height: 60vh; overflow: hidden; }
.sp-compact h2 { font-size: 1.8rem; color: #9a958a; }
.sp-spend { margin-top: 1.5rem; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.sp-spend .story-hl { background: #2a2d34; color: #d9cfa8; }

/* 照片拼贴：1 全屏 / 2 对分 / 3-4 网格 / ≥5 三列自动行。 */
.sp-photos { display: grid; gap: 10px; width: 100%; height: 100%; grid-auto-rows: 1fr; }
.sp-photos img { width: 100%; height: 100%; object-fit: contain; min-height: 0; }
.sp-n1 { grid-template-columns: 1fr; }
.sp-n2 { grid-template-columns: 1fr 1fr; }
.sp-n3 { grid-template-columns: repeat(3, 1fr); }
.sp-n4 { grid-template-columns: 1fr 1fr; }
.sp-n5, .sp-n6 { grid-template-columns: repeat(3, 1fr); }

.sp-minimap { position: absolute; right: 24px; bottom: 40px; width: 240px; height: 190px;
              background: rgba(255,255,255,.92); border-radius: 10px; overflow: hidden; }
.sp-caption { position: absolute; left: 24px; bottom: 40px; font-size: .9rem; color: #9a958a;
              font-variant-numeric: tabular-nums; }
.sp-paused { position: absolute; top: 20px; right: 24px; font-size: 1.6rem; display: none; }
.sp-progress { position: absolute; left: 0; right: 0; bottom: 0; height: 3px;
               background: rgba(255,255,255,.12); }
.sp-progress i { display: block; height: 100%; width: 0; background: #d9b06c; }
```

- [ ] **Step 4: 手动验证**

`python run.py`，开一个有多天多图的旅程故事页：
- 点「▶ 放映」→ 进全屏深底，开场页显示标题+摘要。
- →/点击逐页翻：正文页（右下角小地图高亮当天城市）、照片页拼贴（1/2/3/4/多张各布局对）。
- 换城市处直切下一天（fly 占位不停留）。
- 结尾页显示统计；↵ 回开场；← 能回退；Esc 退出且滚到当前天。
- 照片分组数符合规则（≤7 天旅程一天最多 3 页、>7 天最多 2 页）。

- [ ] **Step 5: 跑测试 + Commit**

Run: `pytest -v` → 全 PASS

```bash
git add app/static/story-present.js app/static/story.css app/templates/trips/story.html
git commit -m "feat: 放映壳骨架——全屏 overlay、slide 组装、手动翻页、照片拼贴

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: 自动播放引擎（节奏 / 暂停 / 进度条 / 光标隐藏）

**Files:**
- Modify: `app/static/story-present.js`

**Interfaces:**
- Consumes: Task 3 的 `slides/show/next/exit` 与 HUD 元素。
- Produces: `durationOf(s)` 节奏表；rAF 主循环（暂停/恢复、总进度条）；空格暂停；光标 3s 隐藏。Task 5 过场时长复用 `durationOf`。

- [ ] **Step 1: 加节奏表**（`buildSlides` 之后加）

```js
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
```

- [ ] **Step 2: 换导航段为播放引擎**

把 Task 3 的「导航」段（从 `let slides = [], idx = 0, active = false;` 到 `function globeShow() {}`，含 `onKey`）整体替换为：

```js
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
  // 占位：Task 5 覆写地球行为。
  function onSlideStart(s) {
    if (s.type === "fly") show(idx + 1);                 // 地球未接入前：过场直切
  }
  function globeShow() {}

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
```

同时改 `start()` / `exit()`：`start()` 里 `show(0);` 之后加

```js
    setPaused(false);
    wakeCursor();
    overlay.addEventListener("mousemove", wakeCursor);
    lastT = performance.now();
    rafId = requestAnimationFrame(loop);
```

`exit()` 里 `active = false;` 之后加

```js
    cancelAnimationFrame(rafId);
    clearTimeout(cursorTimer);
    overlay.removeEventListener("mousemove", wakeCursor);
```

（Task 3 里 `show()` 调用的 `resetTimer()` 占位已不存在，注意替换后不要遗留对它的引用。）

- [ ] **Step 3: 手动验证**

- 不动键盘：自动翻页；长日记页停更久（封顶 15s）、紧凑天 3s、照片页 5s。
- 空格暂停（⏸ 出现、进度条停），再按继续。
- 底部进度条随播放推进；结尾页停住不再走。
- 鼠标不动 3s 光标消失，动一下回来。
- Esc / 退全屏均正常退出。

- [ ] **Step 4: 跑测试 + Commit**

Run: `pytest -v` → 全 PASS

```bash
git add app/static/story-present.js
git commit -m "feat: 放映壳自动播放——节奏表、暂停、进度条、光标隐藏

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: 3D 地球（懒加载 + 开场 + 过场 + 结尾 + 降级）

**Files:**
- Modify: `app/static/story-present.js`

**Interfaces:**
- Consumes: Task 4 的 `onSlideStart(s)` / `globeShow(on)` 占位、`.sp-globe` 层、`VENDOR` 基址。
- Produces: `ensureGlobe()`（懒加载，失败置 `globeReady=false`）；`openingFlight()` / `flyTo(s)` / `endingView()`。降级规则：`globeReady` 为 false 时开场为静态标题页、fly 页直切、结尾无地球。

- [ ] **Step 1: 地球模块**（`durationOf` 之后加）

```js
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
```

- [ ] **Step 2: 接线**

把 Task 4 的两个占位函数替换为：

```js
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
```

`start()` 改为 async，进全屏后等地球再开播（把 `show(0);` 起的四行包进去）：

```js
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
```

- [ ] **Step 3: 手动验证**

- 多城市旅程：开场地球从远处拉近第一站、标题浮现；换城市时全屏地球弧线飞行 ~3s 后进新一天；结尾地球拉远显示全程弧线 + 统计。
- 过场中按 → 立即进下一页。
- 单城市旅程：无过场，开场/结尾仍有地球。
- 降级：把 `data-vendor` 临时改错（DevTools 里改属性再点放映）→ 无地球、直切、不报错阻塞。
- 故事页首次加载 Network 里**没有** three/globe.gl；点放映后才加载。

- [ ] **Step 4: 跑测试 + Commit**

Run: `pytest -v` → 全 PASS

```bash
git add app/static/story-present.js
git commit -m "feat: 放映壳 3D 地球——懒加载、开场拉近、换城飞行、结尾总览与降级

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: 验收、文档同步、合并

**Files:**
- Modify: `ROADMAP.md`（勾选）
- Modify: `docs/specs/2026-07-14-trip-story-page-design.md`（第 8 节移除「全屏演示模式」一条，加一句指向新 spec）

- [ ] **Step 1: 全场景人工验收**

用真实数据各过一遍：长旅程（201910 意大利瑞士）、单城市（201708 青岛）、照片很多的天、没日记没照片的紧凑天、缺坐标场景（若无现成数据，临时在 DevTools 删 `data-map` 验证）。

- [ ] **Step 2: 文档同步**

- `ROADMAP.md`：「全屏演示模式」`- [ ]` → `- [x]`，句末加 `已上线（实际日期），设计见 [docs/specs/2026-07-15-presentation-mode-design.md](docs/specs/2026-07-15-presentation-mode-design.md)。`
- 故事页 spec 第 8 节「明确不做」删掉全屏演示那一条（已做完），其余不动。

- [ ] **Step 3: 最终测试 + 合并**

```bash
pytest -v          # 全 PASS
git add ROADMAP.md docs/specs/2026-07-14-trip-story-page-design.md
git commit -m "docs: 勾选全屏演示模式，故事页 spec 移除已完成的不做项

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git checkout main && git merge feat/presentation-mode
```
