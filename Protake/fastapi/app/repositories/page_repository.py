from sqlalchemy import select

from app.models.page import Page
from app.repositories.base import BaseRepository


class PageRepository(BaseRepository[Page]):
    model = Page

    def for_blueprint(self, blueprint_id: int):
        return select(Page).where(Page.blueprint_id == blueprint_id).order_by(Page.page_number)
