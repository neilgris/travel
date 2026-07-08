/* 首页地球：把 build_globe_data() 的数据画成 Globe.gl 弧线 + 城市点。
   弧线按旅程上色，中点贴交通 emoji；hover 出信息卡，列表与地球联动高亮。 */
(function () {
  const wrap = document.querySelector(".globe-wrap");
  const el = document.getElementById("globe");
  if (!wrap || !el || typeof Globe === "undefined") return;

  const data = JSON.parse(wrap.dataset.globe);
  const STATIC = "/static/vendor/";

  // 弧线拍平成 Globe.gl 需要的字段；顺便记录所属旅程与交通。
  const arcs = [];
  const labels = [];               // 弧线中点的 emoji
  const cityTrips = {};            // 城市名 -> Set(旅程标题)，供城市 hover
  data.trips.forEach((t) => {
    t.arcs.forEach((a) => {
      arcs.push({
        startLat: a.from.lat, startLng: a.from.lng,
        endLat: a.to.lat, endLng: a.to.lng,
        color: t.color, tripId: t.id, tripTitle: t.title,
        dates: (t.start_date || "") + " → " + (t.end_date || ""),
        mode: a.mode, emoji: a.emoji,
      });
      if (a.emoji) {
        const mid = midpoint(a.from, a.to);
        labels.push({ lat: mid.lat, lng: mid.lng, alt: mid.alt, emoji: a.emoji, tripId: t.id });
      }
      [a.from, a.to].forEach((c) => {
        (cityTrips[c.name] || (cityTrips[c.name] = new Set())).add(t.title);
      });
    });
  });

  let focusId = null;             // 当前高亮的旅程 id（null=全部）
  const dim = (hex) => hex + "33";   // 加透明度做淡出
  const arcColor = (d) => (focusId && d.tripId !== focusId ? dim(d.color) : d.color);

  const world = Globe()
    .globeImageUrl(STATIC + "earth-blue-marble.jpg")
    .backgroundImageUrl(STATIC + "night-sky.png")
    .atmosphereColor("#5aa9ff")
    .atmosphereAltitude(0.18)
    // 城市点
    .pointsData(data.cities)
    .pointLat("lat").pointLng("lng")
    .pointColor(() => "#ffe08a")
    .pointAltitude(0.01)
    .pointRadius(0.28)
    .pointLabel((c) => cityCard(c.name))
    // 弧线
    .arcsData(arcs)
    .arcColor(arcColor)
    .arcStroke(0.55)
    .arcDashLength(1).arcDashGap(0)
    .arcAltitudeAutoScale(0.4)
    .arcLabel(arcCard)
    .onArcHover((a) => setFocus(a ? a.tripId : null))
    // 交通 emoji
    .htmlElementsData(labels)
    .htmlLat("lat").htmlLng("lng").htmlAltitude("alt")
    .htmlElement((d) => {
      const s = document.createElement("div");
      s.className = "arc-emoji";
      s.textContent = d.emoji;
      s.dataset.trip = d.tripId;
      return s;
    })
    (el);

  world.controls().autoRotate = false;
  sizeToWrap();
  fitAllCities();

  // ---- 联动：列表 hover 高亮地球，反之亦然 ----
  function setFocus(id) {
    if (focusId === id) return;
    focusId = id;
    world.arcColor(arcColor);   // 重设 accessor 触发重绘
    el.querySelectorAll(".arc-emoji").forEach((n) => {
      n.style.opacity = focusId && +n.dataset.trip !== focusId ? 0.15 : 1;
    });
    document.querySelectorAll(".trip-item").forEach((n) => {
      n.classList.toggle("focus", focusId && +n.dataset.trip === focusId);
      n.classList.toggle("dim", focusId && +n.dataset.trip !== focusId);
    });
  }

  document.querySelectorAll(".trip-item").forEach((item) => {
    const id = +item.dataset.trip;
    item.addEventListener("mouseenter", () => { setFocus(id); focusTrip(id); });
    item.addEventListener("mouseleave", () => setFocus(null));
  });

  // ---- 视角 ----
  function fitAllCities() {
    if (!data.cities.length) return;
    const c = centroid(data.cities);
    world.pointOfView({ lat: c.lat, lng: c.lng, altitude: 2.2 }, 0);
  }
  function focusTrip(id) {
    const t = data.trips.find((x) => x.id === id);
    if (!t || !t.arcs.length) return;
    const pts = [];
    t.arcs.forEach((a) => pts.push(a.from, a.to));
    const c = centroid(pts);
    world.pointOfView({ lat: c.lat, lng: c.lng, altitude: 1.8 }, 700);
  }

  // ---- 尺寸自适应 ----
  function sizeToWrap() {
    world.width(el.clientWidth).height(el.clientHeight);
  }
  window.addEventListener("resize", sizeToWrap);

  // ---- helpers ----
  function midpoint(a, b) {
    // 大圆中点近似 + 抬高到弧顶附近（与 arcAltitudeAutoScale 一致）。
    const lat = (a.lat + b.lat) / 2;
    let dLng = b.lng - a.lng;
    if (dLng > 180) dLng -= 360; else if (dLng < -180) dLng += 360;
    const lng = a.lng + dLng / 2;
    const theta = angle(a, b);              // 弧度
    return { lat, lng, alt: 0.4 * (theta / Math.PI) };
  }
  function angle(a, b) {
    const toR = Math.PI / 180;
    const la1 = a.lat * toR, la2 = b.lat * toR, dLa = (b.lat - a.lat) * toR,
      dLo = (b.lng - a.lng) * toR;
    const h = Math.sin(dLa / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLo / 2) ** 2;
    return 2 * Math.asin(Math.min(1, Math.sqrt(h)));
  }
  function centroid(pts) {
    let x = 0, y = 0, z = 0;
    const toR = Math.PI / 180;
    pts.forEach((p) => {
      const la = p.lat * toR, lo = p.lng * toR;
      x += Math.cos(la) * Math.cos(lo);
      y += Math.cos(la) * Math.sin(lo);
      z += Math.sin(la);
    });
    const n = pts.length;
    x /= n; y /= n; z /= n;
    return {
      lat: Math.atan2(z, Math.sqrt(x * x + y * y)) / toR,
      lng: Math.atan2(y, x) / toR,
    };
  }
  function arcCard(a) {
    return `<div class="g-card"><b>${esc(a.tripTitle)}</b>
      <span>${esc(a.dates)}</span>
      <span>${a.emoji || ""} ${esc(a.mode || "")}</span></div>`;
  }
  function cityCard(name) {
    const trips = Array.from(cityTrips[name] || []);
    return `<div class="g-card"><b>${esc(name)}</b>
      <span>${trips.map(esc).join("、")}</span></div>`;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
})();
