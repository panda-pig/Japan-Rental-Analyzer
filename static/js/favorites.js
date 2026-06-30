const STATUSES = ["気になる", "問い合わせ予定", "問い合わせ済み", "内見予定", "内見済み", "申込候補", "申込済み", "見送り", "成約不可"];

async function load() {
  const res = await fetch("/api/status");
  const data = await res.json();
  if (!data.length) {
    document.getElementById("fav-list").innerHTML = "<p>お気に入りがありません。物件一覧から「気になる」を追加してください。</p>";
    return;
  }
  document.getElementById("fav-list").innerHTML = data.map(s => `
    <div class="card">
      <h3>${s.title}</h3><p>${s.ward || ""} / ${(s.total_monthly_cost || 0).toLocaleString()}円</p>
      <select onchange="updateStatus(${s.id}, this.value)">
        ${STATUSES.map(st => `<option ${st === s.status ? "selected" : ""}>${st}</option>`).join("")}
      </select>
      <input type="text" placeholder="メモ" value="${s.memo || ""}" onblur="updateMemo(${s.id}, this.value)">
      <button class="btn btn-ghost" onclick="removeFav(${s.id})">削除</button>
      <a class="btn btn-primary" href="${s.detail_url}" target="_blank">原平台</a>
    </div>`).join("");
}

async function updateStatus(id, status) {
  await fetch(`/api/status/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
}

async function updateMemo(id, memo) {
  await fetch(`/api/status/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ memo }) });
}

async function removeFav(id) {
  await fetch(`/api/status/${id}`, { method: "DELETE" });
  load();
}

load();