let cardView = true;
let compareIds = new Set(JSON.parse(localStorage.getItem("compareIds") || "[]"));

function buildQuery() {
  const p = new URLSearchParams();
  const v = id => document.getElementById(id).value;
  if (v("f_max_cost")) p.set("max_total_cost", v("f_max_cost"));
  if (v("f_min_area")) p.set("min_area", v("f_min_area"));
  if (v("f_min_floor")) p.set("min_floor", v("f_min_floor"));
  if (v("f_walk")) p.set("max_walk_minutes", v("f_walk"));
  if (v("f_age")) p.set("max_building_age", v("f_age"));
  if (v("f_pet") === "1") p.set("pet_allowed", "1");
  if (v("f_score")) p.set("min_score", v("f_score"));
  if (v("f_sort")) p.set("sort", v("f_sort"));
  return p.toString();
}

async function loadListings() {
  const res = await fetch("/api/listings?" + buildQuery());
  const data = await res.json();
  const el = document.getElementById("results");
  el.className = cardView ? "grid" : "";
  if (!data.length) {
    el.innerHTML = "<p>該当物件がありません。</p>";
    return;
  }
  el.innerHTML = cardView ? data.map(renderCard).join("") : renderTable(data);
}

function renderCard(l) {
  const over = l.total_monthly_cost > 140000 ? "over-budget" : "";
  const commute = l.commute_resolved
    ? `<span class="tag">通勤${l.score_commute_minutes || l.commute_minutes || "?"}分</span>`
    : `<span class="tag">通勤分未取得</span>`;
  const inCompare = compareIds.has(l.id);
  return `<div class="card listing-card">
    <span class="badge score">${l.total_score || "-"}</span>
    <span class="badge platform">${l.platform}</span>
    <h3>${l.title || ""}</h3>
    <p>${l.ward || ""} / ${l.nearest_station || ""} 徒歩${l.walk_minutes || "?"}分</p>
    <div class="price ${over}">月額 ${(l.total_monthly_cost || 0).toLocaleString()}円</div>
    <div class="meta">${l.layout || ""} / ${l.area_m2 || "?"}㎡ / ${l.floor || "?"}階 / 築${l.building_age || "?"}年</div>
    <div>${commute}${l.pet_allowed ? '<span class="tag">ペット可</span>' : ""}</div>
    <p class="reason">${l.score_reason || ""}</p>
    <button class="btn btn-ghost" onclick="addFavorite(${l.id})">気になる</button>
    <button class="btn ${inCompare ? "btn-primary" : "btn-ghost"}" onclick="toggleCompare(${l.id})">${inCompare ? "比較済" : "比較追加"}</button>
    <a class="btn btn-primary" href="${l.detail_url}" target="_blank" rel="noopener">原平台で見る</a>
  </div>`;
}

function renderTable(data) {
  return `<table><thead><tr><th>推薦分</th><th>物件名</th><th>プラットフォーム</th><th>月額</th><th>面積</th><th>間取り</th><th>階</th><th>徒歩</th><th></th></tr></thead>
  <tbody>${data.map(l => `<tr>
    <td>${l.total_score || "-"}</td><td>${l.title || ""}</td><td>${l.platform}</td>
    <td>${(l.total_monthly_cost || 0).toLocaleString()}</td><td>${l.area_m2 || "?"}</td>
    <td>${l.layout || ""}</td><td>${l.floor || "?"}</td><td>${l.walk_minutes || "?"}分</td>
    <td><a href="${l.detail_url}" target="_blank">→</a></td></tr>`).join("")}</tbody></table>`;
}

async function addFavorite(id) {
  await fetch("/api/status", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ listing_id: id, status: "気になる" }),
  });
  alert("気になるに追加しました");
}

function toggleCompare(id) {
  if (compareIds.has(id)) {
    compareIds.delete(id);
  } else if (compareIds.size < 4) {
    compareIds.add(id);
  } else {
    alert("比較は最大4件です");
    return;
  }
  localStorage.setItem("compareIds", JSON.stringify([...compareIds]));
  loadListings();
}

function toggleView() {
  cardView = !cardView;
  loadListings();
}

loadListings();