import asyncio
import logging
import random
import signal
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx

from . import config, db, parser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("gold-collector")

_tz_utc8 = timezone(timedelta(hours=8))


def _now_utc8() -> datetime:
    return datetime.now(_tz_utc8)


_shutdown_event = asyncio.Event()


def _handle_signal(sig: int) -> None:
    log.info("Received signal %s, shutting down gracefully...", sig)
    _shutdown_event.set()


async def fetch_price(client: httpx.AsyncClient) -> str:
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    url = config.API_URL_TEMPLATE.format(timestamp=timestamp)
    response = await client.get(url, headers=config.HEADERS, timeout=config.REQUEST_TIMEOUT)
    response.raise_for_status()
    text = response.text.strip()
    if not text:
        raise ValueError("Empty response body")
    return text


async def poll_once(client: httpx.AsyncClient) -> None:
    now = _now_utc8()
    now_iso = now.isoformat(timespec="seconds")
    raw = await fetch_price(client)
    parsed = parser.parse_response(raw)
    db.insert_record(fetched_at=now_iso, parsed=parsed, raw_response=raw, created_at=now_iso)
    price = parsed.get("current_price")
    log.info(
        "Recorded price=%.2f (high=%.2f low=%.2f) at %s",
        price,
        parsed.get("max_today") or 0,
        parsed.get("min_today") or 0,
        parsed.get("quote_time", "?"),
    )


async def main_loop() -> None:
    db_path = Path(config.DB_PATH)
    db.init_db(db_path)
    log.info("Database initialised at %s", db_path.resolve())

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: _handle_signal(s))

    limits = httpx.Limits(max_keepalive_connections=1, max_connections=1)
    async with httpx.AsyncClient(limits=limits) as client:
        while not _shutdown_event.is_set():
            try:
                await poll_once(client)
            except parser.ParseError as e:
                log.warning("Parse error: %s", e)
            except httpx.HTTPStatusError as e:
                log.warning("HTTP error: %s (status %s)", e, e.response.status_code)
            except httpx.TimeoutException:
                log.warning("Request timed out")
            except Exception:
                log.exception("Unexpected error in poll cycle")

            delay = random.uniform(config.POLL_MIN_INTERVAL, config.POLL_MAX_INTERVAL)
            try:
                await asyncio.wait_for(_shutdown_event.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass  # timer expired, continue loop

    log.info("Collector stopped.")


def main() -> None:
    asyncio.run(main_loop())


if __name__ == "__main__":
    main()
