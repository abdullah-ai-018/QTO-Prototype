from sqlalchemy import select

from app.models.enums import TradeKey
from app.models.ground_truth import GroundTruthReference
from app.repositories.base import BaseRepository


class GroundTruthReferenceRepository(BaseRepository[GroundTruthReference]):
    model = GroundTruthReference

    def for_blueprint_and_trade(self, blueprint_id: int, trade: TradeKey) -> list[GroundTruthReference]:
        stmt = select(GroundTruthReference).where(
            GroundTruthReference.blueprint_id == blueprint_id,
            GroundTruthReference.trade == trade,
        )
        return list(self.db.execute(stmt).scalars().all())

    def for_blueprint(self, blueprint_id: int) -> list[GroundTruthReference]:
        stmt = select(GroundTruthReference).where(GroundTruthReference.blueprint_id == blueprint_id)
        return list(self.db.execute(stmt).scalars().all())
