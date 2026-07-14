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
let scoreByWard = {};
let tableSort = { key: 'overall_score', dir: -1 };

const man = v => (v / 10000).toFixed(1) + '万';
const regionName = r => r.ward || r.city || r.prefecture || '-';
function scoreColor(s) { return s >= 75 ? CHART.good : s >= 60 ? CHART.primary : s >= 45 ? CHART.warn : CHART.bad; }
function regionGroup(r) {
  if (r.prefecture === '東京都') return '東京23区';
  if (r.city === '横浜市') return '横浜市';
  if (r.city === '川崎市') return '川崎市';
  return '主要都市';
}
const GROUP_COLOR = { '東京23区': CHART.palette[0], '横浜市': CHART.palette[1], '川崎市': CHART.palette[2], '主要都市': CHART.palette[3] };

function bar(id, data) {
  const el = document.getElementById(id); if (!el || !data || !data.length) return;
  echarts.init(el).setOption({
    ...BASE_OPTION,
    grid: { top: 16, right: 16, bottom: 70, left: 40, containLabel: true },
    xAxis: { type: 'category', data: data.map(x => x.name), axisLabel: { color: CHART.text, fontSize: 10, rotate: 45 }, axisLine: { lineStyle: { color: CHART.border } } },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: CHART.border } }, axisLabel: { color: CHART.textMuted, formatter: v => (v / 10000) + '万' } },
    series: [{
      type: 'bar', barMaxWidth: 26,
      data: data.map(x => ({ value: x.value, itemStyle: { color: scoreColor(scoreByWard[x.name] ?? 50), borderRadius: [4, 4, 0, 0] } })),
    }],
    tooltip: { trigger: 'axis', formatter: p => `${p[0].name}<br/>相場 ${p[0].value.toLocaleString()}円<br/>総合評価 ${scoreByWard[p[0].name] ?? '-'}` },
  });
}

function valueMap() {
  const el = document.getElementById('chart-value-map'); if (!el) return;
  const rented = regionData.filter(r => r.avg_rent);
  if (!rented.length) return;
  const rents = rented.map(r => r.avg_rent).sort((a, b) => a - b);
  const medRent = rents[Math.floor(rents.length / 2)];
  const groups = {};
  rented.forEach(r => { const g = regionGroup(r); (groups[g] = groups[g] || []).push(r); });
  const series = Object.entries(groups).map(([g, arr]) => ({
    name: g, type: 'scatter', symbolSize: 15,
    itemStyle: { color: GROUP_COLOR[g], opacity: 0.82, borderColor: '#fff', borderWidth: 1 },
    data: arr.map(r => ({ value: [r.avg_rent, r.overall_score], name: regionName(r) })),
    markLine: g === Object.keys(groups)[0] ? {
      silent: true, symbol: 'none', lineStyle: { color: CHART.textMuted, type: 'dashed' },
      label: { color: CHART.textMuted, fontSize: 10 },
      data: [{ xAxis: medRent, label: { formatter: '相場中央値' } }, { yAxis: 60, label: { formatter: '評価60' } }],
    } : undefined,
  }));
  echarts.init(el).setOption({
    ...BASE_OPTION,
    grid: { top: 40, right: 24, bottom: 60, left: 56, containLabel: true },
    legend: { bottom: 0, textStyle: { fontFamily: CHART_FONT, color: CHART.text, fontSize: 12 } },
    tooltip: { formatter: p => `${p.data.name}<br/>相場 ${p.data.value[0].toLocaleString()}円<br/>総合評価 ${p.data.value[1]}` },
    xAxis: { type: 'value', name: '相場(円)', nameLocation: 'middle', nameGap: 34, axisLabel: { color: CHART.textMuted, formatter: v => (v / 10000) + '万' }, splitLine: { lineStyle: { color: CHART.border } } },
    yAxis: { type: 'value', name: '総合評価', min: 20, max: 100, axisLabel: { color: CHART.textMuted }, splitLine: { lineStyle: { color: CHART.border } } },
    series,
  });
}

function radar(id, indicators, seriesData) {
  const el = document.getElementById(id); if (!el) return;
  echarts.init(el).setOption({
    ...BASE_OPTION,
    legend: { bottom: 0, textStyle: { fontFamily: CHART_FONT, color: CHART.text, fontSize: 11 } },
    radar: {
      indicator: indicators, shape: 'polygon', radius: '62%',
      splitArea: { areaStyle: { color: ['rgba(37,99,235,0.02)', 'rgba(37,99,235,0.04)'] } },
      axisName: { color: CHART.text, fontFamily: CHART_FONT, fontSize: 11 },
    },
    series: [{ type: 'radar', data: seriesData, symbol: 'circle', symbolSize: 6, areaStyle: { opacity: 0.08 }, lineStyle: { width: 2 } }],
  });
}

function renderRegionRadar() {
  const s1 = document.getElementById('region-selector-1').value;
  const s2 = document.getElementById('region-selector-2').value;
  const series = [];
  for (const sel of [s1, s2]) {
    if (!sel) continue;
    const r = regionData.find(x => regionName(x) === sel);
    if (!r) continue;
    const i = series.length;
    series.push({
      value: [r.safety_score, r.convenience_score, r.environment_score, Math.round((r.avg_rent || 0) / 300000 * 100)],
      name: regionName(r),
      itemStyle: { color: CHART.palette[i % CHART.palette.length] },
    });
  }
  if (!series.length) return;
  radar('chart-region-radar',
    [{ name: '安全性', max: 100 }, { name: '便利度', max: 100 }, { name: '環境', max: 100 }, { name: '相場の高さ', max: 100 }],
    series);
}

function scoreBar(s) {
  const c = scoreColor(s);
  return `<div style="display:flex;align-items:center;gap:8px;min-width:90px;">
    <div style="flex:1;height:6px;background:var(--bg-alt);border-radius:3px;overflow:hidden;min-width:44px;"><div style="width:${s}%;height:100%;background:${c};border-radius:3px;"></div></div>
    <span style="font-size:11px;color:var(--text-muted);width:20px;text-align:right;">${s}</span></div>`;
}

function renderTable() {
  const tbody = document.querySelector('#region-table tbody');
  if (!tbody) return;
  const rows = [...regionData].sort((a, b) => {
    const k = tableSort.key;
    if (k === 'name') return (regionName(a) > regionName(b) ? 1 : -1) * tableSort.dir;
    return ((a[k] || 0) - (b[k] || 0)) * tableSort.dir;
  });
  tbody.innerHTML = rows.map(r => `<tr>
    <td style="font-weight:600;color:var(--text-primary);">${regionName(r)}</td>
    <td>${r.avg_rent ? man(r.avg_rent) : '-'}</td>
    <td>${scoreBar(r.overall_score)}</td>
    <td>${scoreBar(r.safety_score)}</td>
    <td>${scoreBar(r.convenience_score)}</td>
    <td>${scoreBar(r.environment_score)}</td>
  </tr>`).join('');
}

function metricCard(num, label, cls, sub) {
  return `<div class="metric ${cls || ''}"><div class="num">${num}</div><div class="label">${label}</div>${sub ? `<div class="label" style="color:var(--text-secondary);margin-top:2px;">${sub}</div>` : ''}</div>`;
}

async function load() {
  const d = await (await fetch('/api/dashboard')).json();
  regionData = d.regions || [];
  scoreByWard = {};
  regionData.forEach(r => { scoreByWard[regionName(r)] = r.overall_score; });

  const s = d.area_summary || {};
  document.getElementById('metrics').innerHTML = [
    metricCard(d.region_count ?? 0, 'エリア数', 'accent'),
    metricCard(s.rent_min && s.rent_max ? `${man(s.rent_min)}〜${man(s.rent_max)}` : '-', '相場レンジ (1LDK)', ''),
    metricCard(s.cheapest ? man(s.cheapest.rent) : '-', '最安エリア', 'good', s.cheapest ? s.cheapest.ward : ''),
    metricCard(s.best_value ? s.best_value.ward : '-', '狙い目エリア', '', s.best_value ? `評価${s.best_value.score} / ${man(s.best_value.rent)}` : ''),
  ].join('');

  valueMap();
  bar('chart-tokyo-rent', d.tokyo_region_rent);
  bar('chart-yokohama-rent', d.yokohama_region_rent);

  const opts = '<option value="">エリアを選択...</option>' +
    regionData.map(r => `<option value="${regionName(r)}">${regionName(r)}</option>`).join('');
  document.getElementById('region-selector-1').innerHTML = opts;
  document.getElementById('region-selector-2').innerHTML = opts;
  if (regionData.length > 0) document.getElementById('region-selector-1').value = regionName(regionData[0]);
  if (regionData.length > 5) document.getElementById('region-selector-2').value = regionName(regionData[5]);
  renderRegionRadar();

  renderTable();
  document.querySelectorAll('#region-table th[data-sort]').forEach(th => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => {
      const k = th.dataset.sort;
      tableSort = { key: k, dir: tableSort.key === k ? -tableSort.dir : (k === 'name' ? 1 : -1) };
      renderTable();
    });
  });
}

let _rz;
window.addEventListener('resize', () => { clearTimeout(_rz); _rz = setTimeout(load, 300); });
load();
