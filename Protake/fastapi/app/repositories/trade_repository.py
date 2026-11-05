from sqlalchemy import select

from app.models.enums import TradeKey
from app.models.trade import TradeConfig
from app.repositories.base import BaseRepository


class TradeConfigRepository(BaseRepository[TradeConfig]):
    model = TradeConfig

    def resolve(self, trade: TradeKey, project_id: int | None) -> TradeConfig | None:
        """Project-specific override wins; otherwise fall back to the
        global default row for this trade.
        """
        if project_id is not None:
            override = self.find_one(trade=trade, project_id=project_id)
            if override is not None:
                return override
        stmt = select(TradeConfig).where(TradeConfig.trade == trade, TradeConfig.is_default.is_(True))
        return self.db.execute(stmt).scalars().first()
