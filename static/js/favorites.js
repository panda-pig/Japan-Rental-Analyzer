const STATUSES = ["気になる", "問い合わせ予定", "問い合わせ済み", "内見予定", "内見済み", "申込候補", "申込済み", "見送り", "成約不可"];

async function load() {
  const res = await fetch("/api/status");
  const data = await res.json();
  const el = document.getElementById("fav-list");
  if (!data.length) {
    el.innerHTML = '<div class="empty-state">お気に入りがありません。<br>物件一覧から「気になる」を追加してください。</div>';
    return;
  }
  el.innerHTML = data.map(s => `
    <div class="card listing-card">
      <div class="card-header">
        <h3>${s.title}</h3>
      </div>
      <p class="location">${s.ward || ""} / ${(s.total_monthly_cost || 0).toLocaleString()}円</p>
      <div class="tags">
        ${s.status ? `<span class="tag accent">${s.status}</span>` : ""}
      </div>
      <select onchange="updateStatus(${s.id}, this.value)" style="width:100%;">
        ${STATUSES.map(st => `<option ${st === s.status ? "selected" : ""}>${st}</option>`).join("")}
      </select>
      <input type="text" placeholder="メモを入力" value="${s.memo || ""}" onblur="updateMemo(${s.id}, this.value)" style="width:100%;">
      <div class="actions">
        <button class="btn btn-ghost btn-sm" onclick="removeFav(${s.id})">削除</button>
        <a class="btn btn-primary btn-sm" href="${s.detail_url}" target="_blank">原平台で見る</a>
      </div>
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