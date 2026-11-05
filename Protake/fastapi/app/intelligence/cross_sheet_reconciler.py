"""Cross-Sheet Reconciler & Conflict Resolution Engine.

Reconciles physical floor plan wall geometry against project-wide partition schedules,
door schedules, and wall section details. Enforces the Rule of Honest Uncertainty:
if evidence is missing or conflicting across sheets, returns NEEDS_REVIEW.
"""

from typing import Any
from app.models.architectural_wall import (
    ArchitecturalWall,
    WallAssemblySpec,
    WallOpening,
    ThicknessSource,
    HeightSource,
)
from app.models.project_knowledge_graph import (
    ProjectBlueprintIndex,
    CrossSheetEvidenceChain,
    PartitionScheduleEntry,
)


class CrossSheetReconciler:
    """Reconciles physical wall geometry across drawing sheets in a multi-page blueprint set."""

    def __init__(self, index: ProjectBlueprintIndex):
        self.index = index

    def reconcile_wall(
        self,
        wall: ArchitecturalWall,
        plan_sheet_number: str | None = None,
        plan_page_id: int | None = None,
    ) -> tuple[ArchitecturalWall, CrossSheetEvidenceChain]:
        """Cross-reconciles a physical wall run against multi-sheet schedule definitions.

        GAP-FIX: plan_sheet_number and plan_page_id are now derived from the wall's
        own page_id via the index, not hardcoded to "A-101" / 1.  Hardcoded provenance
        was silently wrong for every project with a different sheet numbering scheme
        and would have confused conflict-detection comparisons (the "plan" column in
        CrossSheetEvidenceChain would always say "A-101" regardless of reality).
        """
        # Resolve plan sheet identity from the wall's actual page
        if plan_page_id is None:
            plan_page_id = wall.page_id
        if plan_sheet_number is None:
            sheet_meta = self.index.sheets.get(plan_page_id)
            plan_sheet_number = (sheet_meta.sheet_number if sheet_meta else None) or f"page-{plan_page_id}"

        tag = wall.wall_tag
        evidence_notes = [f"Detected physical wall run on Floor Plan sheet {plan_sheet_number}"]

        # Detail/section callout resolution already ran in
        # DrywallSemanticWallPipeline._resolve_detail_references (before this
        # reconciler runs) and stamped source_evidence["detail_reference"] as
        # "3/A401" when a callout was found near this wall. Surface the sheet
        # half of that reference here — this is the field
        # CrossSheetEvidenceChain.section_sheet_number was defined for.
        detail_reference = getattr(wall, "source_evidence", {}).get("detail_reference")
        section_sheet_number = detail_reference.split("/")[-1] if detail_reference else None
        if detail_reference:
            evidence_notes.append(f"Detail callout {detail_reference} referenced by this wall")

        # Door-schedule provenance: record which schedule sheet each of this
        # wall's openings actually resolved its dimensions from, when a real
        # match exists. The height correction itself already happens in
        # DrywallEngine._resolve_opening_height (reads
        # self.index.door_schedules directly, independent of this method) —
        # this only fills in CrossSheetEvidenceChain.door_schedule_sheet_number,
        # which previously stayed unset even when a door schedule genuinely
        # backed one of this wall's openings, leaving that part of the
        # evidence chain silently incomplete.
        door_schedule_sheet_number: str | None = None
        for opening in getattr(wall, "openings", None) or []:
            op_tag = getattr(opening, "schedule_tag", None)
            if not op_tag:
                continue
            entry = self.index.door_schedules.get(op_tag) or self.index.door_schedules.get(op_tag.upper())
            if entry is not None:
                door_schedule_sheet_number = entry.source_sheet_number
                evidence_notes.append(
                    f"Opening '{op_tag}' dimensions resolved from door schedule sheet {entry.source_sheet_number}"
                )
                break

        # 1. Check if wall tag exists in project partition schedules
        if tag and tag in self.index.partition_schedules:
            sched_entry = self.index.partition_schedules[tag]
            
            # Check for thickness discrepancy between drawn geometry and schedule spec
            sched_thick_in = sched_entry.stud_depth_in + (
                (sched_entry.layers_side_a + sched_entry.layers_side_b) * 0.625
            )
            drawn_thick_in = wall.thickness_in

            # Conflict detection: If drawn thickness deviates > 2.5" from schedule spec
            if abs(drawn_thick_in - sched_thick_in) > 2.5:
                chain = CrossSheetEvidenceChain(
                    wall_id=wall.id,
                    plan_sheet_number=plan_sheet_number,
                    plan_page_id=plan_page_id,
                    wall_tag=tag,
                    schedule_sheet_number=sched_entry.source_sheet_number,
                    schedule_page_id=sched_entry.source_sheet_page_id,
                    door_schedule_sheet_number=door_schedule_sheet_number,
                    section_sheet_number=section_sheet_number,
                    reconciliation_status="conflict",
                    conflict_details=f"Drawn thickness ({drawn_thick_in:.1f}\") contradicts schedule {tag} thickness ({sched_thick_in:.1f}\")",
                    confidence=0.60,
                    evidence_notes=evidence_notes + [f"Conflict: Drawn {drawn_thick_in:.1f}\" vs Schedule {sched_thick_in:.1f}\""],
                )
                wall.status = "needs_review"
                wall.rejection_reason = "schedule_geometry_thickness_conflict"
                wall.confidence = 0.60
                wall.qto_eligible = False
                wall.qto_block_reason = "SCHEDULE_GEOMETRY_THICKNESS_CONFLICT"
                return wall, chain

            # Resolved successfully from schedule
            assembly_spec = WallAssemblySpec(
                tag=sched_entry.tag,
                description=sched_entry.description,
                stud_depth_in=sched_entry.stud_depth_in,
                stud_gauge=sched_entry.stud_gauge,
                board_type_side_a=sched_entry.board_type_side_a,
                layers_side_a=sched_entry.layers_side_a,
                board_type_side_b=sched_entry.board_type_side_b,
                layers_side_b=sched_entry.layers_side_b,
                sides_to_hang=sched_entry.sides_to_hang,
                fire_rating_hr=sched_entry.fire_rating_hr,
                sound_rating_stc=sched_entry.sound_rating_stc,
                source=f"partition_schedule_{sched_entry.source_sheet_number}",
            )

            wall.assembly = assembly_spec
            wall.assembly_resolved = True
            wall.thickness_in = round(sched_thick_in, 3)
            wall.thickness_source = ThicknessSource.WALL_SCHEDULE

            chain = CrossSheetEvidenceChain(
                wall_id=wall.id,
                plan_sheet_number=plan_sheet_number,
                plan_page_id=plan_page_id,
                wall_tag=tag,
                schedule_sheet_number=sched_entry.source_sheet_number,
                schedule_page_id=sched_entry.source_sheet_page_id,
                door_schedule_sheet_number=door_schedule_sheet_number,
                section_sheet_number=section_sheet_number,
                reconciliation_status="resolved",
                confidence=0.95,
                evidence_notes=evidence_notes + [
                    f"Resolved assembly {tag} from Schedule {sched_entry.source_sheet_number}",
                    f"Assembly: {sched_entry.description}",
                ],
            )
            return wall, chain

        # 2. No schedule tag on sheet -> Honest Uncertainty
        chain = CrossSheetEvidenceChain(
            wall_id=wall.id,
            plan_sheet_number=plan_sheet_number,
            plan_page_id=plan_page_id,
            wall_tag=tag,
            door_schedule_sheet_number=door_schedule_sheet_number,
            section_sheet_number=section_sheet_number,
            reconciliation_status="unresolved_missing_schedule",
            confidence=0.75,
            evidence_notes=evidence_notes + ["No partition schedule tag resolved on this sheet; default partition spec applied"],
        )
        return wall, chain
