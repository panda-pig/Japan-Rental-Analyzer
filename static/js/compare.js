// スクレイプ由来の文字列は innerHTML に直接入れない
const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ESC[c]);
function safeUrl(u) {
  try {
    const p = new URL(u, location.origin);
    return (p.protocol === 'http:' || p.protocol === 'https:') ? p.href : '';
  } catch (e) { return ''; }
}

const CHART_FONT = "'Noto Sans JP', sans-serif";
const PALETTE = ['#56696E', '#5C7A5B', '#A97A2E', '#8C86A0'];
const RADAR_DIMS = [
  { name: '予算', max: 20 }, { name: '面積', max: 15 }, { name: '通勤', max: 15 },
  { name: '階数', max: 10 }, { name: 'ペット', max: 15 }, { name: '駅距離', max: 10 },
  { name: '築年数', max: 10 }, { name: '初期費用', max: 5 },
];

let radarChart = null;
function drawCompareRadar(data) {
  const card = document.getElementById('radar-card');
  const el = document.getElementById('compare-radar');
  const scored = data.filter(l => l.total_score != null);
  if (!el || scored.length < 2) { if (card) card.style.display = 'none'; return; }
  card.style.display = '';
  // canvas はスクリーンリーダーには空 → role=img + 各物件のスコアを読み上げ可能にする
  el.setAttribute('role', 'img');
  el.setAttribute('aria-label', `${scored.length}件の物件を8次元スコアで比較するレーダーチャート。` +
    scored.map(l => `${l.title}は総合${l.total_score}点`).join('、') +
    '。項目ごとの数値は下の比較表を参照してください。');
  if (radarChart) radarChart.dispose();
  radarChart = echarts.init(el);
  radarChart.setOption({
    // OS の「視差効果を減らす」設定時は登場アニメーションを止める
    animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    textStyle: { fontFamily: CHART_FONT, color: '#6E6C63', fontSize: 12 },
    tooltip: {
      backgroundColor: '#FFFFFF', borderColor: '#E7E4DB', borderWidth: 1,
      textStyle: { fontFamily: CHART_FONT, color: '#2B2A26', fontSize: 12 },
      extraCssText: 'box-shadow: 0 3px 10px rgba(35,45,95,0.10); border-radius: 8px;',
    },
    legend: { bottom: 0, data: scored.map(l => l.title), textStyle: { color: '#6E6C63', fontFamily: CHART_FONT, fontSize: 12 } },
    radar: {
      indicator: RADAR_DIMS, shape: 'polygon', radius: '68%', center: ['50%', '48%'],
      axisName: { color: '#6E6C63', fontFamily: CHART_FONT, fontSize: 12 },
      splitArea: { areaStyle: { color: ['rgba(86,105,110,0.02)', 'rgba(86,105,110,0.05)'] } },
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
  let html = '<table style="width:100%;"><thead><tr><th>項目</th>' + data.map(l => `<th>${esc(l.title)}</th>`).join("") + '</tr></thead><tbody>';
  for (const [label, key] of rows) {
    html += `<tr><td style="font-weight:600;color:var(--text-primary);">${label}</td>` + data.map(l => {
      const v = l[key];
      // cell は完成した HTML。素の値(間取り・駅名・プラットフォーム等)は必ず esc() を通す。
      let cell;
      if (["total_monthly_cost", "rent", "management_fee", "initial_cost_estimate", "deposit", "key_money"].includes(key))
        cell = esc((v || 0).toLocaleString() + '円');
      else if (key === "total_score" && v != null)
        cell = `<span class="badge score${v >= 75 ? '' : v >= 60 ? ' mid' : ' low'}">${esc(v)}</span>`;
      else if (key === "pet_allowed")
        cell = v ? '<span class="tag good">可</span>' : '<span class="tag muted">不可</span>';
      else if (key === "commute_minutes" && !l.commute_resolved)
        cell = '<span class="tag muted">未取得</span>';
      else if (key === "platform" && v)
        cell = `<span class="badge platform">${esc(v)}</span>`;
      else
        cell = esc(v ?? '-');
      return `<td>${cell}</td>`;
    }).join("") + "</tr>";
  }
  html += `<tr><td style="font-weight:600;color:var(--text-primary);">原平台</td>` + data.map(l => `<td>${safeUrl(l.detail_url) ? `<a href="${esc(safeUrl(l.detail_url))}" target="_blank" rel="noopener" style="color:var(--accent);font-weight:600;text-decoration:none;">詳細を見る</a>` : '-'}</td>`).join("") + "</tr>";
  html += '</tbody></table>';
  el.innerHTML = '<div style="overflow-x:auto;">' + html + '</div>';
}

let _rz;
window.addEventListener('resize', () => {
  clearTimeout(_rz);
  _rz = setTimeout(() => { if (radarChart) radarChart.resize(); }, 250);
});
load();
