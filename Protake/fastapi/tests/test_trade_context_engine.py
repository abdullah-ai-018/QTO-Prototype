"""Tests for Trade-wise Context Engine & Forensic Wall Proof Card System.

Validates that every architectural wall carries comprehensive proof across:
  geometry + physics + topology + document context + trade context + cross-sheet evidence
"""

import pytest
from app.geometry.trade_context_engine import (
    TradeContextEngine,
    WallProofCard,
    TradeContextReport,
)


class MockArchitecturalWall:
    def __init__(
        self,
        wall_id: str = "W-023",
        source: str = "vector",
        length_ft: float = 24.7,
        height_ft: float = 10.0,
        thickness_ft: float = 4.875 / 12.0,
        wall_tag: str = "W2",
        side_a_room_index: int = 101,
        side_b_room_index: int = 102,
        openings: list = None,
        height_source: str = "RCP-A201",
        status: str = "approved",
        qto_eligible: bool = True,
        confidence: float = 0.97,
    ):
        self.wall_id = wall_id
        self.source = source
        self.length_ft = length_ft
        self.height_ft = height_ft
        self.thickness_ft = thickness_ft
        self.wall_tag = wall_tag
        self.side_a_room_index = side_a_room_index
        self.side_b_room_index = side_b_room_index
        self.room_ids = [side_a_room_index, side_b_room_index]
        self.openings = openings or [{"id": "D-12", "width_ft": 3.0}]
        self.height_source = height_source
        self.status = status
        self.qto_eligible = qto_eligible
        self.confidence = confidence
        self.has_independent_faces = True
        self.assembly_resolved = True
        self.assembly_verified = True


def test_build_wall_proof_card_exact_schema():
    """Validates that WallProofCard produces the exact required JSON proof schema."""
    tce = TradeContextEngine()
    mock_wall = MockArchitecturalWall()

    card = tce.build_wall_proof_card(
        wall=mock_wall,
        sheet_code="A-101",
        discipline="architectural",
        level="Level 1",
        scale_source="verified",
    )

    card_dict = card.to_dict()

    # Exact required fields
    assert card_dict["wall_id"] == "W-023"
    assert card_dict["source"] == "vector"
    assert card_dict["sheet"] == "A-101"
    assert card_dict["trade"] == "architectural"
    assert card_dict["level"] == "Level 1"
    assert card_dict["room_left"] == "101"
    assert card_dict["room_right"] == "102"
    assert card_dict["length_ft"] == 24.7
    assert card_dict["thickness_in"] == pytest.approx(4.875, abs=1e-3)
    assert card_dict["height_ft"] == 10.0
    assert card_dict["wall_type"] == "W2"
    assert card_dict["opening_ids"] == ["D-12"]
    assert card_dict["scale_source"] == "verified"
    assert card_dict["height_source"] == "RCP-A201"
    assert card_dict["physics"] == "PASS"
    assert card_dict["topology"] == "PASS"
    assert card_dict["qto_eligible"] is True
    assert card_dict["confidence"] == 0.97


def test_wall_proof_card_evidence_breakdown():
    """Validates the 6 deep evidence layers inside the proof card."""
    tce = TradeContextEngine()
    mock_wall = MockArchitecturalWall()

    card = tce.build_wall_proof_card(
        wall=mock_wall,
        sheet_code="A-101",
        discipline="architectural",
        level="Level 1",
        scale_source="verified",
    )

    bd = card.evidence_breakdown
    assert "geometry" in bd
    assert bd["geometry"]["length_ft"] == 24.7
    assert "physics" in bd
    assert bd["physics"]["thickness_bounds_valid"] is True
    assert "topology" in bd
    assert bd["topology"]["room_left"] == "101"
    assert bd["topology"]["room_right"] == "102"
    assert "document_context" in bd
    assert bd["document_context"]["sheet"] == "A-101"
    assert "cross_sheet" in bd
    assert bd["cross_sheet"]["height_source"] == "RCP-A201"
    assert "trade_context" in bd
    assert bd["trade_context"]["qto_eligible"] is True


def test_evaluate_sheet_trade_context():
    """Evaluates sheet-level aggregation of wall proof cards."""
    tce = TradeContextEngine()
    w1 = MockArchitecturalWall(wall_id="W-1", length_ft=20.0, height_ft=10.0)
    w2 = MockArchitecturalWall(wall_id="W-2", length_ft=30.0, height_ft=10.0)

    report = tce.evaluate_sheet_trade_context(
        walls=[w1, w2],
        sheet_code="A-101",
        discipline="architectural",
        level="Level 1",
        page_id=1,
    )

    assert report.total_walls_evaluated == 2
    assert report.qto_eligible_walls_count == 2
    assert report.qto_blocked_walls_count == 0
    # Gross SF = (20 + 30) * 10 * 2 = 1000 SF
    assert report.summary["estimated_gross_drywall_sf"] == 1000.0


def test_rejected_wall_proof_card_flagged():
    """A rejected wall with thickness violations produces physics FAIL/FLAGGED and qto_eligible=False."""
    tce = TradeContextEngine()
    w_bad = MockArchitecturalWall(
        wall_id="W-999",
        status="rejected",
        qto_eligible=False,
        confidence=0.25,
    )
    w_bad.rejection_reasons = ["impossible_thickness:35.00in"]

    card = tce.build_wall_proof_card(w_bad)
    assert card.qto_eligible is False
    assert card.physics in ("FAIL", "FLAGGED")
