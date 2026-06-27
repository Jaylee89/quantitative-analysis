# Architecture Reference

## Modules

- **`src/config.py`** — constants: API URL template, request headers, poll interval range, DB path. No secrets.
- **`src/collector.py`** — asyncio main loop. Creates an `httpx.AsyncClient`, polls at randomized 2-3s intervals, handles signals (SIGINT/SIGTERM) for graceful shutdown. Each cycle: fetch → parse → log → store. Exceptions are caught per-cycle so a single failure doesn't kill the loop.
- **`src/parser.py`** — parses the `var hq_str = "..."` format returned by the API. Uses string prefix/suffix stripping + CSV split, then regex-matched date/time fields. Raises `ParseError` on malformed responses.
- **`src/db.py`** — SQLite access via `sqlite3`. WAL mode, NORMAL sync. Module-level `_DB_PATH` is set once by `init_db()`. `insert_record()` inserts a single parsed row. Also manages the signals DB (`data/signals.db`) via `init_signals_db()`, `insert_signal()`, and `fetch_signals()`.
- **`src/analyst/indicators.py`** — pure computation: `sma()`, `ema()`, `rsi()`, `bollinger_bands()`, `macd()`. All return aligned lists (padding with `None` where insufficient data).
- **`src/analyst/signals.py`** — evaluates indicator values into `SignalResult` named tuples per strategy (SMA crossover, RSI thresholds, Bollinger %B, MACD crossover). `aggregate_signals()` votes across strategies for a consensus (BUY/SELL/HOLD).
- **`src/analyst/engine.py`** — `SignalEngine` class: DB → unique ticks → 1-minute OHLC bars → indicators → signals. Supports full `refresh()` and incremental `tick()`. Returns a snapshot dict with bars, indicators, signals, and consensus.
- **`src/cli_signal.py`** — terminal UI using `rich` live display. Shows last 20 minute bars with indicators and a footer with active signals and consensus. Pass `--signals-db` to write signals to a separate DB (defaults to `data/signals.db`).
- **`src/streamlit_app.py`** — web dashboard using Streamlit + Altair. Price chart with SMA/BB overlay, RSI chart with thresholds, MACD chart, signal history table. Auto-refreshes every 2 seconds.
- **`schema.sql`** — reference DDL for the `gold_prices` table. Not executed directly; `db.init_db()` runs the same DDL.

## Data flow

1. `collector.poll_once()` timestamps the fetch (UTC+8), calls `fetch_price()` with a millisecond cache-busting param
2. Raw string goes to `parser.parse_response()` which extracts `current_price`, `open_price`, `max_today`, `min_today`, `quote_date`, `quote_time`
3. `db.insert_record()` writes one row to `gold_prices` table in `data/gold.db`
4. `SignalEngine` reads raw ticks from DB, deduplicates by (date, time), aggregates into 1-minute OHLC bars
5. Indicators are computed over the bar close prices
6. Signal rules evaluate indicators and vote for consensus

## Data source

- API: `api.jijinhao.com` gold quote endpoint (`JO_92233`)
- Response format: `var hq_str = "name,code,open,current,high,low,...,date,time";`
- Frequency window: 2-3 seconds between polls to balance data density vs. rate limit

## Signals Database

Buy/sell signals are persisted to a separate `data/signals.db` SQLite database. Records are written when the consensus changes or a new non-HOLD signal fires.

```bash
# Query signal history
sqlite3 data/signals.db "SELECT * FROM signals ORDER BY recorded_at DESC;"

# Filter by action
sqlite3 data/signals.db "SELECT * FROM signals WHERE action='BUY' ORDER BY recorded_at DESC;"

# Summary counts
sqlite3 data/signals.db "SELECT action, COUNT(*) FROM signals GROUP BY action;"
```

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `recorded_at` | TEXT | When the signal was generated (UTC+8 ISO) |
| `action` | TEXT | `BUY`, `SELL`, or `HOLD` |
| `strength` | REAL | Signal strength 0.0–1.0 |
| `reason` | TEXT | Human-readable reason (e.g. "RSI 28.3 < 30 (oversold)") |
| `indicator` | TEXT | Strategy name (`SMA Crossover`, `RSI`, `Bollinger Bands`, `MACD`, or `CONSENSUS`) |
| `price` | REAL | Gold price at signal time |
| `bar_time` | TEXT | Minute bar timestamp |
| `created_at` | TEXT | Record creation timestamp (same as `recorded_at`) |

### How it works

1. `SignalEngine._build_snapshot()` checks if consensus changed since last poll
2. On consensus change → writes a `CONSENSUS` record with reason like `"Consensus changed from HOLD to BUY"`
3. Each individual strategy that fires a non-HOLD signal is written once (deduplicated by `indicator|action` key until it clears)
4. All signals include the current price and bar timestamp for context
