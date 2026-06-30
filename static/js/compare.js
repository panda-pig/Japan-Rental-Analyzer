async function load() {
  const ids = JSON.parse(localStorage.getItem("compareIds") || "[]");
  const el = document.getElementById("compare-table");
  if (ids.length < 2) {
    el.innerHTML = '<div class="empty-state">比較には2件以上選択してください。<br>物件一覧で「比較追加」ボタンを押してください。</div>';
    return;
  }
  const res = await fetch("/api/compare?ids=" + ids.join(","));
  const data = await res.json();
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