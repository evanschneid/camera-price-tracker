"""A static web page of current price drops, for GitHub Pages (docs/index.html).

A "drop" is a source whose latest price is at least alert_drop_percent below
the highest price that source showed in the last LOOKBACK_DAYS. The page shows
that higher price struck through, the new price, and a link to the listing.
"""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .config import Config
from .notify import money

LOOKBACK_DAYS = 30


@dataclass
class Drop:
    camera: str
    source: str
    was: float
    now: float
    currency: str
    url: str | None
    target: float | None = None
    lowest_ever: bool = False

    @property
    def saved(self) -> float:
        return self.was - self.now

    @property
    def percent_off(self) -> float:
        return self.saved / self.was * 100


@dataclass
class Current:
    camera: str
    source: str
    price: float
    currency: str
    url: str | None


def _when(row: dict) -> datetime:
    return datetime.fromisoformat(row["checked_at"])


def analyze(rows: list[dict], config: Config) -> tuple[list[Drop], list[Current], str | None]:
    """Return (drops, all current prices, time of the latest check)."""
    if not rows:
        return [], [], None
    latest = max(r["checked_at"] for r in rows)
    since = datetime.fromisoformat(latest) - timedelta(days=LOOKBACK_DAYS)
    drops: list[Drop] = []
    current: list[Current] = []

    for camera in config.cameras:
        cam_rows = [r for r in rows if r["camera"] == camera.name]
        lowest = min((r["price"] for r in cam_rows), default=None)
        for source in camera.sources:
            src_rows = [r for r in cam_rows if r["source"] == source.label]
            # Skip sources missing from the latest check (broken or out of stock):
            # their last price is stale.
            if not src_rows or src_rows[-1]["checked_at"] != latest:
                continue
            last = src_rows[-1]
            currency = last.get("currency") or config.currency
            url = last.get("listing_url") or source.url
            current.append(Current(camera.name, source.label, last["price"], currency, url))

            was = max(r["price"] for r in src_rows if _when(r) >= since)
            if last["price"] <= was * (1 - config.alert_drop_percent / 100):
                drops.append(Drop(camera.name, source.label, was, last["price"], currency, url,
                                  camera.target_price, last["price"] <= lowest))

    drops.sort(key=lambda d: d.percent_off, reverse=True)
    return drops, current, latest


def _link(url: str | None, text: str, cls: str = "") -> str:
    attr = f' class="{cls}"' if cls else ""
    if not url:
        return f"<span{attr}>{html.escape(text)}</span>"
    return (f'<a{attr} href="{html.escape(url)}" target="_blank" rel="noopener">'
            f"{html.escape(text)}</a>")


def _drop_card(d: Drop) -> str:
    badges = []
    if d.target is not None and d.now <= d.target:
        badges.append('<span class="badge good">At or below target</span>')
    if d.lowest_ever:
        badges.append('<span class="badge">Lowest seen</span>')
    return f"""
    <article class="card">
      <div class="card-top">
        <h3>{html.escape(d.camera)}</h3>
        <span class="off">−{d.percent_off:.0f}%</span>
      </div>
      <p class="source">{html.escape(d.source)}</p>
      <p class="prices">
        <s class="was" aria-label="was">{money(d.was, d.currency)}</s>
        <span class="now">{money(d.now, d.currency)}</span>
      </p>
      <p class="saved">Save {money(d.saved, d.currency)}</p>
      {f'<p class="badges">{"".join(badges)}</p>' if badges else ""}
      {_link(d.url, f"View at {d.source} →", "go")}
    </article>"""


def render(rows: list[dict], config: Config) -> str:
    drops, current, latest = analyze(rows, config)

    if drops:
        drops_html = f'<div class="grid">{"".join(_drop_card(d) for d in drops)}</div>'
    elif latest:
        drops_html = '<p class="empty">No price drops right now. Check back after the next run.</p>'
    else:
        drops_html = '<p class="empty">No prices recorded yet. They appear after the first run.</p>'

    table_rows = "".join(
        f"<tr><td>{html.escape(c.camera)}</td><td>{_link(c.url, c.source)}</td>"
        f'<td class="num">{money(c.price, c.currency)}</td></tr>'
        for c in current)
    table_html = (f"""
  <h2>All current prices</h2>
  <table>
    <thead><tr><th>Camera</th><th>Source</th><th class="num">Price</th></tr></thead>
    <tbody>{table_rows}</tbody>
  </table>""" if current else "")

    checked = (f'Last checked <time datetime="{html.escape(latest)}">{html.escape(latest)} UTC</time>'
               if latest else "")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Camera Price Drops</title>
<style>
  :root {{
    --bg: #f6f7f9; --card: #ffffff; --text: #16181d; --muted: #646b78;
    --line: #e3e6eb; --accent: #0b7a3e; --accent-bg: #e3f5ea; --link: #1a5fd0;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #111317; --card: #1a1d23; --text: #eceef2; --muted: #9aa1ad;
      --line: #2a2e36; --accent: #4cd68a; --accent-bg: #173326; --link: #7fb0ff;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text);
         font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }}
  main {{ max-width: 1000px; margin: 0 auto; padding: 32px 16px 64px; }}
  h1 {{ margin: 0 0 4px; font-size: 1.8rem; }}
  h2 {{ margin: 40px 0 12px; font-size: 1.2rem; }}
  .meta {{ color: var(--muted); margin: 0 0 24px; font-size: .9rem; }}
  .grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); }}
  .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 12px;
          padding: 18px; display: flex; flex-direction: column; }}
  .card-top {{ display: flex; justify-content: space-between; align-items: start; gap: 12px; }}
  .card h3 {{ margin: 0; font-size: 1.05rem; }}
  .off {{ background: var(--accent-bg); color: var(--accent); font-weight: 700;
         border-radius: 999px; padding: 2px 10px; font-size: .85rem; white-space: nowrap; }}
  .source {{ margin: 2px 0 12px; color: var(--muted); font-size: .9rem; }}
  .prices {{ margin: 0; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }}
  .was {{ color: var(--muted); font-size: 1.05rem; text-decoration-thickness: 2px; }}
  .now {{ font-size: 1.7rem; font-weight: 700; color: var(--accent);
         font-variant-numeric: tabular-nums; }}
  .saved {{ margin: 2px 0 0; font-size: .9rem; color: var(--muted); }}
  .badges {{ margin: 10px 0 0; display: flex; gap: 6px; flex-wrap: wrap; }}
  .badge {{ font-size: .75rem; border: 1px solid var(--line); border-radius: 999px; padding: 1px 8px; }}
  .badge.good {{ border-color: var(--accent); color: var(--accent); }}
  .go {{ margin-top: auto; padding-top: 16px; font-weight: 600; }}
  a {{ color: var(--link); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .empty {{ background: var(--card); border: 1px dashed var(--line); border-radius: 12px;
           padding: 24px; color: var(--muted); }}
  table {{ width: 100%; border-collapse: collapse; background: var(--card);
          border: 1px solid var(--line); border-radius: 12px; overflow: hidden; font-size: .95rem; }}
  th, td {{ text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--line); }}
  th {{ color: var(--muted); font-weight: 600; font-size: .85rem; }}
  tr:last-child td {{ border-bottom: 0; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
</style>
</head>
<body>
<main>
  <h1>📉 Camera price drops</h1>
  <p class="meta">Prices at least {config.alert_drop_percent:g}% below their {LOOKBACK_DAYS}-day high. {checked}</p>
  {drops_html}
  {table_html}
</main>
<script>
  // Show the check time in the viewer's own time zone.
  for (const t of document.querySelectorAll("time[datetime]")) {{
    const d = new Date(t.getAttribute("datetime"));
    if (!isNaN(d)) t.textContent = d.toLocaleString([], {{dateStyle: "medium", timeStyle: "short"}});
  }}
</script>
</body>
</html>
"""


def write_site(rows: list[dict], config: Config, site_dir: str | Path = "docs") -> Path:
    path = Path(site_dir) / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(rows, config), encoding="utf-8")
    return path
