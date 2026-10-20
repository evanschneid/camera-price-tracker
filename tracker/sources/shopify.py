"""Lowest matching in-stock price at a Shopify shop (K&M Camera, Brooklyn Film Camera...).

Used-camera shops list one-off items rather than one page per model, so we
search the shop like eBay and keep the cheapest listing whose title passes the
filters. Shopify's search suggestions are public JSON at /search/suggest.json
and return the top 10 in-stock products for a query. Shipping isn't included.
"""
from __future__ import annotations

import json
from urllib.parse import urlencode

from . import OutOfStock, PriceResult, SourceError, parse_price
from .ebay import title_matches


def search_url(shop: str, query: str) -> str:
    params = {
        "q": query,
        "resources[type]": "product",
        "resources[limit]": "10",                                # Shopify's maximum
        "resources[options][unavailable_products]": "hide",
    }
    return f"https://{_host(shop)}/search/suggest.json?" + urlencode(params)


def extract_lowest(text: str, shop: str, has_any: list[str], exclude: list[str],
                   min_price: float = 0.0) -> PriceResult:
    try:
        products = json.loads(text)["resources"]["results"]["products"]
    except (ValueError, KeyError, TypeError):
        raise SourceError("unexpected search response (not a Shopify shop, or blocked)")
    matches = []
    for p in products:
        price = parse_price(p.get("price_min") or p.get("price"))
        if (p.get("available") is not False and price and price >= min_price
                and title_matches(p.get("title", ""), has_any, exclude)):
            matches.append((price, p))
    if not matches:
        raise OutOfStock(f"nothing matching listed right now ({len(products)} results checked)")
    price, best = min(matches, key=lambda m: m[0])
    url = best.get("url", "").split("?")[0]
    return PriceResult(price=price, currency=None, in_stock=True, title=best.get("title"),
                       method=f"shopify ({len(matches)} matches)",
                       url=f"https://{_host(shop)}{url}" if url.startswith("/") else url or None)


def _host(shop: str) -> str:
    return shop.removeprefix("https://").removeprefix("http://").strip("/")
