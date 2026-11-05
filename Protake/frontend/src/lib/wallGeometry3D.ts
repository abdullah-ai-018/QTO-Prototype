import type { Point } from "@/types";
import { WALL_CATEGORY_COLORS, CanonicalWallCategory, getCanonicalWallCategory } from "@/lib/colors";

export interface WallGeometry3DParams {
  lengthFt?: number | null;
  heightFt?: number | null;
  thicknessIn?: number | null;
  thicknessFt?: number | null;
  points?: Point[] | null;
  categoryCode?: CanonicalWallCategory | null;
  wallType?: "interior" | "exterior" | null;
  wallTypeCode?: string | null;
  wallTag?: string | null;
  status?: string | null;
  confidence?: number | null;
  classification?: string | null;
}

export interface Point2D {
  x: number;
  y: number;
}

export interface DimensionLine {
  start: Point2D;
  end: Point2D;
  tickStart1: Point2D;
  tickStart2: Point2D;
  tickEnd1: Point2D;
  tickEnd2: Point2D;
  textPos: Point2D;
  label: string;
}

export interface WallGeometry3DResult {
  valid: boolean;
  errorMessage?: string;

  // Real physical dimensions
  lengthFt: number;
  heightFt: number;
  thicknessIn: number;
  thicknessFt: number;

  // Classification & Appearance
  categoryCode: CanonicalWallCategory;
  categoryColor: string;
  categoryLabel: string;

  // Orientation
  orientation: "horizontal" | "vertical" | "angled";
  orientationLabel: string;
  angleDeg: number;

  // Visual Scale Flag
  isVisualScaleApplied: boolean;
  visualScaleNotice: string;

  // 2D Projected Vertices for SVG rendering
  viewBox: { width: number; height: number };
  frontFacePoints: string;
  topFacePoints: string;
  sideFacePoints: string;
  outlinePoints: string;

  // Coordinates for dimension leaders
  lengthDim: DimensionLine;
  heightDim: DimensionLine;
  thicknessDim: DimensionLine;

  // Face coordinate arrays for testing / custom canvas
  vertices: {
    frontBottomLeft: Point2D;
    frontBottomRight: Point2D;
    frontTopRight: Point2D;
    frontTopLeft: Point2D;
    backTopLeft: Point2D;
    backTopRight: Point2D;
    backBottomRight: Point2D;
  };
}

/**
 * Calculates data-driven 3D isometric wall geometry from real wall dimensions.
 * Strictly adheres to QTO data without fabricating missing dimensions.
 */
export function calculateWall3DGeometry(
  params: WallGeometry3DParams,
  svgWidth = 300,
  svgHeight = 180
): WallGeometry3DResult {
  // 1. Resolve Classification & Color
  const categoryCode: CanonicalWallCategory =
    params.categoryCode ||
    getCanonicalWallCategory(
      params.wallTypeCode,
      params.wallType,
      params.wallTag,
      params.status as any,
      params.confidence,
      params.classification
    );

  const catConfig = WALL_CATEGORY_COLORS[categoryCode] ?? WALL_CATEGORY_COLORS.NEEDS_REVIEW;
  const categoryColor = catConfig.color;
  const categoryLabel = catConfig.label;

  // 2. Validate Dimensions strictly (Do NOT invent fake geometry)
  const lengthFt = params.lengthFt != null && !isNaN(params.lengthFt) ? Number(params.lengthFt) : 0;
  const heightFt = params.heightFt != null && !isNaN(params.heightFt) ? Number(params.heightFt) : 0;

  let thicknessIn = 0;
  if (params.thicknessIn != null && !isNaN(params.thicknessIn) && params.thicknessIn > 0) {
    thicknessIn = Number(params.thicknessIn);
  } else if (params.thicknessFt != null && !isNaN(params.thicknessFt) && params.thicknessFt > 0) {
    thicknessIn = Number(params.thicknessFt) * 12;
  }

  const thicknessFt = thicknessIn / 12;

  // If any critical dimension is missing or <= 0, return invalid result
  if (lengthFt <= 0 || heightFt <= 0 || thicknessIn <= 0) {
    return {
      valid: false,
      errorMessage: "Geometry preview unavailable — source dimension missing",
      lengthFt,
      heightFt,
      thicknessIn,
      thicknessFt,
      categoryCode,
      categoryColor,
      categoryLabel,
      orientation: "horizontal",
      orientationLabel: "Unknown",
      angleDeg: 0,
      isVisualScaleApplied: false,
      visualScaleNotice: "",
      viewBox: { width: svgWidth, height: svgHeight },
      frontFacePoints: "",
      topFacePoints: "",
      sideFacePoints: "",
      outlinePoints: "",
      lengthDim: createEmptyDim(),
      heightDim: createEmptyDim(),
      thicknessDim: createEmptyDim(),
      vertices: {
        frontBottomLeft: { x: 0, y: 0 },
        frontBottomRight: { x: 0, y: 0 },
        frontTopRight: { x: 0, y: 0 },
        frontTopLeft: { x: 0, y: 0 },
        backTopLeft: { x: 0, y: 0 },
        backTopRight: { x: 0, y: 0 },
        backBottomRight: { x: 0, y: 0 },
      },
    };
  }

  // 3. Compute Orientation from source geometry points
  let orientation: "horizontal" | "vertical" | "angled" = "horizontal";
  let angleDeg = 0;
  let orientationLabel = "Horizontal (0.0°)";

  if (params.points && params.points.length >= 2) {
    const p0 = params.points[0];
    const p1 = params.points[1];
    const dx = p1.x - p0.x;
    const dy = p1.y - p0.y;
    const rad = Math.atan2(dy, dx);
    angleDeg = Math.round(((rad * 180) / Math.PI) * 10) / 10;

    const absDx = Math.abs(dx);
    const absDy = Math.abs(dy);

    if (absDy > absDx * 1.5) {
      orientation = "vertical";
      orientationLabel = `Vertical (${Math.abs(angleDeg).toFixed(1)}°)`;
    } else if (absDx > absDy * 1.5) {
      orientation = "horizontal";
      orientationLabel = `Horizontal (${Math.abs(angleDeg).toFixed(1)}°)`;
    } else {
      orientation = "angled";
      orientationLabel = `Angled (${Math.abs(angleDeg).toFixed(1)}°)`;
    }
  }

  // 4. Calculate 3D Dimensions & Visual Scale
  // In real life, wall thickness (4" - 8.4") is 1-3% of a 32ft wall length.
  // We apply a sensible visual scale so thin walls remain clearly legible
  // while preserving true proportional differences (e.g. 8.4" is visibly >2x thicker than 4.0").
  const isVisualScaleApplied = true;
  const visualScaleNotice = "Visual scale applied — dimensions are not to scale";

  // Drawing canvas bounding box
  const padLeft = 46;
  const padRight = 36;
  const padTop = 32;
  const padBottom = 38;

  const availW = svgWidth - padLeft - padRight;
  const availH = svgHeight - padTop - padBottom;

  // Visual depth calculation proportional to thickness (inches)
  // 4 in -> ~18px, 8.4 in -> ~30px, 12 in -> ~40px
  const visualDepth = Math.max(12, Math.min(46, 8 + (thicknessIn / 12) * 32));

  // Isometric angle projection constants
  const isoAngleL = orientation === "vertical" ? 0.60 : 0.32; // angle radians for length
  const cosL = Math.cos(isoAngleL);
  const sinL = Math.sin(isoAngleL);

  const cosD = Math.cos(0.55); // ~31.5 deg depth angle
  const sinD = Math.sin(0.55);

  const depthDx = visualDepth * cosD;
  const depthDy = -visualDepth * sinD;

  // Scale length and height to fit availW and availH proportionally
  const maxSpanX = availW - depthDx;
  const maxSpanY = availH - visualDepth * sinD;

  // Proportional scaling for L and H
  const scaleL = maxSpanX / (lengthFt * cosL);
  const scaleH = maxSpanY / heightFt;
  const uniformScale = Math.min(scaleL, scaleH, 14.0); // clamp max scale for very short walls

  // Minimum length and height to prevent subpixel collapse
  const drawLength = Math.max(28, lengthFt * uniformScale);
  const drawHeight = Math.max(24, heightFt * uniformScale);

  const lengthDx = drawLength * cosL;
  const lengthDy = drawLength * sinL;

  // Center model in SVG
  const totalModelW = lengthDx + depthDx;
  const totalModelH = drawHeight + Math.abs(depthDy) + lengthDy;

  const originX = padLeft + Math.max(0, (availW - totalModelW) / 2);
  const originY = padTop + Math.max(0, (availH - totalModelH) / 2) + drawHeight + Math.abs(depthDy);

  // Vertices calculation
  const pFrontBottomLeft: Point2D = { x: originX, y: originY };
  const pFrontBottomRight: Point2D = { x: originX + lengthDx, y: originY + lengthDy };
  const pFrontTopRight: Point2D = { x: originX + lengthDx, y: originY + lengthDy - drawHeight };
  const pFrontTopLeft: Point2D = { x: originX, y: originY - drawHeight };

  const pBackTopLeft: Point2D = { x: originX + depthDx, y: originY - drawHeight + depthDy };
  const pBackTopRight: Point2D = { x: originX + lengthDx + depthDx, y: originY + lengthDy - drawHeight + depthDy };
  const pBackBottomRight: Point2D = { x: originX + lengthDx + depthDx, y: originY + lengthDy + depthDy };

  // SVG Polygon Points Strings
  const frontFacePoints = `${pFrontBottomLeft.x},${pFrontBottomLeft.y} ${pFrontBottomRight.x},${pFrontBottomRight.y} ${pFrontTopRight.x},${pFrontTopRight.y} ${pFrontTopLeft.x},${pFrontTopLeft.y}`;
  const topFacePoints = `${pFrontTopLeft.x},${pFrontTopLeft.y} ${pFrontTopRight.x},${pFrontTopRight.y} ${pBackTopRight.x},${pBackTopRight.y} ${pBackTopLeft.x},${pBackTopLeft.y}`;
  const sideFacePoints = `${pFrontBottomRight.x},${pFrontBottomRight.y} ${pBackBottomRight.x},${pBackBottomRight.y} ${pBackTopRight.x},${pBackTopRight.y} ${pFrontTopRight.x},${pFrontTopRight.y}`;
  const outlinePoints = `${pFrontBottomLeft.x},${pFrontBottomLeft.y} ${pFrontBottomRight.x},${pFrontBottomRight.y} ${pBackBottomRight.x},${pBackBottomRight.y} ${pBackTopRight.x},${pBackTopRight.y} ${pBackTopLeft.x},${pBackTopLeft.y} ${pFrontTopLeft.x},${pFrontTopLeft.y}`;

  // 5. Engineering Dimension Callouts
  // Length Dimension (along bottom-front edge)
  const lengthOffset = 18;
  const lenStart: Point2D = { x: pFrontBottomLeft.x, y: pFrontBottomLeft.y + lengthOffset };
  const lenEnd: Point2D = { x: pFrontBottomRight.x, y: pFrontBottomRight.y + lengthOffset };
  const lengthDim: DimensionLine = {
    start: lenStart,
    end: lenEnd,
    tickStart1: { x: lenStart.x, y: lenStart.y - 4 },
    tickStart2: { x: lenStart.x, y: lenStart.y + 4 },
    tickEnd1: { x: lenEnd.x, y: lenEnd.y - 4 },
    tickEnd2: { x: lenEnd.x, y: lenEnd.y + 4 },
    textPos: { x: (lenStart.x + lenEnd.x) / 2, y: (lenStart.y + lenEnd.y) / 2 + 12 },
    label: `L ${lengthFt.toFixed(2)} ft`,
  };

  // Height Dimension (along vertical front-left edge)
  const heightOffset = 18;
  const hStart: Point2D = { x: pFrontBottomLeft.x - heightOffset, y: pFrontBottomLeft.y };
  const hEnd: Point2D = { x: pFrontTopLeft.x - heightOffset, y: pFrontTopLeft.y };
  const heightDim: DimensionLine = {
    start: hStart,
    end: hEnd,
    tickStart1: { x: hStart.x - 4, y: hStart.y },
    tickStart2: { x: hStart.x + 4, y: hStart.y },
    tickEnd1: { x: hEnd.x - 4, y: hEnd.y },
    tickEnd2: { x: hEnd.x + 4, y: hEnd.y },
    textPos: { x: hStart.x - 6, y: (hStart.y + hEnd.y) / 2 + 4 },
    label: `H ${heightFt.toFixed(2)} ft`,
  };

  // Thickness Dimension (along top-left depth edge)
  const thickOffset = 14;
  const tStart: Point2D = { x: pFrontTopLeft.x - thickOffset * sinD, y: pFrontTopLeft.y - thickOffset * cosD };
  const tEnd: Point2D = { x: pBackTopLeft.x - thickOffset * sinD, y: pBackTopLeft.y - thickOffset * cosD };
  const thicknessDim: DimensionLine = {
    start: tStart,
    end: tEnd,
    tickStart1: { x: tStart.x - 3, y: tStart.y + 3 },
    tickStart2: { x: tStart.x + 3, y: tStart.y - 3 },
    tickEnd1: { x: tEnd.x - 3, y: tEnd.y + 3 },
    tickEnd2: { x: tEnd.x + 3, y: tEnd.y - 3 },
    textPos: { x: (tStart.x + tEnd.x) / 2 - 4, y: (tStart.y + tEnd.y) / 2 - 8 },
    label: `T ${thicknessIn.toFixed(2)} in`,
  };

  return {
    valid: true,
    lengthFt,
    heightFt,
    thicknessIn,
    thicknessFt,
    categoryCode,
    categoryColor,
    categoryLabel,
    orientation,
    orientationLabel,
    angleDeg,
    isVisualScaleApplied,
    visualScaleNotice,
    viewBox: { width: svgWidth, height: svgHeight },
    frontFacePoints,
    topFacePoints,
    sideFacePoints,
    outlinePoints,
    lengthDim,
    heightDim,
    thicknessDim,
    vertices: {
      frontBottomLeft: pFrontBottomLeft,
      frontBottomRight: pFrontBottomRight,
      frontTopRight: pFrontTopRight,
      frontTopLeft: pFrontTopLeft,
      backTopLeft: pBackTopLeft,
      backTopRight: pBackTopRight,
      backBottomRight: pBackBottomRight,
    },
  };
}

function createEmptyDim(): DimensionLine {
  return {
    start: { x: 0, y: 0 },
    end: { x: 0, y: 0 },
    tickStart1: { x: 0, y: 0 },
    tickStart2: { x: 0, y: 0 },
    tickEnd1: { x: 0, y: 0 },
    tickEnd2: { x: 0, y: 0 },
    textPos: { x: 0, y: 0 },
    label: "",
  };
}
