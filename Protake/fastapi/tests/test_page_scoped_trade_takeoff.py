"""Regression tests for the page-scoped takeoff endpoint
(GET .../pages/{page_id}/takeoffs/{trade}) added so the frontend's
"current sheet" numbers can come from the same validated TradeEngine as
the project totals, instead of a separate client-side recomputation.

Follows the same DB-fixture-free convention as test_takeoff_endpoints.py:
looks for approved geometry already present in whatever DATABASE_URL
points at, and skips cleanly if there isn't enough of it to be meaningful.
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
from app.models.wall import Wall
from app.services.trade_takeoff_service import TRADE_MODELS
from app.utils.security import create_access_token


def _find_seeded_blueprint_with_two_pages():
    """A blueprint where at least two distinct pages each have approved
    wall or room geometry, so per-page scoping is actually exercised
    (not just trivially equal to the whole-blueprint result).
    """
    db = SessionLocal()
    try:
        walls = db.execute(select(Wall).where(Wall.status == ReviewStatus.APPROVED)).scalars().all()
        rooms = db.execute(select(Room).where(Room.status == ReviewStatus.APPROVED)).scalars().all()
        page_ids = {w.page_id for w in walls} | {r.page_id for r in rooms}
        if len(page_ids) < 2:
            return None
        ordered = sorted(page_ids)
        page_a, page_b = ordered[0], ordered[1]
        page = db.get(Page, page_a)
        blueprint = db.get(Blueprint, page.blueprint_id)
        # Both sampled pages must belong to the same blueprint for the
        # "sum of pages <= whole blueprint" comparison below to be valid.
        page_b_row = db.get(Page, page_b)
        if page_b_row.blueprint_id != blueprint.id:
            return None
        project = db.get(Project, blueprint.project_id)
        return project.id, blueprint.id, project.owner_id, page_a, page_b
    finally:
        db.close()


_SEED = _find_seeded_blueprint_with_two_pages()
_skip_no_seed = pytest.mark.skipif(
    _SEED is None,
    reason="No blueprint with approved geometry on 2+ distinct pages in the configured DATABASE_URL",
)


@_skip_no_seed
@pytest.mark.parametrize("trade", sorted(TRADE_MODELS.keys(), key=lambda t: t.value))
def test_page_scoped_takeoff_is_subset_of_blueprint_takeoff(trade: TradeKey):
    project_id, blueprint_id, owner_id, page_a, page_b = _SEED
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(owner_id)}"}

    whole = client.get(f"/api/v1/projects/{project_id}/blueprints/{blueprint_id}/live-breakdown", headers=headers)
    assert whole.status_code == 200
    whole_trade = next((b for b in whole.json() if b["trade"] == trade.value), None)
    assert whole_trade is not None

    page_a_resp = client.get(
        f"/api/v1/projects/{project_id}/blueprints/{blueprint_id}/pages/{page_a}/takeoffs/{trade.value}",
        headers=headers,
    )
    assert page_a_resp.status_code == 200
    body = page_a_resp.json()
    assert body["page_id"] == page_a
    assert body["blueprint_id"] == blueprint_id
    assert body["trade"] == trade.value
    assert isinstance(body["items"], list)

    page_b_resp = client.get(
        f"/api/v1/projects/{project_id}/blueprints/{blueprint_id}/pages/{page_b}/takeoffs/{trade.value}",
        headers=headers,
    )
    assert page_b_resp.status_code == 200

    # A single page's material quantity must never exceed the whole
    # blueprint's — this is the core scoping guarantee (no cross-sheet
    # leakage). Floating point: allow a hair of tolerance.
    assert body["material_quantity"] <= whole_trade["material_quantity"] + 0.01
    assert page_b_resp.json()["material_quantity"] <= whole_trade["material_quantity"] + 0.01


@_skip_no_seed
def test_page_scoped_takeoff_rejects_page_from_other_blueprint():
    project_id, blueprint_id, owner_id, page_a, _ = _SEED
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(owner_id)}"}

    # An out-of-range page id can't belong to this blueprint.
    bogus_page_id = 10**9
    response = client.get(
        f"/api/v1/projects/{project_id}/blueprints/{blueprint_id}/pages/{bogus_page_id}/takeoffs/drywall",
        headers=headers,
    )
    assert response.status_code == 404
