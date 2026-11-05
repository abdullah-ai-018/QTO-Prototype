"""Integration smoke test for the per-trade takeoff endpoints
(POST/GET .../takeoffs/{trade}), parametrized over every trade currently
wired into TRADE_MODELS so it extends automatically as painting/flooring/
roofing get added, rather than one near-duplicate file per trade.

This project has no DB-fixture test convention yet — every other file
under tests/ is DB-free — so rather than fabricate rows against
guessed-at required columns, this looks for a blueprint that already has
approved geometry in whatever database DATABASE_URL points at, and skips
cleanly if none exists (e.g. a fresh CI database with no seed data).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models.blueprint import Blueprint
from app.models.enums import ReviewStatus, TradeKey
from app.models.page import Page
from app.models.project import Project
from app.models.room import Room
from app.services.trade_takeoff_service import TRADE_MODELS
from app.utils.security import create_access_token


def _find_seeded_blueprint():
    db = SessionLocal()
    try:
        room = db.execute(select(Room).where(Room.status == ReviewStatus.APPROVED)).scalars().first()
        if room is None:
            return None
        page = db.get(Page, room.page_id)
        blueprint = db.get(Blueprint, page.blueprint_id)
        project = db.get(Project, blueprint.project_id)
        return project.id, blueprint.id, project.owner_id
    finally:
        db.close()


_SEED = _find_seeded_blueprint()
_skip_no_seed = pytest.mark.skipif(
    _SEED is None, reason="No approved room/wall geometry in the configured DATABASE_URL to exercise this integration test against"
)


@_skip_no_seed
@pytest.mark.parametrize("trade", sorted(TRADE_MODELS.keys(), key=lambda t: t.value))
def test_compute_then_read_takeoff(trade: TradeKey):
    project_id, blueprint_id, owner_id = _SEED
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(owner_id)}"}

    computed = client.post(f"/api/v1/projects/{project_id}/blueprints/{blueprint_id}/takeoffs/{trade.value}", headers=headers)
    assert computed.status_code == 201
    body = computed.json()
    assert body["trade"] == trade.value
    assert body["status"] in ("validated", "needs_review", "error")
    assert 0.0 <= body["confidence"] <= 1.0
    assert "room_ids" in body["evidence"]
    assert isinstance(body["items"], list)

    fetched = client.get(f"/api/v1/projects/{project_id}/blueprints/{blueprint_id}/takeoffs/{trade.value}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


@_skip_no_seed
def test_unwired_trade_returns_404_not_a_crash():
    """Whichever trade isn't in TRADE_MODELS yet should 404 cleanly
    rather than error — asserted against whatever's still unwired so this
    stays meaningful as more trades get added.
    """
    unwired = next((t for t in TradeKey if t not in TRADE_MODELS), None)
    if unwired is None:
        pytest.skip("Every trade is wired into TRADE_MODELS now — nothing left to assert 404 against")

    project_id, blueprint_id, owner_id = _SEED
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(owner_id)}"}

    response = client.post(f"/api/v1/projects/{project_id}/blueprints/{blueprint_id}/takeoffs/{unwired.value}", headers=headers)
    assert response.status_code == 404
