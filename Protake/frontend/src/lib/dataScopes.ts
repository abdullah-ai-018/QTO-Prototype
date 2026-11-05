/**
 * lib/dataScopes.ts
 *
 * Clear data scope definitions for production-grade construction estimating.
 * Every component must know which scope it is displaying and consuming.
 * 
 * CORE PRINCIPLE: UI = REAL DATA + REAL GEOMETRY + REAL CALCULATION + REAL PROVENANCE
 */

import type { Detection, Sheet, Measurement } from "@/types";
import type { TradeBreakdown } from "@/lib/estimating";
import type { SheetTakeoffResult } from "@/lib/sheetTakeoff";

// ═══════════════════════════════════════════════════════════════════════════════
// A. PROJECT SCOPE - Blueprint-wide aggregated data
// ═══════════════════════════════════════════════════════════════════════════════

export interface ProjectScope {
  projectId: number;
  blueprintId: number;
  totalSheets: number;
  takeoffEligibleSheets: number;
  
  // Aggregated detection counts across all sheets
  totalWalls: number;
  totalRooms: number;
  totalOpenings: number;
  totalFixtures: number;
  
  // Project-wide trade breakdowns (blueprint scope)
  tradeBreakdowns: Record<string, TradeBreakdown>;
  
  // Live QTO totals computed from backend — null until backend responds.
  // Never substitute hardcoded stale numbers here.
  liveQtoTotals: {
    sheets: number | null;
    wallNetHangAreaSf: number | null;
    ceilingAreaSf: number | null;
    laborHours: number | null;
    directCost: number | null;
    materialCost: number | null;
    laborCost: number | null;
  } | null;
  
  calculationStatus: "validated" | "needs_review" | "calculating" | "error";
  lastCalculated: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// B. SHEET SCOPE - Single sheet context and calculations
// ═══════════════════════════════════════════════════════════════════════════════

export interface SheetScope {
  // Sheet Identity
  sheetId: string;
  sheetCode: string; // A101, A102, etc.
  sheetTitle: string;
  sheetNumber: number;
  pageNumber: number;
  sourceFile: string;
  
  // Sheet Classification
  drawingType: string; // "floor_plan" | "roof_plan" | "elevation" | etc.
  discipline: string; // "architectural" | "structural" | "mep" | etc.
  takeoffEligible: boolean;
  eligibilityReason: string;
  
  // Sheet Geometry Context
  widthPx: number;
  heightPx: number;
  scale: number; // pixels per foot at 100% zoom
  scaleSource: "measured" | "assumed_default" | "calibrated";
  
  // Sheet Detection Counts
  wallCount: number;
  roomCount: number;
  openingCount: number;
  fixtureCount: number;
  
  // Sheet-specific takeoff calculations
  takeoffResult: SheetTakeoffResult;
  
  calculationStatus: "calculated" | "not_eligible" | "needs_review" | "error";
  calculationTimestamp: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// C. WALL SCOPE - Individual wall entity with complete provenance
// ═══════════════════════════════════════════════════════════════════════════════

export interface WallScope {
  // Wall Identity
  wallId: string;
  wallTag: string | null;
  sheetId: string;
  
  // Wall Classification
  category: string; // INTERIOR_PARTITION, EXTERIOR_PERIMETER, etc.
  classification: string | null;
  classificationSource: "ai_detected" | "schedule_reference" | "manual_override";
  confidence: number;
  
  // Wall Geometry
  startPoint: { x: number; y: number }; // normalized coordinates
  endPoint: { x: number; y: number };
  centerline: Array<{ x: number; y: number }>;
  polygon: Array<{ x: number; y: number }> | null;
  lengthFt: number;
  heightFt: number;
  heightSource: "measured" | "assumed" | "schedule";
  thicknessFt: number;
  thicknessSource: "measured" | "assumed" | "schedule";
  
  // Wall Assembly
  assemblyTag: string | null;
  assemblyDescription: string | null;
  assemblyVerified: boolean;
  studSize: string | null;
  gwbLayers: number;
  sidesToHang: number;
  
  // Wall Relationships
  leftRoom: string | null;
  rightRoom: string | null;
  adjacentSpaces: string[];
  openings: Array<{
    id: string;
    type: "door" | "window" | "opening";
    widthFt: number;
    heightFt: number;
    areaSqFt: number;
  }>;
  
  // Wall QTO Calculations
  grossAreaSqFt: number;
  openingDeductionSqFt: number;
  netHangAreaSqFt: number;
  qtoEligible: boolean;
  qtoBlockReason: string | null;
  requiredSheets: number;
  
  // Wall Status
  status: "pending" | "approved" | "rejected" | "needs_review";
  reviewReason: string | null;
  lastModified: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// D. ROOM SCOPE - Individual room entity with spatial context
// ═══════════════════════════════════════════════════════════════════════════════

export interface RoomScope {
  // Room Identity
  roomId: string;
  roomName: string;
  roomNumber: string | null;
  roomTag: string | null;
  sheetId: string;
  
  // Room Classification
  roomType: string | null; // "office" | "corridor" | "bathroom" | etc.
  occupancyType: string | null;
  finishType: string | null;
  
  // Room Geometry
  polygon: Array<{ x: number; y: number }>; // normalized coordinates
  centroid: { x: number; y: number };
  areaSqFt: number;
  perimeterFt: number;
  ceilingHeightFt: number;
  floorLevel: string | null;
  
  // Room Relationships
  adjacentWalls: string[];
  adjacentRooms: string[];
  containedFixtures: string[];
  
  // Room QTO Context
  floorFinish: string | null;
  wallFinish: string | null;
  ceilingFinish: string | null;
  contributes: {
    flooring: boolean;
    painting: boolean;
    ceiling: boolean;
  };
  
  // Room Status
  status: "pending" | "approved" | "rejected" | "needs_review";
  confidence: number;
  lastModified: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// E. OPENING SCOPE - Doors, windows, and other openings
// ═══════════════════════════════════════════════════════════════════════════════

export interface OpeningScope {
  // Opening Identity
  openingId: string;
  openingTag: string | null;
  sheetId: string;
  parentWallId: string;
  
  // Opening Type
  type: "door" | "window" | "pass_through" | "opening";
  subtype: string | null; // "entry_door" | "interior_door" | "casement_window" | etc.
  
  // Opening Geometry
  polygon: Array<{ x: number; y: number }>;
  widthFt: number;
  heightFt: number;
  areaSqFt: number;
  sillHeightFt: number | null;
  
  // Opening Properties
  material: string | null;
  manufacturer: string | null;
  model: string | null;
  fireRating: string | null;
  
  // Opening QTO Impact
  deductsFromWall: boolean;
  deductionAreaSqFt: number;
  installationCost: number | null;
  installationLabor: number | null;
  
  // Opening Status
  status: "pending" | "approved" | "rejected" | "needs_review";
  confidence: number;
  detectionSource: "ai_detected" | "schedule_reference" | "manual_added";
  lastModified: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// F. QTO LINE-ITEM SCOPE - Individual calculation line items
// ═══════════════════════════════════════════════════════════════════════════════

export interface QtoLineItemScope {
  // Line Item Identity
  lineItemId: string;
  description: string;
  category: string; // "material" | "labor" | "equipment"
  trade: string; // "drywall" | "painting" | etc.
  
  // Line Item Calculation
  quantity: number;
  unit: string;
  unitCost: number;
  extendedCost: number;
  wasteFactorPct: number;
  
  // Line Item Source Evidence
  sourceEntities: Array<{
    type: "wall" | "room" | "opening";
    id: string;
    contribution: number;
  }>;
  
  calculationFormula: string;
  calculationSteps: Array<{
    step: string;
    value: number;
    unit: string;
  }>;
  
  // Line Item Scope
  scope: "project" | "sheet" | "custom";
  sheetIds: string[]; // empty for project scope
  
  // Line Item Provenance
  calculatedAt: string;
  calculationEngine: string;
  validationStatus: "validated" | "needs_review" | "error";
  
  lastAudited: string | null;
  auditTrail: Array<{
    timestamp: string;
    action: string;
    oldValue: number | null;
    newValue: number;
    reason: string;
    user: string;
  }>;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SCOPE VALIDATION & UTILITIES
// ═══════════════════════════════════════════════════════════════════════════════

type ExpectedScope = "PROJECT" | "SHEET" | "WALL" | "ROOM" | "OPENING" | "QTO_LINE_ITEM";

// Identity fields that MUST be present on a well-formed scope object. Used
// to catch a component accidentally reading the wrong scope shape (e.g. a
// WALL-scope component that was handed a raw Detection or a SheetScope).
const REQUIRED_SCOPE_FIELDS: Record<ExpectedScope, string[]> = {
  PROJECT: ["projectId", "totalSheets", "validatedTotals"],
  SHEET: ["sheetId", "sheetCode", "takeoffEligible"],
  WALL: ["wallId", "sheetId", "category"],
  ROOM: ["roomId", "sheetId", "polygon"],
  OPENING: ["openingId", "sheetId", "parentWallId"],
  QTO_LINE_ITEM: ["lineItemId", "description", "scope"],
};

/**
 * Validates that a component is consuming data from the correct scope.
 *
 * `SHEET`/`WALL`/`ROOM`/`OPENING` scopes are legitimately `null` when
 * nothing is active/selected — that is not a violation. Any other value is
 * checked for the scope's required identity fields; a mismatch (e.g. a
 * WallScope handed to a component expecting RoomScope) means a component is
 * reading the wrong data shape and is logged so it can be fixed.
 */
export function validateDataScope(
  componentName: string,
  expectedScope: ExpectedScope,
  dataSource: unknown,
): boolean {
  if (dataSource === null || dataSource === undefined) return true;

  // QTO_LINE_ITEM scope is a list of line items, not a single object — an
  // empty list is a legitimate "no line items yet" state; a non-empty list
  // is checked via its first element below.
  if (Array.isArray(dataSource)) {
    if (expectedScope !== "QTO_LINE_ITEM") {
      console.warn(`[DataScope] ${componentName} expected ${expectedScope} scope data but got an array.`);
      return false;
    }
    if (dataSource.length === 0) return true;
    return validateDataScope(componentName, expectedScope, dataSource[0]);
  }

  if (typeof dataSource !== "object") {
    console.warn(`[DataScope] ${componentName} expected ${expectedScope} scope data but got a non-object value.`);
    return false;
  }

  const record = dataSource as Record<string, unknown>;
  const required = REQUIRED_SCOPE_FIELDS[expectedScope];
  const missing = required.filter((key) => record[key] === undefined);
  if (missing.length > 0) {
    console.warn(
      `[DataScope] ${componentName} expected ${expectedScope} scope data but is missing field(s): ${missing.join(", ")}. This usually means a component is reading a different scope than it declares.`,
    );
    return false;
  }
  return true;
}

/**
 * Creates a scoped data context for a component.
 */
export function createScopedContext<T>(
  scope: "PROJECT" | "SHEET" | "WALL" | "ROOM" | "OPENING" | "QTO_LINE_ITEM",
  data: T
): { scope: string; data: T; timestamp: string } {
  return {
    scope,
    data,
    timestamp: new Date().toISOString()
  };
}

/**
 * Filters detections to a specific sheet scope.
 */
export function filterToSheetScope(
  detections: Detection[], 
  sheetId: string
): Detection[] {
  return detections.filter(d => d.sheetId === sheetId);
}

/**
 * Filters detections to a specific wall scope.
 */
export function filterToWallScope(
  detections: Detection[], 
  sheetId: string
): Detection[] {
  return detections.filter(
    d => d.sheetId === sheetId && d.kind === "wall" && d.status !== "rejected"
  );
}

/**
 * Filters detections to a specific room scope.
 */
export function filterToRoomScope(
  detections: Detection[], 
  sheetId: string
): Detection[] {
  return detections.filter(
    d => d.sheetId === sheetId && d.kind === "room" && d.status !== "rejected"
  );
}

/**
 * Filters detections to openings scope.
 */
export function filterToOpeningScope(
  detections: Detection[], 
  sheetId: string
): Detection[] {
  return detections.filter(
    d => d.sheetId === sheetId && 
    (d.kind === "door" || d.kind === "window") && 
    d.status !== "rejected"
  );
}

/**
 * Creates a comprehensive scope summary for debugging/audit purposes.
 */
export function createScopeSummary(
  projectScope: ProjectScope,
  activeSheetScope: SheetScope | null,
  selectedWallScope: WallScope | null
): {
  project: { sheets: number; walls: number; cost: number };
  sheet: { code: string; walls: number; cost: number } | null;
  wall: { id: string; category: string; area: number } | null;
} {
  return {
    project: {
      sheets: projectScope.totalSheets,
      walls: projectScope.totalWalls,
      cost: projectScope.liveQtoTotals?.directCost ?? 0
    },
    sheet: activeSheetScope ? {
      code: activeSheetScope.sheetCode,
      walls: activeSheetScope.wallCount,
      cost: activeSheetScope.takeoffResult.directCost
    } : null,
    wall: selectedWallScope ? {
      id: selectedWallScope.wallId,
      category: selectedWallScope.category,
      area: selectedWallScope.netHangAreaSqFt
    } : null
  };
}