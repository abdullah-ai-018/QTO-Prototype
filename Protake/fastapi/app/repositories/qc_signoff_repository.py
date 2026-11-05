from sqlalchemy import select

from app.models.enums import TradeKey
from app.models.qc_signoff import QcSignoff
from app.repositories.base import BaseRepository


class QcSignoffRepository(BaseRepository[QcSignoff]):
    model = QcSignoff

    def for_estimate(self, estimate_id: int):
        return select(QcSignoff).where(QcSignoff.estimate_id == estimate_id)

    def get_for_trade(self, estimate_id: int, trade: TradeKey) -> QcSignoff | None:
        return self.find_one(estimate_id=estimate_id, trade=trade)
