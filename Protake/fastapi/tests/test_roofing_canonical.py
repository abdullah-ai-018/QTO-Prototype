import pytest
from app.bim.models import (
    CanonicalBIMModel,
    CanonicalRoof,
    CanonicalSlab,
    CanonicalStorey,
    DataProvenanceStatus,
    QTOEligibilityStatus,
)
from app.bim.normalizer import BIMNormalizer
from app.trades.roofing_bim import BIMRoofingEngine, BIMRoofingSummary


def test_canonical_roof_model_defaults():
    """Verify CanonicalRoof has no hardcoded 4:12 or asphalt defaults."""
    roof = CanonicalRoof(
        id="R1",
        ifc_guid="GUID-R1",
        name="Test Roof",
        storey_id="ST1",
    )
    assert roof.slope_degrees is None
    assert roof.pitch_ratio is None
    assert roof.pitch_multiplier is None
    assert roof.primary_material == "UNASSIGNED"
    assert roof.material_provenance == DataProvenanceStatus.UNKNOWN_UNRESOLVED
    assert roof.slope_provenance == DataProvenanceStatus.UNKNOWN_UNRESOLVED
    assert roof.source_type == "IfcRoof"


def test_normalizer_zero_synthetic_roof_when_missing():
    """Verify normalizer does NOT invent a roof if none exist in IFC."""
    normalizer = BIMNormalizer()
    raw_data = {
        "project": {"guid": "P1", "name": "Test Project"},
        "storeys": [{"guid": "S1", "name": "Level 1", "elevation": 0.0}],
        "walls": [],
        "slabs": [
            {
                "guid": "SL1",
                "name": "Floor Slab",
                "storey_guid": "S1",
                "predefined_type": "FLOOR",
                "is_roof": False,
                "area": 100.0,
                "perimeter": 40.0,
                "thickness": 0.2,
                "psets": {},
            }
        ],
        "roofs": [],
        "spaces": [],
        "openings": [],
        "columns": [],
    }

    model = normalizer.normalize(raw_data)
    assert len(model.roofs) == 0

    engine = BIMRoofingEngine()
    summary = engine.calculate(model)
    assert summary.total_true_surface_area_sqft == 0.0
    assert summary.total_elements_evaluated == 0
    assert len(summary.line_items) == 0


def test_normalizer_explicit_ifc_roof_extraction():
    """Verify explicit IfcRoof extraction with explicit slope and material."""
    normalizer = BIMNormalizer()
    raw_data = {
        "project": {"guid": "P1", "name": "Project"},
        "storeys": [{"guid": "S1", "name": "Roof Level", "elevation": 6.0}],
        "walls": [],
        "slabs": [],
        "roofs": [
            {
                "guid": "ROOF-GABLE-01",
                "name": "Metal Gable Roof Assembly",
                "storey_guid": "S1",
                "predefined_type": "GABLE_ROOF",
                "gross_area": 150.0,  # sq meters
                "projected_area": 130.0,
                "material_layers": [{"material_name": "Standing Seam Metal Sheet"}],
                "psets": {
                    "Pset_RoofCommon": {
                        "Slope": 26.57  # ~6:12 pitch
                    }
                },
            }
        ],
        "spaces": [],
        "openings": [],
        "columns": [],
    }

    model = normalizer.normalize(raw_data)
    assert len(model.roofs) == 1
    rf = model.roofs[0]
    assert rf.ifc_guid == "ROOF-GABLE-01"
    assert rf.source_type == "IfcRoof"
    assert rf.roof_type == "GABLE"
    assert rf.slope_degrees == 26.57
    assert rf.pitch_ratio == "6.0:12"
    assert rf.primary_material == "METAL"
    assert rf.material_provenance == DataProvenanceStatus.VERIFIED_EXPLICIT
    assert rf.slope_provenance == DataProvenanceStatus.VERIFIED_EXPLICIT
    assert rf.qto_eligibility == QTOEligibilityStatus.ELIGIBLE

    # QTO Engine Calculation
    engine = BIMRoofingEngine()
    summary = engine.calculate(model)
    assert summary.total_elements_evaluated == 1
    assert summary.eligible_elements_count == 1
    assert len(summary.line_items) == 1

    item = summary.line_items[0]
    assert item.trade == "ROOFING"
    assert item.category == "ROOFING_SURFACE"
    assert item.unit == "SF"
    assert item.quantity > 0.0
    assert item.provenance.slope_degrees == 26.57
    assert item.provenance.pitch_ratio == "6.0:12"
    assert item.provenance.primary_material == "METAL"


def test_roof_slab_promotion_precedence():
    """Verify IfcSlab with PredefinedType == 'ROOF' is promoted when no IfcRoof exists."""
    normalizer = BIMNormalizer()
    raw_data = {
        "project": {"guid": "P1", "name": "Project"},
        "storeys": [{"guid": "S1", "name": "Upper Level", "elevation": 3.0}],
        "walls": [],
        "slabs": [
            {
                "guid": "SLAB-ROOF-01",
                "name": "Flat Roof Slab",
                "storey_guid": "S1",
                "predefined_type": "ROOF",
                "is_roof": True,
                "area": 200.0,
                "perimeter": 60.0,
                "thickness": 0.3,
                "material_layers": [{"material_name": "EPDM Waterproofing Membrane"}],
                "psets": {},
            }
        ],
        "roofs": [],
        "spaces": [],
        "openings": [],
        "columns": [],
    }

    model = normalizer.normalize(raw_data)
    assert len(model.roofs) == 1
    rf = model.roofs[0]
    assert rf.source_type == "IfcSlab"
    assert rf.roof_type == "FLAT"
    assert rf.slope_degrees == 0.0
    assert rf.pitch_ratio == "0:12"
    assert rf.primary_material == "MEMBRANE"
    assert rf.material_provenance == DataProvenanceStatus.VERIFIED_EXPLICIT


def test_missing_slope_handled_as_review():
    """Verify that when slope is ambiguous, it is tagged UNKNOWN_UNRESOLVED and REVIEW_REQUIRED."""
    normalizer = BIMNormalizer()
    raw_data = {
        "project": {"guid": "P1", "name": "Project"},
        "storeys": [{"guid": "S1", "name": "Roof", "elevation": 10.0}],
        "walls": [],
        "slabs": [],
        "roofs": [
            {
                "guid": "ROOF-UNKNOWN-SLOPE",
                "name": "Generic Roof",
                "storey_guid": "S1",
                "predefined_type": "NOTDEFINED",
                "gross_area": 100.0,
                "projected_area": 100.0,
                "material_layers": [],
                "psets": {},
            }
        ],
        "spaces": [],
        "openings": [],
        "columns": [],
    }

    model = normalizer.normalize(raw_data)
    rf = model.roofs[0]
    assert rf.slope_degrees is None
    assert rf.pitch_ratio is None
    assert rf.slope_provenance == DataProvenanceStatus.UNKNOWN_UNRESOLVED
    assert rf.qto_eligibility == QTOEligibilityStatus.REVIEW_REQUIRED
    assert "SLOPE_NOT_SPECIFIED_IN_IFC" in rf.review_reasons

    engine = BIMRoofingEngine()
    summary = engine.calculate(model)
    assert summary.review_elements_count == 1
    assert summary.line_items[0].provenance.status == "REVIEW"
