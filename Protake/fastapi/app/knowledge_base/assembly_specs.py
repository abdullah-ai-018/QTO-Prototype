"""Construction Knowledge Base (Assembly Specs): Maps finish schedule material codes
and wall-type designations (e.g. P1, W3, F1, C1) to standard civil engineering
material assembly specifications.
"""

from dataclasses import dataclass, field


@dataclass
class AssemblySpec:
    code: str
    category: str  # Paint, Wall, Flooring, Ceiling
    title: str
    description: str
    material_components: list[str] = field(default_factory=list)
    attributes: dict[str, str | float | int] = field(default_factory=dict)


_SPECS_DATABASE: dict[str, AssemblySpec] = {
    "P1": AssemblySpec(
        code="P1",
        category="Paint",
        title="Interior Eggshell Paint (Standard)",
        description="Sherwin Williams ProMar 200 Interior Acrylic Eggshell, 2 coats over 1 coat PVA primer.",
        material_components=["Sherwin Williams ProMar 200 Eggshell", "PVA Drywall Primer"],
        attributes={"coats": 2, "requires_primer": True, "coverage_sqft_per_gal": 350.0},
    ),
    "P2": AssemblySpec(
        code="P2",
        category="Paint",
        title="Interior Semi-Gloss Epoxy Paint",
        description="Water-based Catalyzed Epoxy Semi-Gloss, high durability finish for wet areas.",
        material_components=["Pro Industrial Waterbased Catalyzed Epoxy Semi-Gloss"],
        attributes={"coats": 2, "requires_primer": True, "coverage_sqft_per_gal": 300.0},
    ),
    "W3": AssemblySpec(
        code="W3",
        category="Wall",
        title="5/8\" Fire-Rated Metal Stud Wall (1-HR)",
        description="5/8\" Type X Fire-Rated Gypsum Board on 6\" 20-Gauge Metal Studs @ 16\" o.c. with R-19 batt insulation.",
        material_components=["5/8\" Type X Gypsum Board", "6\" 20-Gauge Metal Studs", "R-19 Acoustic Batt Insulation"],
        attributes={"fire_rating_hr": 1.0, "stud_spacing_in": 16, "board_thickness_in": 0.625},
    ),
    "W4": AssemblySpec(
        code="W4",
        category="Wall",
        title="1/2\" Standard Partition Wall",
        description="1/2\" Standard Gypsum Wallboard on 3-5/8\" 25-Gauge Metal Studs @ 24\" o.c.",
        material_components=["1/2\" Standard GWB", "3-5/8\" 25-Gauge Metal Studs"],
        attributes={"fire_rating_hr": 0.0, "stud_spacing_in": 24, "board_thickness_in": 0.5},
    ),
    "F1": AssemblySpec(
        code="F1",
        category="Flooring",
        title="Vinyl Composition Tile (VCT)",
        description="12\" x 12\" x 1/8\" Commercial VCT Tile with premium acrylic adhesive and 4\" vinyl cove base.",
        material_components=["12x12 VCT Tile", "Commercial Tile Adhesive", "4\" Vinyl Cove Base"],
        attributes={"unit": "sqft", "baseboard_ft_ratio": 1.0},
    ),
    "F2": AssemblySpec(
        code="F2",
        category="Flooring",
        title="Sealed & Polished Concrete",
        description="Multi-pass mechanical polish to 800-grit with lithium silicate densifier and penetrating sealer.",
        material_components=["Lithium Silicate Densifier", "Penetrating Concrete Sealer"],
        attributes={"unit": "sqft", "passes": 3},
    ),
    "C1": AssemblySpec(
        code="C1",
        category="Ceiling",
        title="2' x 4' Suspended Acoustical Tile Ceiling (ACT)",
        description="24\" x 48\" x 5/8\" Mineral Fiber Acoustic Ceiling Tiles on 15/16\" Exposed Tee Suspension Grid.",
        material_components=["24x48 Mineral Fiber ACT Panels", "15/16\" Main Runners & Cross Tees", "12ga Hanger Wire"],
        attributes={"tile_size": "2x4", "grid_type": "15/16 Exposed Tee"},
    ),
}


def lookup_assembly_spec(code: str | None) -> AssemblySpec | None:
    if not code:
        return None
    cleaned_code = code.strip().upper()
    return _SPECS_DATABASE.get(cleaned_code)


def list_available_specs() -> list[AssemblySpec]:
    return list(_SPECS_DATABASE.values())
