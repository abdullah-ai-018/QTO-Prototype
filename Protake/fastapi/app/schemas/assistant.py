from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMModel


class AssistantHistoryTurn(ORMModel):
    role: str  # "user" | "assistant"
    content: str


class AssistantSelectedContext(ORMModel):
    # What the user currently has selected on the canvas, from the
    # frontend's own local Detection object — not re-fetched here, just
    # forwarded so the model knows what "this" refers to in a question like
    # "why is this flagged" or "reject this". source+backend_id map
    # directly onto the same IDs propose_* tools expect (source="room" ->
    # room_id, source="detection" -> detection_id); source="wall" has no
    # matching propose tool yet (see assistant_tools.py).
    source: str  # "room" | "wall" | "detection"
    backend_id: int
    name: str
    kind: str
    area_sqft: float | None = None
    perimeter_ft: float | None = None
    confidence: float
    status: str
    sheet_name: str | None = None


class AssistantQueryRequest(ORMModel):
    project_id: int
    message: str = Field(min_length=1, max_length=4000)
    # Prior turns, oldest first, omitted/empty for a fresh conversation —
    # see assistant_service.ask()'s docstring for why only the latest turn
    # gets the project context re-attached.
    history: list[AssistantHistoryTurn] = []
    # What's selected on the canvas right now, if anything, and which
    # toolbar tool is active — lets a question like "what is this" or "how
    # do I use this" resolve without the user having to spell it out.
    selected_context: AssistantSelectedContext | None = None
    active_tool: str | None = None


class AssistantSuggestion(ORMModel):
    title: str
    trade: str | None = None
    rationale: str | None = None


class AssistantToolCall(ORMModel):
    tool: str
    arguments: dict
    result: dict


class AssistantProposedAction(ORMModel):
    # Mirrors the propose_* tool result shape from assistant_tools.py —
    # kept as a loose dict-backed model since the fields differ by action
    # type (detection vs. room, rename vs. status change).
    action: str
    proposed: bool = True
    detection_id: int | None = None
    room_id: int | None = None
    label: str | None = None
    kind: str | None = None
    current_status: str | None = None
    new_status: str | None = None
    current_name: str | None = None
    new_name: str | None = None
    page_number: int | None = None
    reason: str | None = None
    # generate_estimate only:
    blueprint_id: int | None = None
    approved_room_count: int | None = None
    approved_room_area_sqft: float | None = None
    approved_wall_count: int | None = None
    approved_wall_area_sqft: float | None = None
    overhead_pct: float | None = None
    profit_pct: float | None = None
    contingency_pct: float | None = None


class AssistantQueryResponse(ORMModel):
    reply: str
    suggestions: list[AssistantSuggestion] = []
    grounded_on: dict
    # Which read-only tools the model actually called this turn and what
    # they returned — lets the caller show exactly what live data backed
    # the answer instead of asking for blind trust.
    tool_calls_made: list[AssistantToolCall] = []
    # Mutations the model proposed this turn — nothing has actually
    # changed yet; the frontend renders these as confirm/cancel chips and
    # only executes them (via the normal audited REST endpoints) if the
    # user clicks confirm.
    proposed_actions: list[AssistantProposedAction] = []
    generated_at: datetime


# ═══════════════════════════════════════════════════════════════════════════════
# WALL-CONTEXT INVESTIGATION SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class WallContextEvidence(ORMModel):
    field: str
    value: str
    status: str  # "VERIFIED" | "ASSUMED" | "DETECTED" | "INFERRED" | "NOT_AVAILABLE" | "CONFLICT"
    source_sheet: str | None = None
    source_page: int | None = None
    source_detail: str | None = None
    evidence_text: str | None = None
    confidence: float | None = 0.95


class WallContextAction(ORMModel):
    type: str  # "FOCUS_SOURCE" | "OPEN_SCHEDULE" | "VIEW_DETAIL" | "HIGHLIGHT_WALL"
    sheet_code: str | None = None
    page_number: int | None = None
    detail: str | None = None
    detection_id: str | None = None
    label: str
    description: str | None = None


class WallContextQueryRequest(ORMModel):
    project_id: int
    wall_id: str
    blueprint_id: int | None = None
    page_id: int | None = None
    message: str = Field(min_length=1, max_length=4000)
    history: list[AssistantHistoryTurn] = []
    selected_wall_data: dict | None = None


class WallContextQueryResponse(ORMModel):
    answer: str
    wall_id: str
    display_code: str
    category_label: str
    confidence: float = 0.95
    status: str
    qto_eligible: bool
    evidence: list[WallContextEvidence] = []
    sources: list[dict] = []
    warnings: list[str] = []
    actions: list[WallContextAction] = []
    generated_at: datetime

