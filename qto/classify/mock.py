"""
Deterministic mock classifier for drywall wall types.
Provides offline, reproducible classification when Jev API is unavailable or in testing environments.
"""

from __future__ import annotations
import re
from typing import Any, Dict


class MockClassifier:
    """
    Deterministic rule-based classifier adhering to SOP 8.2 (A4) criteria.
    - True (>= 0.90): Gypsum Wall Board (GWB), Gypsum Board, metal studs, furring.
    - False (< 0.50): Glass officefront (GL1, GL2), demountable privacy wall (PW), raw masonry.
    """

    def __init__(self, default_drywall_prob: float = 0.92):
        self.default_drywall_prob = default_drywall_prob

    def evaluate(self, wall_tag: str, materials: str) -> float:
        tag_upper = wall_tag.strip().upper()
        mat_upper = materials.strip().upper()

        # Non-drywall tags
        if tag_upper.startswith("GL") or tag_upper in {"GL1", "GL2", "GL3", "GL4"}:
            return 0.05
        if tag_upper == "PW":
            return 0.10

        # Check explicit negative keywords in materials
        if "GLASS" in mat_upper or "GLAZING" in mat_upper or "DEMOUNTABLE" in mat_upper:
            if not ("GYPSUM" in mat_upper or "GWB" in mat_upper or "DRYWALL" in mat_upper):
                return 0.05

        if "MASONRY" in mat_upper or "CMU" in mat_upper or "CONCRETE BLOCK" in mat_upper:
            if not ("FURRING" in mat_upper or "GYPSUM" in mat_upper or "GWB" in mat_upper):
                return 0.10

        # Check explicit drywall keywords
        drywall_keywords = [
            "GWB",
            "GYP",
            "GYPSUM",
            "DRYWALL",
            "SHEETROCK",
            "TYPE X",
            "TYPE C",
            "TYPE-C",
            "TYPE-SCX",
            "METAL STUD",
            "STEEL STUD",
            "CH STUD",
            "C-H STUD",
            "FURRING",
            "DRYWALL ON",
        ]
        if any(kw in mat_upper for kw in drywall_keywords):
            return 0.95

        # Check standard partition tag pattern (e.g. 1A, 2B, 7A, 1A2)
        if re.match(r"^([0-9][A-Z]|[1-9][A-Z][0-9])$", tag_upper):
            return self.default_drywall_prob

        return 0.50


_default_mock_classifier = MockClassifier()


def evaluate_with_mock(wall_tag: str, materials: str) -> float:
    """Evaluates drywall probability using the deterministic MockClassifier."""
    return _default_mock_classifier.evaluate(wall_tag, materials)
