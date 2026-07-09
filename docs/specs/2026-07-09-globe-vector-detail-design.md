# 矢量地图放大看细节（两级图层）— 设计

> 状态快照。范围：首页地球的 **D3 矢量渲染器**（`globe-d3.js`），给它加"放大看省/州界"的能力。
> 关联：[docs/specs/2026-07-08-globe-home-design.md](2026-07-08-globe-home-design.md)（首页地球总设计）。

## 1. 背景与目标

矢量渲染器当前只有一份 `land-110m.json`（自然地球 1:1.1 亿 land 轮廓，仅大陆海岸线，无国界），
放大时只是把粗轮廓拉大，看不到任何新细节。

**目标**：矢量模式放大后能看到**国界 + 省/州界**，缩小时保持现有干净的粗轮廓视图。

写实（gl）/ 卫星（sat）模式靠贴图与 Esri 瓦片本就有放大细节，本特性**只作用于矢量渲染器**——
三种模式"放大看细节"的能力就此对齐，实现各异（符合"渲染器视图无关、能力对齐"的原则）。

## 2. 两级图层

按当前 `zoom` 选择绘制哪一层。阈值 `DETAIL_ZOOM ≈ 2.5`（约"放大到能看清一个国家"，实现时按手感微调）。

| 层级 | 触发条件 | 绘制内容 | 数据来源 |
|------|----------|----------|----------|
| Tier 0（默认/缩小） | `zoom < DETAIL_ZOOM` | 现有海岸线填充 + 经纬网 | 现 `land-110m.json`（不改） |
| Tier 1（详情/放大） | `zoom ≥ DETAIL_ZOOM` | 精细海岸线填充 + 湖泊 + 河流 + 国界&省/州界 | 新 `land-50m.json` + `lakes-10m.json` + `rivers-10m.json` + `admin1-10m.json` |

> 海岸线填充选 **50m**（非 10m）：实测逐帧重投影 10m 陆地约 187ms，是拖拽卡顿主因；
> 50m 海岸线相比 110m 已明显精细，重投影成本却低一个量级。省/州界与河湖仍取自 10m 源数据。

**关键简化**：admin-1 用 `topojson.mesh(..., (a,b) => a !== b)` 取**相邻共享边**，
一次同时得到国界（相邻国家/海陆边）与省/州界——不需要单独的国家边界文件，且无重复描边。
该 mesh 再按线段拆成要素数组，供第 5 节视口裁剪逐段判定。

Tier 1 生效时，海岸线填充从 `land-110m` 换为 `land-50m`，避免"粗海岸线 + 细省界"的错配。

**Tier 1 内部绘制顺序（自下而上）**：land-50m 填充 → 湖泊填充 → 河流描边 → admin-1 边界描边。
湖泊是填充面（水色），河流是折线描边；两者提升"放大看地形"的观感，与省界同档（10m）、同为懒加载。

## 3. 加载与切换

- **懒加载**：四个详情文件仅在 `zoom` **首次**越过 `DETAIL_ZOOM` 时并行 `fetch`，
  不影响首屏。加载入口放在 `globe-home.js` 的 `ensureDeps`（或等价钩子），结果存进
  `shared.landHi` / `shared.admin1` / `shared.lakes` / `shared.rivers`，**仅 D3 渲染器消费**，gl/sat 不受影响。
- **绘制切换**：`globe-d3.js` 的 `draw()` 按当前 `zoom` 选层。
  - `zoom < DETAIL_ZOOM`：走 Tier 0（现逻辑）。
  - `zoom ≥ DETAIL_ZOOM`：`shared.landHi` 填充 → `shared.lakes` 填充 → `shared.rivers` 描边 → `shared.admin1` 描边。
    四者均为**要素数组**（land 拆成多边形、admin 边界拆成线段），逐帧按视口裁剪只画可见的（见第 5 节）。
- **数据未就绪的过渡**：首次跨阈值时文件可能还没到——先照旧画 Tier 0，`fetch` resolve 后调一次 `draw()` 补上。
  无阻塞、无闪烁、无占位空白。

## 4. 数据来源与体积

| 文件 | 来源 | 处理 | 体积（约） |
|------|------|------|-----------|
| `land-50m.json` | world-atlas 现成 | 直接入 `vendor/` | ~0.5MB |
| `admin1-10m.json` | 自然地球 `ne_10m_admin_1_states_provinces` | mapshaper `-simplify 12% keep-shapes -filter-fields` → topojson，object `admin1` | ~1.5MB |
| `lakes-10m.json` | 自然地球 `ne_10m_lakes` | mapshaper `-simplify 25%` 同上，object `lakes` | ~0.4MB |
| `rivers-10m.json` | 自然地球 `ne_10m_rivers_lake_centerlines` | mapshaper `-simplify 20%` 同上，object `rivers` | ~0.6MB |

- 需联网下载源数据；转换（mapshaper）在实现阶段一次性完成，产物入 `app/static/vendor/`。
- 仓库现有 vendor 文件是**入库**的（非 gitignore），新文件照此处理。
- 合计新增 ~3MB，均为**懒加载**，仅第一次放大时下载。四个文件一并在跨阈值时拉取。

## 5. 性能：视口裁剪（viewport culling）

实测：详情态逐帧重投影**全球** land + admin + 河 + 湖约 100–300ms/帧（约 3–10fps），拖拽/缩放卡顿。
根因是 d3 每帧重投影**整个世界**的几何，即便只有一小块在视口内；且瓶颈是**几何顶点数**，
非自适应采样——调 `projection.precision` 几乎无效（实测 187ms→180ms）。

故采用**视口裁剪**：详情几何全部拆成**要素数组**（land→多边形、admin 边界网→线段、河/湖本就是要素集），
每个要素预缓存球面外接（中心 `_c` + 角半径 `_r`，`d3.geoBounds` 一次算出）。
每帧只 `filter` 出「要素外接与视口角半径相交」的要素再 `path`：

```
cap = asin(min(1, 半对角/scale)) + 余量        // 视口角半径；缩小时→半球（不裁剪）
keep(f) = geoDistance(视口中心, f._c) < cap + f._r
```

- **深放大**：可见要素骤减 → 重绘 ~15ms（约 60fps），且**越放大越快**、越放大越清晰。
- **详情全程可见**：不再有"交互中降级/停手补详情"的闪烁，拖拽/缩放时详情与海岸线始终在。
- **代价**：刚过 `DETAIL_ZOOM`（视口约含整块大陆）时大部分要素仍可见，裁剪帮不上忙，
  该缩放带**主动拖拽**时 ~80ms/帧（约 12fps）；静态观看始终瞬时。

`ZOOM_MAX` 由 8 放宽到 **50**，可持续放大到省/市级（配合裁剪，深放大反而更流畅）。

## 6. 分层与接口影响

- `globe-home.js`：`ensureDeps` 增加详情层懒加载分支；`shared` 增加 `landHi` / `admin1` / `lakes` / `rivers` 字段。
- `globe-d3.js`：`draw()` 按 zoom 分支选层，新增 `gLake` / `gRiver` 组；`wheel` / `flyTo` 缩放路径里，跨阈值时触发懒加载。
- 不改数据模型、后端、其它渲染器接口（`setFocus/focusView/initialView/resetView/resize/pause/resume` 不变）。

## 7. 测试与验证

矢量层是纯前端（无 pytest 覆盖，与项目"纯前端不写测试"一致）。用 preview 验证：

1. 放大越过阈值 → 国界 + 省/州界 + 河流 + 湖泊出现，海岸线变精细。
2. 缩小回到阈值以下 → 详情层消失，回到粗轮廓。
3. 首次放大时懒加载文件到达后自动补画，无空白/闪烁。
4. 拖拽 / 缩放流畅（观察掉帧）。
5. 切到写实 / 卫星模式不受影响，来回切换正常。

## 8. 明确不做（YAGNI）

- 不做按可视区域分片下载（per-region tiling）——本项目单机私用，懒加载整份足够。
- 不做 50m 中间层——两级（110m / 10m）已够，避免多余复杂度。
- 不改写实 / 卫星模式。
