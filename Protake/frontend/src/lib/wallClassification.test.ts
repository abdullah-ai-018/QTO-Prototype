import { describe, it, expect } from "vitest";
import {
  normalizeWallClassification,
  getCanonicalWallCategory,
  WALL_CATEGORY_COLORS,
  CANONICAL_WALL_CATEGORIES,
} from "./colors";
import { architecturalWallToDetection } from "./backendConversion";
import { buildWallInspectionData } from "./wallInspectorModel";
import type { BackendArchitecturalWall, Detection } from "@/types";
import type { AppState } from "@/state/AppContext";

describe("Canonical Wall Classification & Engineering Inspector System", () => {
  // 1-9: Normalization tests for all 9 categories
  it("1. normalizes interior variants to INTERIOR_PARTITION", () => {
    expect(normalizeWallClassification("interior")).toBe("INTERIOR_PARTITION");
    expect(normalizeWallClassification("interior_wall")).toBe("INTERIOR_PARTITION");
    expect(normalizeWallClassification("partition")).toBe("INTERIOR_PARTITION");
    expect(normalizeWallClassification("interior_partition")).toBe("INTERIOR_PARTITION");
    expect(normalizeWallClassification("drywall_partition")).toBe("INTERIOR_PARTITION");
  });

  it("2. normalizes exterior variants to EXTERIOR_PERIMETER", () => {
    expect(normalizeWallClassification("exterior")).toBe("EXTERIOR_PERIMETER");
    expect(normalizeWallClassification("exterior_wall")).toBe("EXTERIOR_PERIMETER");
    expect(normalizeWallClassification("perimeter")).toBe("EXTERIOR_PERIMETER");
    expect(normalizeWallClassification("perimeter_wall")).toBe("EXTERIOR_PERIMETER");
    expect(normalizeWallClassification("curtain_wall")).toBe("EXTERIOR_PERIMETER");
    expect(normalizeWallClassification("exterior_perimeter_wall")).toBe("EXTERIOR_PERIMETER");
  });

  it("3. normalizes structural variants to STRUCTURAL_BEARING", () => {
    expect(normalizeWallClassification("structural")).toBe("STRUCTURAL_BEARING");
    expect(normalizeWallClassification("bearing")).toBe("STRUCTURAL_BEARING");
    expect(normalizeWallClassification("structural_bearing")).toBe("STRUCTURAL_BEARING");
    expect(normalizeWallClassification("structural_bearing_wall")).toBe("STRUCTURAL_BEARING");
    expect(normalizeWallClassification("masonry")).toBe("STRUCTURAL_BEARING");
    expect(normalizeWallClassification("concrete")).toBe("STRUCTURAL_BEARING");
  });

  it("4. normalizes stair/core variants to STAIR_CORE", () => {
    expect(normalizeWallClassification("stair")).toBe("STAIR_CORE");
    expect(normalizeWallClassification("core")).toBe("STAIR_CORE");
    expect(normalizeWallClassification("stair_core")).toBe("STAIR_CORE");
    expect(normalizeWallClassification("stair_core_wall")).toBe("STAIR_CORE");
  });

  it("5. normalizes corridor variants to CORRIDOR", () => {
    expect(normalizeWallClassification("corridor")).toBe("CORRIDOR");
    expect(normalizeWallClassification("corridor_wall")).toBe("CORRIDOR");
    expect(normalizeWallClassification("CORRIDOR")).toBe("CORRIDOR");
  });

  it("6. normalizes wet core variants to WET_CORE", () => {
    expect(normalizeWallClassification("wet_core")).toBe("WET_CORE");
    expect(normalizeWallClassification("wet")).toBe("WET_CORE");
    expect(normalizeWallClassification("wet_core_wall")).toBe("WET_CORE");
    expect(normalizeWallClassification("plumbing_chase")).toBe("WET_CORE");
  });

  it("7. normalizes demising variants to DEMISING", () => {
    expect(normalizeWallClassification("demising")).toBe("DEMISING");
    expect(normalizeWallClassification("demising_wall")).toBe("DEMISING");
  });

  it("8. normalizes shaft variants to SHAFT", () => {
    expect(normalizeWallClassification("shaft")).toBe("SHAFT");
    expect(normalizeWallClassification("shaft_wall")).toBe("SHAFT");
  });

  it("9. normalizes unknown/unclassified to NEEDS_REVIEW", () => {
    expect(normalizeWallClassification("unknown")).toBe("NEEDS_REVIEW");
    expect(normalizeWallClassification("unclassified")).toBe("NEEDS_REVIEW");
    expect(normalizeWallClassification("random_value")).toBe("NEEDS_REVIEW");
    expect(normalizeWallClassification(null)).toBe("NEEDS_REVIEW");
    expect(normalizeWallClassification(undefined)).toBe("NEEDS_REVIEW");
  });

  it("10. ensures DEFAULT assembly tag never becomes a wall category", () => {
    const rawWall: BackendArchitecturalWall = {
      id: "wall-1",
      page_id: 1,
      start_norm: { x: 0, y: 0 },
      end_norm: { x: 1, y: 0 },
      clipped_segments_norm: [[{ x: 0, y: 0 }, { x: 1, y: 0 }]],
      length_ft: 10,
      height_ft: 9,
      height_provenance: "ASSUMED",
      thickness_in: 4.875,
      thickness_source: "project_default",
      classification: "interior",
      wall_tag: "DEFAULT",
      assembly_tag: "DEFAULT",
      sides_to_hang: 2,
      layers_side_a: 1,
      layers_side_b: 1,
      assembly_verified: false,
      gross_sf: 180,
      openings_count: 0,
      opening_deduction_sf: 0,
      net_sf: 180,
      decision_state: "physical_wall_confirmed",
      qto_eligible: true,
      confidence: 0.95,
      status: "approved",
    };

    const det = architecturalWallToDetection(rawWall, "sheet-0");
    expect(det.name).not.toContain("[DEFAULT]");
    expect(det.wallTypeCode).toBe("INTERIOR_PARTITION");
    expect(det.wallTag).toBeNull();
  });

  it("11. ensures real wall_tag remains visible e.g. [NR-1]", () => {
    const rawWall: BackendArchitecturalWall = {
      id: "wall-2",
      page_id: 1,
      start_norm: { x: 0, y: 0 },
      end_norm: { x: 1, y: 0 },
      clipped_segments_norm: [[{ x: 0, y: 0 }, { x: 1, y: 0 }]],
      length_ft: 17,
      height_ft: 9,
      height_provenance: "ASSUMED",
      thickness_in: 4.875,
      thickness_source: "project_default",
      classification: "interior",
      wall_tag: "NR-1",
      assembly_tag: "DEFAULT",
      sides_to_hang: 2,
      layers_side_a: 1,
      layers_side_b: 1,
      assembly_verified: false,
      gross_sf: 306,
      openings_count: 0,
      opening_deduction_sf: 0,
      net_sf: 306,
      decision_state: "physical_wall_confirmed",
      qto_eligible: true,
      confidence: 0.95,
      status: "approved",
    };

    const det = architecturalWallToDetection(rawWall, "sheet-0");
    expect(det.name).toContain("[NR-1]");
    expect(det.wallTag).toBe("NR-1");
  });

  it("12. verifies category colors match specification", () => {
    expect(WALL_CATEGORY_COLORS.INTERIOR_PARTITION.color).toBe("#10B981"); // Green
    expect(WALL_CATEGORY_COLORS.EXTERIOR_PERIMETER.color).toBe("#F97316"); // Orange
    expect(WALL_CATEGORY_COLORS.STRUCTURAL_BEARING.color).toBe("#A855F7"); // Purple
    expect(WALL_CATEGORY_COLORS.STAIR_CORE.color).toBe("#EAB308"); // Yellow
    expect(WALL_CATEGORY_COLORS.CORRIDOR.color).toBe("#06B6D4"); // Cyan
    expect(WALL_CATEGORY_COLORS.WET_CORE.color).toBe("#3B82F6"); // Blue
    expect(WALL_CATEGORY_COLORS.DEMISING.color).toBe("#EC4899"); // Pink/Magenta
    expect(WALL_CATEGORY_COLORS.SHAFT.color).toBe("#8B5CF6"); // Violet
    expect(WALL_CATEGORY_COLORS.NEEDS_REVIEW.color).toBe("#94A3B8"); // Gray
  });

  it("13. ensures buildWallInspectionData calculates wall-specific metrics accurately", () => {
    const mockState = {
      sheets: [{ id: "sheet-0", code: "A104", pageIndex: 0, pageNumber: 378, name: "Floor Plan" }],
      activeSheetId: "sheet-0",
      detections: [],
      selectedDetectionId: "backend-archwall-wall-1",
      hoveredDetectionId: null,
      zoom: 1,
      pan: { x: 0, y: 0 },
      unitSystem: "imperial",
      summaryTab: "drywall",
      revision: "rev-1",
      history: [],
      hiddenTrades: {} as any,
      hiddenWallCategories: {} as any,
      wallCategoryFilter: null,
      showRoomGeometry: true,
    } as unknown as AppState;

    const wallA: Detection = {
      id: "backend-archwall-wall-1",
      sheetId: "sheet-0",
      kind: "wall",
      name: "Interior Partition",
      trade: "drywall",
      points: [{ x: 0.1, y: 0.1 }, { x: 0.5, y: 0.1 }],
      areaSqFt: 153,
      perimeterFt: 17,
      heightFt: 9,
      thicknessIn: 4,
      wallTypeCode: "INTERIOR_PARTITION",
      sidesToHang: 2,
      layersSideA: 1,
      layersSideB: 1,
      grossSf: 306,
      openingDeductionSf: 0,
      netSf: 306,
      openingsCount: 0,
      qtoEligible: true,
      confidence: 0.95,
      status: "approved",
    };

    const dataA = buildWallInspectionData(wallA, mockState);
    expect(dataA.lengthFt).toBe(17);
    expect(dataA.heightFt).toBe(9);
    expect(dataA.wallFaceAreaSf).toBe(153);
    expect(dataA.openingDeductionSf).toBe(0);
    expect(dataA.grossHangAreaSf).toBe(306);
    expect(dataA.netHangAreaSf).toBe(306);
    expect(dataA.categoryCode).toBe("INTERIOR_PARTITION");
    expect(dataA.requiredSheets).toBe(Math.ceil((306 * 1.10) / 32)); // 11 sheets

    const wallB: Detection = {
      id: "backend-archwall-wall-2",
      sheetId: "sheet-0",
      kind: "wall",
      name: "Corridor Wall",
      trade: "drywall",
      points: [{ x: 0.1, y: 0.2 }, { x: 0.7, y: 0.2 }],
      areaSqFt: 246,
      perimeterFt: 32,
      heightFt: 9,
      thicknessIn: 6,
      wallTypeCode: "CORRIDOR",
      sidesToHang: 2,
      layersSideA: 1,
      layersSideB: 1,
      grossSf: 576,
      openingDeductionSf: 42,
      netSf: 534,
      openingsCount: 2,
      qtoEligible: true,
      confidence: 0.95,
      status: "approved",
    };

    const dataB = buildWallInspectionData(wallB, mockState);
    expect(dataB.lengthFt).toBe(32);
    expect(dataB.heightFt).toBe(9);
    expect(dataB.wallFaceAreaSf).toBe(288);
    expect(dataB.openingDeductionSf).toBe(42);
    expect(dataB.grossHangAreaSf).toBe(576);
    expect(dataB.netHangAreaSf).toBe(534);
    expect(dataB.categoryCode).toBe("CORRIDOR");
    expect(dataB.requiredSheets).toBe(Math.ceil((534 * 1.10) / 32)); // 19 sheets
  });

  // 14-16: getCanonicalWallCategory must never silently fall back to
  // INTERIOR_PARTITION for an unknown/uncertain wall — the honest fallback
  // is always NEEDS_REVIEW, so the canvas/legend/filter never claim
  // certainty the system doesn't have.
  it("14. getCanonicalWallCategory falls back to NEEDS_REVIEW for a completely unclassified wall", () => {
    expect(getCanonicalWallCategory(null, undefined, null, "approved", 0.95, null)).toBe("NEEDS_REVIEW");
  });

  it("15. getCanonicalWallCategory forces NEEDS_REVIEW below the confidence threshold, even with an otherwise-valid classification", () => {
    expect(getCanonicalWallCategory("INTERIOR_PARTITION", "interior", null, "approved", 0.5, "interior")).toBe(
      "NEEDS_REVIEW",
    );
  });

  it("16. getCanonicalWallCategory preserves classification regardless of pending/approved status", () => {
    expect(getCanonicalWallCategory("EXTERIOR_PERIMETER", "exterior", null, "pending", 0.95, "exterior")).toBe(
      "EXTERIOR_PERIMETER",
    );
    expect(getCanonicalWallCategory("INTERIOR_PARTITION", "interior", null, "pending", 0.95, "interior")).toBe(
      "INTERIOR_PARTITION",
    );
  });

  it("17. legend invariant: SUM(per-category counts) always equals the active-sheet wall count, for any mix of classified/unclassified/low-confidence walls (see Sidebar.tsx categoryCounts)", () => {
    const walls: Array<Parameters<typeof getCanonicalWallCategory>> = [
      ["INTERIOR_PARTITION", "interior", null, "approved", 0.95, "interior"],
      ["EXTERIOR_PERIMETER", "exterior", null, "approved", 0.95, "exterior"],
      [null, undefined, null, "approved", 0.95, null], // fully unclassified -> NEEDS_REVIEW
      ["STRUCTURAL_BEARING", "interior", null, "pending", 0.95, "structural"], // pending STRUCTURAL_BEARING
      ["CORRIDOR", "interior", null, "approved", 0.4, "corridor"], // low confidence -> forced NEEDS_REVIEW
      ["SHAFT", "interior", null, "approved", 0.95, "shaft"],
    ];

    const counts: Record<string, number> = {
      INTERIOR_PARTITION: 0, EXTERIOR_PERIMETER: 0, STRUCTURAL_BEARING: 0, STAIR_CORE: 0,
      CORRIDOR: 0, WET_CORE: 0, DEMISING: 0, SHAFT: 0, NEEDS_REVIEW: 0,
    };
    for (const w of walls) {
      const code = getCanonicalWallCategory(...w);
      counts[code]++;
    }

    const sum = Object.values(counts).reduce((a, b) => a + b, 0);
    expect(sum).toBe(walls.length);
    expect(counts.NEEDS_REVIEW).toBe(2); // unclassified + low-confidence
    expect(counts.STRUCTURAL_BEARING).toBe(1);
  });

  // 18-20: regression coverage for the getCanonicalWallCategory fall-through
  // bug — a wallTypeCode/classification that is PRESENT but does not
  // normalize to a known category must stay NEEDS_REVIEW. It must never
  // fall through to the legacy wallType binary check, which the conversion
  // layer always forces to "interior" or "exterior" for every real wall —
  // that fallback silently turned every unresolved wall into
  // INTERIOR_PARTITION (green) instead of gray.
  it("18. an unrecognized wallTypeCode stays NEEDS_REVIEW even though wallType is forced to 'interior'", () => {
    expect(
      getCanonicalWallCategory("SOME_JUNK_CODE", "interior", null, "approved", 0.95, null)
    ).toBe("NEEDS_REVIEW");
  });

  it("19. an unrecognized wallTypeCode stays NEEDS_REVIEW even though wallType is forced to 'exterior'", () => {
    expect(
      getCanonicalWallCategory("SOME_JUNK_CODE", "exterior", null, "approved", 0.95, null)
    ).toBe("NEEDS_REVIEW");
  });

  it("20. an unrecognized classification (with no usable wallTypeCode) stays NEEDS_REVIEW even though wallType is forced to 'interior'", () => {
    expect(
      getCanonicalWallCategory(null, "interior", null, "approved", 0.95, "totally_unknown_value")
    ).toBe("NEEDS_REVIEW");
  });

  it("21. an unrecognized classification never silently resolves to INTERIOR_PARTITION just because wallType defaults there", () => {
    const result = getCanonicalWallCategory("", "interior", null, "approved", 0.95, "garbage_in");
    expect(result).not.toBe("INTERIOR_PARTITION");
    expect(result).toBe("NEEDS_REVIEW");
  });

  it("22. legacy wallType fallback still applies when wallTypeCode AND classification are both genuinely absent", () => {
    expect(getCanonicalWallCategory(null, "interior", null, "approved", 0.95, null)).toBe("INTERIOR_PARTITION");
    expect(getCanonicalWallCategory(undefined, "exterior", null, "approved", 0.95, undefined)).toBe("EXTERIOR_PERIMETER");
    expect(getCanonicalWallCategory("", "interior", null, "approved", 0.95, "")).toBe("INTERIOR_PARTITION");
  });
});
