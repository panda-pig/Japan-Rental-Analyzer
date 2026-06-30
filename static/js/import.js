async function loadSources() {
  const res = await fetch("/api/sources");
  const data = await res.json();
  const el = document.getElementById("source-list");
  if (!data.length) {
    el.innerHTML = '<div class="empty-state">データソースが未設定です。下記フォームから追加してください。</div>' + sourceForm();
    return;
  }
  el.innerHTML = `<table><thead><tr>
    <th>名前</th><th>プラットフォーム</th><th>URL</th><th>最終取得</th><th>ステータス</th>
  </tr></thead><tbody>${data.map(s => `<tr>
    <td style="font-weight:600;color:var(--text-primary);">${s.name}</td>
    <td><span class="badge platform">${s.platform}</span></td>
    <td><a href="${s.source_url}" target="_blank" style="color:var(--accent);font-size:12px;">${(s.source_url || "").slice(0, 50)}...</a></td>
    <td style="font-size:12px;color:var(--text-muted);">${s.last_scraped_at || "-"}</td>
    <td>${renderStatus(s.last_status)}</td>
  </tr>`).join("")}</tbody></table>` + sourceForm();
}

function renderStatus(status) {
  if (!status || status === "-") return '<span style="color:var(--text-muted);font-size:12px;">-</span>';
  if (status === "ok") return '<span class="tag good">OK</span>';
  return `<span class="tag" style="background:var(--warn-bg);color:var(--warn);">${status}</span>`;
}

function sourceForm() {
  return `<hr style="border:none;border-top:1px solid var(--border);margin:20px 0;">
  <h2 style="font-size:15px;">データソース追加</h2>
  <div class="filters" style="margin-top:12px;">
    <div><label>名前</label><input type="text" id="src_name" placeholder="横浜 ペット可"></div>
    <div><label>プラットフォーム</label><select id="src_platform">
      <option value="SUUMO">SUUMO</option><option value="HOMES">HOMES</option><option value="athome">athome</option>
    </select></div>
    <div><label>検索URL</label><input type="text" id="src_url" placeholder="https://..."></div>
    <div style="flex-direction:row;align-items:flex-end;"><button class="btn btn-primary" onclick="addSource()">追加</button></div>
  </div>`;
}

async function addSource() {
  const data = {
    name: document.getElementById("src_name").value,
    platform: document.getElementById("src_platform").value,
    source_url: document.getElementById("src_url").value,
  };
  if (!data.name || !data.source_url) { alert("名前とURLを入力してください"); return; }
  await fetch("/api/sources", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  loadSources();
}

async function scrapeAll() {
  document.getElementById("scrape-result").textContent = "取得中...";
  try {
    const res = await fetch("/api/scrape", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const d = await res.json();
    document.getElementById("scrape-result").innerHTML =
      `完了: <span style="color:var(--good);font-weight:600;">新規${d.inserted_count || 0}</span> / <span style="color:var(--accent);font-weight:600;">更新${d.updated_count || 0}</span> / エラー${d.error_count || 0}`;
  } catch (e) {
    document.getElementById("scrape-result").textContent = "エラーが発生しました";
  }
  loadSources();
}

loadSources();