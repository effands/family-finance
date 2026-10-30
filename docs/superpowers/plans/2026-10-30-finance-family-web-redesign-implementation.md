# Finance Family Web Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Finance Family web pages and add practical financial filtering, weekly/monthly summaries, CSV import, and downloadable exports without adding runtime dependencies.

**Architecture:** Keep the existing WSGI app and SQLite database. Move presentation into a local CSS asset, add small HTML helpers and query parsing in `passenger_wsgi.py`, and use standard-library CSV/HTML responses for import/export.

**Tech Stack:** Python WSGI, SQLite, HTML5, CSS3, standard-library `csv`, existing project tests.

**Spec:** `docs/superpowers/specs/2026-10-30-finance-family-web-redesign-design.md`

## Global Constraints

- No frontend framework, npm, CDN, or new runtime dependency.
- Preserve existing endpoints and Telegram behavior.
- Keep all Rupiah values as integers and escape transaction data before HTML rendering.
- UI language remains Bahasa Indonesia.
- Import accepts only validated CSV fields and never overwrites existing rows by default.

## Review Focus

- Invalid date/filter combinations must fail safely and show an Indonesian explanation.
- CSV formula-like values must be escaped or rejected rather than becoming spreadsheet formulas.
- Importing the same file twice must not silently duplicate rows when an import key is present.
- Empty result sets must have a useful empty state, not a broken table.
- Mobile and print layouts must remain usable with long descriptions and category names.

### Task 1: Query and report support

**Files:**
- Modify: `src/database.py`
- Modify: `src/reports.py`
- Test: `tests/test_reports.py`

**Interfaces:**
- Produces `Database.list_transactions(chat_id, start_date=None, end_date=None, transaction_type=None, category=None, search=None, sort_by="transaction_date", sort_dir="desc")`.
- Produces report summary data for selected period: income, expense, balance, category totals, user totals, transaction count.

- [ ] Add tests for filtered date ranges, type/category/search filters, sorting, and empty periods.
- [ ] Run the focused report/database tests and confirm they fail for missing interfaces.
- [ ] Implement parameterized SQLite queries with an allow-list for sortable columns and directions.
- [ ] Implement weekly/monthly summary helpers using existing transaction data.
- [ ] Run `pytest tests/test_database.py tests/test_reports.py -q` and confirm PASS.
- [ ] Commit `feat: add web transaction filters and period summaries`.

### Task 2: Local design system CSS

**Files:**
- Create: `static/app.css`
- Modify: `passenger_wsgi.py`

**Interfaces:**
- Produces `_html_page(title, body, extra_head="")` that references `/keuangan/static/app.css`.
- Provides semantic classes for auth, layout, metric cards, filters, table, badges, buttons, alerts, empty states, responsive, and print.

- [ ] Add the CSS file with tokens, responsive layouts, focus states, reduced-motion handling, and print rules.
- [ ] Replace the current one-line inline CSS with the local asset reference and semantic HTML shell.
- [ ] Add a consistent web title: `Finance Family — Catatan Keuangan Keluarga`.
- [ ] Run a local WSGI smoke check that the shell includes the stylesheet and title.
- [ ] Commit `style: add local Finance Family design system`.

### Task 3: Login and dashboard redesign

**Files:**
- Modify: `passenger_wsgi.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Login remains POST password-based and redirects to `/keuangan/dashboard` on success.
- Dashboard accepts `period=week|month|all|custom`, `start`, `end`, `type`, `category`, `q`, `sort`, and `dir` query values.

- [ ] Add WSGI tests for login success/failure, query parameter rendering, and empty results.
- [ ] Implement polished login page with clear error state and no password leakage.
- [ ] Implement dashboard header, period selector, filter form, three metrics, category/user summaries, and sortable transaction table.
- [ ] Add clear/reset filter links and preserve selected values in the form.
- [ ] Run `pytest tests/test_web.py -q` and confirm PASS.
- [ ] Commit `feat: redesign login and dashboard`.

### Task 4: Export and import workflows

**Files:**
- Modify: `passenger_wsgi.py`
- Modify: `src/database.py`
- Test: `tests/test_web.py`, `tests/test_database.py`

**Interfaces:**
- GET `/keuangan/export.csv` returns an attachment with UTF-8 CSV headers.
- GET `/keuangan/excel` renders a styled, filter-aware export table.
- POST `/keuangan/import` accepts multipart CSV and reports inserted/skipped/invalid rows.

- [ ] Add tests for CSV headers, Rupiah integer values, formula-prefix sanitization, invalid rows, and duplicate import keys.
- [ ] Implement CSV serializer with `Content-Disposition: attachment` and spreadsheet-safe text handling.
- [ ] Implement CSV parser with required columns, date/type/amount validation, category fallback, and per-row error reporting.
- [ ] Add import form and export controls to dashboard/export pages.
- [ ] Run the full test suite and confirm PASS.
- [ ] Commit `feat: add practical import and export workflows`.

### Task 5: Verification and deployment handoff

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-10-30-finance-family-web-redesign-design.md`

- [ ] Document filter meanings, weekly/monthly selection, CSV format, import safety, and download/share options.
- [ ] Run `pytest -q`.
- [ ] Inspect generated HTML/CSS for desktop, mobile, and print behavior.
- [ ] Verify existing Telegram bot commands and database tests remain green.
- [ ] Commit `docs: document Finance Family web dashboard controls`.
