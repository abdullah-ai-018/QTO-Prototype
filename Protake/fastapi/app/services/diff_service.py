"""Blueprint Change Detection & Diffing Engine:
Compares old blueprint revision vs new blueprint revision, detecting added,
deleted, and modified room polygons so estimators only re-verify changed areas.
"""

from dataclasses import dataclass, field
from sqlalchemy.orm import Session

from app.models.room import Room
from app.repositories.page_repository import PageRepository
from app.repositories.room_repository import RoomRepository


@dataclass
class RoomDiff:
    name: str
    status: str  # ADDED, DELETED, MODIFIED, UNCHANGED
    old_area_sqft: float | None
    new_area_sqft: float | None
    area_delta_sqft: float | None


@dataclass
class BlueprintDiffResult:
    old_blueprint_id: int
    new_blueprint_id: int
    added_rooms_count: int
    deleted_rooms_count: int
    modified_rooms_count: int
    room_diffs: list[RoomDiff] = field(default_factory=list)


def compare_blueprint_revisions(db: Session, old_blueprint_id: int, new_blueprint_id: int) -> BlueprintDiffResult:
    old_pages = PageRepository(db).find(blueprint_id=old_blueprint_id)
    new_pages = PageRepository(db).find(blueprint_id=new_blueprint_id)

    old_page_ids = [p.id for p in old_pages]
    new_page_ids = [p.id for p in new_pages]

    room_repo = RoomRepository(db)
    old_rooms = []
    for pid in old_page_ids:
        old_rooms.extend(room_repo.find(page_id=pid))

    new_rooms = []
    for pid in new_page_ids:
        new_rooms.extend(room_repo.find(page_id=pid))

    old_map = {r.name.upper(): r for r in old_rooms}
    new_map = {r.name.upper(): r for r in new_rooms}

    diffs: list[RoomDiff] = []
    added_count = 0
    deleted_count = 0
    modified_count = 0

    all_names = set(old_map.keys()) | set(new_map.keys())

    for name in sorted(all_names):
        old_r = old_map.get(name)
        new_r = new_map.get(name)

        if not old_r and new_r:
            added_count += 1
            diffs.append(RoomDiff(name=new_r.name, status="ADDED", old_area_sqft=None, new_area_sqft=new_r.area_sqft, area_delta_sqft=new_r.area_sqft))
        elif old_r and not new_r:
            deleted_count += 1
            diffs.append(RoomDiff(name=old_r.name, status="DELETED", old_area_sqft=old_r.area_sqft, new_area_sqft=None, area_delta_sqft=-old_r.area_sqft))
        elif old_r and new_r:
            delta = round(new_r.area_sqft - old_r.area_sqft, 2)
            if abs(delta) > 1.0:  # Area changed by more than 1 sqft
                modified_count += 1
                diffs.append(RoomDiff(name=new_r.name, status="MODIFIED", old_area_sqft=old_r.area_sqft, new_area_sqft=new_r.area_sqft, area_delta_sqft=delta))
            else:
                diffs.append(RoomDiff(name=new_r.name, status="UNCHANGED", old_area_sqft=old_r.area_sqft, new_area_sqft=new_r.area_sqft, area_delta_sqft=0.0))

    return BlueprintDiffResult(
        old_blueprint_id=old_blueprint_id,
        new_blueprint_id=new_blueprint_id,
        added_rooms_count=added_count,
        deleted_rooms_count=deleted_count,
        modified_rooms_count=modified_count,
        room_diffs=diffs,
    )
