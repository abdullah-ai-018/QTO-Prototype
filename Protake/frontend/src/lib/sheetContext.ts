/**
 * lib/sheetContext.ts
 *
 * Engineering-grade sheet context system that provides comprehensive metadata,
 * classification, and engineering context for every sheet in the project.
 * 
 * Every sheet must have complete engineering context including:
 * - Sheet identification and classification
 * - Drawing type and discipline 
 * - Scale and calibration status
 * - Takeoff eligibility and reasoning
 * - Detection counts and quality metrics
 * - Engineering validation status
 */

import type { Sheet, Detection } from "@/types";
import { isTakeoffEligible, getEligibilityReason } from "@/lib/sheetTakeoff";
import { getCanonicalWallCategory } from "@/lib/colors";

// ═══════════════════════════════════════════════════════════════════════════════
// SHEET CLASSIFICATION ENGINE
// ═══════════════════════════════════════════════════════════════════════════════

export type DrawingDiscipline = 
  | "architectural" 
  | "structural" 
  | "mechanical" 
  | "electrical" 
  | "plumbing" 
  | "fire_protection"
  | "landscape"
  | "civil"
  | "unknown";

export type DrawingType = 
  | "floor_plan"
  | "roof_plan" 
  | "ceiling_plan"
  | "elevation"
  | "section"
  | "detail"
  | "schedule"
  | "specification"
  | "title_sheet"
  | "site_plan"
  | "unknown";

export type ScaleStatus = 
  | "calibrated_measured"    // User measured scale on drawing
  | "calibrated_schedule"    // Scale from title block/schedule
  | "assumed_standard"       // Standard assumed scale (1/8" = 1'-0")
  | "assumed_default"        // System default fallback
  | "unknown"               // No scale information
  | "not_applicable";       // Non-scaled drawing (schedules, specs)

export type TakeoffEligibilityLevel = 
  | "fully_eligible"        // Full takeoff capabilities
  | "partial_eligible"      // Limited takeoff (ceiling only, etc.)
  | "reference_only"        // Reference for other sheets
  | "not_eligible"          // No takeoff capabilities
  | "unknown";             // Needs classification

// ═══════════════════════════════════════════════════════════════════════════════
// ENGINEERING SHEET CONTEXT
// ═══════════════════════════════════════════════════════════════════════════════

export interface EngineeringSheetContext {
  // SHEET IDENTITY
  sheetId: string;
  sheetCode: string;              // A101, S201, M301, etc.
  sheetTitle: string;             // "First Floor Plan", "Foundation Plan", etc.
  sheetNumber: number;            // Sequential number in set
  pageNumber: number;             // Page in PDF
  
  // SHEET SOURCE
  sourceFileName: string;
  sourcePageIndex: number;
  sourcePdfPage: number;
  
  // DRAWING CLASSIFICATION
  discipline: DrawingDiscipline;
  disciplineConfidence: number;   // 0-1 confidence in discipline classification
  drawingType: DrawingType;
  typeConfidence: number;         // 0-1 confidence in type classification
  // Backend page-classifier field (Page.geometry_authority): what this
  // sheet is the authoritative source for — PARTITION_WALLS | CEILING_GWB |
  // ROOF_SURFACES | DEMOLITION | CONTEXT_ONLY | NONE. "NONE" when the page
  // hasn't been classified yet, not a claim of no authority.
  geometryAuthority: string;
  
  // SHEET GEOMETRY & SCALE
  widthPx: number;
  heightPx: number;
  aspectRatio: number;
  scale: number;                  // Pixels per foot at 100% zoom
  scaleStatus: ScaleStatus;
  scaleConfidence: number;        // 0-1 confidence in scale accuracy
  
  // TAKEOFF ELIGIBILITY
  eligibilityLevel: TakeoffEligibilityLevel;
  eligibilityReason: string;
  eligibilityConfidence: number;  // 0-1 confidence in eligibility decision
  
  // DETECTION METRICS
  wallCount: number;
  wallQuality: number;            // 0-1 average wall detection confidence
  roomCount: number;
  roomQuality: number;            // 0-1 average room detection confidence
  openingCount: number;
  openingQuality: number;         // 0-1 average opening detection confidence
  
  // WALL CLASSIFICATION BREAKDOWN
  wallCategories: {
    [category: string]: {
      count: number;
      totalLengthFt: number;
      avgConfidence: number;
    };
  };
  
  // ENGINEERING VALIDATION
  engineeringStatus: "validated" | "needs_review" | "error" | "not_processed";
  validationReasons: string[];
  validationTimestamp: string | null;
  
  // SHEET RELATIONSHIPS
  referencedBySheets: string[];   // Other sheets that reference this one
  referencesToSheets: string[];   // Sheets this one references
  partOfDrawingSet: string[];     // Related sheets (floor plan series, etc.)
  
  // CALCULATION CONTEXT
  calculationEligible: boolean;
  lastCalculated: string | null;
  calculationWarnings: string[];
  calculationErrors: string[];
  
  // METADATA
  createdAt: string;
  lastModified: string;
  processingVersion: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SHEET CLASSIFICATION LOGIC
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Classifies drawing discipline from sheet code and title.
 */
/**
 * `backendDiscipline`/`backendConfidence` come from the backend's own page
 * classifier (Page.discipline / classification_confidence) when the page
 * has been through classification — a real analysis of title-block text
 * and drawing content, not a sheet-code/title string-match guess. Prefer
 * it whenever present; fall back to the local heuristic below only when
 * the backend hasn't classified this page (e.g. pre-classification data).
 */
export function classifyDiscipline(
  sheetCode: string,
  sheetTitle: string,
  backendDiscipline?: string | null,
  backendConfidence?: number | null,
): {
  discipline: DrawingDiscipline;
  confidence: number;
} {
  if (backendDiscipline) {
    const normalized = backendDiscipline.toLowerCase();
    const known: readonly string[] = [
      "architectural", "structural", "mechanical", "electrical", "plumbing", "civil", "landscape", "fire_protection",
    ];
    if (known.includes(normalized)) {
      return { discipline: normalized as DrawingDiscipline, confidence: backendConfidence ?? 0.95 };
    }
    // "General" and any other backend value we don't have a specific
    // DrawingDiscipline bucket for — fall through to the local heuristic
    // rather than silently mapping to the wrong discipline.
  }

  const code = sheetCode.toUpperCase();
  const title = sheetTitle.toLowerCase();
  
  // Architectural sheets (A series)
  if (code.startsWith('A') || title.includes('floor') || title.includes('plan') || title.includes('elevation')) {
    return { discipline: "architectural", confidence: 0.9 };
  }
  
  // Structural sheets (S series)
  if (code.startsWith('S') || title.includes('structural') || title.includes('foundation') || title.includes('framing')) {
    return { discipline: "structural", confidence: 0.9 };
  }
  
  // Mechanical sheets (M series)
  if (code.startsWith('M') || title.includes('hvac') || title.includes('mechanical') || title.includes('duct')) {
    return { discipline: "mechanical", confidence: 0.9 };
  }
  
  // Electrical sheets (E series)
  if (code.startsWith('E') || title.includes('electrical') || title.includes('power') || title.includes('lighting')) {
    return { discipline: "electrical", confidence: 0.9 };
  }
  
  // Plumbing sheets (P series)
  if (code.startsWith('P') || title.includes('plumbing') || title.includes('water') || title.includes('sewer')) {
    return { discipline: "plumbing", confidence: 0.9 };
  }
  
  // Fire protection (FP series)
  if (code.startsWith('FP') || title.includes('fire') || title.includes('sprinkler')) {
    return { discipline: "fire_protection", confidence: 0.9 };
  }
  
  // Civil/Site (C series)
  if (code.startsWith('C') || title.includes('site') || title.includes('civil') || title.includes('grading')) {
    return { discipline: "civil", confidence: 0.8 };
  }
  
  // Landscape (L series)
  if (code.startsWith('L') || title.includes('landscape') || title.includes('planting')) {
    return { discipline: "landscape", confidence: 0.8 };
  }
  
  return { discipline: "unknown", confidence: 0.0 };
}

/**
 * Classifies drawing type from sheet title and detected content.
 */
export function classifyDrawingType(
  sheetTitle: string, 
  detections: Detection[]
): {
  drawingType: DrawingType;
  confidence: number;
} {
  const title = sheetTitle.toLowerCase();
  
  // Floor plans
  if (title.includes('floor') || title.includes('plan') && !title.includes('roof') && !title.includes('ceiling')) {
    const hasRooms = detections.some(d => d.kind === "room");
    const hasWalls = detections.some(d => d.kind === "wall");
    const confidence = (hasRooms && hasWalls) ? 0.95 : 0.7;
    return { drawingType: "floor_plan", confidence };
  }
  
  // Roof plans
  if (title.includes('roof')) {
    return { drawingType: "roof_plan", confidence: 0.9 };
  }
  
  // Ceiling plans (RCP - Reflected Ceiling Plan)
  if (title.includes('ceiling') || title.includes('rcp') || title.includes('reflected')) {
    return { drawingType: "ceiling_plan", confidence: 0.9 };
  }
  
  // Elevations
  if (title.includes('elevation')) {
    return { drawingType: "elevation", confidence: 0.9 };
  }
  
  // Sections
  if (title.includes('section') || title.includes('sect')) {
    return { drawingType: "section", confidence: 0.9 };
  }
  
  // Details
  if (title.includes('detail') || title.includes('det')) {
    return { drawingType: "detail", confidence: 0.8 };
  }
  
  // Schedules
  if (title.includes('schedule') || title.includes('finish') || title.includes('door') || title.includes('window')) {
    return { drawingType: "schedule", confidence: 0.9 };
  }
  
  // Specifications
  if (title.includes('spec') || title.includes('note') || title.includes('general')) {
    return { drawingType: "specification", confidence: 0.8 };
  }
  
  // Title sheets
  if (title.includes('title') || title.includes('cover') || title.includes('index')) {
    return { drawingType: "title_sheet", confidence: 0.9 };
  }
  
  // Site plans
  if (title.includes('site') || title.includes('plot') || title.includes('survey')) {
    return { drawingType: "site_plan", confidence: 0.8 };
  }
  
  return { drawingType: "unknown", confidence: 0.0 };
}

/**
 * Determines scale status and confidence.
 */
export function classifyScaleStatus(
  scale: number,
  scaleSource: string | null | undefined,
  sheetTitle: string
): {
  scaleStatus: ScaleStatus;
  confidence: number;
} {
  const title = sheetTitle.toLowerCase();
  
  // Non-scaled drawings
  if (title.includes('schedule') || title.includes('spec') || title.includes('note') || title.includes('title')) {
    return { scaleStatus: "not_applicable", confidence: 1.0 };
  }
  
  // User measured
  if (scaleSource === "measured" || scaleSource === "calibrated") {
    return { scaleStatus: "calibrated_measured", confidence: 0.95 };
  }
  
  // Title block extracted
  if (scaleSource === "title_block" || scaleSource === "schedule_reference") {
    return { scaleStatus: "calibrated_schedule", confidence: 0.85 };
  }
  
  // Standard architectural scales
  const pixelsPerFoot = scale;
  const commonScales = [
    { scale: 1/96, name: "1/8\" = 1'-0\"" },   // Most common
    { scale: 1/48, name: "1/4\" = 1'-0\"" },
    { scale: 1/192, name: "1/16\" = 1'-0\"" },
    { scale: 1/24, name: "1/2\" = 1'-0\"" },
  ];
  
  for (const commonScale of commonScales) {
    const expectedPixels = commonScale.scale * 96; // Assuming 96 DPI
    if (Math.abs(pixelsPerFoot - expectedPixels) < expectedPixels * 0.1) {
      return { scaleStatus: "assumed_standard", confidence: 0.7 };
    }
  }
  
  if (scale > 0) {
    return { scaleStatus: "assumed_default", confidence: 0.4 };
  }
  
  return { scaleStatus: "unknown", confidence: 0.0 };
}

/**
 * Determines takeoff eligibility level and confidence.
 */
export function classifyTakeoffEligibility(
  sheet: Sheet,
  detections: Detection[],
  discipline: DrawingDiscipline,
  drawingType: DrawingType
): {
  eligibilityLevel: TakeoffEligibilityLevel;
  confidence: number;
  reason: string;
} {
  // Use existing eligibility logic as base
  const basicEligible = isTakeoffEligible(sheet);
  const basicReason = getEligibilityReason(sheet);
  
  if (!basicEligible) {
    return {
      eligibilityLevel: "not_eligible",
      confidence: 0.9,
      reason: basicReason
    };
  }
  
  // Architectural floor plans with wall evidence
  if (discipline === "architectural" && drawingType === "floor_plan") {
    const walls = detections.filter(d => d.kind === "wall" && d.status !== "rejected");
    const rooms = detections.filter(d => d.kind === "room" && d.status !== "rejected");
    
    if (walls.length > 0 && rooms.length > 0) {
      return {
        eligibilityLevel: "fully_eligible",
        confidence: 0.95,
        reason: `${walls.length} walls and ${rooms.length} rooms detected`
      };
    }
    
    if (walls.length > 0) {
      return {
        eligibilityLevel: "partial_eligible", 
        confidence: 0.8,
        reason: `${walls.length} walls detected, no rooms`
      };
    }
  }
  
  // Ceiling plans for ceiling takeoff
  if (drawingType === "ceiling_plan") {
    const rooms = detections.filter(d => d.kind === "room" && d.status !== "rejected");
    if (rooms.length > 0) {
      return {
        eligibilityLevel: "partial_eligible",
        confidence: 0.85,
        reason: `Ceiling takeoff eligible - ${rooms.length} ceiling areas`
      };
    }
  }
  
  // Reference sheets (elevations, sections, details)
  if (drawingType === "elevation" || drawingType === "section" || drawingType === "detail") {
    return {
      eligibilityLevel: "reference_only",
      confidence: 0.9,
      reason: "Reference drawing - no direct takeoff"
    };
  }
  
  // Schedules provide assembly/finish information
  if (drawingType === "schedule") {
    return {
      eligibilityLevel: "reference_only", 
      confidence: 0.9,
      reason: "Schedule authority - assembly/finish reference"
    };
  }
  
  return {
    eligibilityLevel: "unknown",
    confidence: 0.0,
    reason: "Needs manual classification"
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// SHEET CONTEXT BUILDER
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Builds complete engineering context for a sheet.
 */
export function buildSheetContext(
  sheet: Sheet,
  detections: Detection[],
  calibration: Record<string, number>,
  sourceFileName?: string | null,
): EngineeringSheetContext {
  const sheetDetections = detections.filter(d => d.sheetId === sheet.id);
  const walls = sheetDetections.filter(d => d.kind === "wall" && d.status !== "rejected");
  const rooms = sheetDetections.filter(d => d.kind === "room" && d.status !== "rejected");
  const openings = sheetDetections.filter(d => (d.kind === "door" || d.kind === "window") && d.status !== "rejected");
  
  // Classify discipline and type
  const disciplineResult = classifyDiscipline(sheet.code, sheet.name, sheet.discipline, sheet.classificationConfidence);
  const typeResult = classifyDrawingType(sheet.name, sheetDetections);
  
  // Scale analysis
  const scale = calibration[sheet.id] || 0;
  const scaleResult = classifyScaleStatus(scale, sheet.scale_source, sheet.name);
  
  // Takeoff eligibility
  const eligibilityResult = classifyTakeoffEligibility(
    sheet, 
    sheetDetections, 
    disciplineResult.discipline, 
    typeResult.drawingType
  );
  
  // Wall classification breakdown
  const wallCategories: { [category: string]: { count: number; totalLengthFt: number; avgConfidence: number } } = {};
  
  walls.forEach(wall => {
    const category = getCanonicalWallCategory(
      wall.wallTypeCode,
      wall.wallType,
      wall.wallTag,
      wall.status,
      wall.confidence,
      wall.classification
    );
    
    if (!wallCategories[category]) {
      wallCategories[category] = { count: 0, totalLengthFt: 0, avgConfidence: 0 };
    }
    
    wallCategories[category].count++;
    wallCategories[category].totalLengthFt += wall.perimeterFt || 0;
    wallCategories[category].avgConfidence += wall.confidence;
  });
  
  // Calculate average confidences
  Object.keys(wallCategories).forEach(category => {
    wallCategories[category].avgConfidence /= wallCategories[category].count;
  });
  
  // Engineering validation
  const validationReasons: string[] = [];
  let engineeringStatus: "validated" | "needs_review" | "error" | "not_processed" = "validated";
  
  if (eligibilityResult.eligibilityLevel === "unknown") {
    validationReasons.push("Sheet eligibility needs manual classification");
    engineeringStatus = "needs_review";
  }
  
  if (scaleResult.scaleStatus === "unknown" && typeResult.drawingType !== "schedule") {
    validationReasons.push("Scale calibration required");
    engineeringStatus = "needs_review";
  }
  
  if (disciplineResult.confidence < 0.7) {
    validationReasons.push("Discipline classification uncertain");
    engineeringStatus = "needs_review";
  }
  
  return {
    // Sheet Identity
    sheetId: sheet.id,
    sheetCode: sheet.code,
    sheetTitle: sheet.name,
    sheetNumber: sheet.pageNumber || sheet.pageIndex + 1,
    pageNumber: sheet.pageIndex + 1,
    
    // Sheet Source
    sourceFileName: sourceFileName || "Not available from source",
    sourcePageIndex: sheet.pageIndex,
    sourcePdfPage: sheet.pageIndex + 1,

    // Drawing Classification
    discipline: disciplineResult.discipline,
    disciplineConfidence: disciplineResult.confidence,
    drawingType: typeResult.drawingType,
    typeConfidence: typeResult.confidence,
    geometryAuthority: sheet.geometryAuthority || "NONE",
    
    // Sheet Geometry & Scale
    widthPx: sheet.widthPx || 0,
    heightPx: sheet.heightPx || 0,
    aspectRatio: (sheet.widthPx && sheet.heightPx) ? sheet.widthPx / sheet.heightPx : 1.0,
    scale,
    scaleStatus: scaleResult.scaleStatus,
    scaleConfidence: scaleResult.confidence,
    
    // Takeoff Eligibility
    eligibilityLevel: eligibilityResult.eligibilityLevel,
    eligibilityReason: eligibilityResult.reason,
    eligibilityConfidence: eligibilityResult.confidence,
    
    // Detection Metrics
    wallCount: walls.length,
    wallQuality: walls.length > 0 ? walls.reduce((sum, w) => sum + w.confidence, 0) / walls.length : 0,
    roomCount: rooms.length,
    roomQuality: rooms.length > 0 ? rooms.reduce((sum, r) => sum + r.confidence, 0) / rooms.length : 0,
    openingCount: openings.length,
    openingQuality: openings.length > 0 ? openings.reduce((sum, o) => sum + o.confidence, 0) / openings.length : 0,
    
    // Wall Classification Breakdown
    wallCategories,
    
    // Engineering Validation
    engineeringStatus,
    validationReasons,
    validationTimestamp: new Date().toISOString(),
    
    // Sheet Relationships (TODO: Implement cross-sheet analysis)
    referencedBySheets: [],
    referencesToSheets: [],
    partOfDrawingSet: [],
    
    // Calculation Context
    calculationEligible: eligibilityResult.eligibilityLevel === "fully_eligible" || eligibilityResult.eligibilityLevel === "partial_eligible",
    lastCalculated: new Date().toISOString(),
    calculationWarnings: [],
    calculationErrors: [],
    
    // Metadata
    createdAt: new Date().toISOString(),
    lastModified: new Date().toISOString(),
    processingVersion: "v1.0.0",
  };
}

/**
 * Builds engineering context for all sheets in a project.
 */
export function buildAllSheetContexts(
  sheets: Sheet[],
  detections: Detection[],
  calibration: Record<string, number>,
  sourceFileName?: string | null,
): Record<string, EngineeringSheetContext> {
  const contexts: Record<string, EngineeringSheetContext> = {};

  sheets.forEach(sheet => {
    contexts[sheet.id] = buildSheetContext(sheet, detections, calibration, sourceFileName);
  });
  
  return contexts;
}

/**
 * Gets a summary of sheet contexts for project overview.
 */
export function getSheetContextSummary(
  contexts: Record<string, EngineeringSheetContext>
): {
  totalSheets: number;
  byDiscipline: Record<DrawingDiscipline, number>;
  byType: Record<DrawingType, number>;
  byEligibility: Record<TakeoffEligibilityLevel, number>;
  needsReview: number;
  fullyCalibrated: number;
} {
  const summary = {
    totalSheets: Object.keys(contexts).length,
    byDiscipline: {} as Record<DrawingDiscipline, number>,
    byType: {} as Record<DrawingType, number>,
    byEligibility: {} as Record<TakeoffEligibilityLevel, number>,
    needsReview: 0,
    fullyCalibrated: 0,
  };
  
  Object.values(contexts).forEach(context => {
    // Count by discipline
    summary.byDiscipline[context.discipline] = (summary.byDiscipline[context.discipline] || 0) + 1;
    
    // Count by type
    summary.byType[context.drawingType] = (summary.byType[context.drawingType] || 0) + 1;
    
    // Count by eligibility
    summary.byEligibility[context.eligibilityLevel] = (summary.byEligibility[context.eligibilityLevel] || 0) + 1;
    
    // Count needing review
    if (context.engineeringStatus === "needs_review") {
      summary.needsReview++;
    }
    
    // Count fully calibrated
    if (context.scaleStatus === "calibrated_measured" || context.scaleStatus === "calibrated_schedule") {
      summary.fullyCalibrated++;
    }
  });
  
  return summary;
}