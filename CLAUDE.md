# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Real-time gold price data collection + technical analysis + trading signal system. Polls `api.jijinhao.com` every 2-3 seconds, parses the response, stores to SQLite, then computes technical indicators (SMA, EMA, RSI, Bollinger Bands, MACD) and generates BUY/SELL/HOLD consensus signals.

Three execution modes:
- **Collector** — continuous data ingestion (asyncio loop)
- **CLI monitor** — terminal live-updating signal dashboard (rich)
- **Streamlit dashboard** — web UI with charts and signal history (streamlit + altair)

## Commands

```bash
# Activate virtual environment (uv)
source .venv/bin/activate

# Install/sync dependencies
uv sync

# 1. Start the collector (continuous data ingestion)
uv run python -m src.collector

# 2. Terminal signal monitor (run alongside collector)
uv run python -m src.cli_signal

# 3. Web dashboard (run alongside collector)
PYTHONPATH=. uv run streamlit run src/streamlit_app.py
```

Dependencies are managed via `uv` and `pyproject.toml`. No test/lint/build tooling configured yet.

## Git / GitHub

Prefer `gh` CLI over raw `git` for GitHub operations (push, PR, issue, etc.). Use `gh` whenever a GitHub remote is involved.

## Architecture

### Pipeline overview

```
config.py → collector.py → parser.py → db.py → SQLite
                                                    ↓
                          streamlit_app.py ← analyst/engine.py ← analyst/indicators.py
                          cli_signal.py   ←    (SignalEngine)   analyst/signals.py
```

### Modules

- **`src/config.py`** — constants: API URL template, request headers, poll interval range, DB path. No secrets.
- **`src/collector.py`** — asyncio main loop. Creates an `httpx.AsyncClient`, polls at randomized 2-3s intervals, handles signals (SIGINT/SIGTERM) for graceful shutdown. Each cycle: fetch → parse → log → store. Exceptions are caught per-cycle so a single failure doesn't kill the loop.
- **`src/parser.py`** — parses the `var hq_str = "..."` format returned by the API. Uses string prefix/suffix stripping + CSV split, then regex-matched date/time fields. Raises `ParseError` on malformed responses.
- **`src/db.py`** — SQLite access via `sqlite3`. WAL mode, NORMAL sync. Module-level `_DB_PATH` is set once by `init_db()`. `insert_record()` inserts a single parsed row.
- **`src/analyst/indicators.py`** — pure computation: `sma()`, `ema()`, `rsi()`, `bollinger_bands()`, `macd()`. All return aligned lists (padding with `None` where insufficient data).
- **`src/analyst/signals.py`** — evaluates indicator values into `SignalResult` named tuples per strategy (SMA crossover, RSI thresholds, Bollinger %B, MACD crossover). `aggregate_signals()` votes across strategies for a consensus (BUY/SELL/HOLD).
- **`src/analyst/engine.py`** — `SignalEngine` class: DB → unique ticks → 1-minute OHLC bars → indicators → signals. Supports full `refresh()` and incremental `tick()`. Returns a snapshot dict with bars, indicators, signals, and consensus.
- **`src/cli_signal.py`** — terminal UI using `rich` live display. Shows last 20 minute bars with indicators and a footer with active signals and consensus.
- **`src/streamlit_app.py`** — web dashboard using Streamlit + Altair. Price chart with SMA/BB overlay, RSI chart with thresholds, MACD chart, signal history table. Auto-refreshes every 2 seconds.
- **`schema.sql`** — reference DDL for the `gold_prices` table. Not executed directly; `db.init_db()` runs the same DDL.

### Data flow

1. `collector.poll_once()` timestamps the fetch (UTC+8), calls `fetch_price()` with a millisecond cache-busting param
2. Raw string goes to `parser.parse_response()` which extracts `current_price`, `open_price`, `max_today`, `min_today`, `quote_date`, `quote_time`
3. `db.insert_record()` writes one row to `gold_prices` table in `data/gold.db`
4. `SignalEngine` reads raw ticks from DB, deduplicates by (date, time), aggregates into 1-minute OHLC bars
5. Indicators are computed over the bar close prices
6. Signal rules evaluate indicators and vote for consensus

### Key design choices

- **asyncio** for concurrent HTTP — single client with keepalive, no thread pool needed
- **WAL mode + NORMAL synchronous** — balances write throughput vs. durability for high-frequency inserts
- **Graceful shutdown** via `asyncio.Event` set by signal handler, waited on with timeout as the sleep mechanism
- **Raw response stored** (`raw_response` column) so parsing can be replayed if the format changes
- **Incremental SignalEngine.tick()** — only fetches new rows since last poll, avoiding repeated DB scans
- **Signal voting** — 4 independent strategies, simple majority consensus with strength weighting, no whipsaw protection per crossover

### Data source

- API: `api.jijinhao.com` gold quote endpoint (`JO_92233`)
- Response format: `var hq_str = "name,code,open,current,high,low,...,date,time";`
- Frequency window: 2-3 seconds between polls to balance data density vs. rate limit
