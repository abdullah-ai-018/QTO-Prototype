"""Revision Service: Extracts drawing revision tags (e.g. REV A, REV B, REVISION 2)
from sheet title blocks and checks for superseded drawings.
"""

import re
from sqlalchemy.orm import Session

from app.models.enums import RevisionStatus
from app.models.page import Page
from app.repositories.page_repository import PageRepository

_REV_RE = re.compile(r"\b(REV(?:ISION)?\s*[:#-]?\s*([A-Z0-9]+))\b", re.IGNORECASE)


def extract_revision_code(raw_text_tokens: list[str]) -> str | None:
    full_text = " ".join(raw_text_tokens)
    match = _REV_RE.search(full_text)
    if match:
        return match.group(1).upper()
    return None


def detect_and_save_revision(db: Session, page: Page, raw_text_tokens: list[str]) -> str | None:
    rev_code = extract_revision_code(raw_text_tokens)
    if rev_code:
        PageRepository(db).update(page, revision_code=rev_code)
    return rev_code
