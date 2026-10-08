"""Only compare rents with matching geography, layout and fee basis."""
from datetime import datetime
import time
from db_helper import query_all


def benchmark_issue(benchmark):
    """One validity rule for reports, public rankings and region charts."""
    if not benchmark or not benchmark.get("rent") or benchmark["rent"] <= 0:
        return "同じ間取りの比較可能な家賃データがありません"
    try:
        age = time.time() - datetime.fromisoformat(benchmark["fetched_at"]).timestamp()
        fresh = -300 <= age <= 180 * 86400
    except (TypeError, ValueError, OverflowError):
        fresh = False
    if not fresh:
        return "相場データが古いか取得日が不正なため比較を保留しています（180日以内の更新が必要）"
    if benchmark.get("includes_management_fee") not in (0, 1):
        return "相場の管理費・共益費の扱いが不明なため、割安・割高の判定を保留しています"
    return None


def attach_region_benchmarks(regions):
    benchmarks = {r["region_id"]: r for r in query_all("SELECT * FROM region_rent_benchmarks WHERE layout='1LDK'")}
    for region in regions:
        benchmark = benchmarks.get(region["id"])
        issue = benchmark_issue(benchmark)
        if benchmark:
            region.update(avg_rent=benchmark["rent"], rent_layout="1LDK", rent_source=benchmark["source_url"],
                          rent_fetched_at=benchmark["fetched_at"])
        # Rankings use one common basis; fee-inclusive rents remain reference data.
        if not issue and benchmark["includes_management_fee"] != 0:
            issue = "管理費込みの参考値です。順位は管理費別の1LDK相場で比較しています"
        region.update(rent_comparable=issue is None,
                      rent_note=issue or "1LDK / 管理費・共益費別 / 180日以内の取得値")
    return regions


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
        issue = benchmark_issue(benchmark)
        if issue:
            listing["benchmark_note"] = issue
            continue
        basis = benchmark["includes_management_fee"]
        cost = listing.get("total_monthly_cost" if basis else "rent")
        if cost is None:
            listing["benchmark_note"] = "比較に必要な家賃・管理費が未取得です"
            continue
        listing.update(region_avg_rent=benchmark["rent"], region_comparison_cost=cost,
                       benchmark_note=f"同じ{benchmark['layout']}の相場 / 管理費・共益費{'込み' if basis else '別'}")
    return listings
