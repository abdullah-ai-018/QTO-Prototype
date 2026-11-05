from fastapi import APIRouter

from app.api.deps import DbSession, OwnedProject
from app.models.enums import TradeKey
from app.schemas.trade import TradeConfigRead, TradeConfigUpsert
from app.trades.pricing_service import PricingService

router = APIRouter(prefix="/projects/{project_id}/trade-configs", tags=["Trades & Pricing"])


@router.get("", response_model=list[TradeConfigRead])
def list_trade_configs(project: OwnedProject, db: DbSession) -> list[TradeConfigRead]:
    service = PricingService(db)
    service.seed_defaults_if_missing()
    resolved = service.resolve_all(project.id)
    return [TradeConfigRead.model_validate(cfg) for cfg in resolved.values()]


@router.get("/{trade}", response_model=TradeConfigRead)
def get_trade_config(trade: TradeKey, project: OwnedProject, db: DbSession) -> TradeConfigRead:
    service = PricingService(db)
    service.seed_defaults_if_missing()
    return TradeConfigRead.model_validate(service.resolve(trade, project.id))


@router.put("", response_model=TradeConfigRead)
def upsert_trade_config(payload: TradeConfigUpsert, project: OwnedProject, db: DbSession) -> TradeConfigRead:
    service = PricingService(db)
    updated = service.upsert_project_override(project.id, payload.model_dump())
    return TradeConfigRead.model_validate(updated)
