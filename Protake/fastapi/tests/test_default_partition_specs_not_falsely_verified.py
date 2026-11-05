"""Regression test for a provenance bug found during the Phase 5 migration
audit: a wall whose tag matched DEFAULT_PARTITION_SPECS (wall_tags.py) — an
industry-standard stock library loaded only when NO real schedule evidence
exists anywhere in the document — was being marked assembly_verified=True,
identical to a wall matched against this project's own real schedule table.

Root cause: DEFAULT_PARTITION_SPECS entries claimed
source="partition_schedule"/"partition_plan_notes" (implying real project
evidence) even though they are hardcoded defaults, and
DrywallSemanticWallPipeline's verification-promotion logic checked only
`tag != "DEFAULT"` — which is true for every DEFAULT_PARTITION_SPECS entry
(their tags are "NR-1", "W1", etc., never the literal string "DEFAULT"), so
every one of them got silently promoted to "verified".

Fixed by: (1) correcting DEFAULT_PARTITION_SPECS entries to
source="default_spec", and (2) checking `assembly.source` instead of the tag
string wherever the pipeline decides whether an assembly is real or assumed.
"""

from app.models.room import Room
from app.models.wall import Wall
from app.models.enums import WallType
from app.models.architectural_wall import WallDecisionState, DrywallScopeDecision
from app.trades.drywall_semantic import DrywallSemanticWallPipeline
from app.geometry.wall_tags import DEFAULT_PARTITION_SPECS


def test_default_partition_specs_source_is_labeled_as_default():
    """Every DEFAULT_PARTITION_SPECS entry must honestly identify itself as
    a stock default, not as project-schedule-derived evidence."""
    assert len(DEFAULT_PARTITION_SPECS) > 0
    for tag, spec in DEFAULT_PARTITION_SPECS.items():
        assert spec.source == "default_spec", (
            f"DEFAULT_PARTITION_SPECS['{tag}'].source is '{spec.source}', "
            "not 'default_spec' — this would make a stock-library match "
            "indistinguishable from a real schedule-verified assembly."
        )


def test_wall_matching_default_partition_spec_is_not_falsely_verified():
    """A wall whose tag matches the DEFAULT_PARTITION_SPECS library, with NO
    real schedule_evidence provided and no referenced-but-missing schedule
    sheet, must be QTO-eligible at the PROVISIONAL tier (assembly_verified
    False, lower confidence) — never CONFIRMED like a real schedule match.

    DrywallSemanticWallPipeline never auto-loads DEFAULT_PARTITION_SPECS into
    its resolver in normal production flow (see the pipeline's __init__: it
    deliberately always passes allow_defaults=False to WallTagResolver so the
    per-wall generic fallback handles unresolved assemblies instead — a real,
    intentional design choice, confirmed by reading it, not a bug). The
    library IS reachable the way a real caller would supply a custom spec
    set: via `schedule_specs`, which WallTagResolver loads unconditionally
    into `self.specs` regardless of `allow_defaults`. That is what this test
    exercises, since it is the only path through the pipeline's public API
    that reaches DEFAULT_PARTITION_SPECS-sourced assemblies today.
    """
    pipeline = DrywallSemanticWallPipeline(schedule_specs=DEFAULT_PARTITION_SPECS)

    rooms = [
        Room(id=1, page_id=1, name="Office", area_sqft=200.0, perimeter_ft=60.0,
             polygon_norm=[{"x": 0.2, "y": 0.2}, {"x": 0.5, "y": 0.2}, {"x": 0.5, "y": 0.5}, {"x": 0.2, "y": 0.5}]),
    ]
    wall = Wall(
        id=301, page_id=1, length_ft=20.0, height_ft=9.0, wall_type=WallType.INTERIOR,
        start_norm={"x": 0.2, "y": 0.2}, end_norm={"x": 0.5, "y": 0.2}, confidence=0.95,
        thickness_ft=0.406, thickness_measured=True,
        face_a_segment_id=3011, face_b_segment_id=3012,
    )
    # "TYPE NR-1" matches DEFAULT_PARTITION_SPECS["NR-1"] — no "SEE SHEET..."
    # reference, and no real schedule_evidence was supplied to the pipeline.
    text_items = [
        (0.25, 0.20, 0.28, 0.22, "TYPE NR-1"),
    ]

    results = pipeline.process_architectural_walls(rooms, [wall], text_items=text_items)
    assert len(results) == 1
    w = results[0]

    assert w.wall_tag == "NR-1"
    assert w.assembly is not None
    assert w.assembly.source == "default_spec"

    # The core regression: this must be False. Before the fix, matching a
    # DEFAULT_PARTITION_SPECS tag (any tag other than the literal string
    # "DEFAULT") silently promoted assembly_verified to True.
    assert w.assembly_verified is False, (
        "A wall matched against DEFAULT_PARTITION_SPECS (an industry-standard "
        "stock library, not this project's real schedule) must never be "
        "reported as assembly_verified=True."
    )

    # Still QTO-eligible, at the PROVISIONAL tier — a stock assumption is
    # allowed to produce a quantity, it just can't claim to be confirmed.
    assert w.qto_eligible is True
    assert w.decision_state != WallDecisionState.WALL_ASSEMBLY_CONFIRMED
    assert w.drywall_scope == DrywallScopeDecision.REQUIRED

    card = w.to_evidence_card()
    assert card["assembly_verified"] is False
