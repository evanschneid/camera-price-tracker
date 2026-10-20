"""Run with:  python -m unittest discover tests"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tracker import fetch as fetch_mod
from tracker import run as run_mod
from tracker import site
from tracker.alerts import find_alerts
from tracker.config import Camera, Config, Source
from tracker.history import History
from tracker.sources import OutOfStock, SourceError, ebay, parse_price, shopify
from tracker.sources.product_page import extract_price


def page_with_ld(data) -> str:
    return (f'<html><head><title>Cam</title><script type="application/ld+json">'
            f'{json.dumps(data)}</script></head><body></body></html>')


class ParsePrice(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_price("$1,999.00"), 1999.0)
        self.assertEqual(parse_price("1999"), 1999.0)
        self.assertEqual(parse_price(1599.95), 1599.95)
        self.assertEqual(parse_price("1.999,00 €"), 1999.0)
        self.assertEqual(parse_price("$1,099.00 to $1,299.00"), 1099.0)
        self.assertEqual(parse_price("US $849.99"), 849.99)
        self.assertIsNone(parse_price("Call for price"))
        self.assertIsNone(parse_price("0.00"))


class ProductPage(unittest.TestCase):
    def test_simple_offer(self):
        r = extract_price(page_with_ld({
            "@type": "Product", "name": "Sony A7 IV",
            "offers": {"@type": "Offer", "price": "2298.00", "priceCurrency": "USD",
                       "availability": "https://schema.org/InStock"}}))
        self.assertEqual((r.price, r.currency, r.in_stock, r.method),
                         (2298.0, "USD", True, "json-ld"))
        self.assertEqual(r.title, "Sony A7 IV")

    def test_aggregate_offer_used_marketplace(self):  # MPB / KEH style
        r = extract_price(page_with_ld({
            "@context": "https://schema.org", "@type": "Product", "name": "X-T5",
            "offers": {"@type": "AggregateOffer", "lowPrice": 1259, "highPrice": 1489,
                       "priceCurrency": "USD", "offerCount": 7}}))
        self.assertEqual(r.price, 1259.0)

    def test_graph_and_multiple_offers_prefers_in_stock(self):
        r = extract_price(page_with_ld({"@graph": [
            {"@type": "WebPage", "name": "x"},
            {"@type": ["Product"], "name": "Kit", "offers": [
                {"price": "1800", "availability": "OutOfStock"},
                {"price": "1999", "availability": "InStock"}]}]}))
        self.assertEqual((r.price, r.in_stock), (1999.0, True))

    def test_all_out_of_stock(self):
        r = extract_price(page_with_ld({"@type": "Product", "offers": {
            "price": "1999", "availability": "https://schema.org/OutOfStock"}}))
        self.assertFalse(r.in_stock)

    def test_bad_json_then_meta_fallback(self):
        html = ('<script type="application/ld+json">{not json</script>'
                '<meta property="product:price:amount" content="1,749.00">'
                '<meta property="product:price:currency" content="USD">')
        r = extract_price(html)
        self.assertEqual((r.price, r.currency), (1749.0, "USD"))

    def test_itemprop_fallback(self):
        html = ('<div itemscope><span itemprop="price" content="1399.00">$1,399</span>'
                '<link itemprop="availability" href="https://schema.org/InStock"></div>')
        r = extract_price(html)
        self.assertEqual((r.price, r.in_stock), (1399.0, True))

    def test_no_price(self):
        with self.assertRaises(SourceError):
            extract_price("<html><body>Access denied</body></html>")


EBAY_CLASSIC = """
<ul>
 <li class="s-item"><div class="s-item__title">Shop on eBay</div>
   <span class="s-item__price">$20.00</span></li>
 <li class="s-item"><a class="s-item__link" href="https://www.ebay.com/itm/1?hash=x">
   <div class="s-item__title"><span>New Listing</span>Sony A7 IV battery grip</div></a>
   <span class="s-item__price">$89.00</span></li>
 <li class="s-item"><a class="s-item__link" href="https://www.ebay.com/itm/2?hash=y">
   <div class="s-item__title">Sony Alpha a7 IV Body ILCE-7M4 - Excellent</div></a>
   <span class="s-item__price">$1,650.00</span>
   <span class="s-item__shipping">+$25.00 shipping</span></li>
 <li class="s-item"><a class="s-item__link" href="https://www.ebay.com/itm/3">
   <div class="s-item__title">Sony A7IV mirrorless camera body only</div></a>
   <span class="s-item__price">$1,665.00</span>
   <span class="s-item__shipping">Free shipping</span></li>
 <li class="s-item"><a class="s-item__link" href="https://www.ebay.com/itm/4">
   <div class="s-item__title">Sony A7 III body</div></a>
   <span class="s-item__price">$1,050.00</span></li>
</ul>"""

EBAY_CARD = """
<ul><li class="s-card"><a class="su-link" href="https://www.ebay.com/itm/9?x=1">
  <div class="s-card__title"><span>Fujifilm X-T5 Body Silver</span></div></a>
  <div class="s-card__price">$1,299.00</div>
  <div class="s-card__attribute-row">+$15.00 delivery</div></li>
 <li class="s-card"><a class="su-link" href="https://www.ebay.com/itm/10">
  <div class="s-card__title">Fujifilm X-T50 body</div></a>
  <div class="s-card__price">$999.00</div></li></ul>"""


class Ebay(unittest.TestCase):
    def test_title_matching_normalizes(self):
        self.assertTrue(ebay.title_matches("Fujifilm XT5 body", ["x-t5"], []))
        self.assertFalse(ebay.title_matches("Fujifilm X-T50", ["x-t5"], ["x-t50"]))

    def test_number_must_not_run_into_more_digits(self):
        m = ebay.title_matches
        self.assertFalse(m("Used Olympus OM-10 | U8", ["om-1"], []))
        self.assertFalse(m("Leica Summicron-M 28mm f/2 | Leica M, 2023 Version", ["leica m2"], []))
        self.assertFalse(m("Leica M 35mm f/1.4 lens", ["leica m3"], []))
        self.assertTrue(m("Olympus OM-1n with 50mm f1.8", ["om-1"], []))
        self.assertTrue(m("Olympus OM1 50mm f1.8", ["om-1"], []))
        self.assertTrue(m("Pentax K1000 50mm kit", ["k1000"], []))
        self.assertTrue(m("Leica M2 + Summaron 35mm", ["leica m2"], []))

    def test_classic_layout_lowest_total(self):
        r = ebay.extract_lowest(EBAY_CLASSIC, ["a7 iv", "a7iv", "ilce-7m4"],
                                ["battery", "grip", "a7 iii"], min_price=1000)
        # $1,665 free shipping beats $1,650 + $25
        self.assertEqual(r.price, 1665.0)
        self.assertEqual(r.url, "https://www.ebay.com/itm/3")

    def test_card_layout_with_delivery(self):
        r = ebay.extract_lowest(EBAY_CARD, ["x-t5"], ["x-t50"])
        self.assertEqual(r.price, 1314.0)
        self.assertEqual(r.url, "https://www.ebay.com/itm/9")

    def test_nothing_matches_is_not_a_failure(self):
        with self.assertRaises(OutOfStock):
            ebay.extract_lowest(EBAY_CLASSIC, ["nikon z8"], [])

    def test_search_url(self):
        url = ebay.search_url("sony a7 iv", "used")
        self.assertIn("LH_ItemCondition=3000", url)
        self.assertIn("LH_BIN=1", url)


def shop_json(*products):
    return json.dumps({"resources": {"results": {"products": [
        {"title": t, "price": p, "available": a, "url": f"/products/{i}?_pos=1&_psq=x"}
        for i, (t, p, a) in enumerate(products)]}}})


class Shopify(unittest.TestCase):
    def test_lowest_matching_in_stock(self):
        text = shop_json(("Used Olympus OM-1 | Chrome | U9", "189.99", True),
                         ("Olympus OM SYSTEM OM-1 Mirrorless Camera", "2799.99", True),
                         ("Used Olympus OM-10 | U8", "99.99", True),
                         ("Used Olympus OM-1 | Black | U8", "149.99", False),
                         ("Used Olympus OM-1n | Black | U8", "209.99", True))
        r = shopify.extract_lowest(text, "kmcamera.com", ["om-1"], ["om-10", "om system"], 60)
        self.assertEqual(r.price, 189.99)
        self.assertEqual(r.url, "https://kmcamera.com/products/0")
        self.assertEqual(r.method, "shopify (2 matches)")

    def test_nothing_listed_is_not_a_failure(self):
        with self.assertRaises(OutOfStock):
            shopify.extract_lowest(shop_json(("Pentax MX", "199", True)), "x.com", ["k1000"], [])

    def test_not_shopify(self):
        with self.assertRaises(SourceError):
            shopify.extract_lowest("<html>Access denied</html>", "x.com", [], [])

    def test_search_url(self):
        url = shopify.search_url("https://www.kmcamera.com/", "pentax k1000")
        self.assertTrue(url.startswith("https://www.kmcamera.com/search/suggest.json?q=pentax+k1000"))
        self.assertIn("unavailable_products%5D=hide", url)


class LoadConfig(unittest.TestCase):
    def test_camera_filters_shared_by_sources(self):
        path = Path(tempfile.mkdtemp()) / "cameras.yaml"
        path.write_text("""
settings: {exclude: [parts]}
cameras:
  - name: Pentax K1000
    search: pentax k1000
    title_has_any: [k1000]
    exclude: [for pentax]
    min_price: 40
    sources:
      - {label: eBay, ebay_query: pentax k1000 body, condition: used}
      - {label: Shop, shop: kmcamera.com, exclude: [kit], min_price: 90}
""")
        from tracker.config import load_config
        ebay_src, shop_src = load_config(path).cameras[0].sources
        self.assertEqual((ebay_src.kind, ebay_src.exclude, ebay_src.min_price),
                         ("ebay", ["parts", "for pentax"], 40))
        self.assertEqual((shop_src.kind, shop_src.query, shop_src.title_has_any),
                         ("shopify", "pentax k1000", ["k1000"]))
        self.assertEqual((shop_src.exclude, shop_src.min_price), (["parts", "for pentax", "kit"], 90))

    def test_one_kind_per_source(self):
        path = Path(tempfile.mkdtemp()) / "cameras.yaml"
        path.write_text("cameras: [{name: X, sources: [{shop: a.com, url: https://a.com/x}]}]")
        from tracker.config import ConfigError, load_config
        with self.assertRaises(ConfigError):
            load_config(path)


class Alerts(unittest.TestCase):
    def test_drop_threshold(self):
        self.assertEqual(find_alerts("c", "s", 970, 1000, None, 3, None, None)[0].reason, "drop")
        self.assertEqual(find_alerts("c", "s", 980, 1000, None, 3, None, None), [])

    def test_target_only_on_first_crossing(self):
        self.assertEqual(find_alerts("c", "s", 1990, 2100, 2000, 3, None, None)[0].reason, "target")
        self.assertEqual(find_alerts("c", "s", 1990, 1995, 2000, 3, None, None), [])

    def test_no_alert_first_time_above_target(self):
        self.assertEqual(find_alerts("c", "s", 2200, None, 2000, 3, None, None), [])

    def test_lowest_ever_flag(self):
        a = find_alerts("c", "s", 900, 1000, None, 3, None, previous_lowest=950)[0]
        self.assertTrue(a.lowest_ever)


class Fetch(unittest.TestCase):
    def setUp(self):
        self.attempts = [{"impersonate": "a"}, {"impersonate": "b"}, {"impersonate": "c"}]
        mock.patch.object(fetch_mod, "_ATTEMPTS", self.attempts).start()
        mock.patch.object(fetch_mod.time, "sleep").start()
        self.get = mock.patch.object(fetch_mod._http, "get").start()
        self.addCleanup(mock.patch.stopall)

    def answers(self, *statuses):
        self.get.side_effect = [mock.Mock(status_code=s, text=f"page {s}") for s in statuses]

    def profiles_tried(self):
        return [c.kwargs["impersonate"] for c in self.get.call_args_list]

    def test_403_tries_next_browser(self):
        self.answers(403, 403, 200)
        self.assertEqual(fetch_mod.fetch("https://x"), "page 200")
        self.assertEqual(self.profiles_tried(), ["a", "b", "c"])

    def test_404_gives_up_at_once(self):
        self.answers(404)
        with self.assertRaisesRegex(fetch_mod.FetchError, "HTTP 404"):
            fetch_mod.fetch("https://x")
        self.assertEqual(self.profiles_tried(), ["a"])

    def test_all_browsers_blocked(self):
        self.answers(403, 403, 403)
        with self.assertRaisesRegex(fetch_mod.FetchError, "HTTP 403"):
            fetch_mod.fetch("https://x")

    def test_server_error_retries_same_browser(self):
        self.answers(503, 200)
        self.assertEqual(fetch_mod.fetch("https://x"), "page 200")
        self.assertEqual(self.profiles_tried(), ["a", "a"])


def price_row(when, source, price, camera="Cam", url=""):
    return {"checked_at": when, "camera": camera, "source": source, "price": price,
            "currency": "USD", "in_stock": True, "listing_url": url}


class Site(unittest.TestCase):
    def setUp(self):
        self.config = Config(alert_drop_percent=3, cameras=[Camera(
            name="Cam", target_price=900,
            sources=[Source(label="A", url="https://a.example/cam"),
                     Source(label="B", url="https://b.example/cam"),
                     Source(label="Gone", url="https://gone.example/cam")])])

    def test_drops_against_recent_high(self):
        rows = [
            price_row("2026-08-01T13:00:00+00:00", "A", 1500),   # older than 30 days: ignored
            price_row("2026-10-01T13:00:00+00:00", "A", 1000),
            price_row("2026-10-10T13:00:00+00:00", "A", 1100),
            price_row("2026-10-01T13:00:00+00:00", "B", 1000),
            price_row("2026-10-01T13:00:00+00:00", "Gone", 2000),
            price_row("2026-10-20T13:00:00+00:00", "A", 880, url="https://a.example/listing"),
            price_row("2026-10-20T13:00:00+00:00", "B", 990),    # only 1% down: not a drop
        ]
        drops, current, latest = site.analyze(rows, self.config)
        self.assertEqual(latest, "2026-10-20T13:00:00+00:00")
        self.assertEqual([(d.source, d.was, d.now) for d in drops], [("A", 1100, 880)])
        self.assertEqual(round(drops[0].percent_off), 20)
        self.assertEqual(drops[0].url, "https://a.example/listing")
        self.assertTrue(drops[0].lowest_ever)
        self.assertEqual([c.source for c in current], ["A", "B"])  # "Gone" is stale

    def test_render(self):
        rows = [price_row("2026-10-01T13:00:00+00:00", "A", 1100),
                price_row("2026-10-20T13:00:00+00:00", "A", 880)]
        page = site.render(rows, self.config)
        self.assertIn("<s class=\"was\" aria-label=\"was\">$1,100.00</s>", page)
        self.assertIn("$880.00", page)
        self.assertIn('href="https://a.example/cam"', page)
        self.assertIn("At or below target", page)
        self.assertIn("No prices recorded yet", site.render([], self.config))


class FullRun(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.config = Config(cameras=[Camera(
            name="Sony A7 IV", target_price=2000,
            sources=[Source(label="Shop", url="https://shop.example/a7iv"),
                     Source(label="Broken", url="https://broken.example/a7iv")])])
        self.prices = {"https://shop.example/a7iv": 2200}
        patch_fetch = mock.patch.object(run_mod, "fetch", side_effect=self.fake_fetch)
        patch_pause = mock.patch.object(run_mod, "polite_pause")
        patch_mail = mock.patch.object(run_mod.notify, "email_configured", return_value=True)
        self.send = mock.patch.object(run_mod.notify, "send_email").start()
        for p in (patch_fetch, patch_pause, patch_mail):
            p.start()
        self.addCleanup(mock.patch.stopall)

    def fake_fetch(self, url):
        if "broken" in url:
            raise run_mod.FetchError("HTTP 403")
        return page_with_ld({"@type": "Product", "offers": {
            "price": self.prices[url], "priceCurrency": "USD", "availability": "InStock"}})

    def test_history_alerts_and_broken_source(self):
        self.assertEqual(run_mod.run(self.config, self.tmp), 0)
        self.send.assert_not_called()                       # first sighting: no alert
        self.prices["https://shop.example/a7iv"] = 1950      # crosses target
        run_mod.run(self.config, self.tmp)
        subject = self.send.call_args[0][0]
        self.assertIn("1,950.00", subject)
        self.assertEqual(len(History(self.tmp).rows), 2)
        self.assertIn("Shop", (self.tmp / "latest.md").read_text())

        self.send.reset_mock()
        for _ in range(run_mod.BROKEN_AFTER - 2):            # keep failing the broken one
            run_mod.run(self.config, self.tmp)
        self.assertIn("stopped working", self.send.call_args[0][0])

    def test_dry_run_writes_nothing(self):
        run_mod.run(self.config, self.tmp, dry_run=True, site_dir=self.tmp / "docs")
        self.assertFalse((self.tmp / "prices.csv").exists())
        self.assertFalse((self.tmp / "docs").exists())

    def test_run_writes_site(self):
        run_mod.run(self.config, self.tmp, site_dir=self.tmp / "docs")
        self.prices["https://shop.example/a7iv"] = 1950
        run_mod.run(self.config, self.tmp, site_dir=self.tmp / "docs")
        page = (self.tmp / "docs" / "index.html").read_text(encoding="utf-8")
        self.assertIn("$2,200.00</s>", page)
        self.assertIn("$1,950.00", page)

    def test_real_config_loads(self):
        from tracker.config import load_config
        cfg = load_config(Path(__file__).parent.parent / "cameras.yaml")
        self.assertTrue(cfg.cameras)


if __name__ == "__main__":
    unittest.main()
