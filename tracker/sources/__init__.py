"""Price sources. Each returns a PriceResult or raises SourceError."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class PriceResult:
    price: float
    currency: str | None = None
    in_stock: bool | None = None
    title: str | None = None
    method: str = ""          # how the price was found, for debugging
    url: str | None = None    # specific listing, when different from the source URL


class SourceError(RuntimeError):
    pass


class OutOfStock(SourceError):
    """Source works fine; the item just isn't available right now. Not a failure."""


_NUM = re.compile(r"\d[\d.,\s]*")


def parse_price(value) -> float | None:
    """Turn '$1,999.00', '1999', 1999.0 or '1.999,00' into a float."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    match = _NUM.search(str(value))
    if not match:
        return None
    s = match.group().replace(" ", "").strip(".,")
    if "," in s and "." in s:
        # whichever separator comes last is the decimal point
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = f"{head.replace(',', '')}.{tail}" if len(tail) == 2 else s.replace(",", "")
    try:
        price = float(s)
    except ValueError:
        return None
    return price if price > 0 else None
