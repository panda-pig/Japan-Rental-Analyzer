const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function page(name, data = []) {
  const elements = new Map();
  const storage = new Map();
  const context = {
    console, URL, setTimeout, clearTimeout,
    location: { origin: 'http://localhost' },
    matchMedia: () => ({ matches: false }), addEventListener() {}, prompt: () => null,
    localStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, v) => storage.set(key, v), removeItem: key => storage.delete(key) },
    document: {
      addEventListener() {}, querySelectorAll: () => [],
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, { id, innerHTML: '', textContent: '', style: {}, setAttribute() {} });
        return elements.get(id);
      },
    },
    fetch: async () => ({ ok: true, status: 200, json: async () => data }),
  };
  context.window = context;
  vm.createContext(context);
  const script = file => fs.readFileSync(path.join(__dirname, '../static/js', file), 'utf8');
  vm.runInContext(script('common.js'), context);
  // Tests invoke page entry points explicitly, with deterministic responses.
  const source = script(name).replace(/^load\(\)\.catch\([^\n]*\);$/m, '');
  vm.runInContext(source, context);
  return { context, elements, storage, run: js => vm.runInContext(js, context) };
}

test('late region response cannot overwrite the selected report', async () => {
  const p = page('my-list.js');
  p.run(`
    globalThis.pending = {};
    getRegion = id => new Promise(resolve => pending[id] = resolve);
    reportHtml = selected => selected.title;
    wordCloudHtml = poolHtml = () => '';
    wirePoolHandlers = updateCompareBtn = () => {};
    state.data = {total: 2, compare_rows: [{id:1, region_id:1, title:'A'}, {id:2, region_id:2, title:'B'}]};
    state.selectedId = 1; globalThis.first = render();
    state.selectedId = 2; globalThis.second = render();
    pending[2](null);
  `);
  await p.context.second;
  p.run('pending[1](null)');
  await p.context.first;
  assert.equal(p.elements.get('analysis-container').innerHTML, 'B');
  assert.equal(p.run('state.selectedId'), 2);
});

test('comparison selection survives report switches and refresh, pruning deleted listings', async () => {
  const p = page('my-list.js');
  p.run(`
    state.compareIds = new Set([1,2]); state.selectedId = 2;
    render = async () => {};
    Rental.requestJSON = async () => ({total:2, compare_rows:[{id:1},{id:2}]});
  `);
  await p.run('loadAnalysis()');
  assert.deepEqual(JSON.parse(p.storage.get('compareIds')), [1, 2]);
  const html = p.run('poolHtml([{id:1,title:"A"},{id:2,title:"B"}], {})');
  assert.equal((html.match(/data-id="[12]" checked/g) || []).length, 2);
  p.run('Rental.requestJSON = async () => ({total:1,compare_rows:[{id:2}]})');
  await p.run('loadAnalysis()');
  assert.deepEqual(JSON.parse(p.storage.get('compareIds')), [2]);
});

test('legacy favorite fields are escaped in text and attributes', async () => {
  const marker = '<img src=x onerror="bad()">';
  const p = page('favorites.js', [{id:1, title:marker, status:marker, memo:marker, viewing_date:marker}]);
  await p.run('load()');
  const html = p.elements.get('fav-list').innerHTML;
  assert.ok(!html.includes(marker));
  assert.ok(html.includes('&lt;img'));
  assert.ok(!html.includes('value="<img'));
});

test('missing prices stay unknown and do not become zero yen', () => {
  const p = page('my-list.js');
  assert.equal(p.context.Rental.money(null), '未取得');
  assert.equal(p.context.Rental.money(0), '0円');
  const html = p.run('reportHtml({id:1,title:"Unknown",deposit:null,key_money:null}, null)');
  assert.ok(html.includes('未取得 / 未取得'));
});

test('corrupt comparison storage is treated as an empty selection', () => {
  const p = page('compare.js');
  p.storage.set('compareIds', '{bad json');
  assert.equal(p.context.Rental.readCompareIds().length, 0);
});

test('failed writes surface the server error instead of showing success', async () => {
  const p = page('settings.js');
  p.context.fetch = async () => ({ ok: false, status: 400, json: async () => ({error:'Invalid budget'}) });
  await assert.rejects(p.context.Rental.requestJSON('/api/preferences', {method:'PUT'}), /Invalid budget/);
});

test('fee-exclusive benchmark uses rent rather than total monthly cost', () => {
  const p = page('my-list.js');
  const delta = p.run('deviationOf({rent:100000,total_monthly_cost:120000,region_comparison_cost:100000,region_avg_rent:100000})');
  assert.equal(delta, 0);
});

test('achievement labels and decisions follow saved preferences', () => {
  const p = page('my-list.js');
  p.run('state.data = {prefs:{min_floor:2,max_walk_minutes:5,max_building_age:6}}');
  const html = p.run('reportHtml({id:1,title:"Test",floor:2,walk_minutes:7,building_age:5,pet_allowed:null}, null)');
  assert.ok(html.includes('chip on">✓ 2階以上'));
  assert.ok(html.includes('chip on">✓ 築6年以内'));
  assert.ok(html.includes('chip off">駅徒歩5分以内'));
  assert.ok(!html.includes('駅徒歩10分以内'));
  assert.ok(html.includes('（未確認）'));
});

test('late price history cannot replace a different listing report', async () => {
  const p = page('my-list.js');
  p.run(`
    globalThis.requests = {}; globalThis.drawn = [];
    Rental.requestJSON = url => new Promise(resolve => requests[url] = resolve);
    drawPriceHistory = (el, history) => drawn.push(history[0].total_monthly_cost);
    renderVersion = 1; state.selectedId = 1;
    globalThis.first = loadReportHistory(1, 1);
    renderVersion = 2; state.selectedId = 2;
    globalThis.second = loadReportHistory(2, 2);
    requests['/api/listings/2/price-history']({history:[{total_monthly_cost:200000}]});
  `);
  await p.context.second;
  p.run("requests['/api/listings/1/price-history']({history:[{total_monthly_cost:100000}]})");
  await p.context.first;
  assert.deepEqual(Array.from(p.context.drawn), [200000]);
});

test('price history is cached per listing and invalidated after pool refresh', async () => {
  const p = page('my-list.js');
  p.run(`
    globalThis.calls = [];
    Rental.requestJSON = async url => {
      calls.push(url);
      return url === '/api/my-list' ? {total:1,compare_rows:[{id:1}]} : {history:[]};
    };
    render = async () => {};
  `);
  await p.run('Promise.all([getPriceHistory(1),getPriceHistory(1)])');
  await p.run('getPriceHistory(1)');
  assert.equal(p.context.calls.length, 1);
  await p.run('loadAnalysis()');
  await p.run('getPriceHistory(1)');
  assert.deepEqual(Array.from(p.context.calls), ['/api/listings/1/price-history', '/api/my-list', '/api/listings/1/price-history']);
});

test('failed history loads remain visible and can be retried', async () => {
  const p = page('my-list.js');
  p.run(`
    renderVersion = 1; state.selectedId = 1;
    Rental.requestJSON = async () => { throw new Error('temporary failure'); };
  `);
  await p.run('loadReportHistory(1, 1)');
  assert.match(p.elements.get('chart-price-history').innerHTML, /価格履歴を取得できませんでした/);
  p.run('Rental.requestJSON = async () => ({history:[]}); drawPriceHistory = () => {globalThis.retried = true}');
  await p.run('loadReportHistory(1, 1)');
  assert.equal(p.context.retried, true);
});

test('returning to the report resumes pending enrichment updates', async () => {
  const p = page('my-list.js');
  p.run(`
    globalThis.watched = [];
    watchEnrichment = id => watched.push(id);
    render = async () => {};
    Rental.requestJSON = async () => ({total:1,compare_rows:[{id:1}],pending_enrichment_ids:[1]});
  `);
  await p.run('loadAnalysis()');
  assert.deepEqual(Array.from(p.context.watched), [1]);
  await p.run('loadAnalysis(false)');
  assert.deepEqual(Array.from(p.context.watched), [1]);
});

test('private GET retries authentication and remembers the token for subsequent reads', async () => {
  const p = page('favorites.js');
  const tokens = [];
  let prompts = 0;
  p.context.prompt = () => { prompts++; return 'test-admin'; };
  p.context.fetch = async (url, options) => {
    const token = options.headers['X-Admin-Token'];
    tokens.push(token);
    return { ok: token === 'test-admin', status: token === 'test-admin' ? 200 : 401,
      json: async () => token === 'test-admin' ? [] : { error: '管理トークンが必要です' } };
  };
  await p.context.Rental.requestJSON('/api/status');
  await p.context.Rental.requestJSON('/api/status');
  assert.deepEqual(tokens, [undefined, 'test-admin', 'test-admin']);
  assert.equal(prompts, 1);
  assert.equal(p.storage.get('adminToken'), 'test-admin');
});

test('cancelling authentication leaves an explicit error and public reads do not prompt', async () => {
  const p = page('favorites.js');
  let prompts = 0;
  p.context.prompt = () => { prompts++; return null; };
  p.context.fetch = async url => ({ ok: url === '/api/dashboard', status: url === '/api/dashboard' ? 200 : 401,
    json: async () => url === '/api/dashboard' ? {} : { error: '管理トークンが必要です' } });
  await p.context.Rental.requestJSON('/api/dashboard');
  assert.equal(prompts, 0);
  await assert.rejects(p.context.Rental.requestJSON('/api/status'), /管理トークンが必要です/);
  assert.equal(prompts, 1);
  assert.equal(p.storage.has('adminToken'), false);
});

test('area charts respect the server comparison flag and omit incomparable rent from the radar', () => {
  const p = page('dashboard.js');
  p.run(`
    globalThis.chartOptions = {};
    initChart = el => ({setOption: option => chartOptions[el.id] = option});
    regionData = [
      {ward:'Fresh',prefecture:'東京都',avg_rent:100000,overall_score:60,rent_comparable:true,safety_score:60,convenience_score:60,environment_score:60},
      {ward:'Stale',prefecture:'東京都',avg_rent:80000,overall_score:85,rent_layout:'1LDK',rent_fetched_at:'2020-01-01',rent_comparable:false,safety_score:85,convenience_score:85,environment_score:85}
    ];
    valueMap();
    document.getElementById('region-selector-1').value = 'Fresh';
    document.getElementById('region-selector-2').value = 'Stale';
    renderRegionRadar();
  `);
  assert.deepEqual(Array.from(p.context.chartOptions['chart-value-map'].series[0].data, row => row.name), ['Fresh']);
  assert.equal(p.context.chartOptions['chart-region-radar'].radar.indicator.length, 3);
  p.run("document.getElementById('region-selector-2').value = ''; renderRegionRadar()");
  assert.equal(p.context.chartOptions['chart-region-radar'].radar.indicator.length, 4);
});

test('area reference table explains excluded benchmarks and escapes the note', () => {
  const p = page('dashboard.js');
  const tbody = {innerHTML:''};
  p.context.document.querySelector = () => tbody;
  p.run(`regionData = [{ward:'Test',avg_rent:100000,rent_comparable:false,rent_note:'古い相場 <img src=x onerror=bad()>',overall_score:60}]; renderTable()`);
  assert.ok(tbody.innerHTML.includes('古い相場 &lt;img'));
  assert.ok(!tbody.innerHTML.includes('<img'));
});
