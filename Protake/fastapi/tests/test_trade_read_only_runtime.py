"""Runtime counterpart to tests/test_trade_read_only_contract.py.

The AST scan there catches the obvious mutation patterns (`w.foo = x`,
`.append(`, direct `db`/`Session` imports) statically, but can't catch
mutation performed through an intermediate helper or a pattern the scan
doesn't recognize. This actually calls every trade engine with real
Room/Wall ORM instances and diffs every mapped column before/after —
the property under test is "the canonical geometry layer is read-only to
trade engines," not "the source code looks like it doesn't write."

Same DB-dependent-fixture rationale as test_takeoff_endpoints.py.
"""

import pytest
from sqlalchemy import inspect as sa_inspect, select

from app.database import SessionLocal
from app.models.blueprint import Blueprint
from app.models.detection import Detection
from app.models.enums import ReviewStatus, TradeKey
from app.models.page import Page
from app.models.project import Project
from app.models.room import Room
from app.models.wall import Wall
from app.trades.pricing_service import PricingService
from app.trades.registry import TRADE_ENGINES


def _find_seeded_blueprint():
    db = SessionLocal()
    try:
        room = db.execute(select(Room).where(Room.status == ReviewStatus.APPROVED)).scalars().first()
        if room is None:
            return None
        page = db.get(Page, room.page_id)
        blueprint = db.get(Blueprint, page.blueprint_id)
        project = db.get(Project, blueprint.project_id)
        return project.id, blueprint.id
    finally:
        db.close()


_SEED = _find_seeded_blueprint()


def _snapshot(obj) -> dict:
    mapper = sa_inspect(obj).mapper
    return {attr.key: getattr(obj, attr.key) for attr in mapper.column_attrs}


@pytest.mark.skipif(_SEED is None, reason="No approved room/wall geometry in the configured DATABASE_URL to exercise this test against")
@pytest.mark.parametrize("trade", sorted(TRADE_ENGINES.keys(), key=lambda t: t.value))
def test_engine_never_mutates_room_or_wall_columns(trade: TradeKey):
    project_id, blueprint_id = _SEED
    db = SessionLocal()
    try:
        pages = db.execute(select(Page).where(Page.blueprint_id == blueprint_id)).scalars().all()
        page_ids = [p.id for p in pages]
        rooms = list(db.execute(select(Room).where(Room.page_id.in_(page_ids), Room.status == ReviewStatus.APPROVED)).scalars().all())
        walls = list(db.execute(select(Wall).where(Wall.page_id.in_(page_ids), Wall.status == ReviewStatus.APPROVED)).scalars().all())
        detections = list(db.execute(select(Detection).where(Detection.page_id.in_(page_ids), Detection.status == ReviewStatus.APPROVED)).scalars().all())

        before = {("room", r.id): _snapshot(r) for r in rooms}
        before.update({("wall", w.id): _snapshot(w) for w in walls})

        config = PricingService(db).resolve(trade, project_id)
        try:
            TRADE_ENGINES[trade].calculate(rooms, walls, config, 0, 0, detections)
        except Exception:
            pass  # A crashing engine is a separate concern (test_failure_isolation.py) — still must not mutate on the way to crashing.

        after = {("room", r.id): _snapshot(r) for r in rooms}
        after.update({("wall", w.id): _snapshot(w) for w in walls})

        assert before == after, f"{trade.value} engine mutated shared Room/Wall geometry — trade engines must be read-only"
    finally:
        db.close()
