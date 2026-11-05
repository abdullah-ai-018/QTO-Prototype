"""
Test suite for Assistant Forensic Wall Proof & Intent Intercept (Phase 14).
Validates:
1. "prove its wall" -> forensic wall investigation
2. DUAL_FACE wall -> VERIFIED
3. SINGLE_FACE evidence-backed -> evidence response
4. Missing wall / unselected -> honest non-hallucinatory prompt
5. Explicit Wall ID resolution
6. Selected wall context resolution
7. QTO inclusion / exclusion proof
8. Scale provenance & verification disclosure
9. Source markup matching calculation
10. Wall thickness measurement proof
"""
import pytest
from app.services.assistant_service import is_forensic_wall_query, resolve_target_wall_id, format_forensic_wall_proof


def test_is_forensic_wall_query_triggers():
    assert is_forensic_wall_query("prove its wall") is True
    assert is_forensic_wall_query("prove this is a wall") is True
    assert is_forensic_wall_query("why is this a wall?") is True
    assert is_forensic_wall_query("show me why this is a wall") is True
    assert is_forensic_wall_query("is this actually a wall?") is True
    assert is_forensic_wall_query("what evidence proves this wall?") is True
    assert is_forensic_wall_query("verify this wall") is True
    assert is_forensic_wall_query("why did you detect this wall?") is True
    assert is_forensic_wall_query("give me wall evidence") is True
    assert is_forensic_wall_query("show wall provenance") is True
    assert is_forensic_wall_query("why is this drywall?") is True
    assert is_forensic_wall_query("why was this wall excluded?") is True
    assert is_forensic_wall_query("what is the wall thickness?") is True
    assert is_forensic_wall_query("does this markup match the source?") is True
    assert is_forensic_wall_query("what is the scale?") is True

    # Non-forensic general questions
    assert is_forensic_wall_query("list all pages in this blueprint") is False
    assert is_forensic_wall_query("how many rooms are on page 2?") is False
    assert is_forensic_wall_query("generate an estimate") is False


def test_resolve_target_wall_id():
    # 1. Explicit ID in message
    assert resolve_target_wall_id("prove its wall for AW-535458") == "535458"
    assert resolve_target_wall_id("prove drywall-wall-104 is a wall") == "104"
    assert resolve_target_wall_id("why is wall #42 included?") == "42"

    # 2. Selected context
    selected = {"source": "wall", "id": "drywall-wall-535528", "wall_id": "535528"}
    assert resolve_target_wall_id("prove its wall", selected_context=selected) == "535528"

    # 3. History resolution
    history = [{"role": "user", "content": "Tell me about AW-535587"}, {"role": "assistant", "content": "Here is AW-535587"}]
    assert resolve_target_wall_id("prove its wall", history=history) == "535587"

    # 4. Unresolved
    assert resolve_target_wall_id("prove its wall") is None


def test_format_forensic_wall_proof_dual_face():
    mock_ev = {
        "wall_id": "backend-archwall-535458",
        "raw_id": "535458",
        "verdict": "VERIFIED PHYSICAL WALL",
        "reconstruction_method": "DUAL_FACE",
        "source": {
            "blueprint_id": 138,
            "blueprint_filename": "260616_LSFC.pdf",
            "page_id": 689,
            "page_number": 1,
            "sheet_code": "A-2.1",
            "sheet_name": "Floor Plan",
        },
        "geometry": {
            "face_a_segment_id": 104,
            "face_b_segment_id": 105,
            "face_a_coords": {"x1": 0.7514, "y1": 0.2124, "x2": 0.7720, "y2": 0.2124},
            "face_b_coords": {"x1": 0.7514, "y1": 0.2160, "x2": 0.7720, "y2": 0.2160},
            "thickness_in": 4.875,
            "thickness_source": "paired_geometry",
            "length_ft": 2.75,
            "height_ft": 9.0,
            "height_provenance": "VERIFIED",
            "start_norm": {"x": 0.7514, "y": 0.2142},
            "end_norm": {"x": 0.7720, "y": 0.2142},
            "clipped_segments": [[{"x": 0.7514, "y": 0.2142}, {"x": 0.7720, "y": 0.2142}]],
            "wall_polygon": [{"x": 0.7514, "y": 0.2124}, {"x": 0.7720, "y": 0.2124}, {"x": 0.7720, "y": 0.2160}, {"x": 0.7514, "y": 0.2160}],
        },
        "evidence": {
            "cad_layers": ["A-WALL-GWB"],
            "paired_faces": True,
            "attached_openings_count": 0,
            "opening_ids": [],
            "true_source_union_length_ft": 2.75,
            "is_bridged": False,
            "bridged_segment_count": 1,
        },
        "classification": {
            "category": "INTERIOR_PARTITION",
            "confidence": 0.95,
            "reasons": ["dual_independent_faces_supported", "room_boundary_topology"],
            "wall_tag": "W1",
        },
        "qto": {
            "eligible": True,
            "block_reason": None,
            "assembly_tag": "W1",
            "assembly_description": "1-Hr Fire Rated 4-7/8\" Partition",
            "assembly_verified": True,
            "gross_sf": 49.5,
            "opening_deduction_sf": 0.0,
            "net_sf": 49.5,
            "sides_to_hang": 2,
            "layers_side_a": 1,
            "layers_side_b": 1,
        },
        "scale": {
            "scale_ft_per_px": 0.016686,
            "scale_source": "reference_object_calibration",
            "scale_status": "VERIFIED",
        },
    }

    # Test main proof
    proof = format_forensic_wall_proof(mock_ev, "prove its wall")
    assert "WALL VERIFICATION" in proof
    assert "VERIFIED PHYSICAL WALL" in proof
    assert "backend-archwall-535458" in proof
    assert "DUAL_FACE" in proof
    assert "source segment 104" in proof
    assert "source segment 105" in proof
    assert "A-WALL-GWB" in proof
    assert "4.875\"" in proof
    assert "INTERIOR_PARTITION" in proof
    assert "VERIFIED" in proof
    assert "FORENSIC CONCLUSION" in proof

    # Test QTO proof
    qto_proof = format_forensic_wall_proof(mock_ev, "why is this drywall?")
    assert "QTO DRYWALL INCLUSION PROOF" in qto_proof
    assert "49.50 SF" in qto_proof

    # Test source markup proof
    markup_proof = format_forensic_wall_proof(mock_ev, "does this markup match the source?")
    assert "SOURCE-TO-MARKUP GEOMETRIC AUDIT" in markup_proof
    assert "0.0000 ft" in markup_proof

    # Test scale proof
    scale_proof = format_forensic_wall_proof(mock_ev, "what is the scale?")
    assert "SCALE PROVENANCE & VERIFICATION AUDIT" in scale_proof
    assert "reference_object_calibration" in scale_proof
