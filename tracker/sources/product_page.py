"""Read the price from a single product page.

Most shops embed schema.org Product data (JSON-LD) for Google Shopping, so
that is tried first; meta tags and itemprop markup are the fallbacks. This
works for B&H, Adorama, MPB, KEH and many others without per-site code.
"""
from __future__ import annotations

import json

from bs4 import BeautifulSoup

from . import PriceResult, SourceError, parse_price


def extract_price(html: str) -> PriceResult:
    soup = BeautifulSoup(html, "html.parser")
    title = _title(soup)
    for finder in (_from_json_ld, _from_meta, _from_itemprop):
        result = finder(soup)
        if result:
            result.title = result.title or title
            return result
    raise SourceError("no price found on page (layout changed, blocked, or out of stock)")


# --- JSON-LD ---------------------------------------------------------------

def _from_json_ld(soup) -> PriceResult | None:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for product in _walk_products(data):
            offers = _collect_offers(product.get("offers"))
            if offers:
                return _best_offer(offers, product.get("name"))
    return None


def _walk_products(node):
    """Yield every Product-like dict (anything with 'offers') in a JSON-LD tree."""
    if isinstance(node, list):
        for item in node:
            yield from _walk_products(item)
    elif isinstance(node, dict):
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if "offers" in node and ("Product" in types or "IndividualProduct" in types or None in types):
            yield node
        for key in ("@graph", "mainEntity", "itemListElement", "item"):
            if key in node:
                yield from _walk_products(node[key])
        # ProductGroup variants
        if "hasVariant" in node:
            yield from _walk_products(node["hasVariant"])


def _collect_offers(offers) -> list[dict]:
    """Flatten Offer / AggregateOffer / lists into [{price, currency, in_stock}]."""
    out: list[dict] = []
    if isinstance(offers, list):
        for o in offers:
            out.extend(_collect_offers(o))
        return out
    if not isinstance(offers, dict):
        return out
    in_stock = _availability(offers.get("availability"))
    currency = offers.get("priceCurrency")
    price = parse_price(offers.get("price"))
    if price is None:
        price = parse_price(offers.get("lowPrice"))
    if price is None and isinstance(offers.get("priceSpecification"), (dict, list)):
        spec = offers["priceSpecification"]
        spec = spec[0] if isinstance(spec, list) and spec else spec
        if isinstance(spec, dict):
            price = parse_price(spec.get("price"))
            currency = currency or spec.get("priceCurrency")
    if price is not None:
        out.append({"price": price, "currency": currency, "in_stock": in_stock})
    if "offers" in offers:  # AggregateOffer with nested offers
        out.extend(_collect_offers(offers["offers"]))
    return out


def _availability(value) -> bool | None:
    if not value:
        return None
    v = str(value).lower()
    if any(w in v for w in ("outofstock", "soldout", "discontinued")):
        return False
    if any(w in v for w in ("instock", "limitedavailability", "onlineonly", "preorder", "backorder")):
        return True
    return None


def _best_offer(offers: list[dict], name) -> PriceResult:
    available = [o for o in offers if o["in_stock"] is not False]
    pool = available or offers
    best = min(pool, key=lambda o: o["price"])
    return PriceResult(price=best["price"], currency=best["currency"],
                       in_stock=best["in_stock"] if available else False,
                       title=name, method="json-ld")


# --- meta tags / microdata -------------------------------------------------

_META_PRICE = ("product:price:amount", "og:price:amount")
_META_CURRENCY = ("product:price:currency", "og:price:currency")


def _from_meta(soup) -> PriceResult | None:
    for key in _META_PRICE:
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        price = parse_price(tag.get("content")) if tag else None
        if price:
            currency = None
            for ckey in _META_CURRENCY:
                ctag = soup.find("meta", attrs={"property": ckey})
                if ctag and ctag.get("content"):
                    currency = ctag["content"]
                    break
            return PriceResult(price=price, currency=currency, method=f"meta:{key}")
    return None


def _from_itemprop(soup) -> PriceResult | None:
    tag = soup.find(attrs={"itemprop": "price"})
    if not tag:
        return None
    price = parse_price(tag.get("content") or tag.get_text())
    if not price:
        return None
    ctag = soup.find(attrs={"itemprop": "priceCurrency"})
    avail = soup.find(attrs={"itemprop": "availability"})
    return PriceResult(
        price=price,
        currency=(ctag.get("content") if ctag else None),
        in_stock=_availability(avail.get("href") or avail.get("content")) if avail else None,
        method="itemprop",
    )


def _title(soup) -> str | None:
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return None
