# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Real-time gold price data collection system. Polls `api.jijinhao.com` every 2-3 seconds, parses the response, and stores to SQLite. Designed as a data pipeline for downstream quantitative analysis.

## Commands

```bash
# Activate virtual environment (uv)
source .venv/bin/activate

# Run the collector
uv run python -m src.collector

# If uv not available, ensure .venv is activated then:
python -m src.collector
```

No test/lint/build tooling is configured yet. Dependencies are managed via `uv` and `pyproject.toml`.

## Git / GitHub

Prefer `gh` CLI over raw `git` for GitHub operations (push, PR, issue, etc.). Use `gh` whenever a GitHub remote is involved.

## Architecture

The pipeline flow: **`config.py` → `collector.py` → `parser.py` → `db.py` → SQLite**

- **`src/config.py`** — constants: API URL template, request headers, poll interval range, DB path. No secrets.
- **`src/collector.py`** — asyncio main loop. Creates an `httpx.AsyncClient`, polls at randomized 2-3s intervals, handles signals (SIGINT/SIGTERM) for graceful shutdown. Each cycle: fetch → parse → log → store. Exceptions are caught per-cycle so a single failure doesn't kill the loop.
- **`src/parser.py`** — parses the `var hq_str = "..."` format returned by the API. Uses string prefix/suffix stripping + CSV split, then regex-matched date/time fields. Raises `ParseError` on malformed responses.
- **`src/db.py`** — SQLite access via `sqlite3`. WAL mode, NORMAL sync. Module-level `_DB_PATH` is set once by `init_db()`. `insert_record()` upserts a single parsed row.
- **`schema.sql`** — reference DDL for the `gold_prices` table. Not executed directly; `db.init_db()` runs the same DDL.

### Data flow

1. `collector.poll_once()` timestamps the fetch (UTC+8), calls `fetch_price()` with a millisecond cache-busting param
2. Raw string goes to `parser.parse_response()` which extracts `current_price`, `open_price`, `max_today`, `min_today`, `quote_date`, `quote_time`
3. `db.insert_record()` writes one row to `gold_prices` table in `data/gold.db`
4. Loop sleeps `random.uniform(2.0, 3.0)` seconds

### Key design choices

- **asyncio** for concurrent HTTP — single client with keepalive, no thread pool needed
- **WAL mode + NORMAL synchronous** — balances write throughput vs. durability for high-frequency inserts
- **Graceful shutdown** via `asyncio.Event` set by signal handler, waited on with timeout as the sleep mechanism
- **Raw response stored** (`raw_response` column) so parsing can be replayed if the format changes

### Data source

- API: `api.jijinhao.com` gold quote endpoint
- Response format: `var hq_str = "name,code,open,current,high,low,...,date,time";`
- Frequency window: 2-3 seconds between polls to balance data density vs. rate limit
