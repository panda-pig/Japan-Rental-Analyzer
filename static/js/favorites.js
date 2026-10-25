// スクレイプ由来の文字列は common.js の Rental 経由でエスケープする
const esc = Rental.esc;
const safeUrl = Rental.safeUrl;

const STATUSES = ["気になる", "問い合わせ予定", "問い合わせ済み", "内見予定", "内見済み", "申込候補", "申込済み", "見送り", "成約不可"];
const STATUS_ORDER = Object.fromEntries(STATUSES.map((s, i) => [s, i]));
const STATUS_CLASS = {
  "気になる": "accent", "問い合わせ予定": "accent", "問い合わせ済み": "accent",
  "内見予定": "warn", "内見済み": "warn", "申込候補": "warn",
  "申込済み": "good", "見送り": "muted", "成約不可": "muted",
};
const VIEWING_STATUSES = new Set(["内見予定", "内見済み", "申込候補", "申込済み"]);
let favoritesData = [];
let loadVersion = 0;
let editVersion = 0;
const pendingWrites = new Map();
const failedFields = new Set();
const deleting = new Set();

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
  const version = ++loadVersion, edits = editVersion;
  const data = await Rental.requestJSON("/api/status");
  if (version !== loadVersion || edits !== editVersion || pendingWrites.size) return;
  favoritesData = data;
  renderFavorites();
}

function renderFavorites() {
  const data = favoritesData;
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
    <div class="card listing-card" id="fav-card-${s.id}">
      <div class="card-header" style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
        <h3 style="margin:0;">${esc(s.title || "(名称不明)")}</h3>
        ${s.total_score != null ? `<span class="badge score${s.total_score >= 75 ? '' : s.total_score >= 60 ? ' mid' : ' low'}">${s.total_score}</span>` : ""}
      </div>
      <p class="location">${esc(s.ward || "エリア不明")} ・ ${Rental.money(s.total_monthly_cost)}${s.area_m2 ? ` ・ ${s.area_m2}㎡` : ""}${s.layout ? ` ・ ${esc(s.layout)}` : ""}</p>
      <div class="tags"><span id="fav-status-${s.id}" class="tag ${cls}">${esc(s.status || "未設定")}</span></div>
      <label style="font-size:11px;color:var(--text-muted);">ステータス</label>
      <select onchange="updateField(${s.id}, 'status', this.value)" style="width:100%;">
        ${STATUSES.map(st => `<option ${st === s.status ? "selected" : ""}>${st}</option>`).join("")}
      </select>
      <div id="fav-viewing-${s.id}" style="display:${showDate ? "block" : "none"};">
        <label style="font-size:11px;color:var(--text-muted);">内見予定日</label>
        <input type="date" value="${esc(s.viewing_date || "")}" onchange="updateField(${s.id}, 'viewing_date', this.value)" style="width:100%;">
      </div>
      <label style="font-size:11px;color:var(--text-muted);">メモ</label>
      <input type="text" placeholder="駅近い / 要確認 など" value="${esc(s.memo || "")}" onblur="updateField(${s.id}, 'memo', this.value)" style="width:100%;">
      <div class="actions">
        <button id="fav-delete-${s.id}" class="btn btn-ghost btn-sm" onclick="removeFav(${s.id})">削除</button>
        ${safeUrl(s.detail_url) ? `<a class="btn btn-primary btn-sm" href="${esc(safeUrl(s.detail_url))}" target="_blank" rel="noopener">原平台で見る</a>` : ""}
      </div>
    </div>`;
  }).join("");
}

function saveMessage(message, ok = true) {
  let el = document.getElementById('fav-save-msg');
  if (!el) {
    el = document.createElement('p');
    el.id = 'fav-save-msg';
    el.setAttribute('role', 'status');
    document.getElementById('fav-list').before(el);
  }
  el.style.color = ok ? 'var(--good)' : 'var(--bad)';
  el.textContent = message;
}

async function queueWrite(id, action) {
  const next = (pendingWrites.get(id) || Promise.resolve()).catch(() => {}).then(action);
  pendingWrites.set(id, next);
  try { return await next; }
  finally { if (pendingWrites.get(id) === next) pendingWrites.delete(id); }
}

function showSaveState() {
  if (failedFields.size) saveMessage('保存できていない項目があります。内容を確認し、再度編集してください。', false);
  else saveMessage(pendingWrites.size ? '保存中…' : '保存しました');
}

async function updateField(id, field, value) {
  if (deleting.has(id)) return;
  editVersion++;
  const key = `${id}:${field}`;
  // Patch only status presentation. Rebuilding the cards would discard drafts
  // and focus in other fields while this request is still in flight.
  if (field === 'status') {
    const tag = document.getElementById(`fav-status-${id}`);
    if (tag) { tag.textContent = value; tag.className = `tag ${STATUS_CLASS[value] || 'muted'}`; }
    const date = document.getElementById(`fav-viewing-${id}`);
    if (date) date.style.display = VIEWING_STATUSES.has(value) ? 'block' : 'none';
  }
  saveMessage('保存中…');
  try {
    await queueWrite(id, () => Rental.requestJSON(`/api/status/${id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [field]: value }),
    }));
    editVersion++;
    const row = favoritesData.find(item => item.id === id);
    if (row) row[field] = value;
    failedFields.delete(key);
    summary(favoritesData);
    showSaveState();
  } catch (error) {
    failedFields.add(key);
    saveMessage(`${error.message}（未保存です。再度編集して保存してください）`, false);
  }
}

async function removeFav(id) {
  if (deleting.has(id)) return;
  if (!confirm("この物件をお気に入りから削除しますか?")) return;
  editVersion++;
  deleting.add(id);
  const button = document.getElementById(`fav-delete-${id}`);
  if (button) button.disabled = true;
  try {
    await queueWrite(id, () => Rental.requestJSON(`/api/status/${id}`, { method: "DELETE" }));
    editVersion++;
    favoritesData = favoritesData.filter(item => item.id !== id);
    document.getElementById(`fav-card-${id}`)?.remove();
    for (const key of failedFields) if (key.startsWith(`${id}:`)) failedFields.delete(key);
    if (favoritesData.length) summary(favoritesData);
    else renderFavorites();
    showSaveState();
  } catch (error) { saveMessage(error.message, false); }
  finally { deleting.delete(id); if (button) button.disabled = false; }
}

load().catch(error => Rental.showError('fav-list', error));
