// ===== 物件分析页：URL解析 + 单套报告 + 房源池(累积/点选/多选对比/收藏) =====

const CHART_FONT = "'Noto Sans JP', sans-serif";
const COLORS = { primary: '#2563EB', good: '#059669', warn: '#D97706', bad: '#DC2626', text: '#5A6B7E', muted: '#8B9AAA', border: '#E4E8EC',
  palette: ['#2563EB', '#059669', '#D97706', '#8B5CF6', '#EC4899', '#14B8A6', '#6366F1', '#F43F5E'] };
const BASE_OPT = {
  textStyle: { fontFamily: CHART_FONT, color: COLORS.text, fontSize: 12 },
  tooltip: { backgroundColor: '#FFFFFF', borderColor: COLORS.border, borderWidth: 1,
    textStyle: { fontFamily: CHART_FONT, color: '#1A2332', fontSize: 12 },
    extraCssText: 'box-shadow: 0 2px 8px rgba(16,24,40,0.08); border-radius: 8px;' },
};

const state = { data: null, selectedId: null, sort: 'score_desc' };
const regionCache = {};

// ---------- URL导入 ----------
async function importAndAnalyze() {
  const url = document.getElementById('import-url').value.trim();
  const el = document.getElementById('import-result');
  const btn = document.getElementById('import-btn');
  if (!url) { el.innerHTML = '<span style="color:var(--bad);">URLを入力してください</span>'; return; }
  if (btn && btn.disabled) return;  // 防止重复提交
  if (btn) { btn.disabled = true; btn.textContent = '解析中…'; }
  el.innerHTML = '<span style="color:var(--text-muted);">解析中… ページを取得しています(数秒かかります)</span>';
  try {
    const res = await fetch('/api/import/detail', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) {
      const errText = await res.text();
      try {
        const errJson = JSON.parse(errText);
        el.innerHTML = '<span style="color:var(--bad);">' + (errJson.error || '解析エラー') + '</span>';
      } catch (e2) {
        el.innerHTML = '<span style="color:var(--bad);">解析に失敗しました(HTTP ' + res.status + ')</span>';
      }
      return;
    }
    const d = await res.json();
    if (d.error) {
      el.innerHTML = '<span style="color:var(--bad);">' + d.error + '</span>';
    } else {
      el.innerHTML = '<span style="color:var(--good);font-weight:600;">' + (d.message || '解析しました') + '</span>';
      document.getElementById('import-url').value = '';
      if (d.id) state.selectedId = d.id;   // 新解析的这套优先显示
      await loadAnalysis();
    }
  } catch (e) {
    el.innerHTML = '<span style="color:var(--bad);">通信エラー: ' + e.message + '</span>';
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '解析'; }
  }
}

// ---------- 轻量 toast(刷新/删除反馈) ----------
function toast(msg, ok = true) {
  let el = document.getElementById('ml-toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'ml-toast';
    el.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:200;padding:10px 18px;border-radius:8px;font-size:13px;font-weight:600;box-shadow:0 4px 16px rgba(16,24,40,0.16);color:#fff;transition:opacity .3s;';
    document.body.appendChild(el);
  }
  el.style.background = ok ? 'var(--good)' : 'var(--bad)';
  el.textContent = msg;
  el.style.opacity = '1';
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.opacity = '0'; }, 3200);
}

// ---------- 数据加载 ----------
async function loadAnalysis() {
  const container = document.getElementById('analysis-container');
  if (container && !state.data) {
    container.innerHTML = '<div class="empty-state">読み込み中…</div>';
  }
  const res = await fetch('/api/my-list');
  state.data = await res.json();
  const pool = state.data.compare_rows || [];
  if (!pool.some(l => l.id === state.selectedId)) {
    state.selectedId = pool.length ? pool[0].id : null;
  }
  await render();
}

async function getRegion(ward) {
  if (!ward) return null;
  if (ward in regionCache) return regionCache[ward];
  try {
    const r = await fetch('/api/regions/' + encodeURIComponent(ward));
    regionCache[ward] = r.ok ? await r.json() : null;
  } catch (e) { regionCache[ward] = null; }
  return regionCache[ward];
}

function deviationOf(l) {
  if (l.total_monthly_cost && l.region_avg_rent)
    return (l.total_monthly_cost - l.region_avg_rent) / l.region_avg_rent;
  return null;
}

function sortPool(rows) {
  const dev = l => { const d = deviationOf(l); return d == null ? Infinity : d; };
  const cmp = {
    score_desc: (a, b) => (b.total_score || 0) - (a.total_score || 0),
    price_asc: (a, b) => (a.total_monthly_cost || 1e12) - (b.total_monthly_cost || 1e12),
    area_desc: (a, b) => (b.area_m2 || 0) - (a.area_m2 || 0),
    ppm_asc: (a, b) => (a.price_per_m2 || 1e12) - (b.price_per_m2 || 1e12),
    dev_asc: (a, b) => dev(a) - dev(b),
  }[state.sort] || (() => 0);
  return [...rows].sort(cmp);
}

// ---------- 主渲染 ----------
async function render() {
  const container = document.getElementById('analysis-container');
  const d = state.data;
  if (!d || !d.total) { await renderEmpty(container); return; }

  const pool = d.compare_rows || [];
  const selected = pool.find(l => l.id === state.selectedId) || pool[0];
  state.selectedId = selected ? selected.id : null;
  const region = selected ? await getRegion(selected.ward) : null;

  container.innerHTML = reportHtml(selected, region) +
    wordCloudHtml(d) +
    (pool.length ? poolHtml(sortPool(pool), d) : '');

  drawReportCharts(selected, region, d.prefs);
  drawWordCloud(d.feature_cloud);
  drawLayoutPie(d.layout_dist);
  if (pool.length >= 2) drawScatter(d.scatter_data);
  wirePoolHandlers();
}

// ---------- 特徴クラウド(词云) ----------
function wordCloudHtml(d) {
  if (!d.feature_cloud || !d.feature_cloud.length) return '';
  return `<div class="card">
    <h2>特徴クラウド <span style="font-size:12px;font-weight:400;color:var(--text-muted);">物件プールの設備・特徴の頻度</span></h2>
    <div id="chart-wordcloud" class="chart"></div>
  </div>`;
}

// 房子轮廓的极坐标半径函数(供 wordcloud2 的 shape 使用)
// 多边形以中心为原点(x右、y下),屋顶朝上(负 y);对每个角度射线求与多边形的最远交点
const HOUSE_POLY = [
  [0.60, 0.58],   // 右下角
  [0.60, -0.18],  // 右墙顶
  [0.72, -0.18],  // 右屋檐
  [0.00, -0.80],  // 屋顶尖(上)
  [-0.72, -0.18], // 左屋檐
  [-0.60, -0.18], // 左墙顶
  [-0.60, 0.58],  // 左下角
];
const HOUSE_MAXR = 0.83; // 归一化基准(最远顶点距离)
function houseShape(theta) {
  const dx = Math.cos(theta), dy = Math.sin(theta);
  let best = 0;
  for (let i = 0; i < HOUSE_POLY.length; i++) {
    const a = HOUSE_POLY[i], b = HOUSE_POLY[(i + 1) % HOUSE_POLY.length];
    const ex = b[0] - a[0], ey = b[1] - a[1];
    const det = -dx * ey + ex * dy;
    if (Math.abs(det) < 1e-9) continue;
    const t = (-a[0] * ey + ex * a[1]) / det;   // 射线距离
    const s = (dx * a[1] - dy * a[0]) / det;    // 线段参数
    if (t > 0 && s >= 0 && s <= 1 && t > best) best = t;
  }
  return Math.min(best / HOUSE_MAXR, 1);
}

function drawWordCloud(cloud) {
  const el = document.getElementById('chart-wordcloud');
  if (!el || !cloud || !cloud.length) return;
  const vals = cloud.map(c => c.value);
  const min = Math.min(...vals), max = Math.max(...vals);

  // 优先用 wordcloud2.js 打包算法(聚合成"房子"形状),失败则降级 HTML 标签云
  if (typeof WordCloud === 'function') {
    el.innerHTML = '';
    const side = Math.min(el.clientWidth || 520, 560);
    const h = Math.round(side * 0.82);
    const canvas = document.createElement('canvas');
    canvas.width = side; canvas.height = h;
    canvas.style.width = side + 'px'; canvas.style.height = h + 'px';
    canvas.style.display = 'block'; canvas.style.margin = '0 auto';
    el.style.height = 'auto';
    el.appendChild(canvas);
    let i = 0;
    WordCloud(canvas, {
      list: cloud.map(c => [c.name, c.value]),
      gridSize: 4,
      weightFactor: v => max === min ? 34 : 14 + (v - min) / (max - min) * 46, // 14~60px
      fontFamily: 'Noto Sans JP, sans-serif',
      fontWeight: '700',
      color: () => COLORS.palette[(i++) % COLORS.palette.length],
      backgroundColor: 'transparent',
      rotateRatio: 0.25, rotationSteps: 2, minRotation: -Math.PI / 2, maxRotation: 0,
      shape: houseShape, ellipticity: 1, drawOutOfBound: false, shrinkToFit: true,
    });
    return;
  }

  // 降级:HTML 标签云
  const size = v => max === min ? 26 : Math.round(16 + (v - min) / (max - min) * 32);
  const chips = cloud.map((c, i2) =>
    `<span title="${c.name}: ${c.value}件" style="font-family:${CHART_FONT};font-weight:700;font-size:${size(c.value)}px;color:${COLORS.palette[i2 % COLORS.palette.length]};line-height:1.1;white-space:nowrap;">${c.name}</span>`).join('');
  el.style.height = 'auto';
  el.innerHTML = `<div style="display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:10px 20px;padding:24px 8px;min-height:180px;">${chips}</div>`;
}

// ---------- 空状态：区域基准看板 ----------
async function renderEmpty(container) {
  let d = null;
  try { d = await (await fetch('/api/dashboard')).json(); } catch (e) {}
  if (!d) { container.innerHTML = '<div class="empty-state">物件をインポートすると分析が表示されます。</div>'; return; }

  const regionRows = (d.regions || []).slice(0, 30).map(r => `
    <tr>
      <td style="font-weight:600;color:var(--text-primary);">${r.ward || r.city || r.prefecture || '-'}</td>
      <td>${(r.avg_rent || 0).toLocaleString()}円</td>
      <td>${r.avg_area || '-'}㎡</td>
      <td>${r.safety_level || '-'}</td>
      <td>${r.convenience_level || '-'}</td>
      <td>${r.environment_level || '-'}</td>
    </tr>`).join('');

  container.innerHTML = `
    <div class="card" style="margin-top:20px;background:var(--accent-bg,#EFF4FF);border:1px solid var(--accent-border,#C7D7FE);">
      <p style="font-size:13px;color:var(--text-secondary);margin:0;">
        まだ物件がありません。気になる物件の詳細ページURLを上に貼り付けて解析すると、
        エリア平均との比較レポートが表示され、この物件があなたの<strong>物件プール</strong>に追加されます。<br>
        下は参考用の<strong>エリア基準データ</strong>です。
      </p>
    </div>
    <div class="card"><h2>東京23区 平均相場</h2><div id="chart-tokyo" class="chart"></div></div>
    <div class="card"><h2>横浜市 各区 平均相場</h2><div id="chart-yokohama" class="chart"></div></div>
    <div class="card" style="padding:0;overflow:hidden;">
      <h2 style="padding:24px 24px 0;">エリア基準データ (${(d.regions || []).length}件)</h2>
      <div style="overflow-x:auto;">
        <table>
          <thead><tr><th>エリア</th><th>平均相場</th><th>平均面積</th><th>治安</th><th>利便性</th><th>環境</th></tr></thead>
          <tbody>${regionRows}</tbody>
        </table>
      </div>
    </div>`;

  drawRegionBar('chart-tokyo', d.tokyo_region_rent);
  drawRegionBar('chart-yokohama', d.yokohama_region_rent);
}

function drawRegionBar(elId, rows) {
  const el = document.getElementById(elId);
  if (!el || !rows || !rows.length) { if (el) el.innerHTML = '<div class="empty-state">データなし</div>'; return; }
  echarts.init(el).setOption({
    ...BASE_OPT,
    grid: { left: 90, right: 30, top: 10, bottom: 30 },
    xAxis: { type: 'value', axisLabel: { color: COLORS.muted, formatter: v => (v / 10000) + '万' } },
    yAxis: { type: 'category', data: rows.map(r => r.name), inverse: true, axisLabel: { color: COLORS.text, fontSize: 11 } },
    series: [{
      type: 'bar', data: rows.map(r => r.value), itemStyle: { color: COLORS.primary, borderRadius: [0, 4, 4, 0] },
      barMaxWidth: 16, label: { show: true, position: 'right', formatter: p => (p.value / 10000).toFixed(1) + '万', fontSize: 11, color: COLORS.text },
    }],
  });
}

// ---------- 单套报告 ----------
function scoreColor(s) { return s >= 75 ? COLORS.good : s >= 60 ? COLORS.primary : s >= 45 ? COLORS.warn : COLORS.bad; }

const AMENITIES = [
  ['bath_toilet_separate', 'バストイレ別'], ['auto_lock', 'オートロック'],
  ['delivery_box', '宅配ボックス'], ['south_facing', '南向き'],
  ['aircon', 'エアコン'], ['pet_allowed', 'ペット可'], ['two_person_allowed', '2人入居可'],
];

function reportHtml(l, region) {
  if (!l) return '';
  const yen = v => (v || 0).toLocaleString() + '円';
  const dev = deviationOf(l);

  // 月額指标卡:带偏差
  let rentLabel = '<div class="label">月額</div>';
  let rentCls = '';
  if (dev != null) {
    const diff = l.total_monthly_cost - l.region_avg_rent;
    rentCls = dev < 0 ? 'good' : '';
    const col = diff > 0 ? 'var(--bad)' : 'var(--good)';
    rentLabel = `<div class="label" style="color:${col};font-weight:600;">エリア平均比 ${diff > 0 ? '+' : ''}${Math.round(dev * 100)}% (${diff > 0 ? '+' : ''}${(diff / 10000).toFixed(1)}万)</div>`;
  }
  const areaLabel = l.region_avg_area ? `エリア平均 ${l.region_avg_area}㎡` : '専有面積';

  const metrics = `
    <div class="metric-grid" style="margin:16px 0 4px;">
      <div class="metric"><div class="num">${l.total_score ?? '-'}</div><div class="label">総合スコア /100</div></div>
      <div class="metric ${rentCls}"><div class="num">${(l.total_monthly_cost || 0).toLocaleString()}<span style="font-size:14px;">円</span></div>${rentLabel}</div>
      <div class="metric"><div class="num">${l.area_m2 || '?'}<span style="font-size:14px;">㎡</span></div><div class="label">${areaLabel}</div></div>
      <div class="metric"><div class="num">${l.price_per_m2 ? Math.round(l.price_per_m2).toLocaleString() : '-'}<span style="font-size:14px;">円</span></div><div class="label">㎡単価</div></div>
      <div class="metric"><div class="num">${l.initial_cost_estimate ? (l.initial_cost_estimate / 10000).toFixed(1) : '-'}<span style="font-size:14px;">万円</span></div><div class="label">初期費用(概算)</div></div>
    </div>`;

  const amenityChips = AMENITIES.map(([k, label]) =>
    l[k] ? `<span class="tag good">✓ ${label}</span>` : `<span class="tag muted">${label}</span>`).join('');

  const isFav = !!l.fav_status;
  const favBtn = `<button class="btn ${isFav ? 'btn-good' : 'btn-outline'}" id="report-fav" data-id="${l.id}" data-favid="${l.fav_status_id || ''}">
      ${isFav ? '★ ' + l.fav_status : '☆ 気になる'}</button>`;

  // 详细数据(2列),已在指标卡展示的不重复
  const detailRows = [
    ['家賃', yen(l.rent)], ['管理費', yen(l.management_fee)],
    ['間取り', l.layout || '-'], ['階数', l.floor ? `${l.floor}階${l.total_floors ? ' / ' + l.total_floors + '階建' : ''}` : '-'],
    ['築年数', `築${l.building_age ?? '?'}年`], ['構造', l.structure || '-'],
    ['最寄駅', `${l.nearest_station || '-'} 徒歩${l.walk_minutes ?? '?'}分`],
    ['敷金 / 礼金', `${yen(l.deposit)} / ${yen(l.key_money)}`],
  ];

  let html = `
    <div class="card" style="margin-top:20px;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;">
        <div>
          <h2 style="margin-bottom:4px;">${l.title || '物件レポート'} <span class="badge platform">${l.platform || '-'}</span></h2>
          <p style="font-size:13px;color:var(--text-secondary);margin:0;">
            ${l.ward || '地域不明'}${l.region_avg_rent ? ` ・ エリア平均と比較` : ' ・ エリア基準データなし'}
          </p>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          ${favBtn}
          ${l.detail_url ? `<a class="btn btn-outline" href="${l.detail_url}" target="_blank" rel="noopener">原平台で見る</a>` : ''}
          ${l.detail_url ? `<button class="btn btn-outline" id="report-refresh" data-id="${l.id}">価格を再取得</button>` : ''}
          <button class="btn btn-ghost btn-sm" id="report-delete" data-id="${l.id}">削除</button>
        </div>
      </div>
      ${metrics}
      <div style="margin-top:16px;">
        <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:8px;">設備・特徴</div>
        ${amenityChips}
      </div>
    </div>`;

  // エリア評価(0~100 展示分,独立卡片,不计入房源评分)
  if (region) {
    const sc = (score, label, level) => `<div class="metric"><div class="num" style="font-size:22px;color:${scoreColor(score ?? 50)};">${score ?? '-'}</div><div class="label">${label}${level ? ` (${level})` : ''}</div></div>`;
    const tradeMetric = region.trade_price_per_m2
      ? `<div class="metric"><div class="num" style="font-size:22px;">${(region.trade_price_per_m2 / 10000).toFixed(0)}<span style="font-size:13px;">万/㎡</span></div><div class="label">取引価格 (中古M・${region.trade_count}件)</div></div>`
      : '';
    const FLOOD_LABELS = { 0: '想定なし', 1: '~0.5m', 2: '0.5~3m', 3: '3~5m', 4: '5~10m', 5: '10~20m', 6: '20m~' };
    const hzColor = region.hazard_level === '高' ? COLORS.bad : region.hazard_level === '中' ? COLORS.warn : COLORS.good;
    const hazardMetric = region.hazard_level
      ? `<div class="metric"><div class="num" style="font-size:22px;color:${hzColor};">${region.hazard_level}</div><div class="label">災害 (洪水${FLOOD_LABELS[region.flood_rank || 0]}・土砂${region.sediment_count || 0}件)</div></div>`
      : '';
    html += `
    <div class="card">
      <h2>エリア評価 <span class="tag muted">エリア参考値・スコア対象外</span></h2>
      <div class="metric-grid" style="margin-top:12px;">
        ${sc(region.overall_score, '総合評価')}
        ${sc(region.safety_score, '治安', region.safety_level)}
        ${sc(region.convenience_score, '便利', region.convenience_level)}
        ${sc(region.environment_score, '住環境', region.environment_level)}
        ${tradeMetric}
        ${hazardMetric}
      </div>
      ${(region.trade_price_per_m2 || region.hazard_level) ? '<p style="font-size:11px;color:var(--text-muted);margin:8px 0 0;">取引価格・災害: 国土交通省 不動産情報ライブラリ (災害は区役所周辺の参考値)</p>' : ''}
    </div>`;
  }

  // 最寄駅の住民評価 (まちむすび, 表示専用)
  if (l.st_avg != null) {
    const starColor = v => v >= 4 ? COLORS.good : v >= 3.5 ? COLORS.primary : v >= 3 ? COLORS.warn : COLORS.bad;
    const stM = (v, label) => v == null ? '' :
      `<div class="metric"><div class="num" style="font-size:22px;color:${starColor(v)};">${v.toFixed(1)}</div><div class="label">${label} /5</div></div>`;
    html += `
    <div class="card">
      <h2>最寄駅の住民評価 <span class="tag muted">${l.nearest_station || ''}駅・スコア対象外</span></h2>
      <div class="metric-grid" style="margin-top:12px;">
        ${stM(l.st_avg, '総合')}
        ${stM(l.st_transport, '交通の利便性')}
        ${stM(l.st_safety, '治安の良さ')}
        ${stM(l.st_shopping, '買い物')}
        ${stM(l.st_childcare, '子育て')}
        ${stM(l.st_nature, '自然の多さ')}
      </div>
      <p style="font-size:11px;color:var(--text-muted);margin:8px 0 0;">出典: LIFULL HOME'S「まちむすび」住民アンケート集計値 (5点満点)</p>
    </div>`;
  }

  if (l.total_score != null) {
    html += `<div class="card"><h2>スコアレーダー <span style="font-size:12px;font-weight:400;color:var(--text-muted);">8次元評価</span></h2><div id="chart-radar-single" class="chart"></div></div>`;
    html += `<div class="card"><h2>初期費用の内訳 <span style="font-size:12px;font-weight:400;color:var(--text-muted);">概算</span></h2><div id="chart-initcost" class="chart"></div></div>`;
    if (l.region_avg_rent && l.total_monthly_cost)
      html += `<div class="card"><h2>エリア平均との比較</h2><div id="chart-compare-bar" class="chart"></div></div>`;
    // 价格推移(有 2+ 次取得历史时才显示)
    const hist = (state.data.price_history || []).filter(h => h.id === l.id);
    if (hist.length >= 2)
      html += `<div class="card"><h2>価格推移 <span style="font-size:12px;font-weight:400;color:var(--text-muted);">再取得の履歴</span></h2><div id="chart-price-history" class="chart"></div></div>`;
    html += `<div class="card"><h2>推薦理由</h2>
      <div style="background:var(--good-bg);border:1px solid var(--good-border);border-radius:var(--radius-sm);padding:12px 16px;font-size:13px;color:var(--good);">
        ${l.score_reason || 'スコア理由がありません'}
      </div></div>`;
  }

  // 详细数据表(次要,放最后)
  html += `
    <div class="card">
      <h2>詳細データ</h2>
      <table style="width:100%;margin-top:8px;">
        <tbody>
          ${detailRows.map(r => `<tr><td style="font-weight:600;color:var(--text-primary);width:40%;">${r[0]}</td><td>${r[1]}</td></tr>`).join('')}
        </tbody>
      </table>
    </div>`;
  return html;
}

function drawReportCharts(l, region, prefs) {
  if (!l || l.total_score == null) return;
  const rEl = document.getElementById('chart-radar-single');
  if (rEl) {
    echarts.init(rEl).setOption({
      ...BASE_OPT,
      radar: {
        indicator: [
          { name: '予算', max: 20 }, { name: '面積', max: 15 }, { name: '通勤', max: 15 },
          { name: '階数', max: 10 }, { name: 'ペット', max: 15 }, { name: '駅距離', max: 10 },
          { name: '築年数', max: 10 }, { name: '初期費用', max: 5 },
        ],
        shape: 'polygon', radius: '65%',
        axisName: { color: COLORS.text, fontFamily: CHART_FONT, fontSize: 11 },
      },
      series: [{
        type: 'radar',
        data: [{
          value: [l.budget_score || 0, l.area_score || 0, l.commute_score || 0, l.floor_score || 0,
                  l.pet_score || 0, l.station_score || 0, l.age_score || 0, l.initial_cost_score || 0],
          name: l.title,
          itemStyle: { color: COLORS.primary }, areaStyle: { opacity: 0.15 },
        }],
      }],
    });
  }
  // 初期費用の内訳(甜甜圈)
  const iEl = document.getElementById('chart-initcost');
  if (iEl) {
    const p = prefs || { broker_fee_rate: 0.55, prepaid_rent_months: 1, misc_cost: 40000 };
    const rent = l.rent || 0;
    const parts = [
      { name: '敷金', value: l.deposit || 0 },
      { name: '礼金', value: l.key_money || 0 },
      { name: '仲介手数料', value: Math.round(rent * p.broker_fee_rate) },
      { name: '前家賃', value: Math.round(rent * p.prepaid_rent_months) },
      { name: '諸費用', value: p.misc_cost || 0 },
    ].filter(x => x.value > 0);
    const total = parts.reduce((s, x) => s + x.value, 0);
    echarts.init(iEl).setOption({
      ...BASE_OPT,
      tooltip: { ...BASE_OPT.tooltip, formatter: p2 => `${p2.name}<br>${p2.value.toLocaleString()}円 (${p2.percent}%)` },
      legend: { bottom: 0, textStyle: { color: COLORS.text, fontFamily: CHART_FONT, fontSize: 11 } },
      series: [{
        type: 'pie', radius: ['45%', '68%'], center: ['50%', '44%'], avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { show: true, position: 'center', formatter: () => `概算\n${(total / 10000).toFixed(1)}万円`, fontFamily: CHART_FONT, fontSize: 13, fontWeight: 600, color: COLORS.text },
        color: COLORS.palette,
        data: parts,
      }],
    });
  }
  const bEl = document.getElementById('chart-compare-bar');
  if (bEl && l.region_avg_rent && l.total_monthly_cost) {
    echarts.init(bEl).setOption({
      ...BASE_OPT,
      xAxis: { type: 'category', data: ['この物件', 'エリア平均'] },
      yAxis: { type: 'value', name: '月額(円)', axisLabel: { color: COLORS.muted } },
      series: [{
        type: 'bar', barMaxWidth: 80,
        data: [
          { value: l.total_monthly_cost, itemStyle: { color: COLORS.primary } },
          { value: l.region_avg_rent, itemStyle: { color: COLORS.warn } },
        ],
        label: { show: true, formatter: p => p.value.toLocaleString() + '円', fontFamily: CHART_FONT, fontSize: 12 },
      }],
    });
  }
  // 价格推移折线
  const hEl = document.getElementById('chart-price-history');
  if (hEl) {
    const hist = (state.data.price_history || []).filter(h => h.id === l.id)
      .sort((a, b) => (a.checked_at || '').localeCompare(b.checked_at || ''));
    echarts.init(hEl).setOption({
      ...BASE_OPT,
      grid: { left: 60, right: 24, top: 20, bottom: 40 },
      xAxis: { type: 'category', data: hist.map(h => (h.checked_at || '').slice(0, 10)), axisLabel: { color: COLORS.muted, fontSize: 10 } },
      yAxis: { type: 'value', name: '月額(円)', axisLabel: { color: COLORS.muted, formatter: v => (v / 10000) + '万' } },
      series: [{
        type: 'line', smooth: true, symbolSize: 7,
        data: hist.map(h => h.total_monthly_cost),
        itemStyle: { color: COLORS.primary }, lineStyle: { color: COLORS.primary, width: 2 },
        areaStyle: { color: 'rgba(37,99,235,0.08)' },
        label: { show: true, formatter: p => (p.value / 10000).toFixed(1) + '万', fontSize: 10, color: COLORS.text },
      }],
    });
  }
}

// ---------- 单套操作(再取得 / 削除) ----------
async function refreshListing(id) {
  const btn = document.getElementById('report-refresh');
  if (btn) { btn.disabled = true; btn.textContent = '取得中…'; }
  try {
    const res = await fetch('/api/listings/' + id + '/refresh', { method: 'POST' });
    const d = await res.json();
    if (!res.ok || d.error) { toast(d.error || '再取得に失敗しました', false); }
    else { toast(d.message || '更新しました', !d.price_changed ? true : true); await loadAnalysis(); }
  } catch (e) { toast('通信エラー: ' + e.message, false); }
  finally { const b = document.getElementById('report-refresh'); if (b) { b.disabled = false; b.textContent = '価格を再取得'; } }
}

async function deleteListing(id) {
  if (!confirm('この物件をプールから削除しますか?(元に戻せません)')) return;
  try {
    await fetch('/api/listings/' + id, { method: 'DELETE' });
    if (state.selectedId === id) state.selectedId = null;
    toast('削除しました');
    await loadAnalysis();
  } catch (e) { toast('削除に失敗しました', false); }
}

// ---------- 房源池列表 ----------
function poolHtml(pool, d) {
  const sortOptions = [
    ['score_desc', 'スコア高い順'], ['price_asc', '月額安い順'], ['area_desc', '面積広い順'],
    ['ppm_asc', '㎡単価安い順'], ['dev_asc', 'エリア偏差(お得)順'],
  ].map(([v, t]) => `<option value="${v}" ${state.sort === v ? 'selected' : ''}>${t}</option>`).join('');

  const rows = pool.map(l => {
    const dev = deviationOf(l);
    const devHtml = dev == null ? '-' :
      `<span style="color:${dev > 0 ? 'var(--bad)' : 'var(--good)'};font-weight:600;">${dev > 0 ? '+' : ''}${Math.round(dev * 100)}%</span>`;
    const sel = l.id === state.selectedId ? ' style="background:var(--accent-bg,#EFF4FF);"' : '';
    const favMark = l.fav_status ? `<span class="tag good" title="${l.fav_status}">★</span>` : '';
    return `<tr data-id="${l.id}" class="pool-row"${sel}>
      <td><input type="checkbox" class="pool-check" data-id="${l.id}"></td>
      <td><span class="badge score">${l.total_score ?? '-'}</span></td>
      <td style="font-weight:600;color:var(--text-primary);">${l.title || ''} ${favMark}</td>
      <td>${l.ward || '-'}</td>
      <td>${(l.total_monthly_cost || 0).toLocaleString()}円</td>
      <td>${l.area_m2 || '?'}㎡</td>
      <td>${devHtml}</td>
      <td><button class="link-btn pool-fav" data-id="${l.id}" data-favid="${l.fav_status_id || ''}">${l.fav_status ? '解除' : '気になる'}</button></td>
      <td>${l.detail_url ? `<a href="${l.detail_url}" target="_blank" rel="noopener" style="color:var(--accent);">→</a>` : ''}</td>
    </tr>`;
  }).join('');

  return `
    <div class="card" style="padding:0;overflow:hidden;">
      <div style="display:flex;justify-content:space-between;align-items:center;padding:24px 24px 12px;flex-wrap:wrap;gap:12px;">
        <h2 style="margin:0;">物件プール (${pool.length}件)</h2>
        <div style="display:flex;gap:8px;align-items:center;">
          <select id="pool-sort" class="select">${sortOptions}</select>
          <button class="btn btn-primary" id="pool-compare" disabled>選択して比較 (0)</button>
          <button class="btn btn-outline" id="pool-clear" title="物件プールを全て削除">プールをクリア</button>
        </div>
      </div>
      <p style="font-size:12px;color:var(--text-muted);padding:0 24px 8px;margin:0;">行をクリックで上のレポートを切替 / チェックで2〜4件を横断比較</p>
      <div style="overflow-x:auto;">
        <table id="pool-table">
          <thead><tr><th></th><th>スコア</th><th>物件名</th><th>エリア</th><th>月額</th><th>面積</th><th>偏差</th><th>お気に入り</th><th></th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
    ${d.layout_dist && d.layout_dist.length ? '<div class="card"><h2>間取り分布 <span style="font-size:12px;font-weight:400;color:var(--text-muted);">物件プール</span></h2><div id="chart-layout" class="chart" style="height:260px;"></div></div>' : ''}
    ${pool.length >= 2 ? '<div class="card"><h2>コスパ散布図 <span style="font-size:12px;font-weight:400;color:var(--text-muted);">面積 vs 月額</span></h2><div id="chart-scatter" class="chart"></div></div>' : ''}`;
}

function drawLayoutPie(dist) {
  const el = document.getElementById('chart-layout');
  if (!el || !dist || !dist.length) return;
  echarts.init(el).setOption({
    ...BASE_OPT,
    tooltip: { ...BASE_OPT.tooltip, formatter: p => `${p.name}: ${p.value}件 (${p.percent}%)` },
    legend: { orient: 'vertical', right: 10, top: 'center', textStyle: { color: COLORS.text, fontFamily: CHART_FONT, fontSize: 12 } },
    series: [{
      type: 'pie', radius: ['42%', '68%'], center: ['38%', '50%'], avoidLabelOverlap: true,
      itemStyle: { borderColor: '#fff', borderWidth: 2 },
      label: { show: false }, color: COLORS.palette,
      data: dist,
    }],
  });
}

function drawScatter(scatter) {
  const el = document.getElementById('chart-scatter');
  if (!el || !scatter || !scatter.length) return;
  const pts = scatter.filter(p => p.x && p.y);
  const avgLine = [];
  const withAvg = pts.filter(p => p.region_avg);
  if (withAvg.length) {
    const avg = withAvg.reduce((s, p) => s + p.region_avg, 0) / withAvg.length;
    avgLine.push({ yAxis: avg, label: { formatter: 'エリア平均 ' + Math.round(avg / 10000) + '万', color: COLORS.warn } });
  }
  echarts.init(el).setOption({
    ...BASE_OPT,
    tooltip: { ...BASE_OPT.tooltip, formatter: p => `${p.data.name}<br>${p.data.ward || ''}<br>面積 ${p.data.value[0]}㎡ / 月額 ${p.data.value[1].toLocaleString()}円` },
    grid: { left: 60, right: 30, top: 20, bottom: 40 },
    xAxis: { type: 'value', name: '面積(㎡)', axisLabel: { color: COLORS.muted } },
    yAxis: { type: 'value', name: '月額(円)', axisLabel: { color: COLORS.muted, formatter: v => (v / 10000) + '万' } },
    series: [{
      type: 'scatter', symbolSize: 14,
      itemStyle: { color: COLORS.primary, opacity: 0.75 },
      data: pts.map(p => ({ value: [p.x, p.y], name: p.name, ward: p.ward })),
      markLine: avgLine.length ? { silent: true, symbol: 'none', lineStyle: { color: COLORS.warn, type: 'dashed' }, data: avgLine } : undefined,
    }],
  });
}

// ---------- 交互 ----------
function updateCompareBtn() {
  const checked = document.querySelectorAll('.pool-check:checked');
  const btn = document.getElementById('pool-compare');
  if (!btn) return;
  btn.textContent = `選択して比較 (${checked.length})`;
  btn.disabled = checked.length < 2 || checked.length > 4;
}

async function toggleFav(id, favId) {
  if (favId) {
    await fetch('/api/status/' + favId, { method: 'DELETE' });
  } else {
    await fetch('/api/status', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ listing_id: id, status: '気になる', priority: 1 }),
    });
  }
  await loadAnalysis();
}

function wirePoolHandlers() {
  // 行点击切换报告(排除 checkbox / 按钮 / 链接)
  document.querySelectorAll('.pool-row').forEach(tr => {
    tr.addEventListener('click', e => {
      if (e.target.closest('input,button,a')) return;
      state.selectedId = parseInt(tr.dataset.id, 10);
      render();
    });
  });
  document.querySelectorAll('.pool-check').forEach(cb => cb.addEventListener('change', updateCompareBtn));
  document.querySelectorAll('.pool-fav').forEach(b =>
    b.addEventListener('click', e => { e.stopPropagation(); toggleFav(parseInt(b.dataset.id, 10), b.dataset.favid || null); }));
  const reportFav = document.getElementById('report-fav');
  if (reportFav) reportFav.addEventListener('click', () => toggleFav(parseInt(reportFav.dataset.id, 10), reportFav.dataset.favid || null));
  const reportRefresh = document.getElementById('report-refresh');
  if (reportRefresh) reportRefresh.addEventListener('click', () => refreshListing(parseInt(reportRefresh.dataset.id, 10)));
  const reportDelete = document.getElementById('report-delete');
  if (reportDelete) reportDelete.addEventListener('click', () => deleteListing(parseInt(reportDelete.dataset.id, 10)));

  const cmp = document.getElementById('pool-compare');
  if (cmp) cmp.addEventListener('click', () => {
    const ids = [...document.querySelectorAll('.pool-check:checked')].map(c => parseInt(c.dataset.id, 10));
    if (ids.length < 2) return;
    localStorage.setItem('compareIds', JSON.stringify(ids));
    location.href = '/compare';
  });
  const sortSel = document.getElementById('pool-sort');
  if (sortSel) sortSel.addEventListener('change', () => { state.sort = sortSel.value; render(); });

  const clearBtn = document.getElementById('pool-clear');
  if (clearBtn) clearBtn.addEventListener('click', async () => {
    const n = (state.data && state.data.total) || 0;
    if (!confirm(`物件プールの ${n} 件を全て削除します。よろしいですか?(元に戻せません)`)) return;
    await fetch('/api/pool/clear', { method: 'POST' });
    state.selectedId = null;
    await loadAnalysis();
  });
}

// ---------- 初始化 ----------
let _resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(() => { if (state.data && state.data.total) render(); }, 300);
});

document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('import-url');
  if (input) input.addEventListener('keydown', e => { if (e.key === 'Enter') importAndAnalyze(); });
  loadAnalysis();
});
