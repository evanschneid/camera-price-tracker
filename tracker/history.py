"""Price history stored as a CSV in the repo (data/prices.csv)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

FIELDS = ["checked_at", "camera", "source", "price", "currency", "in_stock", "listing_url"]


class History:
    def __init__(self, data_dir: str | Path = "data"):
        self.dir = Path(data_dir)
        self.csv_path = self.dir / "prices.csv"
        self.status_path = self.dir / "status.json"
        self.rows = self._load()

    def _load(self) -> list[dict]:
        if not self.csv_path.exists():
            return []
        with self.csv_path.open(newline="") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            r["price"] = float(r["price"])
        return rows

    def last_price(self, camera: str, source: str) -> float | None:
        for r in reversed(self.rows):
            if r["camera"] == camera and r["source"] == source:
                return r["price"]
        return None

    def lowest_ever(self, camera: str) -> float | None:
        prices = [r["price"] for r in self.rows if r["camera"] == camera]
        return min(prices) if prices else None

    def append(self, rows: list[dict]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        new_file = not self.csv_path.exists()
        with self.csv_path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if new_file:
                writer.writeheader()
            for r in rows:
                writer.writerow({k: r.get(k, "") for k in FIELDS})
        self.rows.extend(rows)

    # --- consecutive failure tracking, so a broken source gets noticed ----

    def load_status(self) -> dict:
        if self.status_path.exists():
            return json.loads(self.status_path.read_text())
        return {}

    def save_status(self, status: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
