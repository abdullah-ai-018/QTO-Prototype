import { describe, it, expect } from "vitest";
import { getDetectionColor, WALL_CATEGORY_COLORS, normalizeWallClassification, getCanonicalWallCategory } from "./colors";
import type { Detection } from "@/types";

describe("Wall Colour Classification & Normalization", () => {
  function makeWall(overrides: Partial<Detection>): Detection {
    return {
      id: "test-wall-1",
      sheetId: "sheet-1",
      kind: "wall",
      name: "Test Wall",
      trade: "drywall",
      points: [
        { x: 0.1, y: 0.2 },
        { x: 0.3, y: 0.2 },
      ],
      areaSqFt: 0,
      perimeterFt: 15,
      confidence: 0.95,
      status: "approved",
      ...overrides,
    };
  }

  it("classifies INTERIOR_PARTITION as solid green (#10B981)", () => {
    const wall = makeWall({ wallTypeCode: "INTERIOR_PARTITION" });
    expect(getDetectionColor(wall)).toBe(WALL_CATEGORY_COLORS.INTERIOR_PARTITION.color);
    expect(getDetectionColor(wall)).toBe("#10B981");
  });

  it("classifies EXTERIOR_PERIMETER as solid orange (#F97316)", () => {
    const wall = makeWall({ wallTypeCode: "EXTERIOR_PERIMETER" });
    expect(getDetectionColor(wall)).toBe(WALL_CATEGORY_COLORS.EXTERIOR_PERIMETER.color);
    expect(getDetectionColor(wall)).toBe("#F97316");
  });

  it("classifies STRUCTURAL_BEARING as solid purple (#A855F7)", () => {
    const wall = makeWall({ wallTypeCode: "STRUCTURAL_BEARING" });
    expect(getDetectionColor(wall)).toBe(WALL_CATEGORY_COLORS.STRUCTURAL_BEARING.color);
    expect(getDetectionColor(wall)).toBe("#A855F7");
  });

  it("classifies STAIR_CORE as solid yellow (#EAB308)", () => {
    const wall = makeWall({ wallTypeCode: "STAIR_CORE" });
    expect(getDetectionColor(wall)).toBe(WALL_CATEGORY_COLORS.STAIR_CORE.color);
    expect(getDetectionColor(wall)).toBe("#EAB308");
  });

  it("classifies CORRIDOR as solid cyan (#06B6D4)", () => {
    const wall = makeWall({ wallTypeCode: "CORRIDOR" });
    expect(getDetectionColor(wall)).toBe(WALL_CATEGORY_COLORS.CORRIDOR.color);
    expect(getDetectionColor(wall)).toBe("#06B6D4");
  });

  it("classifies WET_CORE as solid blue (#3B82F6)", () => {
    const wall = makeWall({ wallTypeCode: "WET_CORE" });
    expect(getDetectionColor(wall)).toBe(WALL_CATEGORY_COLORS.WET_CORE.color);
    expect(getDetectionColor(wall)).toBe("#3B82F6");
  });

  it("classifies DEMISING as solid pink (#EC4899)", () => {
    const wall = makeWall({ wallTypeCode: "DEMISING" });
    expect(getDetectionColor(wall)).toBe(WALL_CATEGORY_COLORS.DEMISING.color);
    expect(getDetectionColor(wall)).toBe("#EC4899");
  });

  it("classifies SHAFT as solid violet (#8B5CF6)", () => {
    const wall = makeWall({ wallTypeCode: "SHAFT" });
    expect(getDetectionColor(wall)).toBe(WALL_CATEGORY_COLORS.SHAFT.color);
    expect(getDetectionColor(wall)).toBe("#8B5CF6");
  });

  it("defensively handles whitespace and lowercase values in wallTypeCode", () => {
    const wall = makeWall({ wallTypeCode: "  corridor_wall  " });
    expect(getDetectionColor(wall)).toBe("#06B6D4");
  });

  it("classifies low-confidence unclassified walls as NEEDS_REVIEW (#94A3B8)", () => {
    const wall = makeWall({ wallTypeCode: null, confidence: 0.55, status: "pending" });
    expect(getDetectionColor(wall)).toBe("#94A3B8");
  });

  it("falls back to wallType exterior (#F97316) when wallTypeCode is absent", () => {
    const wall = makeWall({ wallTypeCode: null, wallType: "exterior", confidence: 0.95 });
    expect(getDetectionColor(wall)).toBe("#F97316");
  });

  it("falls back to wallType interior (#10B981) when wallTypeCode is absent", () => {
    const wall = makeWall({ wallTypeCode: null, wallType: "interior", confidence: 0.95 });
    expect(getDetectionColor(wall)).toBe("#10B981");
  });

  it("classifies unknown wall types as NEEDS_REVIEW (#94A3B8)", () => {
    const wall = makeWall({ wallTypeCode: "SOME_FUTURE_UNKNOWN_TYPE" as any });
    expect(getDetectionColor(wall)).toBe("#94A3B8");
  });

  // Regression coverage for the "approval turns everything green" bug: the
  // category color returned by getDetectionColor/getCanonicalWallCategory
  // must never change because a wall's status becomes "approved" — approval
  // has its own visual treatment in EngineeringCanvasLayer (badge/glow/dash)
  // layered on top, but the underlying category color is what feeds it and
  // must stay the real classification color at all times.
  describe("category color is unaffected by approval status", () => {
    it("an approved EXTERIOR_PERIMETER wall stays orange (#F97316), not green", () => {
      const wall = makeWall({ wallTypeCode: "EXTERIOR_PERIMETER", status: "approved" });
      expect(getDetectionColor(wall)).toBe("#F97316");
    });

    it("an approved STRUCTURAL_BEARING wall stays purple (#A855F7), not green", () => {
      const wall = makeWall({ wallTypeCode: "STRUCTURAL_BEARING", status: "approved" });
      expect(getDetectionColor(wall)).toBe("#A855F7");
    });

    it("an approved SHAFT wall stays violet (#8B5CF6), not green", () => {
      const wall = makeWall({ wallTypeCode: "SHAFT", status: "approved" });
      expect(getDetectionColor(wall)).toBe("#8B5CF6");
    });

    it("an approved CORRIDOR wall stays cyan (#06B6D4), not green", () => {
      const wall = makeWall({ wallTypeCode: "CORRIDOR", status: "approved" });
      expect(getDetectionColor(wall)).toBe("#06B6D4");
    });

    it("a rejected EXTERIOR_PERIMETER wall stays orange (#F97316), not red", () => {
      const wall = makeWall({ wallTypeCode: "EXTERIOR_PERIMETER", status: "rejected" });
      expect(getDetectionColor(wall)).toBe("#F97316");
    });

    it("a wall with an unresolved classification stays gray/NEEDS_REVIEW (#94A3B8) even once approved", () => {
      const wall = makeWall({ wallTypeCode: "totally_unrecognized_value" as any, status: "approved" });
      expect(getDetectionColor(wall)).toBe(WALL_CATEGORY_COLORS.NEEDS_REVIEW.color);
      expect(getDetectionColor(wall)).toBe("#94A3B8");
    });

    it("a needs-review wall (unresolved classification, wallType forced to interior) stays gray even once approved, never green", () => {
      const wall = makeWall({
        wallTypeCode: "unclassified",
        wallType: "interior",
        status: "approved",
        confidence: 0.95,
      });
      const color = getDetectionColor(wall);
      expect(color).toBe("#94A3B8");
      expect(color).not.toBe("#10B981");
    });

    it("an unknown/unrecognized classification string never resolves to INTERIOR_PARTITION, approved or not", () => {
      for (const status of ["pending", "approved", "rejected"] as const) {
        const wall = makeWall({ wallTypeCode: "garbage_value" as any, status });
        expect(getDetectionColor(wall)).not.toBe(WALL_CATEGORY_COLORS.INTERIOR_PARTITION.color);
      }
    });
  });
});
