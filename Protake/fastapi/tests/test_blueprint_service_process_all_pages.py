"""Regression test for BlueprintService.process_all_pages document context logging.

Guards against UnboundLocalError on blueprint_id during the whole-document
understanding pass and its exception handler.
"""

from unittest.mock import MagicMock
import concurrent.futures
import pytest

from app.models.blueprint import Blueprint
from app.models.enums import BlueprintStatus
from app.services.blueprint_service import BlueprintService


class _ImmediateExecutor:
    """Synchronous executor for testing without cross-process serialization."""
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def submit(self, fn, *args, **kwargs):
        f = concurrent.futures.Future()
        try:
            res = fn(*args, **kwargs)
            f.set_result(res)
        except Exception as e:
            f.set_exception(e)
        return f


def _mock_repo_update(obj, **kwargs):
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj


def test_process_all_pages_document_context_success_regression(monkeypatch):
    """Verifies that when build_document_context succeeds, blueprint_id is properly
    bound and logged without UnboundLocalError.
    """
    mock_db = MagicMock()
    mock_bp_repo = MagicMock()
    mock_bp_repo.update.side_effect = _mock_repo_update
    mock_page_repo = MagicMock()

    service = BlueprintService(mock_db)
    service.blueprints = mock_bp_repo
    service.pages = mock_page_repo

    dummy_bp = Blueprint(
        id=108,
        project_id=1,
        uploaded_by_id=1,
        original_filename="test_blueprint.pdf",
        stored_filename="test_blueprint_stored.pdf",
        file_path="/dummy/path/test_blueprint.pdf",
        file_size_bytes=1024,
        status=BlueprintStatus.UPLOADED,
    )

    mock_context = MagicMock()
    mock_context.summary_line.return_value = "Document summary: 1 eligible page"
    divergence_mock = MagicMock()
    divergence_mock.reason = "Sheet A101 divergence reason"
    mock_context.classification_divergences = [divergence_mock]

    monkeypatch.setattr("app.services.blueprint_service.get_page_count", lambda path: 1)
    monkeypatch.setattr("app.services.blueprint_service.build_document_context", lambda path: mock_context)
    monkeypatch.setattr("concurrent.futures.ProcessPoolExecutor", _ImmediateExecutor)
    monkeypatch.setattr("app.services.blueprint_service._process_one_page_standalone", lambda bp_id, idx, total, **kwargs: 1)

    mock_page = MagicMock()
    mock_page.page_number = 1
    mock_page_repo.find.return_value = [mock_page]

    # Must execute cleanly without UnboundLocalError
    pages = service.process_all_pages(dummy_bp)
    assert len(pages) == 1
    assert dummy_bp.status == BlueprintStatus.PROCESSED
    assert mock_bp_repo.update.called


def test_process_all_pages_document_context_exception_regression(monkeypatch):
    """Verifies that if build_document_context fails, the exception block safely logs
    without raising UnboundLocalError and processing continues safely.
    """
    mock_db = MagicMock()
    mock_bp_repo = MagicMock()
    mock_bp_repo.update.side_effect = _mock_repo_update
    mock_page_repo = MagicMock()

    service = BlueprintService(mock_db)
    service.blueprints = mock_bp_repo
    service.pages = mock_page_repo

    dummy_bp = Blueprint(
        id=108,
        project_id=1,
        uploaded_by_id=1,
        original_filename="test_blueprint.pdf",
        stored_filename="test_blueprint_stored.pdf",
        file_path="/dummy/path/test_blueprint.pdf",
        file_size_bytes=1024,
        status=BlueprintStatus.UPLOADED,
    )

    def failing_build_context(path):
        raise ValueError("Simulated failure in document context extraction")

    monkeypatch.setattr("app.services.blueprint_service.get_page_count", lambda path: 1)
    monkeypatch.setattr("app.services.blueprint_service.build_document_context", failing_build_context)
    monkeypatch.setattr("concurrent.futures.ProcessPoolExecutor", _ImmediateExecutor)
    monkeypatch.setattr("app.services.blueprint_service._process_one_page_standalone", lambda bp_id, idx, total, **kwargs: 1)

    mock_page = MagicMock()
    mock_page.page_number = 1
    mock_page_repo.find.return_value = [mock_page]

    # Must catch exception and continue without UnboundLocalError
    pages = service.process_all_pages(dummy_bp)
    assert len(pages) == 1
    assert dummy_bp.status == BlueprintStatus.PROCESSED
    assert mock_bp_repo.update.called
