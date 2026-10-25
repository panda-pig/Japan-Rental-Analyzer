# Reliability update

- Startup creates and migrates the database without any external API or scraping.
  Existing databases are backed up to `db/backups/` before the first migration.
  Duplicate favorites are merged, notes are preserved, and original records are
  kept in `migration_archive`. New favorites and scores are unique per listing.
- Old price history is retained as `legacy` because its timestamps referred to
  the subsequent refresh. Charts use actual observations, starting with the
  latest known price and subsequent refreshes.
- Private API reads and all API writes require `ADMIN_TOKEN` when configured.
  This includes listings, price history, comparisons, favorites and settings.
  On Render, a missing token returns 503 for private APIs instead of allowing
  anonymous access. The browser requests the token on first private access.
  Private responses use `Cache-Control: private, no-store`.
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
`gunicorn.conf.py` applies these defaults to Render services whose saved start
command does not include thread and timeout options.
Saving preferences recalculates scores using cached commute results immediately.
Changing the destination also queues a new commute lookup. Requests arriving
during a pending job are coalesced into another pass; an old origin/destination
lookup cannot overwrite the score for the new route. The analysis page resumes
checking pending jobs when reopened.

## Parser and report corrections

- Detail parsers retain missing deposits and key money as unknown, including
  unsupported values and dashes. SUUMO accepts decimal month amounts and
  full-width characters. Explicit zero amounts remain zero.
- Pet permission has three states: allowed, prohibited and unknown. Unrelated
  restrictions such as musical instruments being prohibited do not cancel pet
  permission. Unknown uses the existing partial pet score and is labelled in
  the report.
- Station names and walking minutes are selected together. Bus travel and the
  walk from a bus stop do not count as walking time to a station.
- Report achievement labels and the feature cloud follow saved floor, walking
  and building-age limits.
- `/api/my-list` no longer includes `price_history`. The report requests
  `/api/listings/<id>/price-history`, returning `{listing_id, history}` for the
  selected listing only. Switching reports reuses that history until the pool
  is refreshed; late responses cannot update a different listing's chart.

No schema migration is required for these corrections. Previously parsed
fields are not guessed or rewritten: use a listing's refresh action to fetch
its current source values and replace any earlier incorrect fields.

## Privacy and snapshot integrity

- The public `/api/dashboard` returns only region information. Personal counts,
  listing distributions and price changes are no longer included. Use the
  authenticated `/api/my-list` for the personal report.
- Refreshing or reimporting an existing listing returns 422 with
  `preserved: true` and `missing_fields` if a previously known field cannot be
  confirmed. The entire previous snapshot, score and price history are retained.
  A missing amenity tag cannot establish removal of a confirmed amenity.
  Explicit zero fees and prohibited pet conditions remain valid updates.
- New listing URLs drop fragments and common tracking parameters (`utm_*`,
  `fbclid`, `gclid`, `yclid`, `msclkid`) while preserving identifying parameters
  and their encoding. Imports also match legacy tracked URLs, preserving IDs,
  favorites and history. Existing duplicate rows are not deleted or merged;
  refreshing one always targets the requested ID.
- The homepage ranking and value map use the same 180-day validity check as
  reports, on a uniform 1LDK rent excluding management fees. Unknown fee bases,
  stale dates and future dates beyond five minutes are excluded. Other values
  remain visible with a reference note; the radar omits rent when its selected
  regions do not all have comparable benchmarks.
- Every listing redirect checks the destination's robots.txt before fetching
  the destination, in addition to hostname and public-IP checks.

These changes require no database migration. Set `ADMIN_TOKEN` in Render before
deploying, and use the same token when the browser prompts for private access.

## Field parsing and request reliability

- Money conversion now uses the unit attached to the matched amount. A value
  such as `5,000円（敷金10万円）` stays 5,000 yen instead of being multiplied by
  another field's `万`. Malformed text without an amount stays unknown.
- Unit floors and building heights are parsed independently. `5階建` means
  the unit floor is unknown, and a building basement no longer overrides an
  explicit unit floor. Full-width notation, `B1F` and floor ranges are supported;
  ranges use the lowest occupied floor for scoring.
- robots.txt redirects are checked for allowed hosts and public destination
  addresses before each request, with a bounded redirect count. Timeouts,
  authentication failures, rate limits and server errors stop the listing fetch.
  Only an explicit 404 or 410 is treated as an absent rules file.
- A valid management token remains saved when an authenticated operation returns
  an ordinary validation error. The operation's error is still shown; rejected
  tokens are removed.

No database migration is required. These parsing changes apply to new imports
and complete refreshes. Previously saved fields are not guessed or rewritten;
incomplete source pages still preserve the previous snapshot.

## Cost totals and editing reliability

- Initial-cost estimates use decimal arithmetic and truncate each calculated
  component to integer yen. For example, 50,000 yen at a 0.29 brokerage rate
  yields 14,500 yen. The report chart consumes the server's components instead
  of independently rounding them. Detail, comparison and personal-report APIs
  derive the total from the same current preferences, including for older rows.
  Unknown deposits or key money remain unknown; explicit zero amounts stay zero.
- Favorites save changes in order for each listing. Status updates and deletions
  preserve the other cards' drafts and focus. Deletion waits for pending saves,
  and failed fields remain marked as unsaved until successfully retried.
- Numeric settings must contain an explicit number before saving. A blank input
  is no longer silently treated as zero; an explicit zero remains valid where
  allowed. The destination station can still be left blank.

No database migration is required. Saved cost estimates are updated on refresh
or score recalculation; report reads derive the current total without modifying
the stored listing.

Tests always use temporary databases and mock external HTTP. Run:

```sh
python -m pytest tests/ -q
node --test tests/frontend.test.cjs
```

The GitHub Actions workflow runs both suites. No database or API keys are needed.
Portable parser tests use synthetic committed fixtures. Four additional tests
use optional local `*_real.html` snapshots and skip when those files are absent.
