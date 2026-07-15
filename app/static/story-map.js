/* 故事页客户端：2D 小地图(d3 等距投影贴合旅程) + 滚动联动 + 照片灯箱。
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
