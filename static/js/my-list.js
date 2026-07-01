// URL导入 + 单套房源分析
async function importAndAnalyze() {
  const url = document.getElementById('import-url').value.trim();
  const el = document.getElementById('import-result');
  if (!url) { el.innerHTML = '<span style="color:var(--bad);">URLを入力してください</span>'; return; }
  el.innerHTML = '<span style="color:var(--text-muted);">解析中... (数秒かかります)</span>';
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
      } catch(e2) {
        el.innerHTML = '<span style="color:var(--bad);">解析に失敗しました(HTTP ' + res.status + ')</span>';
      }
      return;
    }
    const d = await res.json();
    if (d.error) {
      el.innerHTML = '<span style="color:var(--bad);">' + d.error + '</span>';
    } else {
      el.innerHTML = '<span style="color:var(--good);font-weight:600;">' + d.message + '</span>';
      document.getElementById('import-url').value = '';
      loadAnalysis();  // 加载分析报告
    }
  } catch (e) {
    el.innerHTML = '<span style="color:var(--bad);">通信エラー: ' + e.message + '</span>';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('import-url');
  if (input) input.addEventListener('keydown', e => { if (e.key === 'Enter') importAndAnalyze(); });
});

const CHART_FONT = "'Noto Sans JP', sans-serif";
const COLORS = { primary: '#2563EB', good: '#059669', warn: '#D97706', bad: '#DC2626', text: '#5A6B7E', muted: '#8B9AAA', border: '#E4E8EC',
  palette: ['#2563EB', '#059669', '#D97706', '#8B5CF6', '#EC4899', '#14B8A6', '#6366F1', '#F43F5E'] };
const BASE_OPT = {
  textStyle: { fontFamily: CHART_FONT, color: COLORS.text, fontSize: 12 },
  tooltip: { backgroundColor: '#FFFFFF', borderColor: COLORS.border, borderWidth: 1,
    textStyle: { fontFamily: CHART_FONT, color: '#1A2332', fontSize: 12 },
    extraCssText: 'box-shadow: 0 2px 8px rgba(16,24,40,0.08); border-radius: 8px;' },
};

async function loadAnalysis() {
  const res = await fetch('/api/my-list');
  const d = await res.json();
  const container = document.getElementById('analysis-container');

  if (!d.total) {
    container.innerHTML = '<div class="empty-state">物件をインポートすると分析が表示されます。</div>';
    return;
  }

  // 找最新导入的房源(取第一条,即最高分的)
  const latest = d.compare_rows[0];
  if (!latest) {
    container.innerHTML = '<div class="empty-state">物件が見つかりません。</div>';
    return;
  }

  // 获取该房源所在区域的基准
  let region = null;
  if (latest.ward) {
    try {
      const rres = await fetch('/api/regions/' + encodeURIComponent(latest.ward));
      if (rres.ok) region = await rres.json();
    } catch(e) {}
  }

  renderReport(latest, region, d);
}

function renderReport(listing, region, allData) {
  const c = document.getElementById('analysis-container');

  // 房源详情 + 区域对比表
  const rows = [
    ['物件名', listing.title, '-'],
    ['プラットフォーム', `<span class="badge platform">${listing.platform}</span>`, '-'],
    ['スコア', `<span class="badge score">${listing.total_score || '-'}</span>`, '-'],
    ['月額', `${(listing.total_monthly_cost || 0).toLocaleString()}円`, region ? `${region.avg_rent.toLocaleString()}円` : '-'],
    ['家賃', `${(listing.rent || 0).toLocaleString()}円`, '-'],
    ['管理費', `${(listing.management_fee || 0).toLocaleString()}円`, '-'],
    ['面積', `${listing.area_m2 || '?'}㎡`, region ? `${region.avg_area}㎡` : '-'],
    ['間取り', listing.layout || '-', '-'],
    ['階数', `${listing.floor || '?'}階`, '-'],
    ['築年数', `築${listing.building_age || '?'}年`, region ? `築${region.avg_building_age}年` : '-'],
    ['徒歩', `${listing.walk_minutes || '?'}分`, '-'],
    ['敷金', `${(listing.deposit || 0).toLocaleString()}円`, '-'],
    ['礼金', `${(listing.key_money || 0).toLocaleString()}円`, '-'],
    ['初期費用', `${(listing.initial_cost_estimate || 0).toLocaleString()}円`, '-'],
    ['平米単価', `${listing.price_per_m2 ? Math.round(listing.price_per_m2).toLocaleString() + '円' : '-'}`, '-'],
    ['ペット', listing.pet_allowed ? '<span class="tag good">可</span>' : '不可', '-'],
  ];

  // 偏差计算
  let deviationText = '-';
  if (region && listing.total_monthly_cost && region.avg_rent) {
    const diff = listing.total_monthly_cost - region.avg_rent;
    const pct = Math.round(diff / region.avg_rent * 100);
    const color = diff > 0 ? COLORS.bad : COLORS.good;
    deviationText = `<span style="color:${color};font-weight:600;">${diff > 0 ? '+' : ''}${diff.toLocaleString()}円 (${pct}%)</span>`;
  }
  rows.push(['エリア平均との偏差', deviationText, '-']);

  // 安全性/便利度/環境
  if (region) {
    rows.push(['エリア安全性', region.safety_level, '-']);
    rows.push(['エリア便利度', region.convenience_level, '-']);
    rows.push(['エリア環境', region.environment_level, '-']);
  }

  let html = `
    <div class="card" style="margin-top:20px;">
      <h2>物件詳細レポート</h2>
      <p style="font-size:13px;color:var(--text-secondary);margin-bottom:16px;">
        ${listing.ward || '地域不明'} の物件解析結果。
        ${region ? `エリア平均(${listing.ward})と比較しています。` : 'このエリアの基準データがありません。'}
      </p>
      <table style="width:100%;">
        <thead><tr><th>項目</th><th>この物件</th><th>エリア平均</th></tr></thead>
        <tbody>
          ${rows.map(r => `<tr><td style="font-weight:600;color:var(--text-primary);">${r[0]}</td><td>${r[1]}</td><td style="color:var(--text-muted);">${r[2]}</td></tr>`).join('')}
        </tbody>
      </table>
    </div>`;

  // 评分雷达(这一套的8维度)
  if (listing.total_score != null) {
    html += `
    <div class="card">
      <h2>スコアレーダー <span style="font-size:12px;font-weight:400;color:var(--text-muted);">8次元評価</span></h2>
      <div id="chart-radar-single" class="chart"></div>
    </div>`;

    // 偏差柱状图
    if (region && listing.total_monthly_cost) {
      html += `
      <div class="card">
        <h2>エリア平均との比較</h2>
        <div id="chart-compare-bar" class="chart"></div>
      </div>`;
    }

    // 推荐理由
    html += `
    <div class="card">
      <h2>推薦理由</h2>
      <div style="background:var(--good-bg);border:1px solid var(--good-border);border-radius:var(--radius-sm);padding:12px 16px;font-size:13px;color:var(--good);">
        ${listing.score_reason || 'スコア理由がありません'}
      </div>
    </div>`;
  }

  // 如果有多套导入的房源,显示全部列表
  if (allData.total > 1) {
    html += `
    <div class="card" style="padding:0;overflow:hidden;">
      <h2 style="padding:24px 24px 0;">インポート済み物件 (${allData.total}件)</h2>
      <div style="overflow-x:auto;">
        <table id="all-listings-table">
          <thead><tr><th>スコア</th><th>物件名</th><th>エリア</th><th>月額</th><th>面積</th><th>偏差</th><th></th></tr></thead>
          <tbody></tbody>
        </table>
      </div>
    </div>`;
  }

  c.innerHTML = html;

  // 渲染雷达图
  if (listing.total_score != null) {
    const el = document.getElementById('chart-radar-single');
    if (el) {
      const ch = echarts.init(el);
      ch.setOption({
        ...BASE_OPT,
        radar: {
          indicator: [
            { name: '予算', max: 20 }, { name: '面積', max: 15 },
            { name: '通勤', max: 15 }, { name: '階数', max: 10 },
            { name: 'ペット', max: 15 }, { name: '駅距離', max: 10 },
            { name: '築年数', max: 10 }, { name: '初期費用', max: 5 },
          ],
          shape: 'polygon', radius: '65%',
          axisName: { color: COLORS.text, fontFamily: CHART_FONT, fontSize: 11 },
        },
        series: [{
          type: 'radar',
          data: [{
            value: [allData.radar_series[0]?.value[0] || 0, allData.radar_series[0]?.value[1] || 0,
                    allData.radar_series[0]?.value[2] || 0, allData.radar_series[0]?.value[3] || 0,
                    allData.radar_series[0]?.value[4] || 0, allData.radar_series[0]?.value[5] || 0,
                    allData.radar_series[0]?.value[6] || 0, allData.radar_series[0]?.value[7] || 0],
            name: listing.title,
            itemStyle: { color: COLORS.primary },
            areaStyle: { opacity: 0.15 },
          }],
        }],
      });
    }
  }

  // 渲染对比柱状图
  if (region && listing.total_monthly_cost) {
    const el2 = document.getElementById('chart-compare-bar');
    if (el2) {
      const ch = echarts.init(el2);
      ch.setOption({
        ...BASE_OPT,
        xAxis: { type: 'category', data: ['この物件', 'エリア平均'] },
        yAxis: { type: 'value', name: '月額(円)', axisLabel: { color: COLORS.muted } },
        series: [{
          type: 'bar',
          data: [
            { value: listing.total_monthly_cost, itemStyle: { color: COLORS.primary } },
            { value: region.avg_rent, itemStyle: { color: COLORS.warn } },
          ],
          barMaxWidth: 80, label: { show: true, formatter: p => p.value.toLocaleString() + '円', fontFamily: CHART_FONT, fontSize: 12 },
        }],
      });
    }
  }

  // 渲染全部列表
  if (allData.total > 1) {
    const tbody = document.querySelector('#all-listings-table tbody');
    if (tbody) {
      tbody.innerHTML = allData.compare_rows.map(l => {
        const dev = l.region_avg_rent && l.total_monthly_cost
          ? `<span style="color:${l.total_monthly_cost > l.region_avg_rent ? 'var(--bad)' : 'var(--good)'};font-weight:600;">${Math.round((l.total_monthly_cost - l.region_avg_rent) / l.region_avg_rent * 100)}%</span>`
          : '-';
        return `<tr>
          <td><span class="badge score">${l.total_score || '-'}</span></td>
          <td style="font-weight:600;color:var(--text-primary);">${l.title || ''}</td>
          <td>${l.ward || '-'}</td>
          <td>${(l.total_monthly_cost || 0).toLocaleString()}円</td>
          <td>${l.area_m2 || '?'}㎡</td>
          <td>${dev}</td>
          <td><a href="${l.detail_url}" target="_blank" style="color:var(--accent);">→</a></td>
        </tr>`;
      }).join('');
    }
  }
}

// 初始加载
loadAnalysis();