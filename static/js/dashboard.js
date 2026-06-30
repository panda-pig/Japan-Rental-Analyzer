async function load() {
  const res = await fetch("/api/dashboard");
  const d = await res.json();
  const metrics = [
    ["総物件数", d.total_listings], ["予算内", d.budget_match_count],
    ["2階以上", d.floor_2plus_count], ["ペット可", d.pet_allowed_count],
    ["平均月額", d.average_total_cost?.toLocaleString()], ["平均面積", d.average_area],
    ["平均推薦分", d.average_score], ["新着", d.new_listing_count],
    ["値下がり", d.price_drop_count], ["お気に入り", d.favorite_count],
  ];
  document.getElementById("metrics").innerHTML = metrics.map(([l, v]) =>
    `<div class="metric"><div class="num">${v ?? 0}</div><div class="label">${l}</div></div>`).join("");

  bar("chart-area-rent", "エリア別平均月額", d.area_rent_data, true);
  bar("chart-rent-dist", "家賃分布", d.rent_distribution);
  scatter("chart-scatter", "面積 vs 月額", d.scatter_data);
  bar("chart-top10", "推薦分 Top10", d.top_score_listings.map(x => ({ name: x.title, value: x.total_score })), true);
  pie("chart-layout", "間取り比率", d.layout_distribution);
  pie("chart-platform", "プラットフォーム比率", d.platform_distribution);
  bar("chart-floor", "階数分布", d.floor_distribution);
  bar("chart-age", "築年数分布", d.age_distribution);
  pie("chart-status", "ステータス分布", d.status_distribution);
  if (d.price_history_chart && d.price_history_chart.length) {
    line("chart-price-history", "価格履歴", d.price_history_chart);
  } else {
    document.getElementById("chart-price-history").innerHTML =
      '<div style="text-align:center;padding:120px;color:#999;">暂无データ(価格履歴は複数回取得後に表示されます)</div>';
  }
}

function bar(id, title, data, horizontal = false) {
  const ch = echarts.init(document.getElementById(id));
  const opt = {
    title: { text: title, left: "center", textStyle: { fontSize: 14 } },
    tooltip: { trigger: "axis" },
    series: [{ type: "bar", data: data.map(x => x.value) }],
  };
  if (horizontal) {
    opt.xAxis = { type: "value" };
    opt.yAxis = { type: "category", data: data.map(x => x.name) };
  } else {
    opt.xAxis = { type: "category", data: data.map(x => x.name) };
    opt.yAxis = { type: "value" };
  }
  ch.setOption(opt);
}

function pie(id, title, data) {
  const ch = echarts.init(document.getElementById(id));
  ch.setOption({
    title: { text: title, left: "center", textStyle: { fontSize: 14 } },
    tooltip: { trigger: "item" },
    series: [{ type: "pie", radius: "60%", data: data.map(x => ({ name: x.name, value: x.value })) }],
  });
}

function scatter(id, title, data) {
  const ch = echarts.init(document.getElementById(id));
  ch.setOption({
    title: { text: title, left: "center", textStyle: { fontSize: 14 } },
    xAxis: { name: "面積(㎡)", type: "value" },
    yAxis: { name: "月額(円)", type: "value" },
    tooltip: { trigger: "item", formatter: p => p.data[2] },
    series: [{ type: "scatter", symbolSize: 8, data: data.map(x => [x.x, x.y, x.title]) }],
  });
}

function line(id, title, data) {
  const ch = echarts.init(document.getElementById(id));
  ch.setOption({
    title: { text: title, left: "center", textStyle: { fontSize: 14 } },
    xAxis: { type: "category", data: data.map(x => x.name) },
    yAxis: { type: "value" },
    series: [{ type: "line", data: data.map(x => x.value) }],
  });
}

load();