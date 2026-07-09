/* 首页地球控制器：解析后端数据 → 组织渲染器无关的共享结构与联动，
   在 Globe.gl / D3 两个渲染器间切换（记 localStorage），列表 hover 联动高亮。 */
(function () {
  const wrap = document.querySelector(".globe-wrap");
  const stage = document.getElementById("globe");
  const stageBox = document.querySelector(".globe-stage");
  if (!wrap || !stage) return;

  const data = JSON.parse(wrap.dataset.globe);
  const STATIC = "/static/vendor/";
  const STORE_KEY = "globe-renderer";
  const toRad = Math.PI / 180;

  // ---- 共享结构（两个渲染器都读这一份）----
  const arcs = [];
  const cityTrips = {};
  data.trips.forEach((t) => {
    t.arcs.forEach((a) => {
      arcs.push({
        from: a.from, to: a.to, mode: a.mode, emoji: a.emoji,
        color: t.color, tripId: t.id, tripTitle: t.title,
        dates: (t.start_date || "") + " → " + (t.end_date || ""),
      });
      [a.from, a.to].forEach((c) => {
        (cityTrips[c.name] || (cityTrips[c.name] = new Set())).add(t.title);
      });
    });
  });

  function centroid(pts) {
    let x = 0, y = 0, z = 0;
    pts.forEach((p) => {
      const la = p.lat * toRad, lo = p.lng * toRad;
      x += Math.cos(la) * Math.cos(lo);
      y += Math.cos(la) * Math.sin(lo);
      z += Math.sin(la);
    });
    const n = pts.length || 1;
    x /= n; y /= n; z /= n;
    return {
      lat: Math.atan2(z, Math.sqrt(x * x + y * y)) / toRad,
      lng: Math.atan2(y, x) / toRad,
    };
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  const shared = {
    STATIC, arcs, cities: data.cities, trips: data.trips,
    centroidOfAll() { return data.cities.length ? centroid(data.cities) : null; },
    centroidOfTrip(id) {
      const t = data.trips.find((x) => x.id === id);
      if (!t || !t.arcs.length) return null;
      const pts = [];
      t.arcs.forEach((a) => pts.push(a.from, a.to));
      return centroid(pts);
    },
    // 一组点的视野范围：中心 + 到最远点的角半径（弧度）。渲染器据此自适应缩放。
    extentOf(pts) {
      if (!pts.length) return null;
      const c = centroid(pts);
      let radius = 0;
      pts.forEach((p) => { const a = this.angle(c, p); if (a > radius) radius = a; });
      return { lat: c.lat, lng: c.lng, radius };
    },
    viewOfAll() { return this.extentOf(data.cities); },
    viewOfTrip(id) {
      const t = data.trips.find((x) => x.id === id);
      if (!t || !t.arcs.length) return null;
      const pts = [];
      t.arcs.forEach((a) => pts.push(a.from, a.to));
      return this.extentOf(pts);
    },
    angle(a, b) {
      const la1 = a.lat * toRad, la2 = b.lat * toRad,
        dLa = (b.lat - a.lat) * toRad, dLo = (b.lng - a.lng) * toRad;
      const h = Math.sin(dLa / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLo / 2) ** 2;
      return 2 * Math.asin(Math.min(1, Math.sqrt(h)));
    },
    arcCard(a) {
      return `<div class="g-card"><b>${esc(a.tripTitle)}</b>
        <span>${esc(a.dates)}</span>
        <span>${a.emoji || ""} ${esc(a.mode || "")}</span></div>`;
    },
    cityCard(name) {
      const trips = Array.from(cityTrips[name] || []);
      return `<div class="g-card"><b>${esc(name)}</b>
        <span>${trips.map(esc).join("、")}</span></div>`;
    },
    onHover(id) { setFocus(id, false); },

    // 详情层懒加载：首次调用拉四份数据并拆成「可裁剪的要素数组」，之后复用同一 Promise。
    // 拆分理由：渲染器按视口逐要素裁剪，故 land 拆成多个多边形、admin 边界网拆成线段，
    // 每份都成为可单独判定是否在视口内的要素列表。
    loadDetail() {
      if (this._detail) return this._detail;
      const get = (f) => fetch(STATIC + f).then((r) => r.json());
      // 修正绕向：个别多边形环序反了，在正射投影里会「填满整个半球」（球面面积 > 2π）。
      // 逐要素检测，反了就翻转各环坐标顺序，避免湖泊/陆地盖住整张图。
      const fixWinding = (f) => {
        if (d3.geoArea(f) <= 2 * Math.PI) return f;
        const g = f.geometry;
        if (g.type === "Polygon") g.coordinates = g.coordinates.map((r) => r.slice().reverse());
        else if (g.type === "MultiPolygon") g.coordinates = g.coordinates.map((p) => p.map((r) => r.slice().reverse()));
        return f;
      };
      this._detail = Promise.all([
        get("land-50m.json"), get("admin1-10m.json"),
        get("lakes-10m.json"), get("rivers-10m.json"),
      ]).then(([land, adm, lakes, rivers]) => {
        // land 的 objects.land 是 GeometryCollection，取出其中单个 MultiPolygon，
        // 再按大陆/岛屿拆成一堆 Polygon 要素以便逐块裁剪
        const mp = topojson.feature(land, land.objects.land).features[0].geometry;
        this.landHi = mp.coordinates.map((coords) => fixWinding({
          type: "Feature", geometry: { type: "Polygon", coordinates: coords },
        }));
        // admin 取相邻共享边（国界+省界）网，拆成一条条线段
        const mesh = topojson.mesh(adm, adm.objects.admin1, (a, b) => a !== b);
        this.admin1 = mesh.coordinates.map((line) => ({
          type: "Feature", geometry: { type: "LineString", coordinates: line },
        }));
        this.lakes = topojson.feature(lakes, lakes.objects.lakes).features.map(fixWinding);
        this.rivers = topojson.feature(rivers, rivers.objects.rivers).features;
      });
      return this._detail;
    },
  };

  // ---- 列表联动（渲染器无关）----
  function setFocus(id, rotate) {
    document.querySelectorAll(".trip-item").forEach((n) => {
      n.classList.toggle("focus", id && +n.dataset.trip === id);
      n.classList.toggle("dim", id && +n.dataset.trip !== id);
    });
    if (active) {
      active.setFocus(id);
      if (rotate && id) active.focusView(id);
    }
  }
  document.querySelectorAll(".trip-item").forEach((item) => {
    const id = +item.dataset.trip;
    item.addEventListener("mouseenter", () => setFocus(id, true));
    item.addEventListener("mouseleave", () => {
      setFocus(null, false);
      if (active && active.resetView) active.resetView();   // 退回全部行程视野
    });
  });

  // ---- 渲染器切换 ----
  const instances = {};   // mode -> {root, api}
  let active = null, activeMode = null;

  async function ensureDeps(mode) {
    if (mode === "d3" && !shared.landTopo) {
      shared.landTopo = await fetch(STATIC + "land-110m.json").then((r) => r.json());
    }
  }
  async function activate(mode) {
    if (mode === activeMode) return;
    await ensureDeps(mode);
    if (active) active.pause();
    if (!instances[mode]) {
      const root = document.createElement("div");
      root.className = "globe-canvas";
      const api = window.GLOBE_FACTORY[mode](root, shared);
      instances[mode] = { root, api };
    }
    const inst = instances[mode];
    stage.replaceChildren(inst.root);
    active = inst.api; activeMode = mode;
    active.resize();
    active.resume();
    active.initialView();
    stageBox.classList.toggle("light", mode === "d3");
    localStorage.setItem(STORE_KEY, mode);
    document.querySelectorAll(".render-switch [data-mode]").forEach((b) =>
      b.classList.toggle("on", b.dataset.mode === mode));
  }

  document.querySelectorAll(".render-switch [data-mode]").forEach((btn) =>
    btn.addEventListener("click", () => activate(btn.dataset.mode)));
  window.addEventListener("resize", () => active && active.resize());

  const saved = localStorage.getItem(STORE_KEY);
  activate(["d3", "sat"].includes(saved) ? saved : "gl");
})();
