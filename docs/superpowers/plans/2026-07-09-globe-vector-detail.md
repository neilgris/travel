# 矢量地图放大看细节（两级图层）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给首页地球的 D3 矢量渲染器加一个"放大越过阈值才出现"的详情层——精细海岸线 + 湖泊 + 河流 + 国界&省/州界。

**Architecture:** 两级图层。缩小时保持现有 `land-110m` 粗轮廓；`zoom` 首次越过 `DETAIL_ZOOM` 时并行懒加载四个 10m TopoJSON 文件存进 `shared`，之后放大即绘制详情层。仅 D3 渲染器消费这些数据，写实/卫星模式不受影响。

**Tech Stack:** 原生 JS + d3-geo（正射投影，已 vendored）+ topojson-client（`feature` / `mesh`，已 vendored）。数据来自 world-atlas（land）与 Natural Earth 10m（admin-1 / lakes / rivers），用 mapshaper 转 TopoJSON 并简化。

## Global Constraints

- **纯前端、无测试框架**：本项目前端无 pytest/JS 测试（见 [DECISIONS.md] / memory "run-tests-backend-only"）。每个任务的"验证"用 **preview 工具**（preview_start / preview_console_logs / preview_screenshot / preview_eval），不是单元测试。
- **渲染器无关**：详情层数据放进 `shared`，只 D3 读；不得改动 `globe-gl.js`（写实/卫星）或渲染器公共接口 `setFocus/focusView/initialView/resetView/resize/pause/resume`。
- **金额/后端不涉及**：本特性零后端改动，不碰 models/services/blueprints，不跑 pytest。
- **离线 vendor 入库**：新数据文件放 `app/static/vendor/`，与现有 vendor 一样**入库**（不 gitignore）。
- **换算/颜色**：D3 浅色主题现有配色 —— 海洋 `#cfe4f5`、经纬网 `#a9c8e0`、陆地填充 `#bfe0c4`/描边 `#7cb890`、城市 `#fff`/`#e8792b`。新图层配色需与之协调。
- **默认端口 8000**；`python run.py` 启动。

---

## File Structure

- `app/static/vendor/land-10m.json` — 新增，world-atlas 10m 陆地 TopoJSON（object: `land`）。
- `app/static/vendor/admin1-10m.json` — 新增，Natural Earth 10m 省/州 TopoJSON（object: `admin1`），用于 `topojson.mesh` 出国界+省界。
- `app/static/vendor/lakes-10m.json` — 新增，Natural Earth 10m 湖泊 TopoJSON（object: `lakes`）。
- `app/static/vendor/rivers-10m.json` — 新增，Natural Earth 10m 河流中心线 TopoJSON（object: `rivers`）。
- `app/static/globe-home.js` — 修改，`shared` 增加详情层懒加载器 `loadDetail()` 与 `landHi/admin1/lakes/rivers` 字段。
- `app/static/globe-d3.js` — 修改，新增 `gLake/gRiver` 组、`DETAIL_ZOOM` 阈值、`draw()` 分层、缩放跨阈值触发懒加载。
- `app/static/style.css` — 修改，新增 `.land-hi/.lake/.river/.admin` 配色。
- `CLAUDE.md` / `DECISIONS.md` — 修改，文档同步。

---

## Task 1: 准备四个 10m 数据文件

**Files:**
- Create: `app/static/vendor/land-10m.json`
- Create: `app/static/vendor/admin1-10m.json`
- Create: `app/static/vendor/lakes-10m.json`
- Create: `app/static/vendor/rivers-10m.json`
- Test: 无（用 node 一行校验产物）

**Interfaces:**
- Consumes: 无（首个任务）。
- Produces: 四个 TopoJSON 文件，object 键固定为 `land` / `admin1` / `lakes` / `rivers`；供 Task 2 fetch、Task 3 用 `topojson.feature` / `topojson.mesh` 消费。

- [ ] **Step 1: 下载 land-10m（world-atlas 现成 TopoJSON，object 已是 `land`）**

```bash
cd /Users/neilgris/Documents/python/qclaw/travel/app/static/vendor
curl -L -o land-10m.json https://cdn.jsdelivr.net/npm/world-atlas@2/land-10m.json
```

- [ ] **Step 2: 下载 Natural Earth 三份 GeoJSON 源到 scratchpad**

```bash
SCRATCH=/private/tmp/claude-501/-Users-neilgris-Documents-python-qclaw-travel/bfcce5d9-9bb1-4c75-816e-1fa6223462aa/scratchpad
BASE=https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson
curl -L -o $SCRATCH/admin1.geojson $BASE/ne_10m_admin_1_states_provinces.geojson
curl -L -o $SCRATCH/lakes.geojson  $BASE/ne_10m_lakes.geojson
curl -L -o $SCRATCH/rivers.geojson $BASE/ne_10m_rivers_lake_centerlines.geojson
```

- [ ] **Step 3: 用 mapshaper 简化并转 TopoJSON，object 名统一**

`-rename-layers` 让输出 object 键固定；`-simplify keep-shapes` 保拓扑不丢小面；只保留绘制所需字段以压体积。

```bash
SCRATCH=/private/tmp/claude-501/-Users-neilgris-Documents-python-qclaw-travel/bfcce5d9-9bb1-4c75-816e-1fa6223462aa/scratchpad
VENDOR=/Users/neilgris/Documents/python/qclaw/travel/app/static/vendor

npx -y mapshaper $SCRATCH/admin1.geojson \
  -simplify 40% keep-shapes -filter-fields \
  -rename-layers admin1 -o format=topojson $VENDOR/admin1-10m.json

npx -y mapshaper $SCRATCH/lakes.geojson \
  -simplify 50% keep-shapes -filter-fields \
  -rename-layers lakes -o format=topojson $VENDOR/lakes-10m.json

npx -y mapshaper $SCRATCH/rivers.geojson \
  -simplify 50% keep-shapes -filter-fields \
  -rename-layers rivers -o format=topojson $VENDOR/rivers-10m.json
```

- [ ] **Step 4: 校验四个文件的 object 键与体积**

```bash
cd /Users/neilgris/Documents/python/qclaw/travel/app/static/vendor
ls -lh land-10m.json admin1-10m.json lakes-10m.json rivers-10m.json
node -e "for(const f of ['land-10m','admin1-10m','lakes-10m','rivers-10m']){const d=require('./'+f+'.json');console.log(f, Object.keys(d.objects));}"
```

Expected:
- `land-10m ['land']`
- `admin1-10m ['admin1']`
- `lakes-10m ['lakes']`
- `rivers-10m ['rivers']`
- 各文件体积大致：land ~1.5MB、admin1 ≤~3MB、lakes ~0.3MB、rivers ~0.4MB。若 admin1/rivers 明显偏大，把对应 `-simplify` 百分比调低（如 25%）重跑该文件。

- [ ] **Step 5: 提交数据文件**

```bash
cd /Users/neilgris/Documents/python/qclaw/travel
git add app/static/vendor/land-10m.json app/static/vendor/admin1-10m.json app/static/vendor/lakes-10m.json app/static/vendor/rivers-10m.json
git commit -m "feat: 矢量详情层 10m 数据（land/admin1/lakes/rivers TopoJSON）"
```

---

## Task 2: globe-home.js 里加详情层懒加载器

**Files:**
- Modify: `app/static/globe-home.js`（`shared` 对象内，`ensureDeps` 附近）
- Test: 无（Task 3 preview 时连带验证加载）

**Interfaces:**
- Consumes: Task 1 的四个文件（`/static/vendor/*-10m.json`）。
- Produces: `shared.loadDetail()` → 返回 Promise；resolve 后 `shared.landHi`（land feature）、`shared.admin1`（border mesh，`GeoJSON MultiLineString`）、`shared.lakes`（feature collection）、`shared.rivers`（feature collection）四个字段就绪。重复调用只加载一次（幂等）。

- [ ] **Step 1: 在 shared 上加 loadDetail（幂等，一次并行拉取四份并转几何）**

在 `globe-home.js` 的 `shared` 对象里（`onHover` 附近）新增。注意 `admin1` 用 `topojson.mesh` 且过滤 `(a,b)=>a!==b`，只取相邻共享边（国界+省界），不含外圈海岸线（海岸由 landHi 填充边体现）。

```javascript
    onHover(id) { setFocus(id, false); },

    // 详情层懒加载：首次调用拉四份 10m 数据并转几何，之后复用同一 Promise。
    loadDetail() {
      if (this._detail) return this._detail;
      const get = (f) => fetch(STATIC + f).then((r) => r.json());
      this._detail = Promise.all([
        get("land-10m.json"), get("admin1-10m.json"),
        get("lakes-10m.json"), get("rivers-10m.json"),
      ]).then(([land, adm, lakes, rivers]) => {
        this.landHi = topojson.feature(land, land.objects.land);
        this.admin1 = topojson.mesh(adm, adm.objects.admin1, (a, b) => a !== b);
        this.lakes = topojson.feature(lakes, lakes.objects.lakes);
        this.rivers = topojson.feature(rivers, rivers.objects.rivers);
      });
      return this._detail;
    },
```

- [ ] **Step 2: 语法自检**

```bash
node -c /Users/neilgris/Documents/python/qclaw/travel/app/static/globe-home.js && echo OK
```

Expected: `OK`（无语法错误）。

- [ ] **Step 3: 提交**

```bash
cd /Users/neilgris/Documents/python/qclaw/travel
git add app/static/globe-home.js
git commit -m "feat: globe shared 增加详情层懒加载器 loadDetail()"
```

---

## Task 3: globe-d3.js 绘制详情层 + 阈值触发 + 配色

**Files:**
- Modify: `app/static/globe-d3.js`
- Modify: `app/static/style.css`（新增 `.land-hi/.lake/.river/.admin`）
- Test: preview（下方 Step 7）

**Interfaces:**
- Consumes: Task 2 的 `shared.loadDetail()` 与 `shared.landHi/admin1/lakes/rivers`。
- Produces: 放大越过 `DETAIL_ZOOM` 时渲染详情层的 D3 渲染器；无新对外接口。

- [ ] **Step 1: 加 gLake/gRiver 组与阈值常量**

在 `globe-d3.js` 现有 `const gLand = ...` 之后插入两个组（顺序决定层叠：湖在陆上、河在湖上、admin 复用 gArc 之前的新组）。改为在 `gLand` 后、`gArc` 前加：

```javascript
    const gLand = svg.append("g");
    const gLake = svg.append("g");
    const gRiver = svg.append("g").attr("fill", "none");
    const gAdmin = svg.append("g").attr("fill", "none");
    const gArc = svg.append("g").attr("fill", "none")
      .attr("stroke-linecap", "round").attr("stroke-width", 2);
```

并在 `ZOOM_MIN/ZOOM_MAX` 附近加阈值：

```javascript
    const ZOOM_MIN = 0.8, ZOOM_MAX = 8;
    const DETAIL_ZOOM = 2.5;   // 越过此缩放即绘制详情层
```

- [ ] **Step 2: draw() 里按 zoom 分层绘制**

替换现有 `gLand.selectAll("path")...` 那一行为：低 zoom 画 `land-110m`；高 zoom 且详情已就绪则画 land-10m 填充 + 湖 + 河 + admin mesh，并清掉粗陆地。把下面这段放在 `gLand` 绘制处。

```javascript
      const detail = zoom >= DETAIL_ZOOM && shared.landHi;
      gLand.selectAll("path").data(detail ? [] : [land]).join("path")
        .attr("class", "land").attr("d", path);

      gLand.selectAll("path.land-hi").data(detail ? [shared.landHi] : []).join(
        (e) => e.append("path").attr("class", "land-hi")).attr("d", path);
      gLake.selectAll("path").data(detail ? [shared.lakes] : []).join("path")
        .attr("class", "lake").attr("d", path);
      gRiver.selectAll("path").data(detail ? [shared.rivers] : []).join("path")
        .attr("class", "river").attr("d", path);
      gAdmin.selectAll("path").data(detail ? [shared.admin1] : []).join("path")
        .attr("class", "admin").attr("d", path);
```

> 注意：删掉原来的 `gLand.selectAll("path").data([land]).join("path").attr("class","land").attr("d",path);` 那一行，改用上面这段。`gGrid` 的 sphere/graticule 绘制保持不动。

- [ ] **Step 3: 缩放跨阈值时触发懒加载**

在 `wheel` 监听里，缩放后若进入详情区且未加载，则加载完再重绘。替换 `wheel` 回调体为：

```javascript
    svg.node().addEventListener("wheel", (ev) => {
      ev.preventDefault();
      zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, zoom * Math.exp(-ev.deltaY * 0.0015)));
      projection.scale(baseScale * zoom);
      draw();
      if (zoom >= DETAIL_ZOOM && !shared.landHi) shared.loadDetail().then(draw);
    }, { passive: false });
```

- [ ] **Step 4: flyTo 补间到详情区时也触发懒加载**

在 `flyTo` 函数体开头（`if (timer) timer.stop();` 之后）加一行，保证 hover 行程放大到详情区时也加载：

```javascript
    function flyTo(target, targetZoom) {
      if (timer) timer.stop();
      if (targetZoom >= DETAIL_ZOOM && !shared.landHi) shared.loadDetail().then(draw);
```

- [ ] **Step 5: 新增配色（style.css，接在 `.d3-globe .land` 行之后）**

```css
.d3-globe .land-hi { fill: #bfe0c4; stroke: #7cb890; stroke-width: 0.5; }
.d3-globe .lake { fill: #cfe4f5; stroke: #a9c8e0; stroke-width: 0.4; }
.d3-globe .river { fill: none; stroke: #8fb9dd; stroke-width: 0.6; }
.d3-globe .admin { fill: none; stroke: #7fae8f; stroke-width: 0.5; opacity: 0.75; }
```

- [ ] **Step 6: 语法自检**

```bash
node -c /Users/neilgris/Documents/python/qclaw/travel/app/static/globe-d3.js && echo OK
```

Expected: `OK`。

- [ ] **Step 7: preview 验证详情层放大出现、缩小消失**

启动并驱动 preview（若 `.claude/launch.json` 无 travel 配置，先按 `python run.py` / 端口 8000 建一个）：

1. `preview_start`（travel 服务），确认首页地球加载。
2. `preview_eval`：切到 D3 矢量渲染器并放大越过阈值，触发懒加载：
   ```js
   localStorage.setItem('globe-renderer','d3'); location.reload();
   ```
   reload 后再 `preview_eval` 模拟滚轮放大（或直接对 `.d3-globe` 派发 wheel 事件多次），观察 `preview_console_logs` 无报错、`preview_network` 里四个 `*-10m.json` 被拉取一次。
3. `preview_screenshot`：放大态应看到省/州界、河流、湖泊、精细海岸线；缩小回默认应只剩粗轮廓。
4. `preview_eval` 切到 `gl`（写实）与 `sat`（卫星）确认不受影响、无报错。

Expected：详情层放大出现、缩小消失，四文件仅加载一次，控制台无错，写实/卫星模式正常。

- [ ] **Step 8: 提交**

```bash
cd /Users/neilgris/Documents/python/qclaw/travel
git add app/static/globe-d3.js app/static/style.css
git commit -m "feat: D3 矢量球放大显示省界+河流+湖泊详情层"
```

---

## Task 4: 性能兜底（仅在实测卡顿时）+ 文档同步

**Files:**
- Modify: `app/static/globe-d3.js`（可选，拖拽降精度）
- Modify: `CLAUDE.md`（vendor 内容一行）
- Modify: `DECISIONS.md`（追加一条）
- Test: preview（拖拽帧率观察）

**Interfaces:**
- Consumes: Task 3 成果。
- Produces: 最终可用特性 + 同步文档。

- [ ] **Step 1: preview 观察详情态拖拽是否掉帧**

在详情缩放态用 `preview_eval` 连续派发 `pointerdown`/`pointermove` 模拟拖拽，或人工观察 `preview_screenshot` 前后旋转是否顺滑。若流畅 → **跳过 Step 2**。

- [ ] **Step 2:（仅当卡顿）拖拽期间降投影精度**

`d3.drag()` 的 `start` 设 `projection.precision(1.2)`，`end` 恢复 `projection.precision(0.4)` 并重绘一帧：

```javascript
    svg.call(d3.drag()
      .on("start", (ev) => { p0 = [ev.x, ev.y]; r0 = projection.rotate(); projection.precision(1.2); })
      .on("drag", (ev) => {
        const k = 70 / projection.scale();
        projection.rotate([r0[0] + (ev.x - p0[0]) * k, r0[1] - (ev.y - p0[1]) * k]);
        draw();
      })
      .on("end", () => { projection.precision(0.4); draw(); }));
```

- [ ] **Step 3: 同步 CLAUDE.md 的 vendor 说明**

把目录结构里 vendor 那行的地形部分补上详情层。找到 `vendor/ 离线 Globe.gl·three·d3·topojson·地球贴图·地形（卫星瓦片走 Esri，联网）`，改为：

```
vendor/ 离线 Globe.gl·three·d3·topojson·地球贴图·地形·矢量详情层（land/admin1/lakes/rivers 10m，放大懒加载；卫星瓦片走 Esri，联网）
```

- [ ] **Step 4: 追加 DECISIONS.md 一条**

在 DECISIONS.md 末尾追加（不改旧条目）：矢量球放大细节走"两级懒加载详情层"，10m 是 D3 正射投影矢量的实用上限，更细走卫星栅格模式；admin-1 用 `topojson.mesh` 一层出国界+省界。

- [ ] **Step 5: 提交**

```bash
cd /Users/neilgris/Documents/python/qclaw/travel
git add -A
git commit -m "docs: 同步矢量详情层（CLAUDE vendor + DECISIONS）"
```

---

## Self-Review

**Spec coverage：**
- 两级图层（110m / 10m 懒加载）→ Task 1（数据）+ Task 3（分层绘制）✅
- admin-1 mesh 一层出国界+省界 → Task 2（`topojson.mesh` 过滤 `a!==b`）✅
- 河流+湖泊 → Task 1/2/3 全链路 ✅
- 懒加载、跨阈值触发、数据未就绪先画 Tier 0 后补画 → Task 2（幂等 Promise）+ Task 3 Step 3/4（`.then(draw)`）✅
- 精细海岸线替换粗海岸线 → Task 3 Step 2（`detail` 时 `land` 数据置空、画 `land-hi`）✅
- 性能兜底 → Task 4 Step 2（条件启用）✅
- 仅 D3 消费、不动 gl/sat → Task 3 Step 7 验证 ✅
- 文档同步 → Task 4 Step 3/4 ✅

**Placeholder scan：** 无 TBD/TODO；每个代码步骤含完整代码或完整命令。✅

**Type consistency：** object 键 `land/admin1/lakes/rivers` 在 Task 1 产出、Task 2 消费、Task 3 引用一致；`shared.loadDetail()` / `shared.landHi/admin1/lakes/rivers` 命名贯穿 Task 2→3 一致；组名 `gLake/gRiver/gAdmin` 在 Task 3 内自洽。✅
