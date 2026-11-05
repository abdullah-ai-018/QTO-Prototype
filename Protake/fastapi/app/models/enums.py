"""Shared enumerations used across ORM models, schemas, and engines."""

import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    ESTIMATOR = "estimator"
    VIEWER = "viewer"


class ProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class BlueprintStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class TradeKey(str, enum.Enum):
    DRYWALL = "drywall"
    PAINTING = "painting"
    FLOORING = "flooring"
    ROOFING = "roofing"


class UnitSystem(str, enum.Enum):
    IMPERIAL = "imperial"
    METRIC = "metric"


class RoomType(str, enum.Enum):
    INTERIOR_ROOM = "interior_room"
    SUB_PARTITION = "sub_partition"
    EXTERIOR_COVERED = "exterior_covered"
    CORRIDOR = "corridor"
    UNKNOWN = "unknown"


class DetectionKind(str, enum.Enum):
    ROOM = "room"
    WALL = "wall"
    DOOR = "door"
    WINDOW = "window"
    COLUMN = "column"
    SYMBOL = "symbol"
    OBJECT = "object"
    # Plumbing/wardrobe fixtures (best.pt: bathtub, shower, sinks, vanity,
    # toilet, robes) — grouped rather than split further because none of
    # them feed a trade engine yet; see app/ai/validation_engine.py.
    FIXTURE = "fixture"
    STAIRS = "stairs"
    # Sheet metadata (best.pt: scale, title-block, dimensions) — not a
    # takeoff item, but worth keeping visible/reviewable rather than
    # silently discarding a trained class.
    ANNOTATION = "annotation"


class DetectionSource(str, enum.Enum):
    GEOMETRY = "geometry"
    OCR = "ocr"
    YOLO = "yolo"
    SAM = "sam"
    FUSION = "fusion"
    MANUAL = "manual"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"



class WallType(str, enum.Enum):
    EXTERIOR = "exterior"
    INTERIOR = "interior"
    PARTITION = "partition"


class MeasurementTool(str, enum.Enum):
    AREA = "area"
    LINEAR = "linear"
    POLYGON = "polygon"
    COUNT = "count"


class EstimateStatus(str, enum.Enum):
    DRAFT = "draft"
    FINAL = "final"


class EstimateItemCategory(str, enum.Enum):
    MATERIAL = "material"
    LABOR = "labor"


class AuditAction(str, enum.Enum):
    CREATED = "created"
    UPDATED = "updated"
    APPROVED = "approved"
    REJECTED = "rejected"
    DELETED = "deleted"
    UNDO = "undo"
    REDO = "redo"


class RoofFeature(str, enum.Enum):
    RIDGE = "ridge"
    HIP = "hip"
    VALLEY = "valley"
    EAVE = "eave"
    RAKE = "rake"
    CHIMNEY = "chimney"
    SKYLIGHT = "skylight"
    VENT_PIPE = "vent_pipe"
    ROOF_HATCH = "roof_hatch"
    DORMER = "dormer"
    GUTTER = "gutter"
    DOWNSPOUT = "downspout"


class RoofType(str, enum.Enum):
    GABLE = "gable"
    HIP = "hip"
    FLAT = "flat"
    SHED = "shed"
    MANSARD = "mansard"
    GAMBREL = "gambrel"
    COMPLEX = "complex"


class RoofMaterialType(str, enum.Enum):
    ASPHALT_SHINGLES = "asphalt_shingles"
    STANDING_SEAM_METAL = "standing_seam_metal"
    TPO = "tpo"
    EPDM = "epdm"
    MODIFIED_BITUMEN = "modified_bitumen"
    BUILT_UP_ROOF = "built_up_roof"
    TILE_CLAY = "tile_clay"
    TILE_CONCRETE = "tile_concrete"
    SLATE = "slate"
    WOOD_SHAKE = "wood_shake"
    CEDAR_SHINGLE = "cedar_shingle"


class RoofComplexity(str, enum.Enum):
    SIMPLE = "simple"           # 5% waste
    MEDIUM = "medium"           # 8% waste
    COMPLEX = "complex"         # 10% waste
    VERY_COMPLEX = "very_complex"  # 15% waste


class FlashingType(str, enum.Enum):
    STEP_FLASHING = "step_flashing"
    COUNTER_FLASHING = "counter_flashing"
    CHIMNEY_FLASHING = "chimney_flashing"
    WALL_FLASHING = "wall_flashing"
    PIPE_FLASHING = "pipe_flashing"
    VALLEY_FLASHING = "valley_flashing"
    DRIP_EDGE = "drip_edge"


class QAFlagLevel(str, enum.Enum):
    WARNING = "warning"
    ERROR = "error"


class RevisionStatus(str, enum.Enum):
    ORIGINAL = "original"
    REVISED = "revised"
    SUPERSEDED = "superseded"


class TradeTakeoffStatus(str, enum.Enum):
    """Outcome of a trade engine's calculate() + post-hoc validation —
    lets API/UI consumers tell "legitimately zero" and "the engine
    crashed" apart, which a bare zeroed TradeResult cannot do.
    """
    VALIDATED = "validated"
    NEEDS_REVIEW = "needs_review"
    ERROR = "error"
