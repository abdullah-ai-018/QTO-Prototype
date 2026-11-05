"""Regression tests proving candidate non-rejected geometry is accepted and REJECTED geometry is excluded in TradeTakeoffService."""

import pytest
from app.database import SessionLocal
from app.models.blueprint import Blueprint
from app.models.page import Page
from app.models.room import Room
from app.models.wall import Wall
from app.models.enums import ReviewStatus, TradeKey
from app.services.trade_takeoff_service import TradeTakeoffService
from app.repositories.wall_repository import WallRepository
from app.repositories.room_repository import RoomRepository
from app.repositories.detection_repository import DetectionRepository


def test_candidate_repository_methods():
    """Test candidate_for_pages includes PENDING but excludes REJECTED."""
    db = SessionLocal()
    try:
        page = Page(blueprint_id=1, page_number=999, page_type="partition_plan", width_px=7980, height_px=5700, image_path="test_page_999.png")
        db.add(page)
        db.flush()

        w_pending = Wall(page_id=page.id, length_ft=10.0, status=ReviewStatus.PENDING, start_norm={"x": 0, "y": 0}, end_norm={"x": 0.1, "y": 0})
        w_approved = Wall(page_id=page.id, length_ft=15.0, status=ReviewStatus.APPROVED, start_norm={"x": 0.2, "y": 0}, end_norm={"x": 0.3, "y": 0})
        w_rejected = Wall(page_id=page.id, length_ft=20.0, status=ReviewStatus.REJECTED, start_norm={"x": 0.4, "y": 0}, end_norm={"x": 0.5, "y": 0})
        db.add_all([w_pending, w_approved, w_rejected])
        db.flush()

        wall_repo = WallRepository(db)
        approved = wall_repo.approved_for_pages([page.id])
        candidates = wall_repo.candidate_for_pages([page.id])

        assert len(approved) == 1
        assert approved[0].id == w_approved.id
        assert len(candidates) == 2
        assert {w.id for w in candidates} == {w_pending.id, w_approved.id}
        assert w_rejected.id not in {w.id for w in candidates}
    finally:
        db.rollback()
        db.close()
