"""One full check of every camera and source."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import notify
from .alerts import Alert, find_alerts
from .config import Config, Source
from .fetch import FetchError, fetch, polite_pause
from .history import History
from .sources import PriceResult, SourceError
from .sources import ebay, product_page

# Email about a source after this many failed runs in a row (2 runs/day -> 3 days).
BROKEN_AFTER = 6


class OutOfStock(SourceError):
    """Page works fine; the item just isn't available. Not a failure."""


def check_source(source: Source) -> PriceResult:
    if source.kind == "ebay":
        html = fetch(ebay.search_url(source.ebay_query, source.condition))
        return ebay.extract_lowest(html, source.title_has_any, source.exclude, source.min_price)
    result = product_page.extract_price(fetch(source.url))
    if result.in_stock is False:
        raise OutOfStock(f"out of stock (listed at {result.price:,.2f})")
    return result


def run(config: Config, data_dir: str | Path = "data", dry_run: bool = False) -> int:
    history = History(data_dir)
    status = history.load_status()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    new_rows: list[dict] = []
    alerts: list[Alert] = []
    errors: list[str] = []
    newly_broken: list[str] = []
    best_now: dict[str, tuple[float, str]] = {}
    report = [f"# Latest prices\n\nChecked {now} UTC\n"]

    first = True
    for camera in config.cameras:
        report.append(f"\n## {camera.name}\n")
        if camera.target_price:
            report.append(f"Target: {notify.money(camera.target_price, config.currency)}\n")
        report.append("\n| Source | Price | Change |\n|---|---|---|")
        lowest_before = history.lowest_ever(camera.name)

        for source in camera.sources:
            if not first:
                polite_pause()
            first = False
            key = f"{camera.name} | {source.label}"
            try:
                result = check_source(source)
            except OutOfStock as exc:
                status[key] = 0
                print(f"  - {key}: {exc}")
                report.append(f"| {source.label} | {exc} | |")
                continue
            except (FetchError, SourceError) as exc:
                fails = status.get(key, 0) + 1
                status[key] = fails
                if fails == BROKEN_AFTER:
                    newly_broken.append(f"{key}: {exc}")
                errors.append(f"{key}: {exc}")
                print(f"  ✗ {key}: {exc}")
                report.append(f"| {source.label} | ⚠️ {exc} | |")
                continue

            status[key] = 0
            previous = history.last_price(camera.name, source.label)
            url = result.url or source.url
            print(f"  ✓ {key}: {result.price:,.2f} [{result.method}]")

            alerts += find_alerts(camera.name, source.label, result.price, previous,
                                  camera.target_price, config.alert_drop_percent, url,
                                  lowest_before)
            new_rows.append({
                "checked_at": now, "camera": camera.name, "source": source.label,
                "price": result.price, "currency": result.currency or config.currency,
                "in_stock": "" if result.in_stock is None else result.in_stock,
                "listing_url": url or "",
            })
            if camera.name not in best_now or result.price < best_now[camera.name][0]:
                best_now[camera.name] = (result.price, source.label)

            change = ""
            if previous:
                pct = (result.price - previous) / previous * 100
                change = f"{pct:+.1f}%" if abs(pct) >= 0.05 else "—"
            price_md = notify.money(result.price, config.currency)
            report.append(f"| {source.label} | [{price_md}]({url}) | {change} |" if url
                          else f"| {source.label} | {price_md} | {change} |")

    print(f"\n{len(new_rows)} prices, {len(errors)} errors, {len(alerts)} alerts")
    if dry_run:
        print("(dry run: nothing saved, no email sent)")
        for a in alerts:
            print(f"  would alert: {a.camera} / {a.source} {a.price:,.2f} ({a.reason})")
        return 0

    history.append(new_rows)
    history.save_status(status)
    Path(data_dir, "latest.md").write_text("\n".join(report) + "\n")

    if alerts or newly_broken:
        subject, text, body = (notify.format_alerts(alerts, config.currency, best_now)
                               if alerts else ("⚠️ Camera tracker: a source stopped working", "", ""))
        if newly_broken:
            note = ("These sources have failed for 3 days straight and may need a new URL "
                    "or filters:\n" + "\n".join(f"- {b}" for b in newly_broken))
            text = f"{text}\n\n{note}".strip()
            body = f"{body}<p>{note.replace(chr(10), '<br>')}</p>"
        if notify.email_configured():
            notify.send_email(subject, text, body)
            print(f"emailed: {subject}")
        else:
            print(f"email not configured; would have sent: {subject}\n{text}")

    # Fail the run only if *everything* failed, so GitHub shows a red X.
    return 1 if errors and not new_rows else 0
