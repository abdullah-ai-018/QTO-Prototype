"""QA & verification endpoints: everything a human reviewer or QC lead
needs to confirm a takeoff is trustworthy before it becomes a bid —
completeness coverage, AI-vs-manual variance checking, a standalone
rule-engine calculator for hand-verification, and per-trade sign-off
gating on the Estimate.
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession, get_owned_project
from app.api.v1.endpoints.blueprints import get_owned_blueprint
from app.models.enums import AuditAction, EstimateStatus, TradeKey
from app.repositories.estimate_repository import EstimateRepository
from app.repositories.qc_signoff_repository import QcSignoffRepository
from app.rules.rule_engine import rules
from app.schemas.estimate import EstimateRead
from app.schemas.qa import (
    CoverageReport,
    CrossValidationResponse,
    EstimateReadinessResponse,
    QAEngineResponse,
    QcSignoffRead,
    QcSignoffRequest,
    RuleCalculateRequest,
    RuleCalculateResponse,
    RuleListResponse,
    VarianceCheckResponse,
)
from app.services.audit_service import AuditService
from app.services.qa_service import build_coverage_report, run_cross_validation, run_pre_estimate_qa, run_variance_check

router = APIRouter(tags=["QA & Verification"])


@router.get("/blueprints/{blueprint_id}/coverage", response_model=CoverageReport)
def get_coverage(blueprint_id: int, db: DbSession, user: CurrentUser) -> CoverageReport:
    blueprint = get_owned_blueprint(blueprint_id, db, user)
    return build_coverage_report(db, blueprint.id)


@router.get("/pages/{page_id}/variance-check", response_model=VarianceCheckResponse)
def get_variance_check(page_id: int, db: DbSession, user: CurrentUser) -> VarianceCheckResponse:
    from app.api.v1.endpoints.pages import get_owned_page

    page = get_owned_page(page_id, db, user)
    return run_variance_check(db, page.id)


@router.get("/blueprints/{blueprint_id}/cross-validation", response_model=CrossValidationResponse)
def get_cross_validation(blueprint_id: int, db: DbSession, user: CurrentUser) -> CrossValidationResponse:
    blueprint = get_owned_blueprint(blueprint_id, db, user)
    return run_cross_validation(db, blueprint.id)


@router.get("/blueprints/{blueprint_id}/qa-check", response_model=QAEngineResponse)
def get_qa_check(blueprint_id: int, db: DbSession, user: CurrentUser) -> QAEngineResponse:
    blueprint = get_owned_blueprint(blueprint_id, db, user)
    return run_pre_estimate_qa(db, blueprint.id)


@router.post("/blueprints/{blueprint_id}/consensus")
def run_consensus(blueprint_id: int, db: DbSession, user: CurrentUser):
    blueprint = get_owned_blueprint(blueprint_id, db, user)
    from app.services.consensus_service import run_multi_source_consensus

    result = run_multi_source_consensus(db, blueprint.id)
    return {
        "blueprint_id": blueprint.id,
        "auto_approved_count": result.auto_approved_count,
        "pending_count": result.pending_count,
        "details": result.details,
    }


@router.get("/blueprints/{blueprint_id}/diff/{other_blueprint_id}")
def diff_blueprints(blueprint_id: int, other_blueprint_id: int, db: DbSession, user: CurrentUser):
    bp1 = get_owned_blueprint(blueprint_id, db, user)
    bp2 = get_owned_blueprint(other_blueprint_id, db, user)
    from app.services.diff_service import compare_blueprint_revisions

    return compare_blueprint_revisions(db, bp1.id, bp2.id)


@router.get("/specs/{code}")
def get_assembly_spec(code: str):
    from app.knowledge_base.assembly_specs import lookup_assembly_spec

    spec = lookup_assembly_spec(code)
    if not spec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No assembly spec found for code '{code}'")
    return spec


@router.get("/specs")
def list_assembly_specs():
    from app.knowledge_base.assembly_specs import list_available_specs

    return list_available_specs()


@router.get("/rules", response_model=RuleListResponse)
def list_rules() -> RuleListResponse:
    return RuleListResponse(rules=rules.names())


@router.post("/rules/calculate", response_model=RuleCalculateResponse)
def calculate_rule(payload: RuleCalculateRequest) -> RuleCalculateResponse:
    """Runs the exact same named formula the trade engines use, directly
    against caller-supplied numbers — lets a QA engineer verify any
    quantity with their own calculator, independent of any blueprint.
    """
    try:
        result = rules.evaluate(payload.rule, **payload.inputs)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except TypeError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Wrong inputs for rule '{payload.rule}': {exc}"
        ) from exc
    except (ValueError, ZeroDivisionError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return RuleCalculateResponse(rule=payload.rule, inputs=payload.inputs, result=result)


@router.post("/estimates/{estimate_id}/signoff", response_model=QcSignoffRead, status_code=status.HTTP_201_CREATED)
def signoff_estimate_trade(estimate_id: int, payload: QcSignoffRequest, db: DbSession, user: CurrentUser) -> QcSignoffRead:
    estimate = EstimateRepository(db).get_or_404(estimate_id)
    get_owned_project(estimate.project_id, db, user)

    repo = QcSignoffRepository(db)
    existing = repo.get_for_trade(estimate_id, payload.trade)
    if existing:
        updated = repo.update(existing, reviewer_id=user.id, signed_off=payload.signed_off, notes=payload.notes)
        record = updated
    else:
        record = repo.create(
            estimate_id=estimate_id,
            reviewer_id=user.id,
            trade=payload.trade,
            signed_off=payload.signed_off,
            notes=payload.notes,
        )

    AuditService(db).log(
        project_id=estimate.project_id,
        user_id=user.id,
        entity_type="Estimate",
        entity_id=estimate.id,
        action=AuditAction.APPROVED if payload.signed_off else AuditAction.UPDATED,
        field_name=f"signoff:{payload.trade.value}",
        new_value={"signed_off": payload.signed_off, "notes": payload.notes},
        reason=f"QC sign-off for {payload.trade.value}",
    )
    return QcSignoffRead.model_validate(record)


@router.get("/estimates/{estimate_id}/signoff", response_model=list[QcSignoffRead])
def list_signoffs(estimate_id: int, db: DbSession, user: CurrentUser) -> list[QcSignoffRead]:
    estimate = EstimateRepository(db).get_or_404(estimate_id)
    get_owned_project(estimate.project_id, db, user)
    repo = QcSignoffRepository(db)
    rows = repo.db.execute(repo.for_estimate(estimate_id)).scalars().all()
    return [QcSignoffRead.model_validate(r) for r in rows]


@router.get("/estimates/{estimate_id}/readiness", response_model=EstimateReadinessResponse)
def get_estimate_readiness(estimate_id: int, db: DbSession, user: CurrentUser) -> EstimateReadinessResponse:
    estimate = EstimateRepository(db).get_or_404(estimate_id)
    get_owned_project(estimate.project_id, db, user)

    repo = QcSignoffRepository(db)
    rows = repo.db.execute(repo.for_estimate(estimate_id)).scalars().all()
    signed = {r.trade for r in rows if r.signed_off}
    missing = [t for t in TradeKey if t not in signed]

    return EstimateReadinessResponse(
        estimate_id=estimate_id,
        signed_off_trades=sorted(signed, key=lambda t: t.value),
        missing_trades=missing,
        ready_to_finalize=not missing,
    )


@router.post("/estimates/{estimate_id}/finalize", response_model=EstimateRead)
def finalize_estimate(estimate_id: int, db: DbSession, user: CurrentUser) -> EstimateRead:
    estimate = EstimateRepository(db).get_or_404(estimate_id)
    get_owned_project(estimate.project_id, db, user)

    repo = QcSignoffRepository(db)
    rows = repo.db.execute(repo.for_estimate(estimate_id)).scalars().all()
    signed = {r.trade for r in rows if r.signed_off}
    missing = [t.value for t in TradeKey if t not in signed]
    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Cannot finalize: missing QC sign-off for {', '.join(missing)}",
        )

    updated = EstimateRepository(db).update(estimate, status=EstimateStatus.FINAL)
    AuditService(db).log(
        project_id=estimate.project_id,
        user_id=user.id,
        entity_type="Estimate",
        entity_id=estimate.id,
        action=AuditAction.APPROVED,
        field_name="status",
        previous_value=EstimateStatus.DRAFT.value,
        new_value=EstimateStatus.FINAL.value,
        reason="All trades signed off — estimate finalized",
    )
    return EstimateRead.model_validate(updated)
