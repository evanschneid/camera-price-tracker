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
    condition: str = "any"
    title_has_any: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    min_price: float = 0.0

    @property
    def kind(self) -> str:
        return "ebay" if self.ebay_query else "page"


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


def load_config(path: str | Path = "cameras.yaml") -> Config:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    settings = raw.get("settings") or {}
    cameras = []
    for i, cam in enumerate(raw.get("cameras") or []):
        name = cam.get("name")
        if not name:
            raise ConfigError(f"camera #{i + 1} has no name")
        sources = []
        for j, src in enumerate(cam.get("sources") or []):
            label = src.get("label") or f"source {j + 1}"
            if bool(src.get("url")) == bool(src.get("ebay_query")):
                raise ConfigError(f"{name} / {label}: give exactly one of url or ebay_query")
            condition = str(src.get("condition", "any")).lower()
            if condition not in ("new", "used", "any"):
                raise ConfigError(f"{name} / {label}: condition must be new, used or any")
            sources.append(Source(
                label=label,
                url=src.get("url"),
                ebay_query=src.get("ebay_query"),
                condition=condition,
                title_has_any=list(src.get("title_has_any") or []),
                exclude=list(src.get("exclude") or []),
                min_price=float(src.get("min_price") or 0),
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
