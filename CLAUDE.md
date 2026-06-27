# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Real-time gold price data collection + technical analysis + trading signal system. Polls `api.jijinhao.com` every 2-3 seconds, parses the response, stores to SQLite, then computes technical indicators (SMA, EMA, RSI, Bollinger Bands, MACD) and generates BUY/SELL/HOLD consensus signals.

Three execution modes:
- **Collector** — continuous data ingestion (asyncio loop)
- **CLI monitor** — terminal live-updating signal dashboard (rich)
- **Streamlit dashboard** — web UI with charts and signal history (streamlit + altair)

For detailed architecture, modules, data flow, and signals database docs, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

For Git/GitHub workflow, see [docs/git-workflow.md](docs/git-workflow.md).

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

## Architecture

```
config.py → collector.py → parser.py → db.py → SQLite
                                                    ↓
                          streamlit_app.py ← analyst/engine.py ← analyst/indicators.py
                          cli_signal.py   ←    (SignalEngine)   analyst/signals.py
```

### Key design choices

- **asyncio** for concurrent HTTP — single client with keepalive, no thread pool needed
- **WAL mode + NORMAL synchronous** — balances write throughput vs. durability for high-frequency inserts
- **Graceful shutdown** via `asyncio.Event` set by signal handler, waited on with timeout as the sleep mechanism
- **Raw response stored** (`raw_response` column) so parsing can be replayed if the format changes
- **Incremental SignalEngine.tick()** — only fetches new rows since last poll, avoiding repeated DB scans
- **Signal voting** — 4 independent strategies, simple majority consensus with strength weighting, no whipsaw protection per crossover
