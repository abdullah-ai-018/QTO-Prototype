from sqlalchemy import select

from app.models.measurement import Measurement
from app.repositories.base import BaseRepository


class MeasurementRepository(BaseRepository[Measurement]):
    model = Measurement

    def for_page(self, page_id: int):
        return select(Measurement).where(Measurement.page_id == page_id)
