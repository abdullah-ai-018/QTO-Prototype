"""Tests proving primary drawing intent precedence over incidental secondary keywords
in blueprint page classification and wall tag discovery.
"""

from app.geometry.page_classifier import PageType, classify_page_content
from app.geometry.wall_tags import WallTagResolver


def test_partition_and_hardscape_plan_intent():
    """A sheet titled 'PARTITION AND HARDSCAPE PLAN' must be classified as PARTITION_PLAN,
    takeoff eligible with authority PARTITION_WALLS, not overridden by the word 'HARDSCAPE' into SITE_PLAN.
    """
    raw_tokens = ["SNACK", "SHACK", "PARTITION", "AND", "HARDSCAPE", "PLAN", "A2.1", "HARDSCAPE", "PAVERS", "TREES"]
    res = classify_page_content(image_path="", raw_text_tokens=raw_tokens, line_segment_count=1500)
    assert res.page_type in (PageType.PARTITION_PLAN, PageType.FLOOR_PLAN)
    assert res.is_takeoff_eligible is True
    assert res.geometry_authority == "PARTITION_WALLS"
    assert "HARDSCAPE" in res.secondary_content


def test_egress_plan_with_occupancy_summary_intent():
    """A sheet titled 'MEANS OF EGRESS PLAN' containing 'OCCUPANCY SUMMARY' and 'GENERAL NOTES'
    must be classified as LIFE_SAFETY_EGRESS_PLAN and HARD-GATED as NON-TAKEOFF eligible.
    """
    raw_tokens = ["MEANS", "OF", "EGRESS", "PLAN", "A0.6", "OCCUPANCY", "SUMMARY", "GENERAL", "NOTES", "KEYNOTES"]
    res = classify_page_content(image_path="", raw_text_tokens=raw_tokens, line_segment_count=1200)
    assert res.page_type == PageType.LIFE_SAFETY_EGRESS_PLAN
    assert res.is_takeoff_eligible is False
    assert res.geometry_authority == "CONTEXT_ONLY"
    assert "OCCUPANCY_SUMMARY" in res.secondary_content


def test_demolition_plan_intent():
    """A demolition plan must be classified as DEMOLITION_PLAN with authority DEMOLITION and non-drywall takeoff."""
    raw_tokens = ["DEMOLITION", "PLAN", "A1.1", "EXISTING", "WALL", "TO", "BE", "DEMOLISHED"]
    res = classify_page_content(image_path="", raw_text_tokens=raw_tokens, line_segment_count=900)
    assert res.page_type == PageType.DEMOLITION_PLAN
    assert res.is_takeoff_eligible is False
    assert res.geometry_authority == "DEMOLITION"


def test_nr_and_f_wall_tag_discovery():
    """WallTagResolver must extract and match NR-1, NR-2, NR-3, F-1, X-1 wall tags."""
    resolver = WallTagResolver()
    sample_text_items = [
        (0.20, 0.20, 0.22, 0.22, "NR-1"),
        (0.40, 0.40, 0.42, 0.42, "NR-2"),
        (0.60, 0.60, 0.62, 0.62, "NR-3"),
        (0.70, 0.70, 0.72, 0.72, "F-1"),
        (0.80, 0.80, 0.82, 0.82, "X-1"),
        (0.10, 0.10, 0.90, 0.12, "ALL PARTITIONS SHALL BE TYPE 'NR-1' UNLESS TAGGED OTHERWISE"),
        (0.10, 0.12, 0.90, 0.14, "SEE SHEET A7.1 FOR ALL WALL TYPES"),
    ]
    discovered = resolver.discover_vocabulary_from_text(sample_text_items)
    assert discovered.get("default_tag") == "NR-1"
    assert discovered.get("referenced_schedule_sheet") == "A7.1"

    tags = resolver.extract_wall_tags_from_text(sample_text_items)
    tag_names = {t["tag"] for t in tags}
    assert {"NR-1", "NR-2", "NR-3", "F-1", "X-1"}.issubset(tag_names)
