/* 故事页客户端：2D 小地图(d3 等距投影贴合旅程) + 滚动联动 + 照片灯箱。
   离线依赖：d3、topojson、static/vendor/land-50m.json。
   render() 挂在 window.STORY_MAP 上，放映壳（story-present.js）复用它渲染角落小地图。 */
(function () {
  // 取景城市集：只用来算缩放范围，离群城市仍会画出（连线飞出画面外），不影响正文。
  // 目标是「保留沿途城市，只甩掉出发地和很远的中转」——
  //   ① 出发地（home，第一段 Leg 的出发城市，通常是北京）几乎每程都有，不强求体现：
  //      默认不参与取景，除非在那儿住够 D 天（真正玩过，而非当天往返）。
  //   ② 其余城市：到「目的地核心中位中心」的距离 ≤ K° 就保留——这样成都/重庆(林芝)、
  //      名古屋(大阪)、吉隆坡(马来西亚)这类沿途城市都留在画内；住够 D 天的远途目的地
  //      （如阿拉斯加）也保留；只有又远又没怎么待的中转（如迪拜 27°+、1 天）被甩出。
  // 中位中心由「住过的城市」（去掉 home）算，中位数对个别远点稳健。
  // 经度用原始差值（与等距圆柱投影一致）。天数字段缺失（旧数据）时退回全部城市。
  const FRAME_K = 20;   // 距目的地核心 ≤20° 即算沿途城市，保留
  const FRAME_D = 2;    // 或住够 2 天的远途目的地也保留
  function framingCities(cities, home) {
    if (cities.length <= 3) return cities;
    const mid = (arr) => {
      const s = arr.slice().sort((a, b) => a - b);
      const n = s.length;
      return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
    };
    const nonHome = cities.filter((c) => c.name !== home);
    let base = nonHome.filter((c) => (c.days || 0) >= 1);
    if (!base.length) base = nonHome.length ? nonHome : cities;
    const cx = mid(base.map((c) => c.lat));
    const cy = mid(base.map((c) => c.lng));
    const cos = Math.cos((cx * Math.PI) / 180);
    const dist = (c) => Math.hypot(c.lat - cx, (c.lng - cy) * cos);
    const keep = cities.filter((c) => {
      if (c.name === home) return (c.days || 0) >= FRAME_D;   // 出发地：住够 D 天才纳入
      return dist(c) <= FRAME_K || (c.days || 0) >= FRAME_D;
    });
    return keep.length ? keep : cities;
  }

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

    // 用取景城市集算包围盒，等距圆柱投影 fitExtent 贴合（区域旅程也看得清）。
    // 出发地（home）= 第一段 Leg 的出发城市（route 已按 seq 排序）。
    const home = route.length ? route[0].from.name : null;
    const feat = { type: "FeatureCollection", features: framingCities(cities, home).map((c) => ({
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

    // ---- 城市点 ----
    const pos = new Map();
    cities.forEach((c) => pos.set(c.name, projection([c.lng, c.lat])));
    const g = svg.append("g");
    g.selectAll("circle.city-dot").data(cities).join("circle")
      .attr("class", "city-dot")
      .attr("data-city", (c) => c.name)
      .attr("cx", (c) => pos.get(c.name)[0])
      .attr("cy", (c) => pos.get(c.name)[1])
      .attr("r", 4).attr("fill", "#5a6472");

    // ---- 城市名标签：贪心避让 ----
    // 聚集区（如林芝/鲁朗/南迦、京都/大阪/奈良）城市点相邻，名字会糊成一团。这里给每个
    // 标签四个候选位（右/左/上/下），按「住得久」优先占位，与已放标签或任何城市点相撞就换
    // 下一个候选位，四个都撞就先藏起来（点仍在）。滚动到的当天城市无论如何都显示并置顶。
    const FS = 11;
    const cand = [
      { dx: 6, dy: 4, anchor: "start" }, { dx: -6, dy: 4, anchor: "end" },
      { dx: 0, dy: -7, anchor: "middle" }, { dx: 0, dy: 15, anchor: "middle" },
    ];
    const boxFor = (c, o) => {
      const p = pos.get(c.name);
      const wd = c.name.length * FS * 0.95;
      let x = p[0] + o.dx;
      if (o.anchor === "end") x -= wd; else if (o.anchor === "middle") x -= wd / 2;
      const y = p[1] + o.dy - FS + 2;
      return { x1: x, y1: y, x2: x + wd, y2: y + FS };
    };
    const hit = (a, b) => !(a.x2 < b.x1 || a.x1 > b.x2 || a.y2 < b.y1 || a.y1 > b.y2);
    const inView = (b) => b.x1 >= 2 && b.x2 <= w - 2 && b.y1 >= 2 && b.y2 <= h - 2;
    const dotBoxes = cities.map((c) => {
      const p = pos.get(c.name);
      return { x1: p[0] - 4, y1: p[1] - 4, x2: p[0] + 4, y2: p[1] + 4 };
    });
    const order = cities.slice().sort((a, b) =>
      (b.days || 0) - (a.days || 0) || a.name.length - b.name.length);
    const placed = [];
    const info = new Map();   // name -> { o, vis }
    order.forEach((c) => {
      let chosen = null;
      for (const o of cand) {
        const box = boxFor(c, o);
        // 候选位不能超出画框、不能压到已放标签或任何城市点。
        if (inView(box) && !placed.some((p) => hit(box, p))
            && !dotBoxes.some((d) => hit(box, d))) {
          chosen = o; placed.push(box); break;
        }
      }
      info.set(c.name, { o: chosen || cand[0], vis: !!chosen });
    });
    const labels = g.selectAll("text.city-label").data(cities).join("text")
      .attr("class", "city-label")
      .attr("data-city", (c) => c.name)
      .attr("font-size", FS)
      .attr("text-anchor", (c) => info.get(c.name).o.anchor)
      .attr("x", (c) => pos.get(c.name)[0] + info.get(c.name).o.dx)
      .attr("y", (c) => pos.get(c.name)[1] + info.get(c.name).o.dy)
      .attr("paint-order", "stroke").attr("stroke", "#eef2f6").attr("stroke-width", 3)
      .style("display", (c) => (info.get(c.name).vis ? null : "none"))
      .text((c) => c.name);

    // ---- 高亮：当天城市点变色放大，标签强制显示并置顶（哪怕平时被藏）----
    const dots = svg.selectAll("circle.city-dot");
    function highlight(name) {
      dots.classed("is-active", (c) => c.name === name)
          .attr("r", (c) => (c.name === name ? 7 : 4));
      labels.each(function (c) {
        const active = c.name === name;
        this.style.display = active || info.get(c.name).vis ? null : "none";
        this.classList.toggle("is-active", active);
        if (active) this.parentNode.appendChild(this);   // 提到最前，压住邻近标签
      });
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
    // 等容器被 CSS 定尺再渲染：脚本可能先于样式生效，此时 clientWidth 极小，
    // 会让 fitExtent 用错误 viewBox（字体巨大）。用 rAF 重试到有合理宽度或超时兜底。
    let tries = 0;
    (function whenSized() {
      if (mapEl.clientWidth >= 120 || tries++ > 30) return initMap();
      requestAnimationFrame(whenSized);
    })();
  }
  function initMap() {
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
