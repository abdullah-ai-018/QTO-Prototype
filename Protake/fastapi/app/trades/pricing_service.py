"""Pricing engine: resolves the effective TradeConfig for a
(trade, project) pair — project-specific override if one exists,
otherwise the seeded national-average default — and lets callers
create custom/regional overrides per project.
"""

from sqlalchemy.orm import Session

from app.models.enums import TradeKey
from app.models.trade import TradeConfig
from app.repositories.trade_repository import TradeConfigRepository
from app.rules.default_trade_configs import DEFAULT_TRADE_CONFIGS


class PricingService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = TradeConfigRepository(db)

    def seed_defaults_if_missing(self) -> None:
        for trade, defaults in DEFAULT_TRADE_CONFIGS.items():
            existing = self.repo.find_one(trade=trade, is_default=True)
            if existing is None:
                self.repo.create(project_id=None, trade=trade, label="National Average (Default)", is_default=True, **defaults)

    def resolve(self, trade: TradeKey, project_id: int | None) -> TradeConfig:
        config = self.repo.resolve(trade, project_id)
        if config is None:
            raise LookupError(f"No pricing configuration available for trade '{trade.value}'. Seed defaults first.")
        return config

    def resolve_all(self, project_id: int | None) -> dict[TradeKey, TradeConfig]:
        return {trade: self.resolve(trade, project_id) for trade in TradeKey}

    def upsert_project_override(self, project_id: int, payload: dict) -> TradeConfig:
        trade_val = payload["trade"]
        trade_key = TradeKey(trade_val) if isinstance(trade_val, str) else trade_val
        base_defaults = dict(DEFAULT_TRADE_CONFIGS.get(trade_key, {}))
        
        clean_payload = {k: v for k, v in payload.items() if v is not None}
        merged = {
            "label": f"Project {trade_key.value.capitalize()} Configuration",
            **base_defaults,
            **clean_payload,
        }
        merged["trade"] = trade_key

        existing = self.repo.find_one(trade=trade_key, project_id=project_id)
        if existing is not None:
            return self.repo.update(existing, **{k: v for k, v in merged.items() if k != "trade"})
        return self.repo.create(project_id=project_id, is_default=False, **merged)

