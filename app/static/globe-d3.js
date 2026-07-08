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
    const gArc = svg.append("g").attr("fill", "none")
      .attr("stroke-linecap", "round").attr("stroke-width", 2);
    const gCity = svg.append("g");
    const gEmoji = svg.append("g");
    const sphere = { type: "Sphere" };

    const tip = document.createElement("div");
    tip.className = "d3-tip"; tip.hidden = true;
    root.appendChild(tip);

    let focusId = null;
    const projection = d3.geoOrthographic().clipAngle(90).precision(0.4);
    const path = d3.geoPath(projection);

    // 初始对准所有城市中心
    const c0 = shared.centroidOfAll();
    projection.rotate(c0 ? [-c0.lng, -c0.lat] : [0, 0]);

    function layout() {
      const w = root.clientWidth, h = root.clientHeight;
      svg.attr("width", w).attr("height", h);
      projection.translate([w / 2, h / 2]).scale(Math.min(w, h) / 2 - 12);
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
      gLand.selectAll("path").data([land]).join("path").attr("class", "land").attr("d", path);

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

    // 拖拽旋转
    let r0, p0;
    svg.call(d3.drag()
      .on("start", (ev) => { p0 = [ev.x, ev.y]; r0 = projection.rotate(); })
      .on("drag", (ev) => {
        const k = 70 / projection.scale();
        projection.rotate([r0[0] + (ev.x - p0[0]) * k, r0[1] - (ev.y - p0[1]) * k]);
        draw();
      }));

    // 旋转补间（focusView 用）
    let timer;
    function rotateTo(target) {
      if (timer) timer.stop();
      const start = projection.rotate();
      const ip = d3.interpolate(start, [target[0], target[1], start[2] || 0]);
      const t0 = Date.now(), dur = 700;
      timer = d3.timer(() => {
        const t = Math.min(1, (Date.now() - t0) / dur);
        projection.rotate(ip(d3.easeCubicInOut(t)));
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
        const c = shared.centroidOfTrip(id);
        if (c) rotateTo([-c.lng, -c.lat]);
      },
      initialView() {
        const c = shared.centroidOfAll();
        if (c) { projection.rotate([-c.lng, -c.lat]); draw(); }
      },
      resize() { layout(); draw(); },
      pause() { if (timer) timer.stop(); },
      resume() {},
    };
  };
})();
