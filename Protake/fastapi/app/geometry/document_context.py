"""Whole-Document Understanding Pre-Pass.

Runs once, before any per-page geometry detection begins, and reads every
page's text/vector-density signal to build a document-wide picture: which
sheets exist, what discipline/type each one is, and which sheets carry
schedule/authority information (partition schedules, door schedules, RCPs).

This module deliberately does NOT decide per-page takeoff eligibility on its
own — that decision stays exactly where it already lives, in
`geometry.page_classifier.classify_page_content`, which is what
`geometry.engine.analyze_page` calls per page. Duplicating or overriding that
decision here would be exactly the kind of second competing classifier this
module exists to avoid.

What this module adds that didn't exist before: the SAME eligibility
classifier and the schedule-authority classifier (`BlueprintSheetClassifier`,
otherwise only run later at takeoff-compute time, after geometry detection
has already happened) are now both run together, once, across the WHOLE
document, before the per-page detection loop starts — and any page where the
two classifiers disagree about discipline/eligibility is recorded as a
`ClassificationDivergence`, so the "three classifiers, no shared source of
truth" problem becomes visible, auditable data instead of silent
inconsistency. It is intentionally observation-only in this phase: nothing
downstream acts on a divergence yet, so introducing this pass cannot change
which pages get processed or how many walls/rooms are detected on any of
them.
"""

from dataclasses import dataclass, field

import fitz

from app.geometry.page_classifier import classify_page_content
from app.intelligence.sheet_classifier import BlueprintSheetClassifier


@dataclass
class ClassificationDivergence:
    page_number: int
    eligibility_page_type: str
    eligibility_is_takeoff_eligible: bool
    schedule_authority_sheet_type: str
    schedule_authority_is_drywall_authoritative: bool
    reason: str


@dataclass
class PageContextEntry:
    page_number: int
    sheet_number: str
    discipline: str
    page_type: str
    is_takeoff_eligible: bool
    schedule_authority_sheet_type: str
    is_drywall_authoritative: bool
    word_count: int
    vector_stroke_count: int


@dataclass
class DocumentContext:
    pdf_path: str
    total_pages: int
    pages: dict[int, PageContextEntry] = field(default_factory=dict)
    authoritative_sheets: dict[str, list[int]] = field(default_factory=dict)
    disciplines_present: list[str] = field(default_factory=list)
    eligible_page_count: int = 0
    classification_divergences: list[ClassificationDivergence] = field(default_factory=list)

    def summary_line(self) -> str:
        divergence_note = (
            f", {len(self.classification_divergences)} classifier divergence(s)"
            if self.classification_divergences
            else ""
        )
        return (
            f"Document understanding: {self.total_pages} pages, "
            f"{self.eligible_page_count} takeoff-eligible, "
            f"disciplines={sorted(self.disciplines_present)}, "
            f"authoritative_sheets={ {k: len(v) for k, v in self.authoritative_sheets.items()} }"
            f"{divergence_note}"
        )

    def to_dict(self) -> dict:
        return {
            "pdf_path": self.pdf_path,
            "total_pages": self.total_pages,
            "eligible_page_count": self.eligible_page_count,
            "disciplines_present": sorted(self.disciplines_present),
            "authoritative_sheets": self.authoritative_sheets,
            "pages": {
                str(pn): {
                    "page_number": e.page_number,
                    "sheet_number": e.sheet_number,
                    "discipline": e.discipline,
                    "page_type": e.page_type,
                    "is_takeoff_eligible": e.is_takeoff_eligible,
                    "schedule_authority_sheet_type": e.schedule_authority_sheet_type,
                    "is_drywall_authoritative": e.is_drywall_authoritative,
                }
                for pn, e in self.pages.items()
            },
            "classification_divergences": [
                {
                    "page_number": d.page_number,
                    "eligibility_page_type": d.eligibility_page_type,
                    "eligibility_is_takeoff_eligible": d.eligibility_is_takeoff_eligible,
                    "schedule_authority_sheet_type": d.schedule_authority_sheet_type,
                    "schedule_authority_is_drywall_authoritative": d.schedule_authority_is_drywall_authoritative,
                    "reason": d.reason,
                }
                for d in self.classification_divergences
            ],
        }


# Sheet types that are legitimately "drywall authoritative" (schedule/RCP
# sources) without being wall-geometry takeoff-eligible floor plans — a
# schedule sheet is never supposed to also be a floor plan, so these pairings
# are expected and are not logged as divergences.
_EXPECTED_NON_ELIGIBLE_AUTHORITY_TYPES = {
    "partition_schedule",
    "door_window_schedule",
    "finish_schedule",
    "reflected_ceiling_plan",
    "wall_sections",
    "cover_index",
}


def build_document_context(pdf_path: str) -> DocumentContext:
    """Reads every page of the document ONCE, before any per-page geometry
    detection runs, and classifies each page with both the live eligibility
    classifier and the schedule-authority classifier. Cheap: text + vector
    stroke counts only, no rasterization, no wall/room detection.
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    schedule_classifier = BlueprintSheetClassifier()
    ctx = DocumentContext(pdf_path=pdf_path, total_pages=total_pages)

    for page_index in range(total_pages):
        page_number = page_index + 1
        page = doc[page_index]

        words = page.get_text("words")
        text_tokens = [w[4].strip() for w in words if w[4].strip()]
        full_text = page.get_text()
        drawings = page.get_drawings()
        stroke_count = sum(len(d.get("items", [])) for d in drawings)

        eligibility = classify_page_content(None, text_tokens, stroke_count)

        # page_id isn't known yet (no Page row exists until process_single_page
        # runs) — page_number is the only stable key available at this stage.
        schedule_meta = schedule_classifier.classify_sheet(
            page_id=page_number,
            page_number=page_number,
            text_content=full_text,
        )

        entry = PageContextEntry(
            page_number=page_number,
            sheet_number=schedule_meta.sheet_number,
            discipline=eligibility.discipline,
            page_type=eligibility.page_type.value,
            is_takeoff_eligible=eligibility.is_takeoff_eligible,
            schedule_authority_sheet_type=schedule_meta.sheet_type.value,
            is_drywall_authoritative=schedule_meta.is_drywall_authoritative,
            word_count=len(text_tokens),
            vector_stroke_count=stroke_count,
        )
        ctx.pages[page_number] = entry

        if eligibility.is_takeoff_eligible:
            ctx.eligible_page_count += 1
        if eligibility.discipline not in ctx.disciplines_present:
            ctx.disciplines_present.append(eligibility.discipline)

        if schedule_meta.sheet_type.value != "unknown":
            ctx.authoritative_sheets.setdefault(schedule_meta.sheet_type.value, []).append(page_number)

        # Flag divergence: the eligibility classifier says this page is a
        # takeoff-eligible floor plan, but the schedule classifier thinks
        # it's something else entirely (a schedule/RCP/section sheet, which
        # should never also be wall-geometry-eligible), or vice versa.
        if eligibility.is_takeoff_eligible and schedule_meta.sheet_type.value in _EXPECTED_NON_ELIGIBLE_AUTHORITY_TYPES - {"wall_sections"}:
            ctx.classification_divergences.append(
                ClassificationDivergence(
                    page_number=page_number,
                    eligibility_page_type=eligibility.page_type.value,
                    eligibility_is_takeoff_eligible=True,
                    schedule_authority_sheet_type=schedule_meta.sheet_type.value,
                    schedule_authority_is_drywall_authoritative=schedule_meta.is_drywall_authoritative,
                    reason=(
                        f"Eligibility classifier marked page {page_number} as takeoff-eligible "
                        f"'{eligibility.page_type.value}', but the schedule classifier identified it as "
                        f"'{schedule_meta.sheet_type.value}' — a sheet type that should not also be a "
                        f"wall-geometry source. Wall detection will still run on this page per the "
                        f"eligibility classifier's decision (unchanged); this divergence is disclosed, "
                        f"not acted on."
                    ),
                )
            )
        elif not eligibility.is_takeoff_eligible and schedule_meta.sheet_type.value == "floor_plan":
            ctx.classification_divergences.append(
                ClassificationDivergence(
                    page_number=page_number,
                    eligibility_page_type=eligibility.page_type.value,
                    eligibility_is_takeoff_eligible=False,
                    schedule_authority_sheet_type=schedule_meta.sheet_type.value,
                    schedule_authority_is_drywall_authoritative=schedule_meta.is_drywall_authoritative,
                    reason=(
                        f"Schedule classifier identified page {page_number} as a 'floor_plan', but the "
                        f"eligibility classifier excluded it ('{eligibility.page_type.value}', "
                        f"is_takeoff_eligible=False). Wall detection will NOT run on this page per the "
                        f"eligibility classifier's decision (unchanged); this divergence is disclosed, "
                        f"not acted on."
                    ),
                )
            )

    doc.close()
    return ctx
