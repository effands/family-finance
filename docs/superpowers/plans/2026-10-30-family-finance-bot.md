# Family Finance Telegram Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a free, runnable Telegram family-finance bot in Python that parses Indonesian natural-language transactions, stores them in SQLite, and serves secure multi-user reports and transaction management commands.

**Architecture:** Telegram updates enter thin handlers. Pure parser and categorizer modules convert text into typed transaction data; a SQLite repository owns persistence; report services query aggregates and render Indonesian monospace output. Configuration, whitelist, rate limiting, and logging remain at the application boundary.

**Tech Stack:** Python 3.11+, python-telegram-bot, FastAPI health endpoint, SQLite, pytest, python-dotenv, zoneinfo, Docker/systemd deployment documentation.

**Spec:** `docs/superpowers/specs/2026-10-30-family-finance-bot-design.md`

## Global Constraints

- UI bot uses casual Bahasa Indonesia.
- All money is integer Rupiah and displayed with dot separators.
- Parser is local rules-based; no paid LLM dependency.
- Default timezone is `Asia/Jakarta`, configurable by `TIMEZONE`.
- Only `ALLOWED_CHAT_IDS` may use the bot.
- Telegram token is loaded from `.env`; never hardcode it.
- Rate limit defaults to 30 messages/minute/user.
- Group reports combine users; private-chat reports scope to the user; `/laporan saya` scopes to the requesting user.
- Ambiguous/no amount/zero amount creates no transaction and asks for clarification.
- `/undo` removes the requester’s latest same-chat transaction within five minutes.
- Dates support today, `kemarin`, `tgl/tanggal N`, `D/M`, `DD-MM-YYYY`, and ISO dates.
- Weeks run Monday through Sunday.

## Review Focus

- Mixed thousand/decimal notation such as `1.5jt`, `1,5jt`, and `1.250.000`; parser tests pin the expected integer Rupiah conversion in Task 2.
- Amount embedded before/after the description and Indonesian filler words; parser tests pin clean descriptions in Task 2.
- Conflicting income/expense keywords; parser tests pin income precedence in Task 2.
- Cross-chat and cross-user edit/delete attempts; repository/handler tests pin authorization in Task 4.
- Empty reports and malformed date ranges; report tests pin safe, readable output in Task 5.

### Task 1: Project scaffold and configuration

**Files:**
- Create: `.env.example`
- Create: `requirements.txt`
- Create: `pyproject.toml`
- Create: `src/__init__.py`
- Create: `src/config.py`
- Create: `src/logging_config.py`
- Create: `data/.gitkeep`
- Create: `.gitignore`

**Interfaces:**
- Produces `Settings` and `load_settings() -> Settings`.
- Produces dependency list and pytest configuration for later tasks.

- [ ] **Step 1: Add dependency and test configuration**
  Include `python-telegram-bot[job-queue]`, `python-dotenv`, `fastapi`, `uvicorn`, and pytest-compatible settings.

- [ ] **Step 2: Implement environment parsing**
  Define typed settings for `BOT_TOKEN`, `ALLOWED_CHAT_IDS`, `TIMEZONE`, `DATABASE_PATH`, `LOG_PATH`, and `RATE_LIMIT_PER_MINUTE`; fail clearly when the token is absent.

- [ ] **Step 3: Add repository hygiene**
  Ignore `.env`, `__pycache__`, test caches, logs, and the SQLite file while retaining `data/.gitkeep`.

- [ ] **Step 4: Verify**
  Run `python -m compileall src` and verify importing `load_settings` does not require Telegram credentials until called.

### Task 2: Parser and categorizer

**Files:**
- Create: `src/parser.py`
- Create: `src/categorizer.py`
- Create: `tests/test_parser.py`
- Create: `tests/test_categorizer.py`

**Interfaces:**
- `ParsedTransaction(type: Literal["income","expense"], amount: int, description: str, transaction_date: date, warnings: list[str])`.
- `parse_message(text: str, now: datetime, timezone: str) -> ParsedTransaction | ParseError`.
- `categorize(description: str, categories: Sequence[Category]) -> str`.
- `default_categories() -> list[Category]`.

- [ ] **Step 1: Write parser tests**
  Cover at least 20 cases: `15000`, `15.000`, `15rb`, `15k`, `15ribu`, `1,5jt`, `1.5jt`, `8juta`, `500k`, income keywords, expense defaults, `kemarin`, `tgl 5`, `tanggal 5`, `5/12`, `05-12-2025`, zero amount, missing amount, and descriptions before/after amount.

- [ ] **Step 2: Run parser tests and verify they fail**
  Run `pytest tests/test_parser.py -q`; expected failure because parser interfaces are not implemented.

- [ ] **Step 3: Implement amount normalization**
  Parse suffixes `rb/k/ribu` as ×1,000 and `jt/juta` as ×1,000,000; treat dotted groups as thousands and comma/dot decimal values with suffixes correctly; return integer Rupiah.

- [ ] **Step 4: Implement type, date, and description parsing**
  Use explicit income keywords before expense keywords, default to expense, resolve dates using the configured timezone, remove the selected nominal and date markers, and return a clear error for missing/zero amounts.

- [ ] **Step 5: Implement rules-based categories**
  Add the specified default mappings, emoji, and type metadata; match case-insensitively and use “Lain-lain” as fallback.

- [ ] **Step 6: Run parser and categorizer tests**
  Run `pytest tests/test_parser.py tests/test_categorizer.py -q`; expected PASS.

### Task 3: SQLite schema and repository

**Files:**
- Create: `src/models.py`
- Create: `src/database.py`
- Create: `tests/test_database.py`

**Interfaces:**
- `Transaction`, `Category@BT, and `TransactionFilters` dataclasses.
- `Database(path: str)` with `initialize()`, `add_transaction()`, `get_transaction()`, `delete_transaction()`, `update_transaction()`, `find_latest_transaction()`, `list_transactions(filters)`, `list_categories()`, `upsert_category()`, and `delete_category()`.
- All SQL uses parameters and stores integer amount/date/timestamps.

- [ ] **Step 1: Write repository tests**
  Test schema creation, insert, list by chat/user/date, latest-within-five-minutes, edit/delete ownership, and category CRUD.

- [ ] **Step 2: Implement schema initialization**
  Create `transactions` and `categories` tables, indexes for chat/date and user/created time, WAL mode, and seed default categories idempotently.

- [ ] **Step 3: Implement CRUD and scoped authorization**
  Enforce same-chat and same-user checks in update/delete service calls; keep database methods parameterized and transaction-safe.

- [ ] **Step 4: Run repository tests**
  Run `pytest tests/test_database.py -q`; expected PASS.

### Task 4: Reports and command services

**Files:**
- Create: `src/formatting.py`
- Create: `src/reports.py`
- Create: `tests/test_reports.py`

**Interfaces:**
- `format_rupiah(amount: int) -> str`.
- `render_confirmation(transaction, actor) -> str`.
- `parse_report_period(args, now, timezone) -> (start_date, end_date, title, scope)`.
- `build_report(database, period, chat_id, user_id=None) -> str`.
- `build_recap(database, period, chat_id, user_id=None) -> str`.

- [ ] **Step 1: Write report tests**
  Cover day/week/month/all/month-specific/range periods, `/laporan saya` scope, empty periods, category percentages, user totals, and Rupiah formatting.

- [ ] **Step 2: Implement period parsing**
  Support `hari`, `minggu`, `bulan`, `all`, `YYYY-MM`, and `YYYY-MM-DD YYYY-MM-DD`; reject invalid or reversed ranges with friendly errors.

- [ ] **Step 3: Implement formatted output**
  Render the required emojis, separators, monospace detail table, income/expense/balance, category percentages, transaction count, and per-user totals.

- [ ] **Step 4: Run report tests**
  Run `pytest tests/test_reports.py -q`; expected PASS.

### Task 5: Telegram handlers, security, and application entrypoint

**Files:**
- Create: `src/rate_limit.py`
- Create: `src/handlers/__init__.py`
- Create: `src/handlers/common.py`
- Create: `src/handlers/messages.py`
- Create: `src/handlers/commands.py`
- Create: `src/main.py`
- Create: `tests/test_rate_limit.py`

**Interfaces:**
- `is_allowed_chat(chat_id: str, settings: Settings) -> bool`.
- `RateLimiter.allow(user_id: str, now: datetime) -> bool`.
- Async Telegram handlers for natural-language messages and all specified commands.

- [ ] **Step 1: Write rate-limit tests**
  Verify 30 allowed messages per minute by default, the 31st rejected, and a new minute resets the bucket.

- [ ] **Step 2: Implement access and throttling**
  Reject non-whitelisted chats, answer rate-limited users briefly in Indonesian, and log rejected requests without leaking the bot token.

- [ ] **Step 3: Implement transaction message handler**
  Parse, categorize, persist actor/chat metadata, and send the exact concise confirmation shape; on parser errors ask for clarification without inserting data.

- [ ] **Step 4: Implement command handlers**
  Add `/undo`, `/hapus`, `/edit`, `/kategori`, `/tambahkategori`, `/hapuskategori`, all report aliases, and `/rekap`.

- [ ] **Step 5: Add application entrypoint**
  Register handlers, initialize database, configure logging, and run Telegram polling plus a lightweight FastAPI health endpoint when deployed.

- [ ] **Step 6: Run all tests**
  Run `pytest -q`; expected PASS.

### Task 6: Documentation, deployment, and end-to-end verification

**Files:**
- Create: `README.md`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `deploy/money-bot.service`
- Create: `tests/test_smoke.py`

**Interfaces:**
- README documents local setup, BotFather, group invite/ID discovery, all commands, mock conversation, VPS/systemd, and Railway with persistent storage caveat.
- Smoke test starts from a fresh temporary SQLite database and verifies input -> confirmation data -> monthly report.

- [ ] **Step 1: Add smoke test**
  Verify a family input is parsed, stored, and included in a monthly report.

- [ ] **Step 2: Add container and service configuration**
  Provide a non-root Docker image and a systemd unit using an explicit working directory and environment file.

- [ ] **Step 3: Write README**
  Explain free stack, setup commands, BotFather steps, whitelist configuration, commands, backup guidance, and mock conversation in Bahasa Indonesia.

- [ ] **Step 4: Run final verification**
  Run `pytest -q`, `python -m compileall src`, and a clean-start smoke command using `.env.example` placeholders without exposing secrets.

- [ ] **Step 5: Review deliverables**
  Confirm every requested source file, test coverage, deployment path, and explicit assumption is present before handoff.

