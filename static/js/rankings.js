async function load() {
  const res = await fetch("/api/rankings?limit=20");
  const data = await res.json();
  document.querySelector("#rank-table tbody").innerHTML = data.map((l, i) =>
    `<tr><td>${i + 1}</td><td><b>${l.total_score}</b></td><td>${l.title}</td>
    <td>${l.ward || ""}</td><td>${(l.total_monthly_cost || 0).toLocaleString()}</td>
    <td>${l.area_m2 || "?"}</td><td>${l.layout || ""}</td><td>${l.floor || "?"}</td>
    <td>${l.pet_allowed ? "可" : "-"}</td><td>${l.score_reason || ""}</td>
    <td><a href="${l.detail_url}" target="_blank">→</a></td></tr>`).join("");
}
load();