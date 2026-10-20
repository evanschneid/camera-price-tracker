"""Decide which price changes are worth an email."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Alert:
    camera: str
    source: str
    price: float
    previous: float | None
    reason: str          # "drop" or "target"
    url: str | None
    lowest_ever: bool = False

    @property
    def change_percent(self) -> float | None:
        if not self.previous:
            return None
        return (self.price - self.previous) / self.previous * 100


def find_alerts(camera: str, source: str, price: float, previous: float | None,
                target: float | None, drop_percent: float, url: str | None,
                previous_lowest: float | None) -> list[Alert]:
    """Alert when a price drops enough, or first crosses the target price."""
    lowest = previous_lowest is not None and price < previous_lowest
    if target is not None and price <= target and (previous is None or previous > target):
        return [Alert(camera, source, price, previous, "target", url, lowest)]
    if previous is not None and price <= previous * (1 - drop_percent / 100):
        return [Alert(camera, source, price, previous, "drop", url, lowest)]
    return []
