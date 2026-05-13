"""Tests for scripts/verify_delta_baseline_archives.py."""

import gzip
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_MAGELO_ROOT = Path(__file__).resolve().parent.parent


class TestVerifyDeltaBaselineArchivesScript(unittest.TestCase):
    def _run(self, tmp: Path) -> int:
        script = _MAGELO_ROOT / "scripts" / "verify_delta_baseline_archives.py"
        env = dict(os.environ)
        proc = subprocess.run(
            [sys.executable, str(script), "--base-dir", str(tmp)],
            cwd=str(_MAGELO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode

    def _write_gz(self, path: Path, obj: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(obj, f)

    def test_ok_when_master_matches_baseline_date(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_gz(
                root / "baseline_master.json.gz",
                {"baseline_date": "2026-02-09", "characters": {}, "inventories": {}},
            )
            self._write_gz(
                root / "delta_daily_2026-05-08.json.gz",
                {
                    "date": "2026-05-08",
                    "baseline_date": "2026-02-09",
                    "char_deltas": {},
                    "inv_deltas": {},
                },
            )
            self.assertEqual(self._run(root), 0)

    def test_fails_when_may_dump_before_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._write_gz(
                root / "baseline_master.json.gz",
                {"baseline_date": "2026-05-13", "characters": {}, "inventories": {}},
            )
            self._write_gz(
                root / "delta_daily_2026-05-09.json.gz",
                {
                    "date": "2026-05-09",
                    "baseline_date": "2026-05-12",
                    "char_deltas": {"x": {}},
                    "inv_deltas": {},
                },
            )
            self.assertNotEqual(self._run(root), 0)
