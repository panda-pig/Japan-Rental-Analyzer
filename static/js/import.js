async function loadSources() {
  const res = await fetch("/api/sources");
  const data = await res.json();
  if (!data.length) {
    document.getElementById("source-list").innerHTML = "<p>データソースが未設定です。下記フォームから追加してください。</p>" + sourceForm();
    return;
  }
  document.getElementById("source-list").innerHTML = `<table>
    <thead><tr><th>名前</th><th>プラットフォーム</th><th>URL</th><th>最終取得</th><th>ステータス</th></tr></thead>
    <tbody>${data.map(s => `<tr><td>${s.name}</td><td>${s.platform}</td>
    <td><a href="${s.source_url}" target="_blank">${(s.source_url || "").slice(0, 40)}...</a></td>
    <td>${s.last_scraped_at || "-"}</td><td>${s.last_status || "-"}</td></tr>`).join("")}</tbody></table>`
    + sourceForm();
}

function sourceForm() {
  return `<hr><h3>データソース追加</h3>
  <div class="filters">
    <div><label>名前</label><input type="text" id="src_name" placeholder="横浜 ペット可"></div>
    <div><label>プラットフォーム</label><select id="src_platform">
      <option value="SUUMO">SUUMO</option><option value="HOMES">HOMES</option><option value="athome">athome</option>
    </select></div>
    <div><label>検索URL</label><input type="text" id="src_url" placeholder="https://..."></div>
    <div style="align-self:end"><button class="btn btn-primary" onclick="addSource()">追加</button></div>
  </div>`;
}

async function addSource() {
  const data = {
    name: document.getElementById("src_name").value,
    platform: document.getElementById("src_platform").value,
    source_url: document.getElementById("src_url").value,
  };
  await fetch("/api/sources", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  loadSources();
}

async function scrapeAll() {
  document.getElementById("scrape-result").textContent = "取得中...";
  const res = await fetch("/api/scrape", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const d = await res.json();
  document.getElementById("scrape-result").innerHTML =
    `完了: 新規${d.inserted_count || 0} 更新${d.updated_count || 0} 重複${d.duplicate_count || 0} エラー${d.error_count || 0}`;
  loadSources();
}

loadSources();