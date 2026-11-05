"""Shared contract every trade engine implements. A trade engine's only
job is: given confirmed geometry (approved Rooms + Walls) and a pricing
config, return quantities, labor hours, and cost line items. No trade
engine ever touches AI output directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.detection import Detection
from app.models.enums import TradeKey, TradeTakeoffStatus
from app.models.room import Room
from app.models.trade import TradeConfig
from app.models.wall import Wall


@dataclass
class LineItem:
    label: str
    quantity: float
    unit: str
    unit_cost: float
    source_proof: dict | None = None
    formula_breakdown: str | None = None

    @property
    def total_cost(self) -> float:
        return round(self.quantity * self.unit_cost, 2)


@dataclass
class TradeValidation:
    """Trade-level counterpart to app/geometry/room_validation.py's
    RoomDecision — the outcome of validate_trade_result() (app/trades/
    validation.py), attached to a TradeResult after the engine runs.

    `confidence` is a GEOMETRY-CONFIDENCE score (how certain the room/wall
    detections that fed this calculation are), not a QTO-ACCURACY score
    (how close the computed quantity is to a real, verified takeoff).
    These only coincide by chance. Do not present `confidence` as
    accuracy anywhere (UI, reports, docs) without an actual ground-truth
    comparison behind it — see app/services/ground_truth_service.py.
    """
    status: TradeTakeoffStatus
    confidence: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class TradeResult:
    trade: TradeKey
    material_quantity: float
    material_unit: str
    labor_hours: float
    line_items: list[LineItem] = field(default_factory=list)
    # Populated by validate_trade_result() after the engine returns, not
    # by the engine itself — every existing `TradeResult(...)` call site
    # in the 4 engines and in tests/scripts is keyword-arg based, so both
    # fields default and stay backward compatible.
    evidence: dict = field(default_factory=dict)
    validation: TradeValidation | None = None

    @property
    def material_cost(self) -> float:
        return round(sum(li.total_cost for li in self.line_items if li.unit != "hrs"), 2)

    @property
    def labor_cost(self) -> float:
        return round(sum(li.total_cost for li in self.line_items if li.unit == "hrs"), 2)

    @property
    def direct_cost(self) -> float:
        return round(self.material_cost + self.labor_cost, 2)


def build_source_proof(rooms: list[Room], walls: list[Wall]) -> dict:
    """The evidence behind a trade's numbers: exactly which approved
    Room/Wall rows (and the pages they live on) fed the calculation —
    so a reviewer or client can trace "1,450 sqft of paint" back to the
    specific walls on the specific sheet, not just trust a total.
    """
    room_ids = sorted({r.id for r in rooms if getattr(r, "id", None) is not None})
    wall_ids = sorted({w.id for w in walls if getattr(w, "id", None) is not None})
    page_ids = sorted({getattr(r, "page_id", 1) for r in rooms} | {getattr(w, "page_id", 1) for w in walls})
    return {"room_ids": room_ids, "wall_ids": wall_ids, "page_ids": page_ids}



class TradeEngine(ABC):
    trade: TradeKey
    # Bump when a trade's formula/assumption set changes materially —
    # lets a persisted takeoff snapshot record which calculation version
    # produced it (see TradeTakeoffService.compute_and_persist), so a
    # takeoff computed before a formula fix can be told apart from one
    # computed after, even with identical input geometry.
    version: str = "1.0.0"

    @abstractmethod
    def calculate(
        self,
        rooms: list[Room],
        walls: list[Wall],
        config: TradeConfig,
        door_count: int = 0,
        window_count: int = 0,
        detections: list[Detection] | None = None,
    ) -> TradeResult:
        """`door_count`/`window_count` are global counts. 
        `detections` contain page-level AI object detections to allow per-wall true deductions.
        """
        raise NotImplementedError
