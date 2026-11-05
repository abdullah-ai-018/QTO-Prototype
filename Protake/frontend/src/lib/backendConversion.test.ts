import { describe, it, expect } from "vitest";
import { architecturalWallToDetection } from "./backendConversion";
import type { BackendArchitecturalWall } from "@/types";

describe("architecturalWallToDetection - Wall Classification and Labeling", () => {
  function makeArchWall(overrides: Partial<BackendArchitecturalWall> = {}): BackendArchitecturalWall {
    return {
      id: "drywall-wall-test-1",
      page_id: 378,
      start_norm: { x: 0.1, y: 0.2 },
      end_norm: { x: 0.5, y: 0.2 },
      clipped_segments_norm: [[{ x: 0.1, y: 0.2 }, { x: 0.5, y: 0.2 }]],
      wall_polygon_norm: [],
      length_ft: 24.0,
      height_ft: 9.0,
      height_provenance: "ASSUMED",
      thickness_in: 6.5,
      thickness_source: "paired_geometry",
      classification: "interior",
      wall_tag: "DEFAULT",
      assembly_tag: "DEFAULT",
      assembly_description: 'Assumed: 3-5/8" Metal Stud Partition, 5/8" GWB Each Side (no schedule)',
      sides_to_hang: 2,
      layers_side_a: 1,
      layers_side_b: 1,
      schedule_sheet: null,
      assembly_verified: false,
      gross_sf: 216.0,
      openings_count: 0,
      opening_deduction_sf: 0.0,
      net_sf: 216.0,
      decision_state: "physical_wall_confirmed",
      qto_eligible: true,
      qto_block_reason: null,
      confidence: 0.95,
      status: "approved",
      rejection_reason: null,
      ...overrides,
    };
  }

  it("formats interior wall with DEFAULT assembly_tag and DEFAULT wall_tag without [DEFAULT] prefix", () => {
    const wall = makeArchWall({
      classification: "interior",
      wall_tag: "DEFAULT",
      assembly_tag: "DEFAULT",
      length_ft: 24.0,
      height_ft: 9.0,
      thickness_in: 6.5,
    });
    const detection = architecturalWallToDetection(wall, "sheet-378");
    
    expect(detection.name).not.toContain("[DEFAULT]");
    expect(detection.name).toBe('Interior Partition (24 ft × 9.0 ft • 6.5" thick)');
    expect(detection.wallType).toBe("interior");
    expect(detection.wallTypeCode).toBe("INTERIOR_PARTITION");
  });

  it("formats interior wall with drawn wall_tag e.g. [NR-1] preserving the notation without DEFAULT assembly clutter", () => {
    const wall = makeArchWall({
      classification: "interior",
      wall_tag: "NR-1",
      assembly_tag: "DEFAULT",
      length_ft: 15.6,
      height_ft: 9.0,
      thickness_in: 6.2,
    });
    const detection = architecturalWallToDetection(wall, "sheet-378");

    expect(detection.name).toBe('[NR-1] Interior Partition (16 ft × 9.0 ft • 6.2" thick)');
    expect(detection.wallType).toBe("interior");
    expect(detection.wallTypeCode).toBe("INTERIOR_PARTITION");
  });

  it("formats exterior wall properly as Exterior / Perimeter with [X-2] notation and EXTERIOR_PERIMETER code", () => {
    const wall = makeArchWall({
      classification: "exterior",
      wall_tag: "X-2",
      assembly_tag: "DEFAULT",
      length_ft: 18.0,
      height_ft: 9.0,
      thickness_in: 8.0,
    });
    const detection = architecturalWallToDetection(wall, "sheet-378");

    expect(detection.name).not.toContain("[DEFAULT]");
    expect(detection.name).toBe('[X-2] Exterior / Perimeter (18 ft × 9.0 ft • 8.0" thick)');
    expect(detection.wallType).toBe("exterior");
    expect(detection.wallTypeCode).toBe("EXTERIOR_PERIMETER");
  });

  it("formats exterior wall without drawn tag as Exterior / Perimeter", () => {
    const wall = makeArchWall({
      classification: "exterior",
      wall_tag: null,
      assembly_tag: "DEFAULT",
      length_ft: 10.0,
      height_ft: 9.0,
      thickness_in: 8.0,
    });
    const detection = architecturalWallToDetection(wall, "sheet-378");

    expect(detection.name).not.toContain("[DEFAULT]");
    expect(detection.name).toBe('Exterior / Perimeter (10 ft × 9.0 ft • 8.0" thick)');
    expect(detection.wallType).toBe("exterior");
    expect(detection.wallTypeCode).toBe("EXTERIOR_PERIMETER");
  });

  it("includes verified real schedule-backed assembly tag when present (non-DEFAULT)", () => {
    const wall = makeArchWall({
      classification: "interior",
      wall_tag: "W1",
      assembly_tag: "TYPE-A1",
      assembly_verified: true,
      length_ft: 20.0,
      height_ft: 9.0,
      thickness_in: 4.875,
    });
    const detection = architecturalWallToDetection(wall, "sheet-378");

    expect(detection.name).toBe('[W1] Interior Partition — TYPE-A1 (20 ft × 9.0 ft • 4.9" thick)');
    expect(detection.wallType).toBe("interior");
  });

  it("handles other classifications such as shaft, demising, curtain_wall", () => {
    const shaftWall = makeArchWall({
      classification: "shaft",
      wall_tag: "S-1",
      length_ft: 12.0,
    });
    expect(architecturalWallToDetection(shaftWall, "sheet-1").name).toContain("[S-1] Shaft Wall");

    const demisingWall = makeArchWall({
      classification: "demising",
      wall_tag: null,
      length_ft: 30.0,
    });
    expect(architecturalWallToDetection(demisingWall, "sheet-1").name).toContain("Demising Wall");
  });
});
