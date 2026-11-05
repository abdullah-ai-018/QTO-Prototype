/**
 * lib/sheetEligibilityEngine.ts
 *
 * Production-grade sheet eligibility engine that determines takeoff eligibility
 * based on comprehensive analysis of sheet content, classification, and evidence.
 * 
 * This engine goes beyond simple page type checking to analyze actual detected
 * content and provide detailed reasoning for eligibility decisions.
 */

import type { Sheet, Detection } from "@/types";
import type { DrawingDiscipline, DrawingType } from "@/lib/sheetContext";
import { getCanonicalWallCategory } from "@/lib/colors";

// ═══════════════════════════════════════════════════════════════════════════════
// ELIGIBILITY CLASSIFICATION TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export type EligibilityLevel = 
  | "fully_eligible"        // Complete takeoff capabilities for all trades
  | "walls_only"           // Wall takeoff only (no rooms/ceiling)
  | "ceiling_only"         // Ceiling takeoff only (RCP, etc.)
  | "reference_authority"   // Schedule/spec authority for other sheets
  | "dimensional_reference" // Elevation/section with dimensions
  | "not_eligible"         // No takeoff capabilities
  | "needs_classification"; // Requires manual review

export type EligibilityReason = 
  | "complete_floor_plan"              // Full architectural floor plan
  | "partial_floor_plan"               // Incomplete architectural plan
  | "wall_plan_only"                   // Partition/wall plan without rooms
  | "ceiling_plan"                     // Reflected ceiling plan
  | "roof_plan"                        // Roof plan for roofing takeoff
  | "elevation_with_dimensions"        // Elevation with takeoff dimensions
  | "section_with_dimensions"          // Section with takeoff dimensions
  | "assembly_schedule"                // Wall/door/window schedules
  | "finish_schedule"                  // Room finish schedules
  | "specification_sheet"              // Text specifications
  | "title_sheet"                      // Drawing index/title
  | "site_plan"                        // Civil/landscape
  | "detail_drawing"                   // Construction details
  | "structural_plan"                  // Structural drawings
  | "mep_plan"                         // MEP drawings
  | "empty_sheet"                      // Blank or minimal content
  | "unclassified_content";            // Unknown content type

export interface EligibilityEvidence {
  // Detection evidence
  wallCount: number;
  wallQuality: number;          // Average confidence 0-1
  roomCount: number;
  roomQuality: number;          // Average confidence 0-1
  openingCount: number;
  openingQuality: number;       // Average confidence 0-1
  
  // Wall classification evidence
  architecturalWalls: number;   // Interior + exterior walls
  structuralWalls: number;      // Structural/bearing walls
  mepWalls: number;            // Shaft/wet core walls
  unclassifiedWalls: number;    // Needs review walls
  
  // Spatial evidence
  hasEnclosedSpaces: boolean;   // Rooms with complete boundaries
  hasOpenSpaces: boolean;       // Partial room detection
  hasCeilingGrid: boolean;      // Ceiling grid patterns
  hasFloorPatterns: boolean;    // Floor tile/pattern detection
  
  // Schedule/text evidence
  hasScheduleTables: boolean;   // Detected schedule tables
  hasFinishCallouts: boolean;   // Room finish annotations
  hasDimensionStrings: boolean; // Dimension annotations
  hasAssemblyTags: boolean;     // Wall type tags/callouts
  
  // Drawing context evidence
  hasArchitecturalContext: boolean;  // Typical arch sheet layout
  hasStructuralContext: boolean;     // Structural notation
  hasMepContext: boolean;            // MEP symbols/equipment
  
  // Quality indicators
  overallDetectionQuality: number;   // Weighted average 0-1
  drawingComplexity: number;         // Content density/complexity 0-1
  scaleAppropriateness: number;      // Scale suitable for takeoff 0-1
}

export interface EligibilityAssessment {
  level: EligibilityLevel;
  reason: EligibilityReason;
  confidence: number;           // 0-1 confidence in assessment
  
  // Detailed breakdown
  evidence: EligibilityEvidence;
  tradeCapabilities: {
    drywall: boolean;
    painting: boolean;
    flooring: boolean;
    ceiling: boolean;
    roofing: boolean;
    openings: boolean;
  };
  
  // Reasoning
  primaryFactors: string[];     // Key factors supporting decision
  limitingFactors: string[];    // Factors preventing higher eligibility
  recommendations: string[];    // Suggested actions to improve eligibility
  
  // Metadata
  assessmentVersion: string;
  assessmentTimestamp: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// EVIDENCE COLLECTION ENGINE
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Analyzes detections to build comprehensive evidence for eligibility assessment.
 */
export function collectEligibilityEvidence(
  sheet: Sheet,
  detections: Detection[],
  discipline: DrawingDiscipline,
  drawingType: DrawingType,
  scale: number
): EligibilityEvidence {
  const sheetDetections = detections.filter(d => d.sheetId === sheet.id && d.status !== "rejected");
  
  // Wall analysis
  const walls = sheetDetections.filter(d => d.kind === "wall");
  const wallQuality = walls.length > 0 ? walls.reduce((sum, w) => sum + w.confidence, 0) / walls.length : 0;
  
  // Room analysis
  const rooms = sheetDetections.filter(d => d.kind === "room");
  const roomQuality = rooms.length > 0 ? rooms.reduce((sum, r) => sum + r.confidence, 0) / rooms.length : 0;
  
  // Opening analysis
  const openings = sheetDetections.filter(d => d.kind === "door" || d.kind === "window");
  const openingQuality = openings.length > 0 ? openings.reduce((sum, o) => sum + o.confidence, 0) / openings.length : 0;
  
  // Wall classification breakdown
  let architecturalWalls = 0;
  let structuralWalls = 0; 
  let mepWalls = 0;
  let unclassifiedWalls = 0;
  
  walls.forEach(wall => {
    const category = getCanonicalWallCategory(
      wall.wallTypeCode,
      wall.wallType,
      wall.wallTag,
      wall.status,
      wall.confidence,
      wall.classification
    );
    
    switch (category) {
      case "INTERIOR_PARTITION":
      case "EXTERIOR_PERIMETER":
      case "CORRIDOR":
      case "DEMISING":
        architecturalWalls++;
        break;
      case "STRUCTURAL_BEARING":
        structuralWalls++;
        break;
      case "WET_CORE":
      case "SHAFT":
        mepWalls++;
        break;
      case "NEEDS_REVIEW":
      default:
        unclassifiedWalls++;
        break;
    }
  });
  
  // Spatial analysis
  const hasEnclosedSpaces = rooms.some(room => 
    room.points.length >= 4 && room.areaSqFt > 50 // Substantial enclosed area
  );
  
  const hasOpenSpaces = rooms.some(room =>
    room.points.length >= 3 && room.areaSqFt > 20 && room.areaSqFt <= 50
  );
  
  // Content analysis based on sheet title and type
  const titleLower = sheet.name.toLowerCase();
  const hasCeilingGrid = titleLower.includes("ceiling") || titleLower.includes("rcp");
  const hasFloorPatterns = titleLower.includes("floor") || titleLower.includes("finish");
  
  // Schedule/annotation analysis (simplified - would use OCR in production)
  const hasScheduleTables = titleLower.includes("schedule") || titleLower.includes("finish");
  const hasFinishCallouts = titleLower.includes("finish") || titleLower.includes("material");
  const hasDimensionStrings = sheetDetections.some(d => d.kind === "annotation");
  const hasAssemblyTags = walls.some(w => w.assemblyTag || w.wallTag);
  
  // Drawing context analysis
  const hasArchitecturalContext = discipline === "architectural";
  const hasStructuralContext = discipline === "structural";
  const hasMepContext = discipline === "mechanical" || discipline === "electrical" || discipline === "plumbing";
  
  // Quality metrics
  const allDetections = sheetDetections.filter(d => 
    d.kind === "wall" || d.kind === "room" || d.kind === "door" || d.kind === "window"
  );
  const overallDetectionQuality = allDetections.length > 0 
    ? allDetections.reduce((sum, d) => sum + d.confidence, 0) / allDetections.length 
    : 0;
  
  // Drawing complexity (based on detection density)
  const drawingArea = (sheet.widthPx || 1000) * (sheet.heightPx || 1000);
  const detectionDensity = sheetDetections.length / (drawingArea / 1000000); // per million pixels
  const drawingComplexity = Math.min(detectionDensity / 10, 1); // Normalized 0-1
  
  // Scale appropriateness for takeoff
  const scaleAppropriateness = scale > 0 && scale < 1000 ? 1.0 : 0.3; // Reasonable scale range
  
  return {
    wallCount: walls.length,
    wallQuality,
    roomCount: rooms.length,
    roomQuality,
    openingCount: openings.length,
    openingQuality,
    
    architecturalWalls,
    structuralWalls,
    mepWalls,
    unclassifiedWalls,
    
    hasEnclosedSpaces,
    hasOpenSpaces,
    hasCeilingGrid,
    hasFloorPatterns,
    
    hasScheduleTables,
    hasFinishCallouts,
    hasDimensionStrings,
    hasAssemblyTags,
    
    hasArchitecturalContext,
    hasStructuralContext,
    hasMepContext,
    
    overallDetectionQuality,
    drawingComplexity,
    scaleAppropriateness,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// ELIGIBILITY ASSESSMENT ENGINE
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Performs comprehensive eligibility assessment based on collected evidence.
 */
export function assessSheetEligibility(
  sheet: Sheet,
  evidence: EligibilityEvidence,
  discipline: DrawingDiscipline,
  drawingType: DrawingType
): EligibilityAssessment {
  let level: EligibilityLevel = "not_eligible";
  let reason: EligibilityReason = "unclassified_content";
  let confidence = 0.0;
  let primaryFactors: string[] = [];
  let limitingFactors: string[] = [];
  let recommendations: string[] = [];
  
  // Trade capabilities (will be determined based on assessment)
  let tradeCapabilities = {
    drywall: false,
    painting: false,
    flooring: false,
    ceiling: false,
    roofing: false,
    openings: false,
  };
  
  // Backend explicit overrides (highest priority)
  if (sheet.isTakeoffEligible === false) {
    level = "not_eligible";
    reason = "specification_sheet"; // or other reason from backend
    confidence = 0.95;
    primaryFactors.push("Backend classification: not eligible");
    limitingFactors.push(sheet.skipReason || "Classified as non-takeoff sheet");
    
    return {
      level,
      reason,
      confidence,
      evidence,
      tradeCapabilities,
      primaryFactors,
      limitingFactors,
      recommendations: ["Manual review if classification seems incorrect"],
      assessmentVersion: "v1.0.0",
      assessmentTimestamp: new Date().toISOString(),
    };
  }
  
  // Architectural floor plans - highest eligibility potential
  if (discipline === "architectural" && drawingType === "floor_plan") {
    if (evidence.wallCount >= 5 && evidence.roomCount >= 3 && evidence.hasEnclosedSpaces) {
      level = "fully_eligible";
      reason = "complete_floor_plan";
      confidence = Math.min(0.95, 0.8 + (evidence.overallDetectionQuality * 0.15));
      
      primaryFactors.push(`${evidence.wallCount} walls detected with ${evidence.wallQuality.toFixed(2)} avg quality`);
      primaryFactors.push(`${evidence.roomCount} rooms detected with enclosed spaces`);
      primaryFactors.push(`${evidence.architecturalWalls} architectural walls for drywall takeoff`);
      
      // Enable relevant trades
      tradeCapabilities.drywall = evidence.architecturalWalls > 0;
      tradeCapabilities.painting = evidence.roomCount > 0 && evidence.wallCount > 0;
      tradeCapabilities.flooring = evidence.hasEnclosedSpaces;
      tradeCapabilities.openings = evidence.openingCount > 0;
      
      if (evidence.wallQuality < 0.7) {
        limitingFactors.push("Wall detection quality could be improved");
        recommendations.push("Review wall detections for accuracy");
      }
      
    } else if (evidence.wallCount >= 3) {
      level = "walls_only";
      reason = "partial_floor_plan";
      confidence = 0.75;
      
      primaryFactors.push(`${evidence.wallCount} walls detected`);
      if (evidence.roomCount === 0) {
        limitingFactors.push("No rooms detected - limits flooring takeoff");
      }
      
      tradeCapabilities.drywall = evidence.architecturalWalls > 0;
      tradeCapabilities.openings = evidence.openingCount > 0;
      
      recommendations.push("Verify room detection for full takeoff capabilities");
      
    } else if (evidence.wallCount > 0) {
      level = "walls_only";
      reason = "wall_plan_only";
      confidence = 0.6;
      
      primaryFactors.push(`${evidence.wallCount} walls detected`);
      limitingFactors.push("Insufficient wall count for comprehensive takeoff");
      
      tradeCapabilities.drywall = evidence.wallCount >= 2;
      
      recommendations.push("Review wall detection completeness");
    }
  }
  
  // Ceiling plans
  else if (drawingType === "ceiling_plan" || evidence.hasCeilingGrid) {
    level = "ceiling_only";
    reason = "ceiling_plan";
    confidence = 0.9;
    
    primaryFactors.push("Ceiling plan detected");
    if (evidence.roomCount > 0) {
      primaryFactors.push(`${evidence.roomCount} ceiling areas identified`);
    }
    
    tradeCapabilities.ceiling = true;
    
    if (evidence.roomCount === 0) {
      recommendations.push("Define ceiling areas for accurate takeoff");
    }
  }
  
  // Roof plans
  else if (drawingType === "roof_plan") {
    if (evidence.roomCount > 0) {
      level = "ceiling_only";
      reason = "roof_plan";
      confidence = 0.85;
      
      primaryFactors.push("Roof plan with defined areas");
      tradeCapabilities.roofing = true;
    } else {
      level = "reference_authority";
      reason = "roof_plan";
      confidence = 0.7;
      
      primaryFactors.push("Roof plan - reference only");
      recommendations.push("Define roof areas for roofing takeoff");
    }
  }
  
  // Schedule sheets
  else if (evidence.hasScheduleTables || drawingType === "schedule") {
    level = "reference_authority";
    reason = "assembly_schedule";
    confidence = 0.9;
    
    primaryFactors.push("Schedule authority for assembly/finish information");
    
    if (evidence.hasFinishCallouts) {
      primaryFactors.push("Contains finish specifications");
    }
  }
  
  // Elevations and sections with dimensions
  else if ((drawingType === "elevation" || drawingType === "section") && evidence.hasDimensionStrings) {
    level = "dimensional_reference";
    reason = drawingType === "elevation" ? "elevation_with_dimensions" : "section_with_dimensions";
    confidence = 0.8;
    
    primaryFactors.push("Contains dimensional information");
    recommendations.push("Use for verification of plan dimensions");
  }
  
  // Structural plans
  else if (discipline === "structural") {
    if (evidence.wallCount > 0) {
      level = "walls_only";
      reason = "structural_plan";
      confidence = 0.7;
      
      primaryFactors.push(`${evidence.structuralWalls} structural elements detected`);
      tradeCapabilities.drywall = evidence.structuralWalls > 0; // Structural walls may need drywall
      
      limitingFactors.push("Structural drawings - limited architectural takeoff");
    } else {
      level = "reference_authority";
      reason = "structural_plan";
      confidence = 0.8;
      
      primaryFactors.push("Structural reference information");
    }
  }
  
  // MEP plans
  else if (evidence.hasMepContext) {
    level = "reference_authority";
    reason = "mep_plan";
    confidence = 0.85;
    
    primaryFactors.push("MEP reference information");
    if (evidence.mepWalls > 0) {
      primaryFactors.push(`${evidence.mepWalls} MEP-related walls detected`);
    }
  }
  
  // Specifications and text sheets
  else if (drawingType === "specification" || drawingType === "title_sheet") {
    level = "reference_authority";
    reason = drawingType === "specification" ? "specification_sheet" : "title_sheet";
    confidence = 0.95;
    
    primaryFactors.push("Reference documentation");
  }
  
  // Empty or minimal content
  else if (evidence.wallCount === 0 && evidence.roomCount === 0 && evidence.openingCount === 0) {
    level = "not_eligible";
    reason = "empty_sheet";
    confidence = 0.9;
    
    limitingFactors.push("No takeoff-relevant content detected");
    recommendations.push("Verify sheet contains expected drawing content");
  }
  
  // Unknown content - needs classification
  else {
    level = "needs_classification";
    reason = "unclassified_content";
    confidence = 0.0;
    
    limitingFactors.push("Unable to classify sheet content automatically");
    recommendations.push("Manual classification required");
    
    if (evidence.wallCount > 0) {
      recommendations.push(`${evidence.wallCount} walls detected - may be eligible for wall takeoff`);
    }
    if (evidence.roomCount > 0) {
      recommendations.push(`${evidence.roomCount} spaces detected - may be eligible for area takeoff`);
    }
  }
  
  // Quality adjustments
  if (evidence.overallDetectionQuality < 0.5 && level !== "not_eligible") {
    confidence *= 0.8; // Reduce confidence for poor detection quality
    limitingFactors.push("Low detection quality affects confidence");
  }
  
  if (evidence.scaleAppropriateness < 0.5 && level !== "not_eligible") {
    confidence *= 0.9; // Reduce confidence for inappropriate scale
    limitingFactors.push("Scale may not be appropriate for accurate takeoff");
  }
  
  return {
    level,
    reason,
    confidence,
    evidence,
    tradeCapabilities,
    primaryFactors,
    limitingFactors,
    recommendations,
    assessmentVersion: "v1.0.0",
    assessmentTimestamp: new Date().toISOString(),
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN ELIGIBILITY ENGINE
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Main entry point for comprehensive sheet eligibility assessment.
 */
export function assessSheetEligibilityComprehensive(
  sheet: Sheet,
  detections: Detection[],
  discipline: DrawingDiscipline,
  drawingType: DrawingType,
  scale: number
): EligibilityAssessment {
  // Collect evidence
  const evidence = collectEligibilityEvidence(sheet, detections, discipline, drawingType, scale);
  
  // Perform assessment
  const assessment = assessSheetEligibility(sheet, evidence, discipline, drawingType);
  
  return assessment;
}

/**
 * Batch assessment for multiple sheets with performance optimization.
 */
export function assessMultipleSheets(
  sheets: Sheet[],
  allDetections: Detection[],
  contexts: Record<string, { discipline: DrawingDiscipline; drawingType: DrawingType; scale: number }>
): Record<string, EligibilityAssessment> {
  const assessments: Record<string, EligibilityAssessment> = {};
  
  sheets.forEach(sheet => {
    const context = contexts[sheet.id];
    if (context) {
      assessments[sheet.id] = assessSheetEligibilityComprehensive(
        sheet,
        allDetections,
        context.discipline,
        context.drawingType,
        context.scale
      );
    }
  });
  
  return assessments;
}

/**
 * Gets summary statistics for project eligibility assessment.
 */
export function getEligibilityProjectSummary(
  assessments: Record<string, EligibilityAssessment>
): {
  totalSheets: number;
  byLevel: Record<EligibilityLevel, number>;
  averageConfidence: number;
  needsReview: number;
  fullyEligible: number;
  tradeCapabilities: Record<string, number>;
} {
  const values = Object.values(assessments);
  
  const summary = {
    totalSheets: values.length,
    byLevel: {} as Record<EligibilityLevel, number>,
    averageConfidence: 0,
    needsReview: 0,
    fullyEligible: 0,
    tradeCapabilities: {
      drywall: 0,
      painting: 0,
      flooring: 0,
      ceiling: 0,
      roofing: 0,
      openings: 0,
    },
  };
  
  let totalConfidence = 0;
  
  values.forEach(assessment => {
    // Count by level
    summary.byLevel[assessment.level] = (summary.byLevel[assessment.level] || 0) + 1;
    
    // Accumulate confidence
    totalConfidence += assessment.confidence;
    
    // Count special cases
    if (assessment.level === "needs_classification") {
      summary.needsReview++;
    }
    if (assessment.level === "fully_eligible") {
      summary.fullyEligible++;
    }
    
    // Count trade capabilities
    (Object.entries(assessment.tradeCapabilities) as [keyof typeof summary.tradeCapabilities, boolean][]).forEach(([trade, capable]) => {
      if (capable) {
        summary.tradeCapabilities[trade]++;
      }
    });
  });
  
  summary.averageConfidence = values.length > 0 ? totalConfidence / values.length : 0;
  
  return summary;
}