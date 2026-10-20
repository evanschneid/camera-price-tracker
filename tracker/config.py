"""Load and validate cameras.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Source:
    label: str
    url: str | None = None
    ebay_query: str | None = None
    shop: str | None = None         # Shopify shop domain, e.g. kmcamera.com
    query: str | None = None        # what to search for at the shop
    condition: str = "any"
    title_has_any: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    min_price: float = 0.0

    @property
    def kind(self) -> str:
        if self.ebay_query:
            return "ebay"
        return "shopify" if self.shop else "page"


@dataclass
class Camera:
    name: str
    sources: list[Source]
    target_price: float | None = None


@dataclass
class Config:
    cameras: list[Camera]
    currency: str = "USD"
    alert_drop_percent: float = 3.0


class ConfigError(ValueError):
    pass


def _words(value) -> list[str]:
    return list(value or [])


def load_config(path: str | Path = "cameras.yaml") -> Config:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    settings = raw.get("settings") or {}
    shared_exclude = _words(settings.get("exclude"))
    cameras = []
    for i, cam in enumerate(raw.get("cameras") or []):
        name = cam.get("name")
        if not name:
            raise ConfigError(f"camera #{i + 1} has no name")
        sources = []
        for j, src in enumerate(cam.get("sources") or []):
            label = src.get("label") or f"source {j + 1}"
            if sum(bool(src.get(k)) for k in ("url", "ebay_query", "shop")) != 1:
                raise ConfigError(f"{name} / {label}: give exactly one of url, ebay_query or shop")
            condition = str(src.get("condition", "any")).lower()
            if condition not in ("new", "used", "any"):
                raise ConfigError(f"{name} / {label}: condition must be new, used or any")
            # Search filters can be set once on the camera; a source can override
            # them, and exclude words add up (settings + camera + source).
            min_price = src.get("min_price", cam.get("min_price"))
            sources.append(Source(
                label=label,
                url=src.get("url"),
                ebay_query=src.get("ebay_query"),
                shop=src.get("shop"),
                query=src.get("query") or cam.get("search") or name,
                condition=condition,
                title_has_any=_words(src.get("title_has_any") or cam.get("title_has_any")),
                exclude=shared_exclude + _words(cam.get("exclude")) + _words(src.get("exclude")),
                min_price=float(min_price or 0),
            ))
        if not sources:
            raise ConfigError(f"{name} has no sources")
        target = cam.get("target_price")
        cameras.append(Camera(name=name, sources=sources,
                              target_price=float(target) if target is not None else None))
    if not cameras:
        raise ConfigError("no cameras configured")
    return Config(
        cameras=cameras,
        currency=settings.get("currency", "USD"),
        alert_drop_percent=float(settings.get("alert_drop_percent", 3)),
    )
