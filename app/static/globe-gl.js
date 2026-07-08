/* Globe.gl（Three.js）渲染器：3D 地球 + 浮起弧线。
   两个变体共用本文件，只是球面不同：
   - gl ：单张蓝色写实贴图（离线）。
   - sat：Esri World Imagery 卫星瓦片，自定义 LOD 瓦片图层，能一路放大到街道级
          （联网，免 token）。用 window.THREE（globe.gl 复用的同一实例）建瓦片材质。
   实现统一渲染器接口，由 globe-home.js 调度。 */
(function () {
  window.GLOBE_FACTORY = window.GLOBE_FACTORY || {};

  // 视野角半径（弧度）→ 相机高度：范围越大越拉远，单点/小行程也不至于贴脸。
  const altFor = (radius) => Math.max(0.35, Math.min(2.4, radius * 1.7 + 0.3));

  // Esri World Imagery：免 token 的卫星瓦片（URL 顺序 z/y/x）。
  const ESRI = (x, y, z) =>
    `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`;

  // 自定义卫星瓦片图层：按相机高度选 Web Mercator 缩放级，只加载视野附近的瓦片，
  // 相机一动就按级重算 → 越拉近级别越高、越清晰（内置引擎封顶 z≈7，这里能到街道级）。
  function setupSatelliteTiles(world, base) {
    const THREE = window.THREE;
    const loader = new THREE.TextureLoader();
    loader.setCrossOrigin("anonymous");
    const matCache = new Map();               // url -> MeshBasicMaterial（避免重复建）
    function tileMat(url) {
      let m = matCache.get(url);
      if (!m) {
        const tex = loader.load(url);
        tex.colorSpace = THREE.SRGBColorSpace;
        // DoubleSide：瓦片球面片默认正面朝内会被背面剔除，双面确保可见。
        m = new THREE.MeshBasicMaterial({ map: tex, side: THREE.DoubleSide });
        matCache.set(url, m);
      }
      return m;
    }

    // 瓦片抬到球外一层壳（tileAltitude），近侧瓦片盖在不透明底图上；底图写深度，
    // 遮住远侧（背面）瓦片，形成实心球，间隙也由底图兜底。
    world.globeImageUrl(base)
      .tileMaterial((d) => d.material)
      .tileLng((d) => d.lng).tileLat((d) => d.lat)
      .tileWidth((d) => d.w).tileHeight((d) => d.h)
      .tileAltitude(0.02)
      .tilesData([]);

    const zoomFor = (alt) => Math.max(2, Math.min(18, Math.round(Math.log2(1 / alt) + 3)));
    const lat2y = (lat, n) => {
      const r = lat * Math.PI / 180;
      return Math.floor((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * n);
    };
    const y2lat = (y, n) => Math.atan(Math.sinh(Math.PI * (1 - 2 * y / n))) * 180 / Math.PI;

    function update() {
      const pov = world.pointOfView();
      const z = zoomFor(pov.altitude), n = 2 ** z;
      const cx = Math.floor((pov.lng + 180) / 360 * n);
      const cy = lat2y(Math.max(-85, Math.min(85, pov.lat)), n);
      const spanDeg = Math.min(360, 140 * pov.altitude);       // 视野大致跨度
      const per = Math.min(8, Math.max(1, Math.ceil(spanDeg / (360 / n))));
      const tiles = [];
      for (let dx = -per; dx <= per; dx++) {
        for (let dy = -per; dy <= per; dy++) {
          const y = cy + dy;
          if (y < 0 || y >= n) continue;                        // 纬向截断
          const x = ((cx + dx) % n + n) % n;                    // 经向环绕
          const west = x / n * 360 - 180, north = y2lat(y, n), south = y2lat(y + 1, n);
          tiles.push({
            lng: west + 180 / n, lat: (north + south) / 2,
            w: 360 / n, h: north - south,
            material: tileMat(ESRI(x, y, z)),
          });
        }
      }
      world.tilesData(tiles);
    }

    let scheduled = false;
    const schedule = () => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => { scheduled = false; update(); });
    };
    world.controls().addEventListener("change", schedule);      // 缩放/旋转都触发重算
    update();
  }

  function makeGl(root, shared, opts) {
    const S = shared.STATIC;
    const arcs = shared.arcs.map((a) => ({
      startLat: a.from.lat, startLng: a.from.lng,
      endLat: a.to.lat, endLng: a.to.lng,
      color: a.color, tripId: a.tripId, tripTitle: a.tripTitle,
      dates: a.dates, mode: a.mode, emoji: a.emoji,
    }));
    const labels = [];
    shared.arcs.forEach((a) => {
      if (!a.emoji) return;
      const m = midpoint(a.from, a.to);
      labels.push({ lat: m.lat, lng: m.lng, alt: m.alt, emoji: a.emoji, tripId: a.tripId });
    });

    let focusId = null;
    const dim = (hex) => hex + "33";
    const arcColor = (d) => (focusId && d.tripId !== focusId ? dim(d.color) : d.color);

    const world = Globe()
      .backgroundImageUrl(S + "night-sky.png")
      .atmosphereColor("#5aa9ff")
      .atmosphereAltitude(0.18)
      .pointsData(shared.cities)
      .pointLat("lat").pointLng("lng")
      .pointColor(() => "#ffe08a")
      .pointAltitude(0.01)
      .pointRadius(0.28)
      .pointLabel((c) => shared.cityCard(c.name))
      .arcsData(arcs)
      .arcColor(arcColor)
      .arcStroke(0.55)
      .arcDashLength(1).arcDashGap(0)
      .arcAltitudeAutoScale(0.4)
      .arcLabel((a) => shared.arcCard(a))
      .onArcHover((a) => shared.onHover(a ? a.tripId : null))
      .htmlElementsData(labels)
      .htmlLat("lat").htmlLng("lng").htmlAltitude("alt")
      .htmlElement((d) => {
        const s = document.createElement("div");
        s.className = "arc-emoji";
        s.textContent = d.emoji;
        s.dataset.trip = d.tripId;
        return s;
      })
      (root);
    world.controls().autoRotate = false;

    // 球面：卫星深缩放瓦片图层，或单张写实贴图。
    if (opts.satellite) {
      setupSatelliteTiles(world, S + "earth-blue-marble.jpg");
    } else {
      world.globeImageUrl(S + "earth-blue-marble.jpg");
    }

    function midpoint(a, b) {
      const lat = (a.lat + b.lat) / 2;
      let dLng = b.lng - a.lng;
      if (dLng > 180) dLng -= 360; else if (dLng < -180) dLng += 360;
      const lng = a.lng + dLng / 2;
      return { lat, lng, alt: 0.4 * (shared.angle(a, b) / Math.PI) };
    }

    return {
      setFocus(id) {
        focusId = id;
        world.arcColor(arcColor);
        root.querySelectorAll(".arc-emoji").forEach((n) => {
          n.style.opacity = focusId && +n.dataset.trip !== focusId ? 0.15 : 1;
        });
      },
      focusView(id) {
        const v = shared.viewOfTrip(id);
        if (v) world.pointOfView({ lat: v.lat, lng: v.lng, altitude: altFor(v.radius) }, 700);
      },
      initialView() {
        const v = shared.viewOfAll();
        if (v) world.pointOfView({ lat: v.lat, lng: v.lng, altitude: altFor(v.radius) }, 0);
      },
      resetView() {
        const v = shared.viewOfAll();
        if (v) world.pointOfView({ lat: v.lat, lng: v.lng, altitude: altFor(v.radius) }, 700);
      },
      resize() { world.width(root.clientWidth).height(root.clientHeight); },
      pause() { world.pauseAnimation && world.pauseAnimation(); },
      resume() { world.resumeAnimation && world.resumeAnimation(); },
    };
  }

  window.GLOBE_FACTORY.gl = (root, shared) => makeGl(root, shared, {});
  window.GLOBE_FACTORY.sat = (root, shared) => makeGl(root, shared, { satellite: true });
})();
