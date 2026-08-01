# cloud-database — Database Selection & Analysis Tool

**A bilingual tool for exploring the global database ecosystem, built to streamline database selection and technical research.**

[DB-Engines](https://db-engines.com/en/ranking) maintains the industry's most authoritative database popularity ranking, but its English-only interface and manual browsing make comparative analysis time-consuming. This project scrapes the full ranking, augments it with curated Chinese translations, and compiles everything into a **single self-contained HTML file** — enabling one-stop search, filtering, and comparison across 400+ database systems.

Data is sourced from the DB-Engines ranking page (currently 434 systems, July 2026), covering rank, database model, description, developer, initial/current release, and license. All fields are translated into Chinese and injected into a single-file HTML template, producing an **offline-ready** analysis page.

## Features

More than a data listing — the page is designed around **selection and analysis workflows**:

- 📊 **Ecosystem overview** — model distribution bar chart and license donut chart reveal industry trends at a glance
- 🔍 **Full-text search** — matches name, description, and developer in both English and Chinese
- 🏷️ **Faceted filtering** — cross-filter by database model (relational / document / graph / vector …), license, release decade, and rank range (Top 10/50/100)
- 📈 **Comparative analysis** — compare systems within the same model: who leads the ranking, who is still actively maintained
- 🌐 **Bilingual UI** — interface and data toggle between Chinese and English, accessible to international teams
- 📦 **Offline-ready** — a single `index.html` with zero external dependencies; open in any browser, drop into an internal wiki or shared drive

## Use Cases

- **Technology selection** — survey competing solutions and identify mainstream options before adopting a database
- **Architecture research** — cite authoritative ranking data in design documents and presentations
- **Team sharing** — walk through the database landscape and surface emerging systems worth watching
- **Personal learning** — track industry dynamics (e.g., the recent rise of vector databases)

## Requirements

- Python 3.10+ (the code uses modern type-annotation syntax such as `int | None`)
- Packages: `requests`, `beautifulsoup4`, `lxml`

```bash
pip install requests beautifulsoup4 lxml
```

> Behind a corporate proxy, SSL verification may fail. Set `CURL_CA_BUNDLE` to a valid CA bundle;
> otherwise the scraper automatically disables certificate verification (public data only).

## Data Pipeline

### Initial Full Build

```bash
# 1. Scrape the ranking page + each system's detail page (~434 requests, 1.5s apart, ~15 min)
python scrape_db_engines.py                 # all systems; --top 20 for the top 20 only

# 2. Re-fetch records whose detail fields are empty (network timeouts)
python retry_failed.py

# 3. Clean up: fix name suffixes, normalize model names, re-translate enum fields
python fix_data.py

# 4. Translate description / developer into Chinese (two options, see below)

# 5. Inject data and generate the final page
python build_html.py                        # produces index.html
```

### Chinese Translation (LLM-assisted, two options)

`description` / `developer` require LLM translation; `database_model` / `license` are handled by built-in enumeration tables.

**Option A: range-based parallel translation** (`translate_range.py`; multiple agents can work on disjoint ranges concurrently)

```bash
python translate_range.py --start 0 --end 75            # prints the pending list to stdout
# after the LLM writes batch-0-75.json:
python translate_range.py --start 0 --end 75 --merge batch-0-75.json
```

**Option B: sequential batch translation** (`translate_cn.py`, 20 records per batch, offset tracked)

```bash
python translate_cn.py --extract                        # prints the current batch
# after the LLM writes translations-batch.json:
python translate_cn.py --merge translations-batch.json
python translate_cn.py --status                         # check progress
```

Progress is persisted in `.translate-progress.json`.

### Monthly Incremental Update

DB-Engines updates its ranking monthly. The incremental flow fetches only the ranking page (1 request), reuses detail-page data for existing systems, and scrapes detail pages **only for newly added systems**:

```bash
# 1. Preview changes (added / removed / renamed / rank shifts), writes nothing
python incremental_update.py --diff

# 2. Apply the update; if new systems exist, emits pending-translations.json
python incremental_update.py --apply

# 3. After translating the new systems, merge back
python incremental_update.py --merge-translations pending-translations.json

# 4. Normalize + rebuild the page
python fix_data.py
python build_html.py
```

> Note: incremental updates do not refresh detail fields (`current_release`, `license`, …) for
> existing systems — DB-Engines detail pages change infrequently. For a full refresh, re-run `scrape_db_engines.py`.

## File Overview

| File | Purpose |
|---|---|
| `scrape_db_engines.py` | Full scrape: ranking page + detail pages → `database-info.json` |
| `retry_failed.py` | Re-fetch records with empty detail fields (proxy timeouts) |
| `fix_data.py` | Cleanup: fix `dbms` names, normalize `database_model`, enum translation fallback |
| `translate_range.py` | Range-based `*_cn` translation (parallel-safe), with model/license enum tables |
| `translate_cn.py` | Sequential batch translation (20 per batch), tracks `.translate-progress.json` |
| `incremental_update.py` | Monthly incremental update: diff preview → apply → merge translations |
| `build_html.py` | Injects `database-info.json` into `index.template.html` → `index.html` |
| `index.template.html` | Page template (with `__DATA_PLACEHOLDER__`); all styles and logic inline |
| `index.html` | Final artifact: the offline analysis page |
| `database-info.json` | Core dataset: 434 records with bilingual fields |
| `batch-*.json` / `translations-batch.json` | LLM translation batches, merged back into the dataset |

## Data Structure

Each record in `database-info.json`:

```json
{
  "rank": 1,
  "dbms": "Oracle",
  "database_model": "Relational DBMS, Document store, ...",
  "database_model_cn": "关系型数据库，文档型数据库，...",
  "detail_url": "https://db-engines.com/en/system/Oracle",
  "description": "Widely used RDBMS",
  "description_cn": "广泛使用的关系型数据库",
  "website": "https://www.oracle.com/database/",
  "developer": "Oracle",
  "developer_cn": "甲骨文（Oracle）",
  "initial_release": "1980",
  "current_release": "26ai",
  "license": "commercial",
  "license_cn": "商业许可"
}
```

Top-level metadata includes `source`, `ranking_month`, and `count`.

## Implementation Notes

- **Primary key**: incremental updates match systems by `detail_url` — stable across vendor renames.
- **Model-name normalization**: the ranking page uses short names for single-model systems (`Relational`) but full names inside multi-model popups (`Relational DBMS`). Both are normalized to the full form before comparison, preventing false "model changed" detections during incremental updates.
- **Vendor-suffix cleanup**: some `<a>` elements embed a "Detailed vendor-provided information available" popup that must be stripped from the display name.
- **Marketing-copy filter**: a few vendors stuff paragraph-length copy into the model infobox; entries longer than 30 characters (the longest standard model name) are discarded.
- **Injection safety**: `build_html.py` escapes `</` as `<\/` in the JSON payload so embedded `</script>` sequences cannot close the script block prematurely; re-injection into an already-populated template is idempotent.

## Data Source

- Ranking & details: [DB-Engines Ranking](https://db-engines.com/en/ranking) (updated monthly)
- This project is for personal learning and internal team analysis only. Requests are throttled to 1.5s by default; please respect the target site's robots.txt and terms of use.
