const CHART = {
  primary: '#2563EB', primaryLight: '#3B82F6',
  good: '#059669', warn: '#D97706', bad: '#DC2626',
  text: '#5A6B7E', textMuted: '#8B9AAA', border: '#E4E8EC',
  palette: ['#2563EB', '#059669', '#D97706', '#8B5CF6', '#EC4899', '#14B8A6', '#6366F1', '#F43F5E'],
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

function scatterWithBaseline(id, data) {
  const el = document.getElementById(id); if (!el) return;
  // 按区域分组基准线
  const wardAvgs = {};
  data.forEach(d => { if (d.region_avg && d.ward) wardAvgs[d.ward] = d.region_avg; });
  const markLines = Object.entries(wardAvgs).map(([ward, avg]) => ({
    yAxis: avg, lineStyle: { type: 'dashed', color: CHART.warn, opacity: 0.5 },
    label: { formatter: `${ward} ${avg.toLocaleString()}`, fontSize: 10, color: CHART.warn },
  }));
  const ch = echarts.init(el);
  ch.setOption({
    ...BASE_OPTION,
    xAxis: { name: '面積(㎡)', type: 'value', splitLine: { lineStyle: { color: CHART.border } }, axisLabel: { color: CHART.textMuted } },
    yAxis: { name: '月額(円)', type: 'value', splitLine: { lineStyle: { color: CHART.border } }, axisLabel: { color: CHART.textMuted } },
    tooltip: { trigger: 'item', formatter: p => `${p.data[2]}<br/>${p.data[0]}㎡ / ${p.data[1].toLocaleString()}円` },
    series: [{ type: 'scatter', symbolSize: 10,
      data: data.map(x => [x.x, x.y, x.name || '']),
      itemStyle: { color: CHART.primary, opacity: 0.7 },
      markLine: { data: markLines, symbol: 'none', animation: false, silent: true },
    }],
  });
}

function radar(id, indicators, series) {
  const el = document.getElementById(id); if (!el) return;
  const ch = echarts.init(el);
  ch.setOption({
    ...BASE_OPTION,
    legend: { bottom: 0, textStyle: { fontFamily: CHART_FONT, color: CHART.text, fontSize: 11 } },
    radar: {
      indicator: indicators,
      shape: 'polygon', radius: '65%',
      splitArea: { areaStyle: { color: ['rgba(37,99,235,0.02)', 'rgba(37,99,235,0.04)', 'rgba(37,99,235,0.06)'] } },
      axisName: { color: CHART.text, fontFamily: CHART_FONT, fontSize: 11 },
    },
    series: [{
      type: 'radar', data: series.map((s, i) => ({
        value: s.value, name: s.name,
        itemStyle: { color: CHART.palette[i % CHART.palette.length] },
        areaStyle: { opacity: 0.08 },
        lineStyle: { width: 2 },
      })),
    }],
  });
}

function deviationBar(id, data) {
  const el = document.getElementById(id); if (!el) return;
  const ch = echarts.init(el);
  ch.setOption({
    ...BASE_OPTION,
    xAxis: { type: 'value', splitLine: { lineStyle: { color: CHART.border } }, axisLabel: { color: CHART.textMuted, formatter: '{value}%' } },
    yAxis: { type: 'category', data: data.map(d => d.name), axisLabel: { color: CHART.text, fontSize: 11 }, axisLine: { lineStyle: { color: CHART.border } } },
    series: [{
      type: 'bar',
      data: data.map(d => ({
        value: d.deviation_pct,
        itemStyle: { color: d.deviation_pct > 0 ? CHART.bad : CHART.good },
      })),
      barMaxWidth: 25,
      markLine: { data: [{ xAxis: 0 }], symbol: 'none', lineStyle: { type: 'solid', color: CHART.textMuted }, animation: false, silent: true },
    }],
    tooltip: { trigger: 'item', formatter: p => {
      const d = data[p.dataIndex];
      return `${d.name}<br/>${d.ward}: ${(d.total_monthly_cost||0).toLocaleString()}円 vs ${(d.region_avg_rent||0).toLocaleString()}円<br/>偏差: ${d.deviation_pct}%`;
    }},
  });
}

async function load() {
  const res = await fetch('/api/my-list');
  const d = await res.json();

  // 指标卡
  const metrics = [
    { label: '物件数', value: d.total, cls: '' },
    { label: '予算内', value: d.budget_match, cls: 'good' },
    { label: '平均月額', value: (d.avg_cost || 0).toLocaleString() + '円', cls: '' },
    { label: '平均スコア', value: d.avg_score, cls: 'accent' },
    { label: '未問合せ', value: d.uncontacted, cls: 'warn' },
  ];
  document.getElementById('my-metrics').innerHTML = metrics.map(m =>
    `<div class="metric ${m.cls}"><div class="num">${m.value ?? 0}</div><div class="label">${m.label}</div></div>`).join('');

  // 散点
  if (d.scatter_data && d.scatter_data.length) {
    scatterWithBaseline('chart-scatter', d.scatter_data);
  } else {
    document.getElementById('chart-scatter').className = 'chart-empty';
    document.getElementById('chart-scatter').innerHTML = '物件をインポートすると表示されます';
  }

  // 雷达
  if (d.radar_series && d.radar_series.length) {
    radar('chart-radar', d.radar_indicators, d.radar_series);
  } else {
    document.getElementById('chart-radar').className = 'chart-empty';
    document.getElementById('chart-radar').innerHTML = '物件をインポートすると表示されます';
  }

  // 偏差
  if (d.deviations && d.deviations.length) {
    deviationBar('chart-deviation', d.deviations);
  } else {
    document.getElementById('chart-deviation').className = 'chart-empty';
    document.getElementById('chart-deviation').innerHTML = '物件をインポートすると表示されます';
  }

  // 对比表
  renderCompareTable(d.compare_rows || []);

  // 状态进度
  renderStatusProgress(d.status_progress || []);

  // 价格历史
  renderPriceHistory(d.price_history || []);
}

function renderCompareTable(rows) {
  const headers = ['スコア', '物件名', 'プラットフォーム', 'エリア', '月額', '面積', '間取り', '階', '徒歩', '築年数', 'ペット', 'エリア平均', '偏差', 'ステータス', '更新', '原平台'];
  document.querySelector('#compare-table thead tr').innerHTML = headers.map(h => `<th>${h}</th>`).join('');
  document.querySelector('#compare-table tbody').innerHTML = rows.map(l => {
    const dev = l.region_avg_rent && l.total_monthly_cost
      ? `<span style="color:${l.total_monthly_cost > l.region_avg_rent ? 'var(--bad)' : 'var(--good)'};font-weight:600;">${Math.round((l.total_monthly_cost - l.region_avg_rent) / l.region_avg_rent * 100)}%</span>`
      : '-';
    return `<tr>
      <td><span class="badge score">${l.total_score || '-'}</span></td>
      <td style="font-weight:600;color:var(--text-primary);">${l.title || ''}</td>
      <td><span class="badge platform">${l.platform || ''}</span></td>
      <td>${l.ward || '-'}</td>
      <td>${(l.total_monthly_cost || 0).toLocaleString()}円</td>
      <td>${l.area_m2 || '?'}㎡</td>
      <td>${l.layout || '-'}</td>
      <td>${l.floor || '?'}階</td>
      <td>${l.walk_minutes || '?'}分</td>
      <td>築${l.building_age || '?'}年</td>
      <td>${l.pet_allowed ? '<span class="tag good">可</span>' : '-'}</td>
      <td>${l.region_avg_rent ? l.region_avg_rent.toLocaleString() + '円' : '-'}</td>
      <td>${dev}</td>
      <td>${l.fav_status ? `<span class="tag accent">${l.fav_status}</span>` : '-'}</td>
      <td><button class="btn btn-ghost btn-sm" onclick="refreshListing(${l.id})">更新</button></td>
      <td><a href="${l.detail_url}" target="_blank" style="color:var(--accent);font-weight:600;">→</a></td>
    </tr>`;
  }).join('');
}

function renderStatusProgress(progress) {
  const el = document.getElementById('status-progress');
  const total = progress.reduce((s, p) => s + p.value, 0);
  if (!total) {
    el.innerHTML = '<div class="empty-state">まだ物件がインポートされていません。</div>';
    return;
  }
  const colors = ['var(--accent)', 'var(--good)', 'var(--warn)', 'var(--bad)'];
  el.innerHTML = `<div style="display:flex;gap:16px;flex-wrap:wrap;">${progress.map((p, i) =>
    `<div style="flex:1;min-width:120px;">
      <div style="font-size:13px;font-weight:600;margin-bottom:4px;">${p.name || '未設定'} <span style="color:var(--text-muted);">(${p.value})</span></div>
      <div style="height:8px;background:var(--bg-alt);border-radius:4px;overflow:hidden;">
        <div style="width:${p.value / total * 100}%;height:100%;background:${colors[i % colors.length]};border-radius:4px;"></div>
      </div>
    </div>`).join('')}</div>`;
}

function renderPriceHistory(history) {
  const el = document.getElementById('chart-price-history');
  if (!history || !history.length) {
    el.className = 'chart-empty';
    el.innerHTML = '価格履歴は複数回取得後に表示されます';
    return;
  }
  // 按 listing 分组
  const groups = {};
  history.forEach(h => { if (!groups[h.id]) groups[h.id] = { name: h.title, dates: [], costs: [] }; groups[h.id].dates.push(h.checked_at); groups[h.id].costs.push(h.total_monthly_cost); });
  const series = Object.values(groups).map((g, i) => ({
    name: g.name[:20], type: 'line', smooth: true,
    data: g.costs, itemStyle: { color: CHART.palette[i % CHART.palette.length] },
  }));
  const dates = Object.values(groups)[0]?.dates || [];
  const ch = echarts.init(el);
  ch.setOption({
    ...BASE_OPTION,
    legend: { bottom: 0, textStyle: { fontFamily: CHART_FONT, color: CHART.text, fontSize: 11 } },
    xAxis: { type: 'category', data: dates, axisLabel: { color: CHART.textMuted } },
    yAxis: { type: 'value', name: '月額(円)', axisLabel: { color: CHART.textMuted } },
    series,
  });
}

async function refreshListing(id) {
  if (!confirm('価格を再取得しますか?')) return;
  const res = await fetch(`/api/listings/${id}/refresh`, { method: 'POST' });
  const d = await res.json();
  if (d.error) {
    alert(d.error);
  } else {
    alert(d.message);
    load();  // 重新加载
  }
}

load();