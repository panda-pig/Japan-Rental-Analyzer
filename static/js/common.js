(() => {
  const escapes = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => escapes[char]);
  async function adminFetch(url, opts = {}) {
    const send = token => fetch(url, { ...opts,
      headers: { ...opts.headers, ...(token ? { 'X-Admin-Token': token } : {}) },
    });
    let response = await send(localStorage.getItem('adminToken') || '');
    if (response.status !== 401) return response;
    const token = window.prompt('この操作には管理トークンが必要です。');
    if (!token) return response;
    response = await send(token);
    if (response.status === 401 || response.status === 403) localStorage.removeItem('adminToken');
    // A validation error happens after authentication; keep the valid token
    // while allowing requestJSON/the caller to display the operation's error.
    else if (response.ok || (response.status >= 400 && response.status < 500)) localStorage.setItem('adminToken', token);
    return response;
  }
  async function requestJSON(url, opts = {}) {
    const response = await adminFetch(url, opts);
    const data = await response.json().catch(() => null);
    if (!response.ok || data == null) throw new Error(data?.error || `通信に失敗しました (HTTP ${response.status})`);
    return data;
  }
  function safeUrl(value) {
    // new URL(null, origin) は origin/null に解決してしまうので先に弾く
    if (typeof value !== 'string' || !value.trim()) return '';
    try {
      const url = new URL(value, location.origin);
      return (url.protocol === 'http:' || url.protocol === 'https:') ? url.href : '';
    } catch { return ''; }
  }
  function readCompareIds() {
    try {
      const value = JSON.parse(localStorage.getItem('compareIds') || '[]');
      return Array.isArray(value) ? [...new Set(value.filter(id => Number.isSafeInteger(id) && id > 0))].slice(0, 4) : [];
    } catch { return []; }
  }
  function showError(id, error) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = `<p role="alert" class="empty-state">${esc(error.message)}<br>ページを再読み込みして再試行してください。</p>`;
  }
  window.Rental = { esc, safeUrl, adminFetch, requestJSON, readCompareIds, showError,
    money: value => value == null ? '未取得' : esc(value.toLocaleString()) + '円' };
})();
