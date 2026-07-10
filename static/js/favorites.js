const STATUSES = ["気になる", "問い合わせ予定", "問い合わせ済み", "内見予定", "内見済み", "申込候補", "申込済み", "見送り", "成約不可"];
const STATUS_ORDER = Object.fromEntries(STATUSES.map((s, i) => [s, i]));
const STATUS_CLASS = {
  "気になる": "accent", "問い合わせ予定": "accent", "問い合わせ済み": "accent",
  "内見予定": "warn", "内見済み": "warn", "申込候補": "warn",
  "申込済み": "good", "見送り": "muted", "成約不可": "muted",
};
// 内見に関わるステータスだけ内見日入力を出す
const VIEWING_STATUSES = new Set(["内見予定", "内見済み", "申込候補", "申込済み"]);

function summary(data) {
  const count = pred => data.filter(pred).length;
  const cards = [
    { num: data.length, label: "合計", cls: "accent" },
    { num: count(s => ["気になる", "問い合わせ予定"].includes(s.status)), label: "検討中", cls: "" },
    { num: count(s => ["問い合わせ済み", "内見予定", "内見済み", "申込候補"].includes(s.status)), label: "進行中", cls: "warn" },
    { num: count(s => s.status === "申込済み"), label: "申込済み", cls: "good" },
    { num: count(s => ["見送り", "成約不可"].includes(s.status)), label: "見送り", cls: "" },
  ];
  document.getElementById("fav-summary").innerHTML = cards.map(c =>
    `<div class="metric ${c.cls}"><div class="num">${c.num}</div><div class="label">${c.label}</div></div>`).join("");
}

async function load() {
  const data = await (await fetch("/api/status")).json();
  const el = document.getElementById("fav-list");
  document.getElementById("fav-summary").innerHTML = "";
  if (!data.length) {
    el.innerHTML = '<div class="empty-state">お気に入りがありません。<br>「物件分析」で物件をインポートし、行の「気になる」を押すと追加されます。</div>';
    return;
  }
  summary(data);
  data.sort((a, b) => (STATUS_ORDER[a.status] ?? 99) - (STATUS_ORDER[b.status] ?? 99));

  el.innerHTML = data.map(s => {
    const cls = STATUS_CLASS[s.status] || "muted";
    const showDate = VIEWING_STATUSES.has(s.status);
    return `
    <div class="card listing-card">
      <div class="card-header" style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
        <h3 style="margin:0;">${s.title || "(名称不明)"}</h3>
        ${s.total_score != null ? `<span class="badge score">${s.total_score}</span>` : ""}
      </div>
      <p class="location">${s.ward || "エリア不明"} ・ ${(s.total_monthly_cost || 0).toLocaleString()}円${s.area_m2 ? ` ・ ${s.area_m2}㎡` : ""}${s.layout ? ` ・ ${s.layout}` : ""}</p>
      <div class="tags"><span class="tag ${cls}">${s.status || "未設定"}</span></div>
      <label style="font-size:11px;color:var(--text-muted);">ステータス</label>
      <select onchange="updateField(${s.id}, 'status', this.value)" style="width:100%;">
        ${STATUSES.map(st => `<option ${st === s.status ? "selected" : ""}>${st}</option>`).join("")}
      </select>
      <div style="display:${showDate ? "block" : "none"};">
        <label style="font-size:11px;color:var(--text-muted);">内見予定日</label>
        <input type="date" value="${s.viewing_date || ""}" onchange="updateField(${s.id}, 'viewing_date', this.value)" style="width:100%;">
      </div>
      <label style="font-size:11px;color:var(--text-muted);">メモ</label>
      <input type="text" placeholder="駅近い / 要確認 など" value="${(s.memo || "").replace(/"/g, "&quot;")}" onblur="updateField(${s.id}, 'memo', this.value)" style="width:100%;">
      <div class="actions">
        <button class="btn btn-ghost btn-sm" onclick="removeFav(${s.id})">削除</button>
        ${s.detail_url ? `<a class="btn btn-primary btn-sm" href="${s.detail_url}" target="_blank" rel="noopener">原平台で見る</a>` : ""}
      </div>
    </div>`;
  }).join("");
}

async function updateField(id, field, value) {
  await fetch(`/api/status/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ [field]: value }),
  });
  if (field === "status") load();  // 状态变了要重排/重算摘要
}

async function removeFav(id) {
  if (!confirm("この物件をお気に入りから削除しますか?")) return;
  await fetch(`/api/status/${id}`, { method: "DELETE" });
  load();
}

load();
