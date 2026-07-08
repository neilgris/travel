/* Globe.gl（Three.js）渲染器：蓝色写实 3D 地球 + 浮起弧线。
   实现统一渲染器接口，由 globe-home.js 调度。 */
(function () {
  window.GLOBE_FACTORY = window.GLOBE_FACTORY || {};

  window.GLOBE_FACTORY.gl = function (root, shared) {
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
      .globeImageUrl(S + "earth-blue-marble.jpg")
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
        const c = shared.centroidOfTrip(id);
        if (c) world.pointOfView({ lat: c.lat, lng: c.lng, altitude: 1.8 }, 700);
      },
      initialView() {
        const c = shared.centroidOfAll();
        if (c) world.pointOfView({ lat: c.lat, lng: c.lng, altitude: 2.2 }, 0);
      },
      resize() { world.width(root.clientWidth).height(root.clientHeight); },
      pause() { world.pauseAnimation && world.pauseAnimation(); },
      resume() { world.resumeAnimation && world.resumeAnimation(); },
    };
  };
})();
