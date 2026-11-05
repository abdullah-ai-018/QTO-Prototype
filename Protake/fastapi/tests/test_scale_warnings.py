import pytest
from app.geometry.metrics import SCALE_SOURCE_ASSUMED, SCALE_SOURCE_MEASURED
from app.services.estimate_service import EstimateService


class MockPage:
    def __init__(self, id: int, page_number: int, scale_source: str, sheet_name: str = None, sheet_code: str = None):
        self.id = id
        self.page_number = page_number
        self.scale_source = scale_source
        self.sheet_name = sheet_name
        self.sheet_code = sheet_code


class MockPageRepo:
    def __init__(self, pages: list[MockPage]):
        self._pages = pages

    def find(self, blueprint_id: int):
        return self._pages


def test_scale_warnings_returns_none_when_no_assumed_pages():
    pages = [
        MockPage(id=1, page_number=1, scale_source=SCALE_SOURCE_MEASURED, sheet_code="A101"),
    ]
    service = EstimateService(db=None)
    service.pages = MockPageRepo(pages)

    warnings = service.get_scale_warnings(blueprint_id=10)
    assert warnings is None


def test_scale_warnings_returns_structured_item_when_assumed_page_exists():
    pages = [
        MockPage(id=1, page_number=1, scale_source=SCALE_SOURCE_MEASURED, sheet_code="A101"),
        MockPage(id=2, page_number=2, scale_source=SCALE_SOURCE_ASSUMED, sheet_code="A102"),
    ]
    service = EstimateService(db=None)
    service.pages = MockPageRepo(pages)

    warnings = service.get_scale_warnings(blueprint_id=10)
    assert warnings is not None
    assert len(warnings) == 1
    assert warnings[0].scale_source == "assumed_default"
    assert warnings[0].page_ids == [2]
    assert "page 2 (A102)" in warnings[0].reason
