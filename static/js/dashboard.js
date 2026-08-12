const CHART = {
  primary: '#56696E', good: '#527051', warn: '#8C6220', bad: '#9E4A46',
  text: '#6E6C63', textMuted: '#767366', border: '#E7E4DB',
  palette: ['#56696E', '#5C7A5B', '#A97A2E', '#8C86A0', '#A98089', '#5A8A82'],
};
const CHART_FONT = "'Noto Sans JP', sans-serif";
// OS の「視差効果を減らす」設定時はグラフの登場アニメーションも止める
const REDUCE_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const BASE_OPTION = {
  animation: !REDUCE_MOTION,
  textStyle: { fontFamily: CHART_FONT, color: CHART.text, fontSize: 12 },
  tooltip: {
    backgroundColor: '#FFFFFF', borderColor: CHART.border, borderWidth: 1,
    textStyle: { fontFamily: CHART_FONT, color: '#2B2A26', fontSize: 12 },
    extraCssText: 'box-shadow: 0 2px 8px rgba(16,24,40,0.08); border-radius: 8px;',
  },
  grid: { top: 30, right: 20, bottom: 30, left: 50, containLabel: true },
};

let regionData = [];
let scoreByWard = {};
let tableSort = { key: 'overall_score', dir: -1 };

// 既存インスタンスを使い回し、リサイズ時は resize() だけ呼ぶ (再取得・再描画しない)
const chartRegistry = {};
function initChart(el) {
  const prev = chartRegistry[el.id];
  if (prev && !prev.isDisposed() && prev.getDom() !== el) prev.dispose();
  const c = echarts.getInstanceByDom(el) || echarts.init(el);
  chartRegistry[el.id] = c;
  return c;
}

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

// canvas はスクリーンリーダーには空。グラフを role=img + 要約テキストにして読めるようにする
function chartA11y(el, label) {
  if (!el) return;
  el.setAttribute('role', 'img');
  el.setAttribute('aria-label', label);
}
const TABLE_HINT = '数値の詳細はページ下部の「全エリア一覧」の表を参照してください。';

const isNarrow = () => window.innerWidth <= 600;

function bar(id, data) {
  const el = document.getElementById(id); if (!el || !data || !data.length) return;
  const sorted = [...data].sort((a, b) => b.value - a.value);
  const hi = sorted[0], lo = sorted[sorted.length - 1];
  chartA11y(el, `相場ランキングの棒グラフ。${data.length}エリア。` +
    `最も高いのは${hi.name} ${man(hi.value)}円、最も安いのは${lo.name} ${man(lo.value)}円。${TABLE_HINT}`);

  const bars = data.map(x => ({ value: x.value, itemStyle: { color: scoreColor(scoreByWard[x.name] ?? 50), borderRadius: [4, 4, 0, 0] } }));
  const names = data.map(x => x.name);
  const valueAxis = { type: 'value', splitLine: { lineStyle: { color: CHART.border } }, axisLabel: { color: CHART.textMuted, formatter: v => (v / 10000) + '万' } };
  const tooltip = { trigger: 'axis', formatter: p => `${p[0].name}<br/>相場 ${p[0].value.toLocaleString()}円<br/>総合評価 ${scoreByWard[p[0].name] ?? '-'}` };
  const narrow = isNarrow();

  if (narrow) {
    // 縦棒だと 23 区のラベルが半分しか描画されない。横棒にして全件読めるようにする。
    el.style.height = (data.length * 19 + 50) + 'px';
    initChart(el).setOption({
      ...BASE_OPTION, tooltip,
      grid: { top: 8, right: 16, bottom: 8, left: 8, containLabel: true },
      xAxis: valueAxis,
      yAxis: { type: 'category', data: names, inverse: true, axisLabel: { color: CHART.text, fontSize: 11 }, axisLine: { lineStyle: { color: CHART.border } } },
      series: [{ type: 'bar', barMaxWidth: 13, data: bars.map(b => ({ ...b, itemStyle: { ...b.itemStyle, borderRadius: [0, 4, 4, 0] } })) }],
    });
    return;
  }
  el.style.height = '';
  initChart(el).setOption({
    ...BASE_OPTION, tooltip,
    grid: { top: 16, right: 16, bottom: 8, left: 40, containLabel: true },
    xAxis: { type: 'category', data: names, axisLabel: { color: CHART.text, fontSize: 10, rotate: 45 }, axisLine: { lineStyle: { color: CHART.border } } },
    yAxis: valueAxis,
    series: [{ type: 'bar', barMaxWidth: 26, data: bars }],
  });
}

function valueMap() {
  const el = document.getElementById('chart-value-map'); if (!el) return;
  const rented = regionData.filter(r => r.avg_rent);
  if (!rented.length) return;
  const rents = rented.map(r => r.avg_rent).sort((a, b) => a - b);
  const medRent = rents[Math.floor(rents.length / 2)];
  // 「安くて評価が高い」= 割安度の高い順に上位3件を代替テキストにする
  const best = [...rented].sort((a, b) => (b.overall_score / b.avg_rent) - (a.overall_score / a.avg_rent)).slice(0, 3);
  chartA11y(el, `狙い目エリアマップ。横軸が相場、縦軸が総合評価の散布図で、${rented.length}エリアを表示。` +
    `相場の中央値は${man(medRent)}円。左上ほど「安くて評価が高い」エリアで、上位は` +
    best.map(r => `${regionName(r)}(相場${man(r.avg_rent)}円 / 評価${r.overall_score})`).join('、') +
    `。${TABLE_HINT}`);
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
  initChart(el).setOption({
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
  initChart(el).setOption({
    ...BASE_OPTION,
    legend: { bottom: 0, textStyle: { fontFamily: CHART_FONT, color: CHART.text, fontSize: 11 } },
    radar: {
      indicator: indicators, shape: 'polygon', radius: '62%',
      splitArea: { areaStyle: { color: ['rgba(86,105,110,0.02)', 'rgba(86,105,110,0.04)'] } },
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
  const dims = ['安全性', '便利度', '環境', '相場の高さ'];
  radar('chart-region-radar',
    dims.map(name => ({ name, max: 100 })),
    series);
  // 選択が変わるたびに代替テキストも更新する
  chartA11y(document.getElementById('chart-region-radar'),
    'エリア比較レーダーチャート。各項目は100点満点。' +
    series.map(s => `${s.name}は` + dims.map((d, i) => `${d}${s.value[i]}`).join('、')).join('。') + '。');
}

function scoreBar(s) {
  const c = scoreColor(s);
  return `<div style="display:flex;align-items:center;gap:8px;min-width:90px;">
    <div style="flex:1;height:6px;background:var(--bg-alt);border-radius:3px;overflow:hidden;min-width:44px;"><div style="width:${s}%;height:100%;background:${c};border-radius:3px;"></div></div>
    <span style="font-size:11px;color:var(--text-muted);width:20px;text-align:right;">${s}</span></div>`;
}

// 住みやすさは高/中/低の3段階 → そのままラベル表示 (高=緑 好 / 中=橙 / 低=赤)
function levelTag(lv) {
  if (!lv) return '<span style="color:var(--text-muted);">-</span>';
  const cls = lv === '高' ? 'good' : lv === '中' ? 'warn' : 'bad';
  return `<span class="tag ${cls}">${lv}</span>`;
}

function renderTable() {
  const tbody = document.querySelector('#region-table tbody');
  if (!tbody) return;
  const HAZ_ORDER = { '高': 3, '中': 2, '低': 1 };
  const rows = [...regionData].sort((a, b) => {
    const k = tableSort.key;
    if (k === 'name') return (regionName(a) > regionName(b) ? 1 : -1) * tableSort.dir;
    if (k === 'hazard_level') return ((HAZ_ORDER[a.hazard_level] || 0) - (HAZ_ORDER[b.hazard_level] || 0)) * tableSort.dir;
    return ((a[k] || 0) - (b[k] || 0)) * tableSort.dir;
  });
  tbody.innerHTML = rows.map(r => `<tr>
    <td style="font-weight:600;color:var(--text-primary);">${regionName(r)}</td>
    <td>${r.avg_rent ? man(r.avg_rent) : '-'}</td>
    <td title="${r.trade_count ? `直近4四半期 ${r.trade_count}件 (中古マンション等, 出典: 不動産情報ライブラリ)` : ''}">${r.trade_price_per_m2 ? man(r.trade_price_per_m2) : '-'}</td>
    <td>${scoreBar(r.overall_score)}</td>
    <td>${levelTag(r.safety_level)}</td>
    <td>${levelTag(r.convenience_level)}</td>
    <td>${levelTag(r.environment_level)}</td>
    <td>${r.hazard_level ? `<span class="tag ${r.hazard_level === '高' ? 'hazard-high' : r.hazard_level === '中' ? 'warn' : 'good'}" title="洪水・土砂 (出典: 不動産情報ライブラリ, 区役所周辺の参考値)">${r.hazard_level}</span>` : '-'}</td>
  </tr>`).join('');
}

// 现在の並び替え状態を aria-sort と矢印で表示 (スクリーンリーダー + 視覚)
function updateSortIndicators() {
  document.querySelectorAll('#region-table th[data-sort]').forEach(th => {
    const active = th.dataset.sort === tableSort.key;
    const asc = tableSort.dir === 1;
    th.setAttribute('aria-sort', active ? (asc ? 'ascending' : 'descending') : 'none');
    th.querySelector('.sort-arrow')?.remove();
    if (active) {
      const a = document.createElement('span');
      a.className = 'sort-arrow';
      a.setAttribute('aria-hidden', 'true');
      a.textContent = asc ? ' ▲' : ' ▼';
      th.appendChild(a);
    }
  });
}

function metricCard(num, label, cls, sub) {
  return `<div class="metric ${cls || ''}"><div class="num">${num}</div><div class="label">${label}</div>${sub ? `<div class="label" style="color:var(--text-secondary);margin-top:2px;">${sub}</div>` : ''}</div>`;
}

// 取得済みデータからグラフだけ描き直す (縦棒⇄横棒の切替に使う。再取得はしない)
let dashData = null;
function renderCharts() {
  if (!dashData) return;
  valueMap();
  bar('chart-tokyo-rent', dashData.tokyo_region_rent);
  bar('chart-yokohama-rent', dashData.yokohama_region_rent);
  renderRegionRadar();
}

async function load() {
  const d = await (await fetch('/api/dashboard')).json();
  dashData = d;
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

  // レーダーはセレクタの値を読むので、先に選択肢を用意してから描画する
  const opts = '<option value="">エリアを選択...</option>' +
    regionData.map(r => `<option value="${regionName(r)}">${regionName(r)}</option>`).join('');
  document.getElementById('region-selector-1').innerHTML = opts;
  document.getElementById('region-selector-2').innerHTML = opts;
  if (regionData.length > 0) document.getElementById('region-selector-1').value = regionName(regionData[0]);
  if (regionData.length > 5) document.getElementById('region-selector-2').value = regionName(regionData[5]);

  renderCharts();

  renderTable();
  document.querySelectorAll('#region-table th[data-sort]').forEach(th => {
    th.style.cursor = 'pointer';
    th.tabIndex = 0;
    th.setAttribute('role', 'button');
    const sortBy = () => {
      const k = th.dataset.sort;
      tableSort = { key: k, dir: tableSort.key === k ? -tableSort.dir : (k === 'name' ? 1 : -1) };
      renderTable();
      updateSortIndicators();
    };
    th.addEventListener('click', sortBy);
    th.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sortBy(); }
    });
  });
  updateSortIndicators();
}

// リサイズでデータを取り直す必要はない。既存グラフの寸法だけ合わせる。
let _rz;
let _wasNarrow = isNarrow();
window.addEventListener('resize', () => {
  clearTimeout(_rz);
  _rz = setTimeout(() => {
    // ブレークポイントをまたいだ時だけ組み替える (それ以外は寸法合わせのみ)
    const now = isNarrow();
    if (now !== _wasNarrow) { _wasNarrow = now; renderCharts(); return; }
    Object.values(chartRegistry).forEach(c => { if (!c.isDisposed()) c.resize(); });
  }, 200);
});
load();
