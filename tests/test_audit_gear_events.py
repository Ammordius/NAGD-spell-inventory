"""Tests for scripts/audit_gear_events.py anomaly scoping."""

from __future__ import annotations

import gzip
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_MAGELO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MAGELO_ROOT not in sys.path:
    sys.path.insert(0, _MAGELO_ROOT)

from scripts.audit_gear_events import audit  # noqa: E402


def _write_minimal_gear_tree(base: Path, manifest_days: dict) -> None:
    gear_root = base / "gear_events"
    gear_root.mkdir(parents=True)
    manifest = {"days": manifest_days}
    (gear_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    events = []
    for d, meta in manifest_days.items():
        gear_n = int(meta.get("gear") or 0)
        for _ in range(gear_n):
            events.append({"d": d, "c": "Char", "i": "1", "s": 1, "n": 1, "v": 0})
    month = "2026-07"
    with gzip.open(gear_root / f"gear_{month}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(events, f)


class TestAuditGearEventsScoping(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.base = Path(self.tmp) / "delta_snapshots"

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_global_anomaly_flags_historical_inflated_day(self):
        days = {f"2026-07-0{i}": {"gear": 100, "char": 0} for i in range(1, 8)}
        days["2024-01-01"] = {"gear": 50000, "char": 0}
        _write_minimal_gear_tree(self.base, days)
        issues = audit(self.base, None, anomaly_median_factor=5.0)
        inflated = [i for i in issues if "2024-01-01" in i]
        self.assertEqual(len(inflated), 1)

    def test_scoped_anomaly_ignores_historical_inflated_day(self):
        days = {f"2026-07-0{i}": {"gear": 100, "char": 0} for i in range(1, 8)}
        days["2024-01-01"] = {"gear": 50000, "char": 0}
        _write_minimal_gear_tree(self.base, days)
        issues = audit(self.base, "2026-06-26", anomaly_median_factor=5.0)
        inflated = [i for i in issues if "2024-01-01" in i]
        self.assertEqual(inflated, [])

    def test_scoped_anomaly_still_flags_recent_inflated_day(self):
        days = {f"2026-07-0{i}": {"gear": 100, "char": 0} for i in range(1, 8)}
        days["2026-07-03"] = {"gear": 50000, "char": 0}
        _write_minimal_gear_tree(self.base, days)
        issues = audit(self.base, "2026-06-26", anomaly_median_factor=5.0)
        inflated = [i for i in issues if "2026-07-03" in i]
        self.assertEqual(len(inflated), 1)


if __name__ == "__main__":
    unittest.main()
