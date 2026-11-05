from datetime import datetime, timezone

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, get_owned_project
from app.schemas.assistant import (
    AssistantProposedAction,
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantSuggestion,
    AssistantToolCall,
    WallContextAction,
    WallContextEvidence,
    WallContextQueryRequest,
    WallContextQueryResponse,
)
from app.services.assistant_service import ask, investigate_wall

router = APIRouter(prefix="/assistant", tags=["AI Assistant"])


@router.post("/query", response_model=AssistantQueryResponse)
def query_assistant(payload: AssistantQueryRequest, db: DbSession, user: CurrentUser) -> AssistantQueryResponse:
    project = get_owned_project(payload.project_id, db, user)
    history = [{"role": turn.role, "content": turn.content} for turn in payload.history]
    selected_context = payload.selected_context.model_dump() if payload.selected_context else None
    reply = ask(db, project, payload.message, history=history, selected_context=selected_context, active_tool=payload.active_tool)

    suggestions = []
    if reply.suggestion_title:
        suggestions.append(AssistantSuggestion(title=reply.suggestion_title, trade=reply.suggestion_trade))

    return AssistantQueryResponse(
        reply=reply.text,
        suggestions=suggestions,
        grounded_on=reply.grounded_on,
        tool_calls_made=[AssistantToolCall(**tc) for tc in reply.tool_calls_made],
        proposed_actions=[AssistantProposedAction(**pa) for pa in reply.proposed_actions],
        generated_at=datetime.now(timezone.utc),
    )


@router.post("/wall-context", response_model=WallContextQueryResponse)
def query_wall_context(payload: WallContextQueryRequest, db: DbSession, user: CurrentUser) -> WallContextQueryResponse:
    project = get_owned_project(payload.project_id, db, user)
    history = [{"role": turn.role, "content": turn.content} for turn in payload.history]
    res = investigate_wall(
        db=db,
        project=project,
        wall_id=payload.wall_id,
        message=payload.message,
        history=history,
        selected_wall_data=payload.selected_wall_data,
    )

    return WallContextQueryResponse(
        answer=res["answer"],
        wall_id=res["wall_id"],
        display_code=res["display_code"],
        category_label=res["category_label"],
        confidence=res["confidence"],
        status=res["status"],
        qto_eligible=res["qto_eligible"],
        evidence=[WallContextEvidence(**e) for e in res["evidence"]],
        sources=res["sources"],
        warnings=res["warnings"],
        actions=[WallContextAction(**a) for a in res["actions"]],
        generated_at=res["generated_at"],
    )

