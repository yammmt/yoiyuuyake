from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from horizon import HorizonProfile, RayHorizon  # noqa: E402
from visibility import assess_visibility  # noqa: E402


def profile_with_angle(angle: float) -> HorizonProfile:
    return HorizonProfile(10, 270, (RayHorizon(270, angle, 1_000, 100),))


class VisibilityTests(unittest.TestCase):
    def test_wide_horizon(self) -> None:
        assessment = assess_visibility(profile_with_angle(0.8), 1.0)

        self.assertEqual(assessment.label, "広い")
        self.assertFalse(assessment.sun_likely_occluded)

    def test_partially_blocked_horizon(self) -> None:
        assessment = assess_visibility(profile_with_angle(2.0), 1.0)

        self.assertEqual(assessment.label, "一部遮られる")
        self.assertTrue(assessment.sun_likely_occluded)

    def test_easily_blocked_horizon(self) -> None:
        assessment = assess_visibility(profile_with_angle(4.1), 6.0)

        self.assertEqual(assessment.label, "遮られやすい")
        self.assertFalse(assessment.sun_likely_occluded)
