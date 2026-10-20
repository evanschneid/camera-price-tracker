"""Email alerts through Gmail (or any SMTP server).

Set these as GitHub Actions secrets (or environment variables locally):
  EMAIL_ADDRESS       the Gmail address that sends the alerts
  EMAIL_APP_PASSWORD  a Gmail *app password* (not your normal password)
  EMAIL_TO            where to send alerts (optional; defaults to EMAIL_ADDRESS)
  SMTP_HOST/SMTP_PORT optional, default smtp.gmail.com:465
"""
from __future__ import annotations

import html
import os
import smtplib
from email.message import EmailMessage

from .alerts import Alert


def email_configured() -> bool:
    return bool(os.environ.get("EMAIL_ADDRESS") and os.environ.get("EMAIL_APP_PASSWORD"))


def send_email(subject: str, text: str, html_body: str | None = None) -> None:
    sender = os.environ["EMAIL_ADDRESS"]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = os.environ.get("EMAIL_TO") or sender
    msg.set_content(text)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
        smtp.login(sender, os.environ["EMAIL_APP_PASSWORD"])
        smtp.send_message(msg)


def money(value: float, currency: str = "USD") -> str:
    symbol = {"USD": "$", "CAD": "CA$", "AUD": "A$", "GBP": "£", "EUR": "€"}.get(currency, "")
    return f"{symbol}{value:,.2f}" + ("" if symbol else f" {currency}")


def format_alerts(alerts: list[Alert], currency: str,
                  best_now: dict[str, tuple[float, str]]) -> tuple[str, str, str]:
    """Return (subject, plain text, html) for an alert email."""
    first = alerts[0]
    if len(alerts) == 1:
        subject = f"📉 {first.camera}: {money(first.price, currency)} at {first.source}"
    else:
        subject = f"📉 {len(alerts)} camera price drops"

    lines, items = [], []
    for a in alerts:
        what = "hit your target" if a.reason == "target" else "price drop"
        was = f" (was {money(a.previous, currency)}, {a.change_percent:+.1f}%)" if a.previous else ""
        badge = " ⭐ lowest ever seen" if a.lowest_ever else ""
        lines.append(f"- {a.camera} — {a.source}: {money(a.price, currency)}{was} — {what}{badge}"
                     + (f"\n  {a.url}" if a.url else ""))
        link = (f'<a href="{html.escape(a.url)}">{html.escape(a.source)}</a>'
                if a.url else html.escape(a.source))
        items.append(f"<li><b>{html.escape(a.camera)}</b> — {link}: "
                     f"<b>{money(a.price, currency)}</b>{html.escape(was)} — {what}"
                     f"{html.escape(badge)}</li>")

    best_lines = [f"- {cam}: {money(p, currency)} at {src}" for cam, (p, src) in best_now.items()]
    text = "\n".join(lines) + "\n\nBest price right now:\n" + "\n".join(best_lines)
    body = (f"<ul>{''.join(items)}</ul><p><b>Best price right now</b></p><ul>"
            + "".join(f"<li>{html.escape(cam)}: {money(p, currency)} at {html.escape(src)}</li>"
                      for cam, (p, src) in best_now.items())
            + "</ul>")
    return subject, text, body
