const CHART = {
  primary: '#2563EB', good: '#059669', warn: '#D97706', bad: '#DC2626',
  text: '#5A6B7E', textMuted: '#8B9AAA', border: '#E4E8EC',
  palette: ['#2563EB', '#059669', '#D97706', '#8B5CF6', '#EC4899', '#14B8A6'],
};
const CHART_FONT = "'Noto Sans JP', sans-serif";
const BASE_OPTION = {
  textStyle: { fontFamily: CHART_FONT, color: CHART.text, fontSize: 12 },
  tooltip: {
    backgroundColor: '#FFFFFF', borderColor: CHART.border, borderWidth: 1,
    textStyle: { fontFamily: CHART_FONT, color: '#1A2332', fontSize: 12 },
    extraCssText: 'box-shadow: 0 2px 8px rgba(16,24,40,0.08); border-radius: 8px;',
  },
  grid: { top: 30, right: 20, bottom: 30, left: 50, containLabel: true },
};

let regionData = [];

function bar(id, data, color) {
  const el = document.getElementById(id); if (!el) return;
  const ch = echarts.init(el);
  ch.setOption({
    ...BASE_OPTION,
    xAxis: { type: 'category', data: data.map(x => x.name), axisLabel: { color: CHART.text, fontSize: 10, rotate: 45 }, axisLine: { lineStyle: { color: CHART.border } } },
    yAxis: { type: 'value', name: '円', splitLine: { lineStyle: { color: CHART.border } }, axisLabel: { color: CHART.textMuted } },
    series: [{ type: 'bar', data: data.map(x => x.value), itemStyle: { color: color || CHART.primary, borderRadius: [4, 4, 0, 0] }, barMaxWidth: 30 }],
    tooltip: { trigger: 'axis', formatter: p => `${p[0].name}<br/>${p[0].value.toLocaleString()}円` },
  });
}

function radar(id, indicators, seriesData) {
  const el = document.getElementById(id); if (!el) return;
  const ch = echarts.init(el);
  ch.setOption({
    ...BASE_OPTION,
    legend: { bottom: 0, textStyle: { fontFamily: CHART_FONT, color: CHART.text, fontSize: 11 } },
    radar: {
      indicator: indicators, shape: 'polygon', radius: '65%',
      splitArea: { areaStyle: { color: ['rgba(37,99,235,0.02)', 'rgba(37,99,235,0.04)'] } },
      axisName: { color: CHART.text, fontFamily: CHART_FONT, fontSize: 11 },
    },
    series: [{ type: 'radar', data: seriesData, symbol: 'circle', symbolSize: 6,
      areaStyle: { opacity: 0.08 }, lineStyle: { width: 2 } }],
  });
}

function renderRegionRadar() {
  const s1 = document.getElementById('region-selector-1').value;
  const s2 = document.getElementById('region-selector-2').value;
  const levelMap = { '高': 3, '中': 2, '低': 1 };
  const series = [];
  for (const sel of [s1, s2]) {
    if (!sel) continue;
    const r = regionData.find(x => (x.ward || x.city) === sel);
    if (!r) continue;
    const name = r.ward || r.city;
    const i = series.length;
    series.push({
      value: [
        levelMap[r.safety_level] || 2,
        levelMap[r.convenience_level] || 2,
        levelMap[r.environment_level] || 2,
        r.avg_rent ? r.avg_rent / 10000 : 0,
      ],
      name: name,
      itemStyle: { color: CHART.palette[i % CHART.palette.length] },
    });
  }
  if (series.length === 0) return;
  radar('chart-region-radar',
    [{ name: '安全性', max: 3 }, { name: '便利度', max: 3 }, { name: '環境', max: 3 }, { name: '賃料(万円)', max: 20 }],
    series
  );
}

async function load() {
  const res = await fetch('/api/dashboard');
  const d = await res.json();

  // 指标卡
  const metrics = [
    { label: 'エリア数', value: d.region_count, cls: 'accent' },
    { label: 'インポート物件', value: d.total_listings, cls: '' },
    { label: '予算内物件', value: d.budget_match_count, cls: 'good' },
    { label: 'お気に入り', value: d.favorite_count, cls: '' },
  ];
  document.getElementById('metrics').innerHTML = metrics.map(m =>
    `<div class="metric ${m.cls}"><div class="num">${m.value ?? 0}</div><div class="label">${m.label}</div></div>`).join('');

  // 区域平均租金
  if (d.tokyo_region_rent && d.tokyo_region_rent.length) {
    bar('chart-tokyo-rent', d.tokyo_region_rent, CHART.primary);
  }
  if (d.yokohama_region_rent && d.yokohama_region_rent.length) {
    bar('chart-yokohama-rent', d.yokohama_region_rent, CHART.good);
  }

  // 区域选择器
  regionData = d.regions || [];
  const opts = '<option value="">エリアを選択...</option>' +
    regionData.map(r => `<option value="${r.ward || r.city}">${r.ward || r.city}</option>`).join('');
  document.getElementById('region-selector-1').innerHTML = opts;
  document.getElementById('region-selector-2').innerHTML = opts;
  // 默认选两个区域
  if (regionData.length > 0) document.getElementById('region-selector-1').value = regionData[0].ward || regionData[0].city;
  if (regionData.length > 5) document.getElementById('region-selector-2').value = regionData[5].ward || regionData[5].city;
  renderRegionRadar();
}

load();