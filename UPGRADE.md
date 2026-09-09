# Reliability update

- Startup creates and migrates the database without any external API or scraping.
  Existing databases are backed up to `db/backups/` before the first migration.
  Duplicate favorites are merged, notes are preserved, and original records are
  kept in `migration_archive`. New favorites and scores are unique per listing.
- Old price history is retained as `legacy` because its timestamps referred to
  the subsequent refresh. Charts use actual observations, starting with the
  latest known price and subsequent refreshes.
- All API writes require `ADMIN_TOKEN` when it is configured. This includes
  imports, refreshes, favorites, settings and deletion. Read access is unchanged.
- Missing deposit/key money is unknown, not zero. Initial-cost totals and that
  score dimension remain unavailable until both amounts are known. Decimal
  month amounts such as `0.5ヶ月` are supported.
- Rent comparisons require matching prefecture/city/ward and layout, a known
  management-fee basis, and data fetched within 180 days. Legacy and manually
  estimated rents remain visible as reference values. Old fixed area/age values
  are not presented as measured averages.

To refresh rent benchmarks explicitly, run `python scripts/seed_regions.py`.
It records each layout separately and preserves previous data on fetch failure.
If the source does not state its fee basis clearly, the comparison stays pending.
Public transaction/hazard data is preserved when refreshing rent benchmarks.

Import/refresh returns the basic report first. Optional commute and resident
reviews run in a bounded background queue. The page checks for completion.
Commute results are cached for 24 hours (failed lookups for 5 minutes). Jobs are
local to the single Gunicorn process; after a restart or a full queue, use the
refresh action to retry. Keep `--workers 1 --threads 4` as in `Procfile`.
Saving preferences recalculates scores using cached commute results immediately.

Tests always use temporary databases and mock external HTTP. Run:

```sh
python -m pytest tests/ -q
node --test tests/frontend.test.cjs
```

The GitHub Actions workflow runs both suites. No database or API keys are needed.
