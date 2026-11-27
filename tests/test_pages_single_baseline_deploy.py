"""Guard: GitHub Pages deploy must ship exactly one canonical baseline archive.

Policy (SYSTEM_MAP / daily-update.yml):
- Pages: only ``baseline_master_2026-02-09.json.gz``
- Repo/cache may also keep ``baseline_master.json.gz`` (working alias; not on Pages)
- Orphan dated archives (e.g. 2026-05-12 / 2026-05-13) must not appear on Pages
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

CANONICAL_PAGES_BASELINE = "baseline_master_2026-02-09.json.gz"
FORBIDDEN_PAGES_SUBSTRINGS = (
    "baseline_master_2026-05-12",
    "baseline_master_2026-05-13",
)


def pages_baseline_names(deploy_root: Path) -> list[str]:
    ds = deploy_root / "delta_snapshots"
    if not ds.is_dir():
        return []
    return sorted(p.name for p in ds.glob("baseline_master*.json.gz") if p.is_file())


def assert_pages_single_baseline(deploy_root: Path) -> list[str]:
    names = pages_baseline_names(deploy_root)
    if names != [CANONICAL_PAGES_BASELINE]:
        raise AssertionError(
            f"Pages deploy must contain exactly [{CANONICAL_PAGES_BASELINE!r}], got {names!r}"
        )
    for n in names:
        for bad in FORBIDDEN_PAGES_SUBSTRINGS:
            if bad in n:
                raise AssertionError(f"Forbidden orphan baseline on Pages: {n}")
    return names


class TestPagesSingleBaselineDeploy(unittest.TestCase):
    def test_accepts_feb9_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ds = root / "delta_snapshots"
            ds.mkdir(parents=True)
            (ds / CANONICAL_PAGES_BASELINE).write_bytes(b"x")
            self.assertEqual(assert_pages_single_baseline(root), [CANONICAL_PAGES_BASELINE])

    def test_rejects_master_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ds = root / "delta_snapshots"
            ds.mkdir(parents=True)
            (ds / CANONICAL_PAGES_BASELINE).write_bytes(b"x")
            (ds / "baseline_master.json.gz").write_bytes(b"x")
            with self.assertRaises(AssertionError):
                assert_pages_single_baseline(root)

    def test_rejects_may_orphans(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ds = root / "delta_snapshots"
            ds.mkdir(parents=True)
            (ds / CANONICAL_PAGES_BASELINE).write_bytes(b"x")
            (ds / "baseline_master_2026-05-12.json.gz").write_bytes(b"x")
            (ds / "baseline_master_2026-05-13.json.gz").write_bytes(b"x")
            with self.assertRaises(AssertionError):
                assert_pages_single_baseline(root)

    def test_rejects_empty(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "delta_snapshots").mkdir(parents=True)
            with self.assertRaises(AssertionError):
                assert_pages_single_baseline(root)

    def test_experiment_snapshot_b_matches_policy(self):
        """Local shrink experiment candidate tree, when present, must pass the guard."""
        snap_b = (
            Path(__file__).resolve().parent.parent
            / "_baseline_shrink_experiment"
            / "snapshot_b"
        )
        if not snap_b.is_dir():
            self.skipTest("snapshot_b experiment tree not present")
        names = assert_pages_single_baseline(snap_b)
        self.assertEqual(names, [CANONICAL_PAGES_BASELINE])


if __name__ == "__main__":
    unittest.main()
