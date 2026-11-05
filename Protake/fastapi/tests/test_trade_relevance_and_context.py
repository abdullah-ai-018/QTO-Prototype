import pytest
from app.geometry.page_classifier import PageType, TradeRelevance, get_trade_relevance
from app.models.enums import DetectionKind, TradeKey

def test_drywall_trade_relevance_classification():
    # Drywall high relevance
    assert get_trade_relevance(PageType.PARTITION_PLAN, "drywall") == TradeRelevance.HIGH
    assert get_trade_relevance(PageType.FLOOR_PLAN, "drywall") == TradeRelevance.HIGH
    assert get_trade_relevance(PageType.SCHEDULE_SPECIFICATION, "drywall") == TradeRelevance.HIGH

    # Drywall medium relevance
    assert get_trade_relevance(PageType.RCP, "drywall") == TradeRelevance.MEDIUM
    assert get_trade_relevance(PageType.SECTION, "drywall") == TradeRelevance.MEDIUM
    assert get_trade_relevance(PageType.ELEVATION, "drywall") == TradeRelevance.MEDIUM

    # Drywall NOT_RELEVANT (must NOT generate drywall takeoff)
    assert get_trade_relevance(PageType.ROOF_PLAN, "drywall") == TradeRelevance.NOT_RELEVANT
    assert get_trade_relevance(PageType.SITE_PLAN, "drywall") == TradeRelevance.NOT_RELEVANT
    assert get_trade_relevance(PageType.DEMOLITION_PLAN, "drywall") == TradeRelevance.NOT_RELEVANT
    assert get_trade_relevance(PageType.LIFE_SAFETY_EGRESS_PLAN, "drywall") == TradeRelevance.NOT_RELEVANT
    assert get_trade_relevance(PageType.NON_ARCHITECTURAL, "drywall") == TradeRelevance.NOT_RELEVANT

def test_roofing_trade_relevance_classification():
    assert get_trade_relevance(PageType.ROOF_PLAN, "roofing") == TradeRelevance.HIGH
    assert get_trade_relevance(PageType.FLOOR_PLAN, "roofing") == TradeRelevance.NOT_RELEVANT
    assert get_trade_relevance(PageType.PARTITION_PLAN, "roofing") == TradeRelevance.NOT_RELEVANT
