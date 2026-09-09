"""Only compare rents with matching geography, layout and fee basis."""
from datetime import datetime, timedelta
from db_helper import query_all


def attach_benchmarks(listings):
    regions = query_all("SELECT * FROM region_stats")
    benchmarks = {(r["region_id"], r["layout"]): r for r in query_all("SELECT * FROM region_rent_benchmarks")}
    for listing in listings:
        matches = [r for r in regions if r["prefecture"] == listing.get("prefecture")
                   and r["city"] == listing.get("city") and r["ward"] == listing.get("ward")]
        region = matches[0] if len(matches) == 1 else None
        listing.update(region_id=region["id"] if region else None,
                       region_avg_rent=None, region_avg_area=None, region_avg_age=None,
                       region_comparison_cost=None, benchmark_source=None, benchmark_fetched_at=None,
                       benchmark_note="同じ地域・間取りの比較可能な家賃データがありません")
        if not region:
            continue
        if region.get("stats_method") == "measured":
            listing.update(region_avg_area=region["avg_area"], region_avg_age=region["avg_building_age"])
        benchmark = benchmarks.get((region["id"], (listing.get("layout") or "").strip().upper()))
        if not benchmark:
            continue
        listing.update(benchmark_source=benchmark["source_url"], benchmark_fetched_at=benchmark["fetched_at"])
        try:
            fresh = datetime.fromisoformat(benchmark["fetched_at"]).timestamp() >= (datetime.now() - timedelta(days=180)).timestamp()
        except (TypeError, ValueError):
            fresh = False
        if not fresh:
            listing["benchmark_note"] = "相場データが古いため比較を保留しています（180日以内の更新が必要）"
            continue
        basis = benchmark["includes_management_fee"]
        if basis is None:
            listing["benchmark_note"] = "相場の管理費・共益費の扱いが不明なため、割安・割高の判定を保留しています"
            continue
        cost = listing.get("total_monthly_cost" if basis else "rent")
        if cost is None:
            listing["benchmark_note"] = "比較に必要な家賃・管理費が未取得です"
            continue
        listing.update(region_avg_rent=benchmark["rent"], region_comparison_cost=cost,
                       benchmark_note=f"同じ{benchmark['layout']}の相場 / 管理費・共益費{'込み' if basis else '別'}")
    return listings
