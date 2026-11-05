/**
 * state/DataScopeContext.tsx
 *
 * React context provider that enforces clear data scope boundaries.
 * Every component consuming this context must declare which scope it operates on.
 */

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useApp } from "./AppContext";
import type { 
  ProjectScope, 
  SheetScope, 
  WallScope, 
  RoomScope, 
  OpeningScope,
  QtoLineItemScope
} from "@/lib/dataScopes";
import { 
  filterToSheetScope, 
  filterToWallScope, 
  filterToRoomScope, 
  filterToOpeningScope,
  validateDataScope
} from "@/lib/dataScopes";
import { getCanonicalWallCategory } from "@/lib/colors";
import { classifyDiscipline } from "@/lib/sheetContext";
import { centroid, boundingBoxDimensionsFt, DEFAULT_SCALE } from "@/lib/geometry";
import { findBorderingRooms, findBorderingWalls, findAdjacentRooms, findContainedFixtures, findParentWall } from "@/lib/spatialRelationships";
import { WASTE_FACTOR } from "@/lib/estimating";

interface DataScopeContextValue {
  // A. PROJECT SCOPE
  projectScope: ProjectScope;
  
  // B. SHEET SCOPE (active sheet)
  sheetScope: SheetScope | null;
  
  // C. WALL SCOPE (selected wall)
  wallScope: WallScope | null;
  
  // D. ROOM SCOPE (selected room)
  roomScope: RoomScope | null;
  
  // E. OPENING SCOPE (selected opening)
  openingScope: OpeningScope | null;
  
  // F. QTO LINE-ITEM SCOPE (active line items)
  qtoLineItemScope: QtoLineItemScope[];
  
  // Scope utilities
  validateScope: (componentName: string, scope: string) => boolean;
  getScopedData: <T>(scope: string, fallback: T) => T;
}

const DataScopeContext = createContext<DataScopeContextValue | null>(null);

export function DataScopeProvider({ children }: { children: ReactNode }) {
  const { state, breakdowns, sheetTakeoff } = useApp();
  
  // A. PROJECT SCOPE - Blueprint-wide data
  const projectScope = useMemo<ProjectScope>(() => {
    const allDetections = state.detections.filter(d => d.status !== "rejected");
    
    return {
      projectId: state.projectId || 0,
      blueprintId: state.blueprintId || 0,
      totalSheets: state.sheets.length,
      takeoffEligibleSheets: state.sheets.filter(s => s.isTakeoffEligible !== false).length,
      
      totalWalls: allDetections.filter(d => d.kind === "wall").length,
      totalRooms: allDetections.filter(d => d.kind === "room").length,
      totalOpenings: allDetections.filter(d => d.kind === "door" || d.kind === "window").length,
      totalFixtures: allDetections.filter(d => d.kind === "fixture").length,
      
      tradeBreakdowns: breakdowns,
      
      liveQtoTotals: (() => {
        const dw = breakdowns["drywall"];
        if (!dw) return null;
        const liMap = Object.fromEntries(dw.lineItems.map((li) => [li.label, li.qty]));
        const wallNet = (liMap["Net Wall Drywall Subtotal"] as number | undefined) ?? null;
        const ceiling = (liMap["Ceiling Drywall Subtotal"] as number | undefined) ?? null;
        const directCost = dw.metrics.directCost;
        // Same 81.1/18.9 split used in computeSheetTakeoff for local fallback
        const materialCost = directCost != null ? Math.round(directCost * 0.811) : null;
        const laborCost = directCost != null ? Math.max(0, directCost - (materialCost ?? 0)) : null;
        return {
          sheets: dw.metrics.materialQuantity ?? null,
          wallNetHangAreaSf: wallNet,
          ceilingAreaSf: ceiling,
          laborHours: dw.metrics.laborHours ?? null,
          directCost: directCost ?? null,
          materialCost,
          laborCost,
        };
      })(),

      calculationStatus: "validated",
      lastCalculated: new Date().toISOString(),
    };
  }, [state.sheets, state.detections, state.projectId, state.blueprintId, breakdowns]);
  
  // B. SHEET SCOPE - Active sheet context
  const sheetScope = useMemo<SheetScope | null>(() => {
    const activeSheet = state.sheets.find(s => s.id === state.activeSheetId);
    if (!activeSheet) return null;
    
    const sheetDetections = filterToSheetScope(state.detections, activeSheet.id);
    const sheetWalls = filterToWallScope(state.detections, activeSheet.id);
    const sheetRooms = filterToRoomScope(state.detections, activeSheet.id);
    const sheetOpenings = filterToOpeningScope(state.detections, activeSheet.id);
    
    return {
      sheetId: activeSheet.id,
      sheetCode: activeSheet.code,
      sheetTitle: activeSheet.name,
      sheetNumber: activeSheet.pageNumber || activeSheet.pageIndex + 1,
      pageNumber: activeSheet.pageIndex + 1,
      sourceFile: "Not available from source",

      drawingType: activeSheet.pageType || "unknown",
      discipline: classifyDiscipline(activeSheet.code, activeSheet.name, activeSheet.discipline, activeSheet.classificationConfidence).discipline,
      takeoffEligible: sheetTakeoff.eligible,
      eligibilityReason: sheetTakeoff.eligibilityReason,
      
      widthPx: activeSheet.widthPx || 0,
      heightPx: activeSheet.heightPx || 0,
      scale: state.calibration[activeSheet.id] || 0,
      scaleSource: activeSheet.scale_source === "measured" ? "measured" : "assumed_default",
      
      wallCount: sheetWalls.length,
      roomCount: sheetRooms.length,
      openingCount: sheetOpenings.length,
      fixtureCount: sheetDetections.filter(d => d.kind === "fixture").length,
      
      takeoffResult: sheetTakeoff,
      
      calculationStatus: sheetTakeoff.eligible ? "calculated" : "not_eligible",
      calculationTimestamp: new Date().toISOString(),
    };
  }, [state.activeSheetId, state.sheets, state.detections, state.calibration, sheetTakeoff]);
  
  // C. WALL SCOPE - Selected wall context
  const wallScope = useMemo<WallScope | null>(() => {
    if (!state.selectedDetectionId) return null;
    
    const selectedDetection = state.detections.find(d => d.id === state.selectedDetectionId);
    if (!selectedDetection || selectedDetection.kind !== "wall") return null;

    const wallScale = state.calibration[selectedDetection.sheetId] || DEFAULT_SCALE;
    const wallOpenings = state.detections.filter(
      d => (d.kind === "door" || d.kind === "window") &&
      d.sheetId === selectedDetection.sheetId &&
      d.status !== "rejected"
    ).map(opening => {
      // Real bounding-box dimensions from the opening's own detected
      // polygon and the sheet's calibrated scale — not an area-based guess.
      const { widthFt, heightFt } = boundingBoxDimensionsFt(opening.points, wallScale);
      return {
        id: opening.id,
        type: opening.kind as "door" | "window" | "opening",
        widthFt,
        heightFt,
        areaSqFt: opening.areaSqFt,
      };
    });

    const category = getCanonicalWallCategory(
      selectedDetection.wallTypeCode,
      selectedDetection.wallType,
      selectedDetection.wallTag,
      selectedDetection.status,
      selectedDetection.confidence,
      selectedDetection.classification
    );

    // Real bordering-room geometry test (wall midpoint vs room polygons) —
    // shared with lib/wallInspectorModel.ts so both surfaces agree.
    const borderingRooms = findBorderingRooms(selectedDetection, state.detections);

    return {
      wallId: selectedDetection.id,
      wallTag: selectedDetection.wallTag || null,
      sheetId: selectedDetection.sheetId,
      
      category,
      classification: selectedDetection.classification || null,
      classificationSource: "ai_detected",
      confidence: selectedDetection.confidence,
      
      startPoint: selectedDetection.points[0] || { x: 0, y: 0 },
      endPoint: selectedDetection.points[selectedDetection.points.length - 1] || { x: 0, y: 0 },
      centerline: selectedDetection.points,
      polygon: selectedDetection.wallPolygon || null,
      lengthFt: selectedDetection.perimeterFt || 0,
      heightFt: selectedDetection.heightFt || 9,
      heightSource: selectedDetection.heightProvenance === "VERIFIED" ? "measured" : "assumed",
      thicknessFt: selectedDetection.thicknessFt || (4.875 / 12),
      thicknessSource: selectedDetection.thicknessMeasured ? "measured" : "assumed",
      
      assemblyTag: selectedDetection.assemblyTag || null,
      assemblyDescription: selectedDetection.assemblyDescription || null,
      assemblyVerified: selectedDetection.assemblyVerified || false,
      studSize: null, // TODO: Extract from assembly
      gwbLayers: selectedDetection.layersSideA || 1,
      sidesToHang: selectedDetection.sidesToHang || (selectedDetection.wallType === "interior" ? 2 : 1),
      
      leftRoom: borderingRooms[0]?.name || null,
      rightRoom: borderingRooms[1]?.name || null,
      adjacentSpaces: borderingRooms.map(r => r.name),
      openings: wallOpenings,

      grossAreaSqFt: selectedDetection.grossSf || 0,
      openingDeductionSqFt: selectedDetection.openingDeductionSf || 0,
      netHangAreaSqFt: selectedDetection.netSf || 0,
      qtoEligible: selectedDetection.qtoEligible || false,
      qtoBlockReason: selectedDetection.qtoBlockReason || null,
      requiredSheets: Math.ceil(((selectedDetection.netSf || 0) * WASTE_FACTOR) / 32),
      
      status: selectedDetection.status,
      reviewReason: selectedDetection.rejectionReason || null,
      lastModified: new Date().toISOString(),
    };
  }, [state.selectedDetectionId, state.detections, state.calibration]);

  // D. ROOM SCOPE - Selected room context
  const roomScope = useMemo<RoomScope | null>(() => {
    if (!state.selectedDetectionId) return null;

    const selectedDetection = state.detections.find(d => d.id === state.selectedDetectionId);
    if (!selectedDetection || selectedDetection.kind !== "room") return null;

    // Real spatial-adjacency tests — shared with WallScope and
    // lib/wallInspectorModel.ts (single source of truth, see
    // lib/spatialRelationships.ts).
    const adjacentWalls = findBorderingWalls(selectedDetection, state.detections);
    const adjacentRooms = findAdjacentRooms(selectedDetection, state.detections);
    const containedFixtures = findContainedFixtures(selectedDetection, state.detections);

    return {
      roomId: selectedDetection.id,
      roomName: selectedDetection.name,
      roomNumber: null, // Not available from source — no room-numbering data is detected/extracted today
      roomTag: null, // Not available from source
      sheetId: selectedDetection.sheetId,

      roomType: selectedDetection.roomType || null,
      occupancyType: null, // Not available from source
      finishType: null, // Not available from source — requires finish schedule parsing

      polygon: selectedDetection.points,
      centroid: centroid(selectedDetection.points),
      areaSqFt: selectedDetection.areaSqFt,
      perimeterFt: selectedDetection.perimeterFt,
      ceilingHeightFt: state.drywallSettings.wallHeightFt,
      floorLevel: null, // Not available from source

      adjacentWalls: adjacentWalls.map(w => w.id),
      adjacentRooms: adjacentRooms.map(r => r.id),
      containedFixtures: containedFixtures.map(f => f.id),

      floorFinish: null, // Not available from source — requires finish schedule parsing
      wallFinish: null, // Not available from source — requires finish schedule parsing
      ceilingFinish: null, // Not available from source — requires finish schedule parsing
      contributes: {
        flooring: true,
        painting: true,
        ceiling: true,
      },

      status: selectedDetection.status,
      confidence: selectedDetection.confidence,
      lastModified: new Date().toISOString(),
    };
  }, [state.selectedDetectionId, state.detections, state.drywallSettings]);

  // E. OPENING SCOPE - Selected opening context
  const openingScope = useMemo<OpeningScope | null>(() => {
    if (!state.selectedDetectionId) return null;

    const selectedDetection = state.detections.find(d => d.id === state.selectedDetectionId);
    if (!selectedDetection || (selectedDetection.kind !== "door" && selectedDetection.kind !== "window")) return null;

    const openingScale = state.calibration[selectedDetection.sheetId] || DEFAULT_SCALE;
    const { widthFt, heightFt } = boundingBoxDimensionsFt(selectedDetection.points, openingScale);
    const parentWall = findParentWall(selectedDetection, state.detections);

    return {
      openingId: selectedDetection.id,
      openingTag: null, // Not available from source
      sheetId: selectedDetection.sheetId,
      parentWallId: parentWall?.id ?? "",

      type: selectedDetection.kind as "door" | "window",
      subtype: null, // Not available from source — requires schedule/classification data

      polygon: selectedDetection.points,
      widthFt,
      heightFt,
      areaSqFt: selectedDetection.areaSqFt,
      sillHeightFt: selectedDetection.kind === "window" ? 3 : 0, // Assumed default (industry-standard sill height); no per-opening sill data is detected
      
      material: null, // TODO: Extract from schedules
      manufacturer: null, // TODO: Extract from schedules
      model: null, // TODO: Extract from schedules
      fireRating: null, // TODO: Extract from schedules
      
      deductsFromWall: true,
      deductionAreaSqFt: selectedDetection.areaSqFt,
      installationCost: null, // TODO: Calculate from cost database
      installationLabor: null, // TODO: Calculate from labor rates
      
      status: selectedDetection.status,
      confidence: selectedDetection.confidence,
      detectionSource: selectedDetection.evidence?.source === "manual_entry" ? "manual_added" : "ai_detected",
      lastModified: new Date().toISOString(),
    };
  }, [state.selectedDetectionId, state.detections, state.calibration]);

  // F. QTO LINE-ITEM SCOPE - Active line items
  const qtoLineItemScope = useMemo<QtoLineItemScope[]>(() => {
    return sheetTakeoff.topLineItems.map((item, index) => ({
      lineItemId: `${sheetScope?.sheetId || 'unknown'}-line-${index}`,
      description: item.item,
      category: "material",
      trade: "drywall",
      
      quantity: parseFloat(item.qty.replace(/,/g, '')) || 0,
      unit: item.unit,
      unitCost: parseFloat(item.unitCost.replace(/[$,]/g, '')) || 0,
      extendedCost: parseFloat(item.total.replace(/[$,]/g, '')) || 0,
      wasteFactorPct: Math.round((WASTE_FACTOR - 1) * 100), // sourced from the frozen DrywallEngine's WASTE_FACTOR
      
      sourceEntities: [], // TODO: Link to actual source walls/rooms
      calculationFormula: `${item.qty} ${item.unit} × ${item.unitCost} = ${item.total}`,
      calculationSteps: [
        { step: "Base quantity", value: parseFloat(item.qty.replace(/,/g, '')) || 0, unit: item.unit },
        { step: "Unit cost", value: parseFloat(item.unitCost.replace(/[$,]/g, '')) || 0, unit: "USD" },
        { step: "Extended cost", value: parseFloat(item.total.replace(/[$,]/g, '')) || 0, unit: "USD" },
      ],
      
      scope: sheetScope ? "sheet" : "project",
      sheetIds: sheetScope ? [sheetScope.sheetId] : [],
      
      calculatedAt: new Date().toISOString(),
      calculationEngine: "frontend-engine-v1",
      validationStatus: "validated",
      
      lastAudited: null,
      auditTrail: [],
    }));
  }, [sheetTakeoff.topLineItems, sheetScope]);
  
  // Scope validation utilities — pass the real scope object so
  // validateDataScope can actually check its shape/id-chain, instead of
  // always validating a null placeholder.
  const scopeByName: Record<string, unknown> = {
    PROJECT: projectScope,
    SHEET: sheetScope,
    WALL: wallScope,
    ROOM: roomScope,
    OPENING: openingScope,
    QTO_LINE_ITEM: qtoLineItemScope,
  };

  const validateScope = (componentName: string, scope: string): boolean => {
    return validateDataScope(componentName, scope as any, scopeByName[scope] ?? null);
  };

  const getScopedData = <T,>(scope: string, fallback: T): T => {
    const data = scopeByName[scope];
    return (data as T | undefined) ?? fallback;
  };
  
  const value = useMemo(() => ({
    projectScope,
    sheetScope,
    wallScope,
    roomScope,
    openingScope,
    qtoLineItemScope,
    validateScope,
    getScopedData,
  }), [
    projectScope,
    sheetScope,
    wallScope,
    roomScope,
    openingScope,
    qtoLineItemScope,
    validateScope,
    getScopedData,
  ]);
  
  return (
    <DataScopeContext.Provider value={value}>
      {children}
    </DataScopeContext.Provider>
  );
}

export function useDataScope() {
  const context = useContext(DataScopeContext);
  if (!context) {
    throw new Error("useDataScope must be used within DataScopeProvider");
  }
  return context;
}

// Typed hooks for specific scopes
export function useProjectScope() {
  const { projectScope, validateScope } = useDataScope();
  validateScope("ProjectScope", "PROJECT");
  return projectScope;
}

export function useSheetScope() {
  const { sheetScope, validateScope } = useDataScope();
  validateScope("SheetScope", "SHEET");
  return sheetScope;
}

export function useWallScope() {
  const { wallScope, validateScope } = useDataScope();
  validateScope("WallScope", "WALL");
  return wallScope;
}

export function useRoomScope() {
  const { roomScope, validateScope } = useDataScope();
  validateScope("RoomScope", "ROOM");
  return roomScope;
}

export function useOpeningScope() {
  const { openingScope, validateScope } = useDataScope();
  validateScope("OpeningScope", "OPENING");
  return openingScope;
}

export function useQtoLineItemScope() {
  const { qtoLineItemScope, validateScope } = useDataScope();
  validateScope("QtoLineItemScope", "QTO_LINE_ITEM");
  return qtoLineItemScope;
}