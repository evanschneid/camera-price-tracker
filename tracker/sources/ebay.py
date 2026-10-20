"""Lowest matching Buy It Now price on eBay (price + shipping).

Searches US listings sorted by lowest total price, then filters titles so a
battery or a different model doesn't count as a "price drop".
"""
from __future__ import annotations

import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from . import OutOfStock, PriceResult, SourceError, parse_price

_CONDITION_CODES = {"new": "1000", "used": "3000"}


def search_url(query: str, condition: str = "any") -> str:
    params = {
        "_nkw": query,
        "LH_BIN": "1",        # Buy It Now only (auction prices aren't real yet)
        "_sop": "15",         # sort: price + shipping, lowest first
        "LH_PrefLoc": "1",    # US located
        "_ipg": "120",
    }
    if condition in _CONDITION_CODES:
        params["LH_ItemCondition"] = _CONDITION_CODES[condition]
    return "https://www.ebay.com/sch/i.html?" + urlencode(params)


def normalize(text: str) -> str:
    """Lowercase and drop everything but letters/digits: 'X-T5 Body' -> 'xt5body'."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _contains(title: str, keyword: str) -> bool:
    """True if title contains keyword, ignoring case, spaces and punctuation.

    A keyword ending in a number must not run into more digits, so "om-1"
    doesn't match "OM-10" and "leica m2" doesn't match "Leica M 28mm".
    """
    chars = normalize(keyword)
    if not chars:
        return False
    pattern = r"[^a-z0-9]*".join(map(re.escape, chars))
    if chars[-1].isdigit():
        pattern += r"(?![0-9])"
    return re.search(pattern, title.lower()) is not None


def title_matches(title: str, has_any: list[str], exclude: list[str]) -> bool:
    if has_any and not any(_contains(title, k) for k in has_any):
        return False
    return not any(_contains(title, k) for k in exclude)


def extract_lowest(html: str, has_any: list[str], exclude: list[str],
                   min_price: float = 0.0) -> PriceResult:
    soup = BeautifulSoup(html, "html.parser")
    listings = list(_listings(soup))
    if not listings:
        raise SourceError("no eBay listings found (blocked or page layout changed)")
    matches = [l for l in listings
               if l["price"] >= min_price and title_matches(l["title"], has_any, exclude)]
    if not matches:
        # Rare cameras can have no matching listing for a while; that's not broken.
        raise OutOfStock(f"nothing matching listed right now ({len(listings)} listings checked)")
    best = min(matches, key=lambda l: l["total"])
    return PriceResult(price=round(best["total"], 2), currency="USD", in_stock=True,
                       title=best["title"], method=f"ebay ({len(matches)} matches)",
                       url=best["url"])


def _listings(soup):
    # eBay has served two layouts: classic "s-item" and newer "s-card".
    for item in soup.select("li.s-item, li.s-card, div.s-item, div.s-card"):
        title_el = item.select_one(".s-item__title, .s-card__title")
        price_el = item.select_one(".s-item__price, .s-card__price")
        link_el = item.select_one("a.s-item__link, a.su-link, a[href*='/itm/']")
        if not (title_el and price_el):
            continue
        title = title_el.get_text(" ", strip=True)
        title = re.sub(r"^New Listing\s*", "", title, flags=re.I)
        if title.lower().startswith("shop on ebay"):
            continue
        price = parse_price(price_el.get_text(" ", strip=True))  # ranges -> low end
        if not price:
            continue
        ship_el = item.select_one(".s-item__shipping, .s-item__logisticsCost, .s-card__shipping")
        shipping = _shipping(ship_el.get_text(" ", strip=True)) if ship_el else 0.0
        if not ship_el:
            for el in item.select(".s-card__attribute-row, .su-styled-text"):
                text = el.get_text(" ", strip=True).lower()
                if "delivery" in text or "shipping" in text:
                    shipping = _shipping(text)
                    break
        href = link_el.get("href") if link_el else None
        yield {"title": title, "price": price, "total": price + shipping,
               "url": href.split("?")[0] if href else None}


def _shipping(text: str) -> float:
    if "free" in text.lower():
        return 0.0
    return parse_price(text) or 0.0
