"""Tests for scripts/refuse_empty_gear_day_commit.py."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_MAGELO_ROOT = Path(__file__).resolve().parents[1]
if str(_MAGELO_ROOT) not in sys.path:
    sys.path.insert(0, str(_MAGELO_ROOT))

from scripts.refuse_empty_gear_day_commit import check  # noqa: E402


class TestRefuseEmptyGearDayCommit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = Path(self.tmp) / "repo"
        self.repo.mkdir()
        gear = self.repo / "delta_snapshots" / "gear_events"
        gear.mkdir(parents=True)
        self.manifest = gear / "manifest.json"
        subprocess.check_call(["git", "init"], cwd=self.repo, stdout=subprocess.DEVNULL)
        subprocess.check_call(
            ["git", "config", "user.email", "test@example.com"], cwd=self.repo
        )
        subprocess.check_call(["git", "config", "user.name", "test"], cwd=self.repo)

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def _commit_manifest(self, days: dict) -> None:
        self.manifest.write_text(
            json.dumps({"version": 1, "days": days}), encoding="utf-8"
        )
        subprocess.check_call(["git", "add", "-A"], cwd=self.repo)
        subprocess.check_call(
            ["git", "commit", "-m", "m"],
            cwd=self.repo,
            stdout=subprocess.DEVNULL,
            env={**os.environ, "GIT_AUTHOR_DATE": "2026-07-13T12:00:00", "GIT_COMMITTER_DATE": "2026-07-13T12:00:00"},
        )

    def test_refuses_n_to_zero(self):
        self._commit_manifest(
            {
                "2026-07-12": {"gear": 100, "char": 10},
                "2026-07-13": {"gear": 200, "char": 20},
            }
        )
        self.manifest.write_text(
            json.dumps(
                {
                    "version": 1,
                    "days": {
                        "2026-07-12": {"gear": 100, "char": 10},
                        "2026-07-13": {"gear": 0, "char": 0},
                    },
                }
            ),
            encoding="utf-8",
        )
        cwd = os.getcwd()
        try:
            os.chdir(self.repo)
            self.assertEqual(check("2026-07-13", self.manifest), 1)
        finally:
            os.chdir(cwd)

    def test_allows_healthy_update(self):
        self._commit_manifest({"2026-07-13": {"gear": 200, "char": 20}})
        self.manifest.write_text(
            json.dumps(
                {"version": 1, "days": {"2026-07-13": {"gear": 190, "char": 18}}}
            ),
            encoding="utf-8",
        )
        cwd = os.getcwd()
        try:
            os.chdir(self.repo)
            self.assertEqual(check("2026-07-13", self.manifest), 0)
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
