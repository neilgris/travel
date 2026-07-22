// 月度/年度/总览三页共用的图表工具：调色板、金额格式化、甜甜圈工厂。
// 三页的分类占比甜甜圈配置完全一样，抽到这里一处维护。
const EXP_PALETTE = ['#e76f51', '#2a9d8f', '#e9c46a', '#4a9fc9', '#9b8cb5', '#b0a99f', '#f4a261', '#606c38'];

Chart.defaults.font.family = "system-ui, -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif";

const expFmt = v => '￥' + v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const expFmt0 = v => '￥' + Math.round(v).toLocaleString('zh-CN');

// data: [{category, total}]。canvasId 指向一个 <canvas>。
function expMakeDonut(canvasId, data) {
  return new Chart(document.getElementById(canvasId), {
    type: 'doughnut',
    data: {
      labels: data.map(c => c.category),
      datasets: [{
        data: data.map(c => c.total),
        backgroundColor: data.map((c, i) => EXP_PALETTE[i % EXP_PALETTE.length]),
        borderWidth: 2, borderColor: '#fff', hoverOffset: 10,
      }],
    },
    options: {
      maintainAspectRatio: false,
      cutout: '64%',
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: i => {
          const total = data.reduce((a, c) => a + c.total, 0);
          const pct = total ? (i.raw / total * 100).toFixed(1) : 0;
          return ` ${i.label}  ${expFmt(i.raw)}  (${pct}%)`;
        } } },
      },
    },
  });
}
