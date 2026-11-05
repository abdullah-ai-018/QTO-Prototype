import { describe, it, expect } from "vitest";
import { calculateWall3DGeometry } from "./wallGeometry3D";
import { CANONICAL_WALL_CATEGORIES, WALL_CATEGORY_COLORS } from "./colors";

describe("wallGeometry3D - Data-Driven 3D Wall Geometry", () => {
  it("Requirement 1 & 2: Two walls with different lengths produce visibly different geometry dimensions", () => {
    const wallA = calculateWall3DGeometry({
      lengthFt: 3.0,
      heightFt: 9.0,
      thicknessIn: 4.88,
      categoryCode: "INTERIOR_PARTITION",
    });

    const wallB = calculateWall3DGeometry({
      lengthFt: 17.0,
      heightFt: 9.0,
      thicknessIn: 4.0,
      categoryCode: "INTERIOR_PARTITION",
    });

    const wallC = calculateWall3DGeometry({
      lengthFt: 32.0,
      heightFt: 9.0,
      thicknessIn: 8.4,
      categoryCode: "EXTERIOR_PERIMETER",
    });

    expect(wallA.valid).toBe(true);
    expect(wallB.valid).toBe(true);
    expect(wallC.valid).toBe(true);

    // Physical dimensions must match exactly
    expect(wallA.lengthFt).toBe(3.0);
    expect(wallB.lengthFt).toBe(17.0);
    expect(wallC.lengthFt).toBe(32.0);

    // Bounding lengths of front face (distance between frontBottomLeft and frontBottomRight)
    const spanA = Math.hypot(
      wallA.vertices.frontBottomRight.x - wallA.vertices.frontBottomLeft.x,
      wallA.vertices.frontBottomRight.y - wallA.vertices.frontBottomLeft.y
    );
    const spanB = Math.hypot(
      wallB.vertices.frontBottomRight.x - wallB.vertices.frontBottomLeft.x,
      wallB.vertices.frontBottomRight.y - wallB.vertices.frontBottomLeft.y
    );
    const spanC = Math.hypot(
      wallC.vertices.frontBottomRight.x - wallC.vertices.frontBottomLeft.x,
      wallC.vertices.frontBottomRight.y - wallC.vertices.frontBottomLeft.y
    );

    // Wall A (3ft) must be significantly shorter than Wall B (17ft), and Wall B shorter than Wall C (32ft)
    expect(spanA).toBeLessThan(spanB);
    expect(spanB).toBeLessThan(spanC);

    // Ensure they don't normalize to the same cube
    expect(spanC / spanA).toBeGreaterThan(2.0);
  });

  it("Requirement 2 & 4: Different thicknesses affect depth proportionally", () => {
    const thinWall = calculateWall3DGeometry({
      lengthFt: 15.0,
      heightFt: 9.0,
      thicknessIn: 4.0,
      categoryCode: "INTERIOR_PARTITION",
    });

    const thickWall = calculateWall3DGeometry({
      lengthFt: 15.0,
      heightFt: 9.0,
      thicknessIn: 8.4,
      categoryCode: "STRUCTURAL_BEARING",
    });

    expect(thinWall.valid).toBe(true);
    expect(thickWall.valid).toBe(true);

    const depthThin = Math.hypot(
      thinWall.vertices.backTopLeft.x - thinWall.vertices.frontTopLeft.x,
      thinWall.vertices.backTopLeft.y - thinWall.vertices.frontTopLeft.y
    );

    const depthThick = Math.hypot(
      thickWall.vertices.backTopLeft.x - thickWall.vertices.frontTopLeft.x,
      thickWall.vertices.backTopLeft.y - thickWall.vertices.frontTopLeft.y
    );

    // 8.4" wall depth must be visibly thicker than 4.0" wall depth
    expect(depthThick).toBeGreaterThan(depthThin);
    expect(thickWall.thicknessIn).toBe(8.4);
    expect(thinWall.thicknessIn).toBe(4.0);
  });

  it("Requirement 6: Canonical classifications produce their exact canonical colors", () => {
    for (const cat of CANONICAL_WALL_CATEGORIES) {
      const geo = calculateWall3DGeometry({
        lengthFt: 10.0,
        heightFt: 9.0,
        thicknessIn: 4.875,
        categoryCode: cat,
      });

      expect(geo.valid).toBe(true);
      expect(geo.categoryCode).toBe(cat);
      expect(geo.categoryColor).toBe(WALL_CATEGORY_COLORS[cat].color);
      expect(geo.categoryLabel).toBe(WALL_CATEGORY_COLORS[cat].label);
    }
  });

  it("Requirement 8: Missing dimensions never generate fake geometry", () => {
    // Missing length
    const noLength = calculateWall3DGeometry({
      lengthFt: 0,
      heightFt: 9.0,
      thicknessIn: 4.88,
    });
    expect(noLength.valid).toBe(false);
    expect(noLength.errorMessage).toBe("Geometry preview unavailable — source dimension missing");

    // Missing height
    const noHeight = calculateWall3DGeometry({
      lengthFt: 20.0,
      heightFt: 0,
      thicknessIn: 4.88,
    });
    expect(noHeight.valid).toBe(false);
    expect(noHeight.errorMessage).toBe("Geometry preview unavailable — source dimension missing");

    // Missing thickness
    const noThickness = calculateWall3DGeometry({
      lengthFt: 20.0,
      heightFt: 9.0,
      thicknessIn: 0,
    });
    expect(noThickness.valid).toBe(false);
    expect(noThickness.errorMessage).toBe("Geometry preview unavailable — source dimension missing");
  });

  it("Requirement 5: Horizontal and vertical orientations are preserved when source geometry points exist", () => {
    // Horizontal wall (dx > dy)
    const horizWall = calculateWall3DGeometry({
      lengthFt: 25.0,
      heightFt: 9.0,
      thicknessIn: 4.88,
      points: [
        { x: 0.1, y: 0.2 },
        { x: 0.8, y: 0.2 },
      ],
    });
    expect(horizWall.orientation).toBe("horizontal");
    expect(horizWall.orientationLabel).toContain("Horizontal");

    // Vertical wall (dy > dx)
    const vertWall = calculateWall3DGeometry({
      lengthFt: 25.0,
      heightFt: 9.0,
      thicknessIn: 4.88,
      points: [
        { x: 0.3, y: 0.1 },
        { x: 0.3, y: 0.9 },
      ],
    });
    expect(vertWall.orientation).toBe("vertical");
    expect(vertWall.orientationLabel).toContain("Vertical");
  });

  it("Requirement 7 & 4: Dimension labels and visual scale notice are formatted properly", () => {
    const geo = calculateWall3DGeometry({
      lengthFt: 32.0,
      heightFt: 9.0,
      thicknessIn: 8.4,
      categoryCode: "EXTERIOR_PERIMETER",
    });

    expect(geo.lengthDim.label).toBe("L 32.00 ft");
    expect(geo.heightDim.label).toBe("H 9.00 ft");
    expect(geo.thicknessDim.label).toBe("T 8.40 in");
    expect(geo.isVisualScaleApplied).toBe(true);
    expect(geo.visualScaleNotice).toBe("Visual scale applied — dimensions are not to scale");
  });

  it("Final Acceptance Test: Walls A, B, and C render distinct geometry", () => {
    const wallA = calculateWall3DGeometry({
      lengthFt: 3.0,
      heightFt: 9.0,
      thicknessIn: 4.88,
      categoryCode: "INTERIOR_PARTITION",
    });

    const wallB = calculateWall3DGeometry({
      lengthFt: 17.0,
      heightFt: 9.0,
      thicknessIn: 4.0,
      categoryCode: "CORRIDOR",
    });

    const wallC = calculateWall3DGeometry({
      lengthFt: 32.0,
      heightFt: 9.0,
      thicknessIn: 8.4,
      categoryCode: "EXTERIOR_PERIMETER",
    });

    // Verification of Wall A
    expect(wallA.lengthFt).toBe(3.0);
    expect(wallA.heightFt).toBe(9.0);
    expect(wallA.thicknessIn).toBe(4.88);
    expect(wallA.categoryColor).toBe(WALL_CATEGORY_COLORS.INTERIOR_PARTITION.color);

    // Verification of Wall B
    expect(wallB.lengthFt).toBe(17.0);
    expect(wallB.heightFt).toBe(9.0);
    expect(wallB.thicknessIn).toBe(4.0);
    expect(wallB.categoryColor).toBe(WALL_CATEGORY_COLORS.CORRIDOR.color);

    // Verification of Wall C
    expect(wallC.lengthFt).toBe(32.0);
    expect(wallC.heightFt).toBe(9.0);
    expect(wallC.thicknessIn).toBe(8.4);
    expect(wallC.categoryColor).toBe(WALL_CATEGORY_COLORS.EXTERIOR_PERIMETER.color);

    // Ensure all 3 SVG front faces have distinct vertex configurations
    expect(wallA.frontFacePoints).not.toEqual(wallB.frontFacePoints);
    expect(wallB.frontFacePoints).not.toEqual(wallC.frontFacePoints);
    expect(wallA.frontFacePoints).not.toEqual(wallC.frontFacePoints);
  });
});
