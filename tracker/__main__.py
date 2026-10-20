"""Command line:

  python -m tracker run            check everything, save, email on drops
  python -m tracker run --dry-run  check everything, change nothing
  python -m tracker check <url>    test one product page, eBay query or shop search
  python -m tracker site           rebuild docs/index.html from saved prices
  python -m tracker test-email     send a test email
"""
from __future__ import annotations

import argparse
import sys

from .config import Source, load_config
from .run import check_source, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tracker", description="Camera price tracker")
    parser.add_argument("--config", default="cameras.yaml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="check all prices")
    p_run.add_argument("--dry-run", action="store_true")
    p_run.add_argument("--data", default="data")
    p_run.add_argument("--site", default="docs", help="where to write the price drop page")

    p_site = sub.add_parser("site", help="rebuild the price drop page without checking prices")
    p_site.add_argument("--data", default="data")
    p_site.add_argument("--site", default="docs")

    p_check = sub.add_parser("check", help="test a single URL, eBay search or shop search")
    p_check.add_argument("target", help="product URL, an eBay search like 'ebay:pentax k1000', "
                                        "or a shop search like 'shop:kmcamera.com pentax k1000'")

    sub.add_parser("test-email", help="send a test email")

    args = parser.parse_args(argv)

    if args.cmd == "run":
        return run(load_config(args.config), data_dir=args.data, dry_run=args.dry_run,
                   site_dir=args.site)

    if args.cmd == "site":
        from .history import History
        from .site import write_site
        path = write_site(History(args.data).rows, load_config(args.config), args.site)
        print(f"wrote {path}")
        return 0

    if args.cmd == "check":
        if args.target.startswith("ebay:"):
            source = Source(label="test", ebay_query=args.target[5:].strip(), condition="any")
        elif args.target.startswith("shop:"):
            shop, _, query = args.target[5:].strip().partition(" ")
            # Shop searches return loosely related items; keep titles with the query in them.
            source = Source(label="test", shop=shop, query=query.strip(),
                            title_has_any=[query.strip()])
        else:
            source = Source(label="test", url=args.target)
        try:
            r = check_source(source)
        except Exception as exc:
            print(f"✗ {exc}")
            return 1
        print(f"✓ {r.price:,.2f} {r.currency or ''}  in_stock={r.in_stock}  via {r.method}")
        print(f"  {r.title}")
        if r.url:
            print(f"  {r.url}")
        return 0

    if args.cmd == "test-email":
        from . import notify
        if not notify.email_configured():
            print("Set EMAIL_ADDRESS and EMAIL_APP_PASSWORD first.")
            return 1
        notify.send_email("✅ Camera tracker test", "Email alerts are working.")
        print("sent")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
