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
    if (response.ok) localStorage.setItem('adminToken', token);
    else localStorage.removeItem('adminToken');
    return response;
  }
  async function requestJSON(url, opts = {}) {
    const method = (opts.method || 'GET').toUpperCase();
    const response = await (method === 'GET' ? fetch(url, opts) : adminFetch(url, opts));
    const data = await response.json().catch(() => null);
    if (!response.ok || data == null) throw new Error(data?.error || `通信に失敗しました (HTTP ${response.status})`);
    return data;
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
  window.Rental = { esc, adminFetch, requestJSON, readCompareIds, showError,
    money: value => value == null ? '未取得' : esc(value.toLocaleString()) + '円' };
})();
