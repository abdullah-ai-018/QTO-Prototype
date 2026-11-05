"""Tests for D-002: Scale Context & Deterministic Geometry Reprocessing.

Guarantees that:
  PDF -> DOCUMENT CONTEXT -> SCALE VERIFIED -> FULL GEOMETRY RE-RUN -> WALLS -> ROOMS -> QTO

When a scale is discovered or calibrated:
  - Full geometry analysis is re-run from scratch at the calibrated scale.
  - Physical filters (minimum wall lengths, room area thresholds) are evaluated against raw pixels.
  - Post-hoc number multiplication is completely avoided.
"""

from unittest.mock import MagicMock
import numpy as np
import pytest
from PIL import Image

from app.geometry.metrics import (
    SCALE_SOURCE_ASSUMED,
    SCALE_SOURCE_MEASURED,
    SCALE_SOURCE_USER,
    ScaleContext,
    wall_length_ft,
)
from app.geometry.polygon_ops import polygon_metrics
from app.models.blueprint import Blueprint
from app.models.enums import BlueprintStatus, ReviewStatus
from app.models.page import Page
from app.services.blueprint_service import BlueprintService


# ---------------------------------------------------------------------------
# 1. Unit Tests for Scale Calibration & Reprocessing Pipeline
# ---------------------------------------------------------------------------

def test_calibrate_page_triggers_full_geometry_re_run(monkeypatch):
    """Calibrating a page via BlueprintService.calibrate_page must update the scale
    and re-run run_geometry_analysis to re-derive all geometry deterministically.
    """
    mock_db = MagicMock()
    mock_pages_repo = MagicMock()

    service = BlueprintService(mock_db)
    service.pages = mock_pages_repo

    dummy_bp = Blueprint(
        id=1,
        project_id=1,
        uploaded_by_id=1,
        original_filename="plan.pdf",
        stored_filename="plan.pdf",
        file_path="/tmp/plan.pdf",
        status=BlueprintStatus.PROCESSED,
    )
    dummy_page = Page(
        id=10,
        blueprint_id=1,
        page_number=1,
        scale_ft_per_px=None,
        scale_source=SCALE_SOURCE_ASSUMED,
        dpi=150.0,
        width_px=3000,
        height_px=2000,
        image_path="/tmp/page_1.png",
    )
    dummy_page.blueprint = dummy_bp

    # Mock pages.update to return the updated page
    def _mock_update(page_obj, **kwargs):
        for k, v in kwargs.items():
            setattr(page_obj, k, v)
        return page_obj

    mock_pages_repo.update.side_effect = _mock_update

    geometry_run_called = []
    def _mock_run_geometry_analysis(page_obj):
        geometry_run_called.append(page_obj.scale_ft_per_px)
        return MagicMock()

    monkeypatch.setattr(service, "run_geometry_analysis", _mock_run_geometry_analysis)

    # Calibrate: distance between (0,0) and (100,0) in px is 100 px, real world = 10 ft -> 0.10 ft/px
    result_page = service.calibrate_page(
        dummy_page,
        point_a=(0.0, 0.0),
        point_b=(100.0, 0.0),
        real_world_value=10.0,
        unit="ft",
        reprocess=True,
    )

    assert result_page.scale_ft_per_px == pytest.approx(0.10)
    assert result_page.scale_source == SCALE_SOURCE_USER
    assert len(geometry_run_called) == 1
    assert geometry_run_called[0] == pytest.approx(0.10)


def test_geometry_recalculation_from_raw_pixels():
    """Measurements must be derived directly from raw pixel coordinates and scale_ft_per_px,
    never through floating-point ratios multiplied onto old numbers.
    """
    # A 200px x 100px rectangle
    pts_px = [(100.0, 100.0), (300.0, 100.0), (300.0, 200.0), (100.0, 200.0)]
    w, h = 1000, 1000

    # Scale 1: 0.05 ft/px (Assumed)
    m1 = polygon_metrics(pts_px, scale_ft_per_px=0.05, image_w=w, image_h=h)
    # Area = 200 * 100 * (0.05^2) = 20000 * 0.0025 = 50.0 sqft
    # Perimeter = (200 + 100 + 200 + 100) * 0.05 = 600 * 0.05 = 30.0 ft
    assert m1["area_sqft"] == pytest.approx(50.0)
    assert m1["perimeter_ft"] == pytest.approx(30.0)

    # Scale 2: 0.025 ft/px (Calibrated) -> Derived fresh from raw pts_px
    m2 = polygon_metrics(pts_px, scale_ft_per_px=0.025, image_w=w, image_h=h)
    # Area = 200 * 100 * (0.025^2) = 20000 * 0.000625 = 12.5 sqft
    # Perimeter = 600 * 0.025 = 15.0 ft
    assert m2["area_sqft"] == pytest.approx(12.5)
    assert m2["perimeter_ft"] == pytest.approx(15.0)

    # Wall length: 200 px segment
    w_len1 = wall_length_ft((100.0, 100.0), (300.0, 100.0), scale_ft_per_px=0.05)
    w_len2 = wall_length_ft((100.0, 100.0), (300.0, 100.0), scale_ft_per_px=0.025)
    assert w_len1 == pytest.approx(10.0)
    assert w_len2 == pytest.approx(5.0)


def test_calibrate_page_recomputes_trade_takeoff(monkeypatch):
    """When a page is calibrated, trade takeoff is automatically recomputed
    for supported trades on the blueprint.
    """
    mock_db = MagicMock()
    mock_pages_repo = MagicMock()

    service = BlueprintService(mock_db)
    service.pages = mock_pages_repo

    dummy_bp = Blueprint(
        id=2,
        project_id=1,
        uploaded_by_id=1,
        original_filename="floor.pdf",
        stored_filename="floor.pdf",
        file_path="/tmp/floor.pdf",
        status=BlueprintStatus.PROCESSED,
    )
    dummy_page = Page(
        id=20,
        blueprint_id=2,
        page_number=1,
        scale_ft_per_px=None,
        scale_source=SCALE_SOURCE_ASSUMED,
        dpi=150.0,
        width_px=3000,
        height_px=2000,
        image_path="/tmp/page_2.png",
    )
    dummy_page.blueprint = dummy_bp

    mock_pages_repo.update.side_effect = lambda p, **kw: p
    monkeypatch.setattr(service, "run_geometry_analysis", lambda p: MagicMock())

    mock_trade_svc = MagicMock()
    mock_trade_svc.is_supported.return_value = True
    monkeypatch.setattr("app.services.trade_takeoff_service.TradeTakeoffService", lambda db: mock_trade_svc)

    service.calibrate_page(
        dummy_page,
        point_a=(0.0, 0.0),
        point_b=(200.0, 0.0),
        real_world_value=20.0,
        unit="ft",
        reprocess=True,
    )

    assert mock_trade_svc.compute_and_persist.called
