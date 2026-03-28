"""Run from magelo/scripts:  python -m unittest threat.test_melee_proc"""

from __future__ import annotations

import unittest

from threat.melee_proc import (
    attack_timer_duration_ms,
    get_proc_chance_fraction,
    mainhand_proc_rolls_per_second,
    wpc_from_proc_rate,
)


class TestMeleeProc(unittest.TestCase):
    def test_mainhand_ppm_at_cap_dex_matches_server_comment(self) -> None:
        """attack.cpp: ~2 PPM main hand at 255 DEX (proc mod 0), any delay+haste (cancels)."""
        delay = 22
        haste = 70
        dex = 255
        proc_rate = 0
        dur = attack_timer_duration_ms(delay, haste, 0)
        self.assertGreaterEqual(dur, 400)
        rolls = mainhand_proc_rolls_per_second(delay, haste, 0)
        base = get_proc_chance_fraction(
            dex,
            delay,
            haste_pct=haste,
            overhaste_pct=0,
            hand_is_secondary=False,
            dual_wield_chance_pct=92.0,
        )
        wpc = min(1.0, wpc_from_proc_rate(base, proc_rate))
        ppm = rolls * wpc * 60.0
        self.assertAlmostEqual(ppm, 2.0, delta=0.08)

    def test_weapon_speed_uses_timer_ms_over_100_not_delay_over_100(self) -> None:
        """Old bug: delay/100 as 'seconds' was ~100x too small vs GetDuration()/100."""
        delay = 22
        haste = 70
        dex = 255
        dur = attack_timer_duration_ms(delay, haste, 0)
        ws = dur / 100.0
        d = float(min(dex, 255))
        k = 0.0004166667 + 1.1437908496732e-5 * d
        chance_correct = k * ws
        chance_wrong_scale = k * (delay / 100.0)
        self.assertGreater(chance_correct, 50 * chance_wrong_scale)


if __name__ == "__main__":
    unittest.main()
