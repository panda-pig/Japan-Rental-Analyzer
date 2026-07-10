const WEIGHT_FIELDS = [["budget_weight", "予算"], ["area_weight", "面積"], ["commute_weight", "通勤"],
  ["floor_weight", "階数"], ["pet_weight", "ペット"], ["station_weight", "駅距離"],
  ["age_weight", "築年数"], ["initial_cost_weight", "初期費用"]];

function updateTotal() {
  let t = 0;
  for (const [k] of WEIGHT_FIELDS) { const el = document.getElementById("w_" + k); if (el) t += (+el.value || 0); }
  const span = document.getElementById("weight-total");
  if (span) { span.textContent = t; span.style.color = t === 100 ? "var(--good)" : "var(--text-muted)"; }
}

function toast(msg, ok = true) {
  const el = document.getElementById("save-msg");
  if (!el) return;
  el.textContent = msg;
  el.style.color = ok ? "var(--good)" : "var(--bad)";
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.textContent = ""; }, 3000);
}

async function load() {
  const p = await (await fetch("/api/preferences")).json();
  const set = (id, v) => document.getElementById(id).value = v ?? "";
  set("p_max_cost", p.max_total_monthly_cost);
  set("p_min_area", p.min_area_m2);
  set("p_ideal_area", p.ideal_area_m2);
  set("p_min_floor", p.min_floor);
  set("p_max_walk", p.max_walk_minutes);
  set("p_max_age", p.max_building_age);
  set("p_target_station", p.target_station);
  set("p_broker", p.broker_fee_rate);
  set("p_prepaid", p.prepaid_rent_months);
  set("p_misc", p.misc_cost);
  document.getElementById("weights").innerHTML = WEIGHT_FIELDS.map(([k, l]) =>
    `<div><label>${l}</label><input type="number" id="w_${k}" value="${p[k]}" oninput="updateTotal()"></div>`).join("");
  updateTotal();
}

function collect() {
  const v = id => document.getElementById(id).value;
  const data = {
    max_total_monthly_cost: +v("p_max_cost"), min_area_m2: +v("p_min_area"),
    ideal_area_m2: +v("p_ideal_area"), min_floor: +v("p_min_floor"),
    max_walk_minutes: +v("p_max_walk"), max_building_age: +v("p_max_age"),
    target_station: v("p_target_station"), broker_fee_rate: +v("p_broker"),
    prepaid_rent_months: +v("p_prepaid"), misc_cost: +v("p_misc"),
  };
  for (const [k] of WEIGHT_FIELDS) data[k] = +document.getElementById("w_" + k).value;
  return data;
}

async function persist() {
  await fetch("/api/preferences", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(collect()) });
}

async function save() {
  await persist();
  toast("保存しました");
}

async function recalc() {
  toast("保存して再計算中…");
  await persist();
  await fetch("/api/scores/recalculate", { method: "POST" });
  toast("再計算が完了しました");
}

load();
