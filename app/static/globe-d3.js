/* D3 正射投影渲染器：浅色矢量线框地球 + 扁平弧线（贴球面）。
   实现与 Globe.gl 相同的渲染器接口，由 globe-home.js 调度。
   依赖：d3（含 d3-geo）、topojson-client、land-110m.json（经 shared.landTopo 传入）。 */
(function () {
  window.GLOBE_FACTORY = window.GLOBE_FACTORY || {};

  window.GLOBE_FACTORY.d3 = function (root, shared) {
    const land = topojson.feature(shared.landTopo, shared.landTopo.objects.land);
    const graticule = d3.geoGraticule10();

    const svg = d3.select(root).append("svg").attr("class", "d3-globe");
    const gGrid = svg.append("g");
    const gLand = svg.append("g");
    const gLake = svg.append("g");
    const gRiver = svg.append("g").attr("fill", "none");
    const gAdmin = svg.append("g").attr("fill", "none");
    const gArc = svg.append("g").attr("fill", "none")
      .attr("stroke-linecap", "round").attr("stroke-width", 2);
    const gCity = svg.append("g");
    const gEmoji = svg.append("g");
    const sphere = { type: "Sphere" };

    const tip = document.createElement("div");
    tip.className = "d3-tip"; tip.hidden = true;
    root.appendChild(tip);

    let focusId = null;
    let zoom = 1, baseScale = 0;           // 实际 scale = baseScale × zoom
    const ZOOM_MIN = 0.8, ZOOM_MAX = 50;   // 上限放宽，可持续放大到省/市级
    const DETAIL_ZOOM = 2.5;               // 越过此缩放即绘制详情层
    const projection = d3.geoOrthographic().clipAngle(90).precision(0.4);
    const path = d3.geoPath(projection);

    // 视口裁剪：为每个要素缓存球面外接（中心 + 角半径），逐帧只画落在视口附近的。
    // 深放大时可见要素骤减 → 详情层始终可见且随缩放变快。
    function meta(f) {
      if (!f._c) {
        const b = d3.geoBounds(f);                 // [[w,s],[e,n]]
        if (b[1][0] < b[0][0]) { f._c = [0, (b[0][1] + b[1][1]) / 2]; f._r = Math.PI; }
        else { f._c = [(b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2]; f._r = d3.geoDistance(b[0], b[1]) / 2 + 0.002; }
      }
      return f;
    }
    // 返回「是否在视口内」判定函数：视口角半径 = asin(半对角 / scale)，缩小时封顶到半球。
    function visibleFilter() {
      const r = projection.rotate();
      const center = [-r[0], -r[1]];
      const half = Math.hypot(root.clientWidth / 2, root.clientHeight / 2);
      const cap = Math.asin(Math.min(1, half / projection.scale())) + 0.05;
      return (f) => d3.geoDistance(center, meta(f)._c) < cap + f._r;
    }

    // 初始对准所有城市中心
    const c0 = shared.centroidOfAll();
    projection.rotate(c0 ? [-c0.lng, -c0.lat] : [0, 0]);

    function layout() {
      const w = root.clientWidth, h = root.clientHeight;
      svg.attr("width", w).attr("height", h);
      baseScale = Math.min(w, h) / 2 - 12;
      projection.translate([w / 2, h / 2]).scale(baseScale * zoom);
    }

    // 背面隐藏：与当前正对点夹角 > 90° 即不可见
    function visible(lng, lat) {
      const r = projection.rotate();
      return d3.geoDistance([lng, lat], [-r[0], -r[1]]) < Math.PI / 2 - 0.01;
    }
    const dimc = (hex) => hex + "40";

    function draw() {
      gGrid.selectAll("path.sphere").data([sphere]).join(
        (e) => e.append("path").attr("class", "sphere")).attr("d", path);
      gGrid.selectAll("path.grat").data([graticule]).join(
        (e) => e.append("path").attr("class", "grat")).attr("d", path);
      // 缩小走粗轮廓 land-110m；放大且详情已就绪则换精细海岸线 + 湖 + 河 + 国界/省界（逐要素裁剪）。
      const detail = zoom >= DETAIL_ZOOM && shared.landHi;
      const keep = detail ? visibleFilter() : null;
      gLand.selectAll("path.land").data(detail ? [] : [land]).join("path")
        .attr("class", "land").attr("d", path);
      gLand.selectAll("path.land-hi").data(detail ? shared.landHi.filter(keep) : []).join("path")
        .attr("class", "land-hi").attr("d", path);
      gLake.selectAll("path").data(detail ? shared.lakes.filter(keep) : []).join("path")
        .attr("class", "lake").attr("d", path);
      gRiver.selectAll("path").data(detail ? shared.rivers.filter(keep) : []).join("path")
        .attr("class", "river").attr("d", path);
      gAdmin.selectAll("path").data(detail ? shared.admin1.filter(keep) : []).join("path")
        .attr("class", "admin").attr("d", path);

      gArc.selectAll("path").data(shared.arcs).join("path")
        .attr("stroke", (a) => (focusId && a.tripId !== focusId ? dimc(a.color) : a.color))
        .attr("d", (a) => path({
          type: "LineString",
          coordinates: [[a.from.lng, a.from.lat], [a.to.lng, a.to.lat]],
        }))
        .on("mouseenter", (ev, a) => { shared.onHover(a.tripId); showTip(ev, shared.arcCard(a)); })
        .on("mousemove", moveTip)
        .on("mouseleave", () => { shared.onHover(null); hideTip(); });

      gCity.selectAll("circle").data(shared.cities).join("circle")
        .attr("r", 3.2).attr("class", "city")
        .attr("display", (c) => (visible(c.lng, c.lat) ? null : "none"))
        .attr("cx", (c) => projection([c.lng, c.lat])[0])
        .attr("cy", (c) => projection([c.lng, c.lat])[1])
        .on("mouseenter", (ev, c) => showTip(ev, shared.cityCard(c.name)))
        .on("mousemove", moveTip)
        .on("mouseleave", hideTip);

      gEmoji.selectAll("text").data(shared.arcs.filter((a) => a.emoji)).join("text")
        .attr("class", "arc-emoji-svg").attr("text-anchor", "middle")
        .attr("dominant-baseline", "central")
        .attr("opacity", (a) => (focusId && a.tripId !== focusId ? 0.15 : 1))
        .each(function (a) {
          const m = mid(a.from, a.to);
          const vis = visible(m[0], m[1]);
          const p = projection(m);
          d3.select(this).attr("display", vis ? null : "none")
            .attr("x", p[0]).attr("y", p[1]).text(a.emoji);
        });
    }

    function mid(a, b) {
      return d3.geoInterpolate([a.lng, a.lat], [b.lng, b.lat])(0.5);
    }

    // 拖拽旋转（详情随视口裁剪，逐帧直接画）
    let r0, p0;
    svg.call(d3.drag()
      .on("start", (ev) => { p0 = [ev.x, ev.y]; r0 = projection.rotate(); })
      .on("drag", (ev) => {
        const k = 70 / projection.scale();
        projection.rotate([r0[0] + (ev.x - p0[0]) * k, r0[1] - (ev.y - p0[1]) * k]);
        draw();
      }));

    // 滚轮缩放（Globe.gl 内置缩放，D3 手动实现，两者行为对齐）
    svg.node().addEventListener("wheel", (ev) => {
      ev.preventDefault();
      zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, zoom * Math.exp(-ev.deltaY * 0.0015)));
      projection.scale(baseScale * zoom);
      draw();
      if (zoom >= DETAIL_ZOOM && !shared.landHi) shared.loadDetail().then(draw);
    }, { passive: false });

    // 视野角半径（弧度）→ 缩放系数：让该范围填满约 92% 短边（贴合坐标区间、尽量大而不裁掉端点）；
    // 上限放到 16、下限贴合小行程（floor 0.02），让默认与 hover 都能明显放大到位。
    function zoomForRadius(radius) {
      const half = Math.min(root.clientWidth, root.clientHeight) / 2;
      const s = 0.92 * half / Math.max(Math.sin(radius), 0.02);  // 需要的 scale
      return Math.max(ZOOM_MIN, Math.min(16, s / baseScale));    // 折算成系数并封顶
    }

    // 旋转 + 缩放补间（focusView 用）
    let timer;
    function flyTo(target, targetZoom) {
      if (timer) timer.stop();
      if (targetZoom >= DETAIL_ZOOM && !shared.landHi) shared.loadDetail().then(draw);
      const rStart = projection.rotate();
      const ip = d3.interpolate(rStart, [target[0], target[1], rStart[2] || 0]);
      const zStart = zoom, zEnd = targetZoom;
      const t0 = Date.now(), dur = 700;
      timer = d3.timer(() => {
        const t = Math.min(1, (Date.now() - t0) / dur);
        const e = d3.easeCubicInOut(t);
        projection.rotate(ip(e));
        zoom = zStart + (zEnd - zStart) * e;
        projection.scale(baseScale * zoom);
        draw();
        if (t >= 1) timer.stop();
      });
    }

    function showTip(ev, html) { tip.innerHTML = html; tip.hidden = false; moveTip(ev); }
    function moveTip(ev) {
      const b = root.getBoundingClientRect();
      tip.style.left = (ev.clientX - b.left + 12) + "px";
      tip.style.top = (ev.clientY - b.top + 12) + "px";
    }
    function hideTip() { tip.hidden = true; }

    layout();
    draw();

    return {
      setFocus(id) { focusId = id; draw(); },
      focusView(id) {
        const v = shared.viewOfTrip(id);
        if (v) flyTo([-v.lng, -v.lat], zoomForRadius(v.radius));
      },
      initialView() {
        const v = shared.viewOfAll();
        if (v) {
          zoom = zoomForRadius(v.radius);
          projection.rotate([-v.lng, -v.lat]).scale(baseScale * zoom);
          draw();
          if (zoom >= DETAIL_ZOOM && !shared.landHi) shared.loadDetail().then(draw);
        }
      },
      resetView() {
        const v = shared.viewOfAll();
        if (v) flyTo([-v.lng, -v.lat], zoomForRadius(v.radius));
      },
      resize() { layout(); draw(); },
      pause() { if (timer) timer.stop(); },
      resume() {},
    };
  };
})();
