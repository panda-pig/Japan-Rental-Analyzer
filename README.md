<div align="center">

# Japan Rental Analyzer

**Paste a listing URL. Get rent, hazard risk and neighbourhood reviews in one report.**

Tokyo · Yokohama · Kawasaki rental decision tool

### [▶ Try it live](https://tokyo-yokohama-rental-intelligence.onrender.com)

[Source](https://github.com/panda-pig/Japan-Rental-Analyzer) · **English** · [日本語](README.ja.md) · [简体中文](README.zh-CN.md)

</div>

![Home](screenshots/hero.png)

<sub>Screenshots use sample listings. Area rents, transaction prices and hazard levels are real.<br>
The demo runs on Render's free tier, so the first request after a quiet spell takes about a minute to wake up.</sub>

---

Apartment hunting in Japan means opening the same listing on four different
sites, then guessing whether the rent is fair, whether the area floods, and
what it is actually like to live near that station. This tool answers all
three from a single pasted URL.

## Features

### 1. Paste a URL, get a full report

Works with SUUMO, LIFULL HOME'S, athome and Yahoo! Real Estate listing pages.
The parser pulls rent, management fee, deposit, key money, size, layout,
floor, building age, walking minutes and amenities.

![Report](screenshots/report.png)

- **8-dimension score** — budget, size, commute, floor, pets, station
  distance, building age and upfront cost, each weighted by your own
  preferences and normalised to 0–100
- **Deviation from the area average** — how many yen and what percent above
  or below the local rate
- **Upfront cost breakdown** — deposit, key money, agency fee, prepaid rent
  and fixed extras as a donut
- **Condition checklist** — which of your eight criteria the listing meets,
  with the misses greyed out rather than hidden
- **Price history** — refresh a listing and the change is tracked on a line

### 2. Public data and resident reviews

Shown alongside the listing, deliberately **excluded from the score** — these
describe the area, not the property.

- **Transaction prices** — median price per m² and transaction count for
  second-hand condominiums, from the MLIT Real Estate Information Library
  (48 Kanto wards, last four quarters)
- **Hazard risk** — maximum expected flood depth plus the number of landslide
  warning zones, summarised as low / mid / high
- **Station reviews** — resident survey scores from LIFULL HOME'S Machimusubi
  (transport, safety, shopping, childcare, nature) for the nearest station

### 3. A pool that fills up as you paste

![Pool](screenshots/pool.png)

Every listing you analyse stays in the pool. Click a row to switch the report
above. Sort by score, rent, size, price per m² or deviation from the area
rate. Check two to four and compare them side by side.

![Compare](screenshots/compare.png)

The comparison overlays the eight-dimension radars and lines up every field in
a table. Values that were never captured read as 未取得 rather than being
silently shown as zero.

### 4. Favourites and progress

![Favourites](screenshots/favorites.png)

Star a listing and track it through 気になる → 内見 → 申込, with notes.

### 5. Area data, useful before you have any listings

![Area](screenshots/area.png)

A value map plotting rent against overall rating — top-left is cheap and
well-rated — plus rent rankings for the 23 Tokyo wards and Yokohama, a radar
to compare two areas, and a sortable table of all 56 areas.

## Data sources

| Data | Source | How it is fetched |
|---|---|---|
| Listing details | Only pages the user pastes | One page at a time, no crawling |
| Area average rent | [SUUMO rent statistics](https://suumo.jp/chintai/soba/) | Low frequency, seeded manually |
| Transaction prices | [MLIT Real Estate Information Library](https://www.reinfolib.mlit.go.jp/) (XIT001) | Official API (key required) |
| Hazard risk | Same library (XKT026 flood / XKT029 landslide) | Official API tiles |
| Station reviews | [LIFULL HOME'S Machimusubi](https://www.homes.co.jp/machimusubi/) | Aggregate scores only, never review text |

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.14 / Flask |
| Database | SQLite, 11 tables |
| Scraping | requests / BeautifulSoup4, robots.txt respected, polite sleep |
| Public data | Real Estate Information Library API + XYZ tile maths |
| Station matching | pykakasi (kanji → romaji) with normalisation and fuzzy matching |
| Commute | NAVITIME Transfer API (optional) |
| Frontend | Jinja2 / vanilla JS / ECharts 5 / wordcloud2.js |
| Tests | pytest, 106 tests |

Fetch targets are restricted to an allow-list matched on the parsed hostname,
private addresses are refused and redirects are re-checked at every hop.
Scraped text is escaped before it reaches the DOM. Destructive and
configuration endpoints require `ADMIN_TOKEN` when it is set.

The interface targets WCAG 2.1 AA: keyboard-operable tables, text
alternatives for every chart, live regions for form results, AA contrast, 44px
touch targets and `prefers-reduced-motion` support.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env
#   REINFOLIB_API_KEY   : Real Estate Information Library (optional)
#   NAVITIME_CLIENT_KEY : commute time (without it the commute axis is skipped)
#   ADMIN_TOKEN         : required for destructive routes when set

python scripts/init_db.py
python scripts/seed_regions.py
python scripts/fetch_public_data.py   # only with REINFOLIB_API_KEY

python app.py    # http://127.0.0.1:5000
```

```bash
.venv/bin/pytest tests/ -q
```

Batch scraping is a command-line job, not a route:
`python scripts/run_scrape.py` works off the rows in `source_configs`.
When `ADMIN_TOKEN` is set, the pages ask for it once on the first
destructive action and remember it in the browser.

## Deploying to Render

1. New → Web Service → connect this repository
2. Build `pip install -r requirements.txt`,
   start `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1`
3. Persistent disk 1 GB mounted at `db`
4. Environment: `DB_PATH=/opt/render/project/src/db/database.db`,
   `REINFOLIB_API_KEY`, `ADMIN_TOKEN`
5. Once, from the shell:
   `python scripts/fetch_public_data.py && python scripts/fetch_station_reviews.py`

## Compliance

- Only pages the user explicitly pastes are parsed. There is no cross-site crawl.
- robots.txt is checked before each fetch and Disallow is honoured, with a
  polite sleep between requests.
- CAPTCHAs and other bot defences are never bypassed; sources that use them
  are not supported.
- Only aggregate review scores are stored — never review text or personal data.
- Public data and resident reviews are attributed in the UI and excluded from
  the property score.
- Built for personal research. The data is not redistributed commercially.
