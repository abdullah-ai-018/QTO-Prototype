"""Test Suite: Scale Validation & Coordinate Transformations.
Verifies metric, architectural, and engineering scale resolution and coordinate mappings.
"""
from app.bim.models import DataProvenanceStatus
from app.pdf.models import (
    DrawingGeometryObject,
    DrawingTextObject,
    GeometryPrimitiveType,
    ScaleEvidence,
    ScaleStatus,
    SemanticContentType,
)
from app.pdf.scale_validator import ScaleValidator


def test_metric_scale_resolution():
    validator = ScaleValidator()
    text_objs = [
        DrawingTextObject(
            id="TXT-1",
            page_number=1,
            text="SCALE: 1:50",
            semantic_type=SemanticContentType.SCALE_LABEL,
            bbox_pdf=[100, 100, 150, 120],
            origin_pdf=[100, 115],
        )
    ]
    evidence = validator.validate_page_scale(text_objs, [])
    assert evidence.scale_status == ScaleStatus.VERIFIED_EXPLICIT
    assert evidence.scale_string == "1:50"
    assert evidence.ratio == 50.0
    # 50 / 864 = 0.05787037
    assert abs(evidence.ft_per_pt - (50.0 / 864.0)) < 1e-6


def test_architectural_scale_resolution():
    validator = ScaleValidator()
    text_objs = [
        DrawingTextObject(
            id="TXT-2",
            page_number=1,
            text='SCALE: 1/4" = 1\'-0"',
            semantic_type=SemanticContentType.SCALE_LABEL,
            bbox_pdf=[100, 100, 180, 120],
            origin_pdf=[100, 115],
        )
    ]
    evidence = validator.validate_page_scale(text_objs, [])
    assert evidence.scale_status == ScaleStatus.VERIFIED_EXPLICIT
    assert '1/4" = 1\'-0"' in evidence.scale_string
    # 1/4" = 18 pt. 1 ft = 18 pt. ft_per_pt = 1/18 = 0.055555...
    assert abs(evidence.ft_per_pt - (1.0 / 18.0)) < 1e-5


def test_civil_engineering_scale_resolution():
    validator = ScaleValidator()
    text_objs = [
        DrawingTextObject(
            id="TXT-3",
            page_number=1,
            text='SCALE: 1" = 50\'',
            semantic_type=SemanticContentType.SCALE_LABEL,
            bbox_pdf=[100, 100, 180, 120],
            origin_pdf=[100, 115],
        )
    ]
    evidence = validator.validate_page_scale(text_objs, [])
    assert evidence.scale_status == ScaleStatus.VERIFIED_EXPLICIT
    assert '1" = 50\'' in evidence.scale_string
    # 1 in = 72 pt = 50 ft. ft_per_pt = 50 / 72
    assert abs(evidence.ft_per_pt - (50.0 / 72.0)) < 1e-5


def test_unresolved_scale_blocks_guessing():
    validator = ScaleValidator()
    text_objs = [
        DrawingTextObject(
            id="TXT-4",
            page_number=1,
            text="FLOOR PLAN",
            semantic_type=SemanticContentType.DRAWING_TITLE,
            bbox_pdf=[100, 100, 180, 120],
            origin_pdf=[100, 115],
        )
    ]
    evidence = validator.validate_page_scale(text_objs, [])
    assert evidence.scale_status == ScaleStatus.SCALE_UNRESOLVED
    assert evidence.ft_per_pt is None


def test_point_and_bbox_transformations():
    evidence = ScaleEvidence(
        scale_status=ScaleStatus.VERIFIED_EXPLICIT,
        scale_string="1:50",
        ratio=50.0,
        ft_per_pt=50.0 / 864.0,
        provenance=DataProvenanceStatus.VERIFIED_EXPLICIT,
    )

    pt_pdf = [100.0, 200.0]
    pt_ft = ScaleValidator.transform_point_to_ft(pt_pdf, evidence)
    assert abs(pt_ft[0] - (100.0 * 50.0 / 864.0)) < 1e-5
    assert abs(pt_ft[1] - (200.0 * 50.0 / 864.0)) < 1e-5

    bbox_pdf = [0.0, 0.0, 1000.0, 500.0]
    bbox_ft = ScaleValidator.transform_bbox_to_ft(bbox_pdf, evidence)
    assert abs(bbox_ft[2] - (1000.0 * 50.0 / 864.0)) < 1e-5
    assert abs(bbox_ft[3] - (500.0 * 50.0 / 864.0)) < 1e-5
