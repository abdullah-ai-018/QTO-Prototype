
"""Project-Level Blueprint Knowledge Graph & Multi-Sheet Provenance Models.

Represents drawing set intelligence, multi-sheet classification, partition schedules,
door/window schedules, and cross-sheet evidence reconciliation.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SheetDiscipline(str, Enum):
    ARCHITECTURAL = "architectural"
    STRUCTURAL = "structural"
    MECHANICAL = "mechanical"
    ELECTRICAL = "electrical"
    PLUMBING = "plumbing"
    GENERAL = "general"
    CIVIL = "civil"
    UNKNOWN = "unknown"


class SheetType(str, Enum):
    COVER_INDEX = "cover_index"
    FLOOR_PLAN = "floor_plan"
    REFLECTED_CEILING_PLAN = "reflected_ceiling_plan"
    WALL_SECTIONS = "wall_sections"
    PARTITION_SCHEDULE = "partition_schedule"
    DOOR_WINDOW_SCHEDULE = "door_window_schedule"
    FINISH_SCHEDULE = "finish_schedule"
    DETAILS_ELEVATIONS = "details_elevations"
    STRUCTURAL_MEP = "structural_mep"
    UNKNOWN = "unknown"


@dataclass
class SheetMetadata:
    page_id: int
    page_number: int
    sheet_number: str | None       # e.g., "A-101", "A-601" — None when unreadable
    sheet_title: str               # e.g., "THIRD FLOOR PLAN", "PARTITION SCHEDULE"
    discipline: SheetDiscipline
    sheet_type: SheetType
    scale_str: str | None = None
    level_elevation: str | None = None
    is_drywall_authoritative: bool = False
    text_content_sample: str = ""      # first 300 chars — for display/debug only
    # The complete sheet text. Schedule parsing must read this, never the
    # sample: a partition or door schedule table runs to several thousand
    # characters, so parsing the 300-char sample finds the schedule's title
    # and none of its rows.
    text_content_full: str = ""


@dataclass
class PartitionScheduleEntry:
    tag: str                       # e.g., "W1", "W2", "PT-01"
    description: str
    stud_depth_in: float
    stud_gauge: str
    board_type_side_a: str
    layers_side_a: int
    board_type_side_b: str
    layers_side_b: int
    sides_to_hang: int
    fire_rating_hr: float | None = None
    sound_rating_stc: float | None = None
    source_sheet_number: str = "A-601"
    source_sheet_page_id: int | None = None
    confidence: float = 0.95


@dataclass
class DetailSheetEntry:
    """A wall-sections/details-elevations sheet, indexed so a detail
    callout (e.g. "3/A401") found near a wall on another sheet can be
    resolved to real content instead of being silently ignored.
    """
    sheet_number: str              # normalized, e.g. "A401"
    page_id: int
    sheet_type: str                # "wall_sections" | "details_elevations"
    text_content_full: str = ""


@dataclass
class DoorScheduleEntry:
    tag: str                       # e.g., "D01", "D02", "WD-1"
    width_ft: float
    height_ft: float
    door_type: str = "single_flush"
    fire_rating_min: float | None = None
    source_sheet_number: str = "A-701"
    source_sheet_page_id: int | None = None


@dataclass
class CrossSheetEvidenceChain:
    """Complete provenance chain linking a physical wall on a floor plan
    to authoritative schedules and details across the drawing set.
    """
    wall_id: str
    plan_sheet_number: str         # e.g., "A-101"
    plan_page_id: int
    wall_tag: str | None = None
    schedule_sheet_number: str | None = None
    schedule_page_id: int | None = None
    section_sheet_number: str | None = None
    door_schedule_sheet_number: str | None = None
    reconciliation_status: str = "resolved"  # "resolved" | "conflict" | "unresolved_missing_schedule"
    conflict_details: str | None = None
    confidence: float = 0.90
    evidence_notes: list[str] = field(default_factory=list)


@dataclass
class ProjectBlueprintIndex:
    """Project-level knowledge graph indexing all sheets in a multi-page blueprint set."""
    blueprint_id: int
    sheets: dict[int, SheetMetadata] = field(default_factory=dict)
    partition_schedules: dict[str, PartitionScheduleEntry] = field(default_factory=dict)
    door_schedules: dict[str, DoorScheduleEntry] = field(default_factory=dict)
    # Keyed by normalize_sheet_ref(sheet_number) (app.geometry.detail_callouts)
    # so a callout's sheet reference and this index agree regardless of
    # "A401" vs "A-401" vs "A 401" formatting differences.
    detail_sheets: dict[str, DetailSheetEntry] = field(default_factory=dict)
    floor_plans: list[int] = field(default_factory=list)
    rcp_plans: list[int] = field(default_factory=list)
    schedule_sheets: list[int] = field(default_factory=list)

    def to_orm(self) -> "ProjectKnowledgeGraphModel":
        sheets_serialized = {
            str(k): {
                "page_id": v.page_id,
                "page_number": v.page_number,
                "sheet_number": v.sheet_number,
                "sheet_title": v.sheet_title,
                "discipline": v.discipline.value if hasattr(v.discipline, "value") else str(v.discipline),
                "sheet_type": v.sheet_type.value if hasattr(v.sheet_type, "value") else str(v.sheet_type),
                "scale_str": v.scale_str,
                "level_elevation": v.level_elevation,
                "is_drywall_authoritative": v.is_drywall_authoritative,
                "text_content_sample": v.text_content_sample,
            }
            for k, v in self.sheets.items()
        }
        part_sched_serialized = {
            k: {
                "tag": v.tag,
                "description": v.description,
                "stud_depth_in": v.stud_depth_in,
                "stud_gauge": v.stud_gauge,
                "board_type_side_a": v.board_type_side_a,
                "layers_side_a": v.layers_side_a,
                "board_type_side_b": v.board_type_side_b,
                "layers_side_b": v.layers_side_b,
                "sides_to_hang": v.sides_to_hang,
                "fire_rating_hr": v.fire_rating_hr,
                "sound_rating_stc": v.sound_rating_stc,
                "source_sheet_number": v.source_sheet_number,
                "source_sheet_page_id": v.source_sheet_page_id,
                "confidence": v.confidence,
            }
            for k, v in self.partition_schedules.items()
        }
        door_sched_serialized = {
            k: {
                "tag": v.tag,
                "width_ft": v.width_ft,
                "height_ft": v.height_ft,
                "door_type": v.door_type,
                "fire_rating_min": v.fire_rating_min,
                "source_sheet_number": v.source_sheet_number,
                "source_sheet_page_id": v.source_sheet_page_id,
            }
            for k, v in self.door_schedules.items()
        }

        return ProjectKnowledgeGraphModel(
            blueprint_id=self.blueprint_id,
            sheets_data=sheets_serialized,
            partition_schedules_data=part_sched_serialized,
            door_schedules_data=door_sched_serialized,
            floor_plans=self.floor_plans,
            rcp_plans=self.rcp_plans,
            schedule_sheets=self.schedule_sheets,
        )


# ── SQLAlchemy Database Model for Persistence ─────────────────────────────────

from sqlalchemy import ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.models.base import TimestampMixin


class ProjectKnowledgeGraphModel(Base, TimestampMixin):
    """Canonical persisted Project Knowledge Graph for a Blueprint."""

    __tablename__ = "project_knowledge_graphs"

    id: Mapped[int] = mapped_column(primary_key=True)
    blueprint_id: Mapped[int] = mapped_column(ForeignKey("blueprints.id", ondelete="CASCADE"), nullable=False, unique=True)

    sheets_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    partition_schedules_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    door_schedules_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    floor_plans: Mapped[list | None] = mapped_column(JSON, nullable=True)
    rcp_plans: Mapped[list | None] = mapped_column(JSON, nullable=True)
    schedule_sheets: Mapped[list | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    blueprint: Mapped["Blueprint"] = relationship()

