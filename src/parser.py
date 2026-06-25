import re
from typing import Optional


class ParseError(Exception):
    pass


def _safe_float(s: str) -> Optional[float]:
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def parse_response(raw: str) -> dict:
    var_prefix = 'var hq_str = "'
    if not raw.startswith(var_prefix):
        raise ParseError("Response does not start with expected prefix")

    body = raw.removeprefix(var_prefix)
    # Strip trailing "; and optional newline
    body = body.removesuffix('";\n').removesuffix('";').removesuffix('"')

    fields = body.split(",")
    if len(fields) < 10:
        raise ParseError(f"Too few fields: {len(fields)}")

    name = fields[0]
    open_price = _safe_float(fields[2])
    current_price = _safe_float(fields[3])
    max_today = _safe_float(fields[4])
    min_today = _safe_float(fields[5])

    # Scan last fields with regex to find date and time
    quote_date = None
    quote_time = None
    for f in reversed(fields):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", f):
            quote_date = f
            break
    for f in reversed(fields):
        if re.fullmatch(r"\d{2}:\d{2}:\d{2}", f):
            quote_time = f
            break

    return {
        "name": name,
        "open_price": open_price,
        "current_price": current_price,
        "max_today": max_today,
        "min_today": min_today,
        "quote_date": quote_date,
        "quote_time": quote_time,
    }
