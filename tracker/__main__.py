"""Command line:

  python -m tracker run            check everything, save, email on drops
  python -m tracker run --dry-run  check everything, change nothing
  python -m tracker check <url>    test one product page or eBay query
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

    p_check = sub.add_parser("check", help="test a single URL or eBay search")
    p_check.add_argument("target", help="product URL, or an eBay search like 'ebay:sony a7 iv'")

    sub.add_parser("test-email", help="send a test email")

    args = parser.parse_args(argv)

    if args.cmd == "run":
        return run(load_config(args.config), data_dir=args.data, dry_run=args.dry_run)

    if args.cmd == "check":
        if args.target.startswith("ebay:"):
            source = Source(label="test", ebay_query=args.target[5:].strip(), condition="any")
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
