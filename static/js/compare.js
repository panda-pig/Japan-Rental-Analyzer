const CHART_FONT = "'Noto Sans JP', sans-serif";
const PALETTE = ['#2563EB', '#059669', '#D97706', '#8B5CF6'];
const RADAR_DIMS = [
  { name: '予算', max: 20 }, { name: '面積', max: 15 }, { name: '通勤', max: 15 },
  { name: '階数', max: 10 }, { name: 'ペット', max: 15 }, { name: '駅距離', max: 10 },
  { name: '築年数', max: 10 }, { name: '初期費用', max: 5 },
];

function drawCompareRadar(data) {
  const card = document.getElementById('radar-card');
  const el = document.getElementById('compare-radar');
  const scored = data.filter(l => l.total_score != null);
  if (!el || scored.length < 2) { if (card) card.style.display = 'none'; return; }
  card.style.display = '';
  echarts.init(el).setOption({
    textStyle: { fontFamily: CHART_FONT, color: '#5A6B7E', fontSize: 12 },
    tooltip: {
      backgroundColor: '#FFFFFF', borderColor: '#E4E8EC', borderWidth: 1,
      textStyle: { fontFamily: CHART_FONT, color: '#1A2332', fontSize: 12 },
      extraCssText: 'box-shadow: 0 2px 8px rgba(16,24,40,0.08); border-radius: 8px;',
    },
    legend: { bottom: 0, data: scored.map(l => l.title), textStyle: { color: '#5A6B7E', fontFamily: CHART_FONT, fontSize: 12 } },
    radar: {
      indicator: RADAR_DIMS, shape: 'polygon', radius: '68%', center: ['50%', '48%'],
      axisName: { color: '#5A6B7E', fontFamily: CHART_FONT, fontSize: 12 },
      splitArea: { areaStyle: { color: ['rgba(37,99,235,0.02)', 'rgba(37,99,235,0.05)'] } },
    },
    series: [{
      type: 'radar',
      data: scored.map((l, i) => ({
        name: l.title,
        value: [l.budget_score || 0, l.area_score || 0, l.commute_score || 0, l.floor_score || 0,
                l.pet_score || 0, l.station_score || 0, l.age_score || 0, l.initial_cost_score || 0],
        itemStyle: { color: PALETTE[i % PALETTE.length] },
        lineStyle: { color: PALETTE[i % PALETTE.length], width: 2 },
        areaStyle: { color: PALETTE[i % PALETTE.length], opacity: 0.08 },
      })),
    }],
  });
}

async function load() {
  const ids = JSON.parse(localStorage.getItem("compareIds") || "[]");
  const el = document.getElementById("compare-table");
  if (ids.length < 2) {
    document.getElementById('radar-card').style.display = 'none';
    el.innerHTML = '<div class="empty-state">比較には2件以上選択してください。<br>物件分析ページの物件プールでチェックして「選択して比較」を押してください。</div>';
    return;
  }
  const res = await fetch("/api/compare?ids=" + ids.join(","));
  const data = await res.json();

  drawCompareRadar(data);

  const rows = [
    ["スコア", "total_score"], ["月額", "total_monthly_cost"], ["家賃", "rent"],
    ["管理費", "management_fee"], ["初期費用", "initial_cost_estimate"],
    ["面積", "area_m2"], ["㎡単価", "price_per_m2"], ["間取り", "layout"],
    ["階", "floor"], ["最寄駅", "nearest_station"], ["徒歩", "walk_minutes"],
    ["築年数", "building_age"], ["ペット", "pet_allowed"], ["敷金", "deposit"],
    ["礼金", "key_money"], ["プラットフォーム", "platform"], ["通勤(分)", "commute_minutes"],
  ];
  let html = '<table style="width:100%;"><thead><tr><th>項目</th>' + data.map(l => `<th>${l.title}</th>`).join("") + '</tr></thead><tbody>';
  for (const [label, key] of rows) {
    html += `<tr><td style="font-weight:600;color:var(--text-primary);">${label}</td>` + data.map(l => {
      let v = l[key];
      if (["total_monthly_cost", "rent", "management_fee", "initial_cost_estimate", "deposit", "key_money"].includes(key))
        v = (v || 0).toLocaleString() + '円';
      if (key === "total_score" && v != null) v = `<span class="badge score">${v}</span>`;
      if (key === "pet_allowed") v = v ? '<span class="tag good">可</span>' : '<span class="tag muted">不可</span>';
      if (key === "commute_minutes" && !l.commute_resolved) v = '<span class="tag muted">未取得</span>';
      if (key === "platform" && v) v = `<span class="badge platform">${v}</span>`;
      return `<td>${v ?? '-'}</td>`;
    }).join("") + "</tr>";
  }
  html += `<tr><td style="font-weight:600;color:var(--text-primary);">原平台</td>` + data.map(l => `<td><a href="${l.detail_url}" target="_blank" style="color:var(--accent);font-weight:600;text-decoration:none;">詳細を見る</a></td>`).join("") + "</tr>";
  html += '</tbody></table>';
  el.innerHTML = html;
}
load();
