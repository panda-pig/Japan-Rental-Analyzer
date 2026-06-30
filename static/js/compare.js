async function load() {
  const ids = JSON.parse(localStorage.getItem("compareIds") || "[]");
  if (ids.length < 2) {
    document.getElementById("compare-table").innerHTML = "<p>比較には2件以上選択してください(物件一覧で「比較追加」)。</p>";
    return;
  }
  const res = await fetch("/api/compare?ids=" + ids.join(","));
  const data = await res.json();
  const rows = [
    ["推薦分", "total_score"], ["月額", "total_monthly_cost"], ["家賃", "rent"],
    ["管理費", "management_fee"], ["初期費用", "initial_cost_estimate"],
    ["面積", "area_m2"], ["㎡単価", "price_per_m2"], ["間取り", "layout"],
    ["階", "floor"], ["最寄駅", "nearest_station"], ["徒歩", "walk_minutes"],
    ["築年数", "building_age"], ["ペット", "pet_allowed"], ["敷金", "deposit"],
    ["礼金", "key_money"], ["プラットフォーム", "platform"], ["通勤(分)", "commute_minutes"],
  ];
  let html = "<table><thead><tr><th>項目</th>" + data.map(l => `<th>${l.title}</th>`).join("") + "</tr></thead><tbody>";
  for (const [label, key] of rows) {
    html += `<tr><td>${label}</td>` + data.map(l => {
      let v = l[key];
      if (["total_monthly_cost", "rent", "management_fee", "initial_cost_estimate", "deposit", "key_money"].includes(key))
        v = (v || 0).toLocaleString();
      if (key === "pet_allowed") v = v ? "可" : "不可";
      if (key === "commute_minutes" && !l.commute_resolved) v = "未取得";
      return `<td>${v ?? "-"}</td>`;
    }).join("") + "</tr>";
  }
  html += `<tr><td>原平台</td>` + data.map(l => `<td><a href="${l.detail_url}" target="_blank">→</a></td>`).join("") + "</tr>";
  html += "</tbody></table>";
  document.getElementById("compare-table").innerHTML = html;
}
load();