// ECharts color palette aligned with CSS design system
const CHART = {
  primary: '#2563EB',
  primaryLight: '#3B82F6',
  good: '#059669',
  warn: '#D97706',
  bad: '#DC2626',
  text: '#5A6B7E',
  textMuted: '#8B9AAA',
  border: '#E4E8EC',
  bg: '#FAFBFC',
  palette: ['#2563EB', '#059669', '#D97706', '#8B5CF6', '#EC4899', '#14B8A6', '#6366F1', '#F43F5E'],
};

const CHART_FONT = "'Noto Sans JP', sans-serif";

const BASE_OPTION = {
  textStyle: { fontFamily: CHART_FONT, color: CHART.text, fontSize: 12 },
  title: { textStyle: { fontFamily: CHART_FONT, fontSize: 14, fontWeight: 600, color: '#1A2332' } },
  tooltip: {
    backgroundColor: '#FFFFFF',
    borderColor: CHART.border,
    borderWidth: 1,
    textStyle: { fontFamily: CHART_FONT, color: '#1A2332', fontSize: 12 },
    extraCssText: 'box-shadow: 0 2px 8px rgba(16,24,40,0.08); border-radius: 8px;',
  },
  grid: { top: 30, right: 20, bottom: 30, left: 50, containLabel: true },
};

function bar(id, title, data, horizontal = false) {
  const el = document.getElementById(id);
  if (!el) return;
  const ch = echarts.init(el);
  ch.setOption({
    ...BASE_OPTION,
    title: { ...BASE_OPTION.title, text: title, left: 'center' },
    xAxis: horizontal ? { type: 'value', splitLine: { lineStyle: { color: CHART.border } }, axisLabel: { color: CHART.textMuted } } : { type: 'category', data: data.map(x => x.name), axisLabel: { color: CHART.text, fontSize: 11 }, axisLine: { lineStyle: { color: CHART.border } } },
    yAxis: horizontal ? { type: 'category', data: data.map(x => x.name), axisLabel: { color: CHART.text, fontSize: 11 }, axisLine: { lineStyle: { color: CHART.border } } } : { type: 'value', splitLine: { lineStyle: { color: CHART.border } }, axisLabel: { color: CHART.textMuted } },
    series: [{
      type: 'bar',
      data: data.map(x => x.value),
      itemStyle: { color: CHART.primary, borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] },
      barMaxWidth: 40,
    }],
  });
}

function pie(id, title, data) {
  const el = document.getElementById(id);
  if (!el) return;
  const ch = echarts.init(el);
  ch.setOption({
    ...BASE_OPTION,
    title: { ...BASE_OPTION.title, text: title, left: 'center' },
    legend: { bottom: 0, textStyle: { fontFamily: CHART_FONT, color: CHART.text, fontSize: 11 } },
    series: [{
      type: 'pie',
      radius: ['40%', '65%'],
      center: ['50%', '45%'],
      data: data.map((x, i) => ({ name: x.name, value: x.value, itemStyle: { color: CHART.palette[i % CHART.palette.length] } })),
      label: { fontFamily: CHART_FONT, color: CHART.text, fontSize: 11 },
      itemStyle: { borderColor: '#FFFFFF', borderWidth: 2 },
    }],
  });
}

function scatter(id, title, data) {
  const el = document.getElementById(id);
  if (!el) return;
  const ch = echarts.init(el);
  ch.setOption({
    ...BASE_OPTION,
    title: { ...BASE_OPTION.title, text: title, left: 'center' },
    xAxis: { name: '面積(㎡)', type: 'value', nameTextStyle: { color: CHART.textMuted, fontFamily: CHART_FONT }, splitLine: { lineStyle: { color: CHART.border } }, axisLabel: { color: CHART.textMuted } },
    yAxis: { name: '月額(円)', type: 'value', nameTextStyle: { color: CHART.textMuted, fontFamily: CHART_FONT }, splitLine: { lineStyle: { color: CHART.border } }, axisLabel: { color: CHART.textMuted } },
    series: [{
      type: 'scatter',
      symbolSize: 8,
      data: data.map(x => [x.x, x.y, x.title]),
      itemStyle: { color: CHART.primary, opacity: 0.7 },
      emphasis: { itemStyle: { color: CHART.primaryLight, opacity: 1, shadowBlur: 8, shadowColor: 'rgba(37,99,235,0.3)' } },
    }],
  });
}

function line(id, title, data) {
  const el = document.getElementById(id);
  if (!el) return;
  const ch = echarts.init(el);
  ch.setOption({
    ...BASE_OPTION,
    title: { ...BASE_OPTION.title, text: title, left: 'center' },
    xAxis: { type: 'category', data: data.map(x => x.name), axisLabel: { color: CHART.textMuted } },
    yAxis: { type: 'value', axisLabel: { color: CHART.textMuted } },
    series: [{ type: 'line', data: data.map(x => x.value), smooth: true, lineStyle: { color: CHART.primary, width: 2 }, itemStyle: { color: CHART.primary } }],
  });
}

async function load() {
  const res = await fetch('/api/dashboard');
  const d = await res.json();

  const metrics = [
    { label: '総物件数', value: d.total_listings, cls: '' },
    { label: '予算内', value: d.budget_match_count, cls: 'good' },
    { label: '2階以上', value: d.floor_2plus_count, cls: '' },
    { label: 'ペット可', value: d.pet_allowed_count, cls: 'accent' },
    { label: '平均月額', value: (d.average_total_cost || 0).toLocaleString() + '円', cls: '' },
    { label: '平均面積', value: (d.average_area || 0) + '㎡', cls: '' },
    { label: '平均推薦分', value: d.average_score || 0, cls: 'accent' },
    { label: '新着', value: d.new_listing_count, cls: 'good' },
    { label: '値下がり', value: d.price_drop_count, cls: 'warn' },
    { label: 'お気に入り', value: d.favorite_count, cls: '' },
  ];

  document.getElementById('metrics').innerHTML = metrics.map(m =>
    `<div class="metric ${m.cls}"><div class="num">${m.value ?? 0}</div><div class="label">${m.label}</div></div>`
  ).join('');

  bar('chart-area-rent', 'エリア別平均月額', d.area_rent_data, true);
  bar('chart-rent-dist', '家賃分布', d.rent_distribution);
  scatter('chart-scatter', '面積 vs 月額', d.scatter_data);
  bar('chart-top10', '推薦スコア Top 10', d.top_score_listings.map(x => ({ name: x.title, value: x.total_score })), true);
  pie('chart-layout', '間取り比率', d.layout_distribution);
  pie('chart-platform', 'プラットフォーム比率', d.platform_distribution);
  bar('chart-floor', '階数分布', d.floor_distribution);
  bar('chart-age', '築年数分布', d.age_distribution);
  pie('chart-status', 'ステータス分布', d.status_distribution);

  const phEl = document.getElementById('chart-price-history');
  if (d.price_history_chart && d.price_history_chart.length) {
    line('chart-price-history', '価格履歴', d.price_history_chart);
  } else {
    phEl.className = 'chart-empty';
    phEl.innerHTML = '価格履歴は複数回取得後に表示されます';
  }
}

load();