import type { Detection, Sheet } from "@/types";
import { WALL_CATEGORY_COLORS, getCanonicalWallCategory, CanonicalWallCategory } from "@/lib/colors";
import type { AppState } from "@/state/AppContext";
import { findBorderingRooms } from "@/lib/spatialRelationships";
import { WASTE_FACTOR } from "@/lib/estimating";

export interface FieldProvenanceEntry {
  value: string | number;
  sourceSheet?: string | null;
  sourceDetail?: string | null;
  method: string;
  confidence: number;
}

export interface WallConflict {
  field: string;
  sources: Array<{ value: string | number; source: string; method: string }>;
  status: string;
}

export interface WallInspectionData {
  // Identification
  wallId: string;
  displayCode: string;
  wallTag: string | null;
  wallTagDisplay: string;
  categoryCode: CanonicalWallCategory;
  categoryColor: string;
  categoryLabel: string;

  // Provenance / Drawing
  sheetCode: string;
  pageNumber: number | string;
  drawingTitle: string;
  source: string;
  confidencePct: number;
  status: "approved" | "rejected" | "pending";
  statusLabel: string;

  // Geometry
  lengthFt: number;
  heightFt: number;
  heightProvenance: string;
  // VERIFIED = derived from this wall's own real source (ceiling spec,
  // elevation callout, resolved section detail, RCP match). ASSUMED = the
  // pipeline's project-wide default/inferred fallback, not this wall's own
  // measured or schedule-verified data. Never fabricated as VERIFIED.
  heightVerificationState: "VERIFIED" | "ASSUMED";
  thicknessIn: number;
  thicknessSource: string;
  thicknessVerificationState: "VERIFIED" | "ASSUMED";
  wallFaceAreaSf: number;
  volumeCf: number;

  // Assembly
  assemblyTag: string;
  assemblyVerified: boolean;
  assemblyDescription: string;
  scheduleSheet: string;

  // Detail/Section Callout Reference — e.g. a wall tagged "3/A401" on its
  // floor plan, resolved (or honestly flagged unresolved) against the
  // drawing set's actual wall-sections/details sheets. Null when the wall
  // has no detail callout nearby (the common case).
  detailReference: string | null;
  detailReferenceStatus: "RESOLVED_WITH_HEIGHT" | "RESOLVED_NO_HEIGHT_DATA" | "REFERENCE_UNRESOLVED" | "CONFLICT" | null;

  // Granular assembly fields — sourced from evidence.card.assembly_definition,
  // the full resolved WallAssemblySpec already serialized server-side.
  // "Not available from source" (via null) whenever not explicitly resolved.
  studDepthIn: number | null;
  studGauge: string | null;
  boardTypeSideA: string | null;
  boardTypeSideB: string | null;
  fireRatingHr: number | null;
  soundRatingStc: number | null;
  insulation: string | null;

    // Field-level provenance (value + source sheet/detail + extraction
  // method + confidence, per engineering input) and any detected
  // schedule-vs-detail conflicts — both set by the backend's detail-
  // reference resolver, never fabricated when absent.
  fieldProvenance: Record<string, FieldProvenanceEntry>;
  conflicts: WallConflict[];
  // "AW-142", "3/A401", "A801" style reference chips a user can click to
  // jump straight to the sheet that resolves it — the id here is the
  // frontend Sheet.id (from state.sheets), null when the reference exists
  // but no matching sheet was found in the currently loaded drawing set.
  scheduleSheetRefSheetId: string | null;
  detailReferenceSheetId: string | null;

  // Spatial Relationships
  leftRoom: string;
  rightRoom: string;
  adjacentRooms: Array<{ id: string; name: string; area?: number }>;
  adjacentSpacesCount: number;
  openingsCount: number;
  openingDeductionSf: number;
  columnRelationship: string;

  // QTO & Calculation Audit
  qtoEligible: boolean;
  qtoReason: string;
  sidesToHang: number;
  layersSideA: number;
  layersSideB: number;
  totalLayers: number;
  grossHangAreaSf: number;
  netHangAreaSf: number;
  sheetCoverageSf: number;
  wasteFactorPct: number;
  requiredSheets: number;
  calculationFormula: string;
  openingsSummary: string;
}

// Raw backend provenance enum values (app/models/architectural_wall.py)
// that mean "derived from this wall's own real source" — everything else
// (project_default / inferred / absent) is the pipeline's fallback, so it
// is ASSUMED, never shown as VERIFIED.
const VERIFIED_HEIGHT_SOURCES = new Set(["room_ceiling_spec", "elevation_callout", "section_detail", "rcp_match"]);
const VERIFIED_THICKNESS_SOURCES = new Set(["paired_geometry", "wall_schedule", "dimension_string", "drawing_callout"]);

function findSheetIdByCode(sheets: Sheet[], code: string | null | undefined): string | null {
  if (!code) return null;
  const normalized = code.trim().toUpperCase().replace(/[\s-]/g, "");
  if (!normalized) return null;
  const match = sheets.find((s) => (s.code || "").trim().toUpperCase().replace(/[\s-]/g, "") === normalized);
  return match?.id ?? null;
}

/**
 * Builds canonical, wall-specific engineering inspection data from a Detection.
 * Guarantees 100% data parity between Canvas Popup and Right Inspector Panel.
 */
export function buildWallInspectionData(d: Detection, state: AppState): WallInspectionData {
  const categoryCode = getCanonicalWallCategory(
    d.wallTypeCode,
    d.wallType,
    d.wallTag,
    d.status,
    d.confidence,
    d.classification
  );
  const catConfig = WALL_CATEGORY_COLORS[categoryCode] ?? WALL_CATEGORY_COLORS.NEEDS_REVIEW;

  const activeSheet = state.sheets.find((s: Sheet) => s.id === (d.sheetId || state.activeSheetId));

  // Clean Wall ID
  const cleanId = d.id.replace(/^backend-(archwall|wall)-/, "").replace(/^drywall-wall-/, "AW-");
  const displayCode = cleanId.startsWith("AW-") || cleanId.startsWith("W-") ? cleanId : `AW-${cleanId}`;

  const wallTag = d.wallTag && d.wallTag !== "DEFAULT" ? d.wallTag : null;
  const wallTagDisplay = wallTag ? `[${wallTag}]` : "Not available from source";

  // Dimensions
  const lengthFt = Math.round((d.perimeterFt || 0) * 100) / 100;
  const heightFt = Math.round((d.heightFt || 9.0) * 100) / 100;
  const heightProvenance = d.heightProvenance || "ASSUMED";
  const heightVerificationState: "VERIFIED" | "ASSUMED" =
    d.heightProvenance && VERIFIED_HEIGHT_SOURCES.has(d.heightProvenance) ? "VERIFIED" : "ASSUMED";
  const thicknessIn = Math.round((d.thicknessIn || (d.thicknessFt ? d.thicknessFt * 12 : 4.875)) * 100) / 100;
  const thicknessSource = d.thicknessMeasured
    ? "Paired geometry"
    : d.thicknessSource
    ? d.thicknessSource.replace(/_/g, " ")
    : "Project default";
  const thicknessVerificationState: "VERIFIED" | "ASSUMED" =
    d.thicknessMeasured || (d.thicknessSource != null && VERIFIED_THICKNESS_SOURCES.has(d.thicknessSource))
      ? "VERIFIED"
      : "ASSUMED";

  const wallFaceAreaSf = Math.round(lengthFt * heightFt * 100) / 100;
  const volumeCf = Math.round(lengthFt * heightFt * (thicknessIn / 12) * 100) / 100;

  // Assembly
  const hasRealAssembly = !!(d.assemblyTag && d.assemblyTag !== "DEFAULT");
  const assemblyTag = hasRealAssembly ? d.assemblyTag! : "Unclassified Assembly";
  const assemblyVerified = d.assemblyVerified ?? false;
  const assemblyDescription = d.assemblyDescription && d.assemblyDescription !== "DEFAULT"
    ? d.assemblyDescription
    : hasRealAssembly
    ? `Assembly ${d.assemblyTag}`
    : "Construction assembly not verified from drawing schedule.";
  const scheduleSheet = (d.evidence?.schedule_reference as string | undefined) || "";

  // Detail/section callout ("3/A401") resolution — set server-side by
  // DrywallSemanticWallPipeline._resolve_detail_references. Absent entirely
  // when the wall has no callout nearby (the common case), not defaulted.
  const detailReference = (d.evidence?.detail_reference as string | undefined) ?? null;
  const detailReferenceStatus =
    (d.evidence?.detail_reference_status as WallInspectionData["detailReferenceStatus"]) ?? null;

  // Granular assembly spec — the backend already serializes the FULL
  // resolved WallAssemblySpec (stud/GWB/layers/fire/acoustic/insulation)
  // into evidence.card.assembly_definition; only assemblyTag/Description
  // were ever read from it before. Every field stays null ("Not available
  // from source" in the UI) when the assembly wasn't resolved that
  // specifically — never inferred.
  const assemblyDefinition = d.evidence?.card?.assembly_definition as Record<string, unknown> | undefined;
  const studDepthIn = typeof assemblyDefinition?.stud_depth_in === "number" ? assemblyDefinition.stud_depth_in : null;
  const studGauge = typeof assemblyDefinition?.stud_gauge === "string" ? assemblyDefinition.stud_gauge : null;
  const boardTypeSideA = typeof assemblyDefinition?.board_type_side_a === "string" ? assemblyDefinition.board_type_side_a : null;
  const boardTypeSideB = typeof assemblyDefinition?.board_type_side_b === "string" ? assemblyDefinition.board_type_side_b : null;
  const fireRatingHr = typeof assemblyDefinition?.fire_rating_hr === "number" ? assemblyDefinition.fire_rating_hr : null;
  const soundRatingStc = typeof assemblyDefinition?.sound_rating_stc === "number" ? assemblyDefinition.sound_rating_stc : null;
  const insulation = typeof assemblyDefinition?.insulation === "string" ? assemblyDefinition.insulation : null;

  // Field-level provenance + any schedule-vs-detail conflicts — set by the
  // backend's detail-reference resolver (app/trades/drywall_semantic.py
  // _resolve_detail_references). Empty when no detail callout was resolved
  // for this wall, which is the common case.
  const rawFieldProvenance = (d.evidence?.field_provenance ?? {}) as Record<string, Record<string, unknown>>;
  const fieldProvenance: Record<string, FieldProvenanceEntry> = Object.fromEntries(
    Object.entries(rawFieldProvenance).map(([key, entry]) => [
      key,
      {
        value: entry.value as string | number,
        sourceSheet: (entry.source_sheet as string | undefined) ?? null,
        sourceDetail: (entry.source_detail as string | undefined) ?? null,
        method: (entry.method as string) ?? "unknown",
        confidence: (entry.confidence as number) ?? 0,
      },
    ]),
  );
  const conflicts = ((d.evidence?.conflicts ?? []) as Array<Record<string, unknown>>).map((c) => ({
    field: c.field as string,
    sources: c.sources as WallConflict["sources"],
    status: c.status as string,
  }));

  // Resolve reference chips to a real, currently-loaded Sheet — null (not
  // a fabricated link) when the reference exists but its sheet isn't in
  // this drawing set.
  const scheduleSheetRefSheetId = findSheetIdByCode(state.sheets, scheduleSheet !== "Not available from source" ? scheduleSheet : null);
  const detailReferenceSheetCode = detailReference ? detailReference.split("/")[1] ?? null : null;
  const detailReferenceSheetId = findSheetIdByCode(state.sheets, detailReferenceSheetCode);

  // Spatial Room Adjacency — real geometry test (wall midpoint vs room polygons)
  let adjacentRooms: Array<{ id: string; name: string; area?: number }> = [];
  if (d.points && d.points.length >= 2) {
    const wallForLookup = d.sheetId ? d : { ...d, sheetId: state.activeSheetId ?? "" };
    const bordering = findBorderingRooms(wallForLookup, state.detections);

    adjacentRooms = bordering.map((r: Detection) => ({
      id: r.id.replace(/\D/g, ""),
      name: r.name || `Room ${r.id.replace(/\D/g, "")}`,
      area: r.areaSqFt,
    }));
  }

  const isExterior = categoryCode === "EXTERIOR_PERIMETER";
  const leftRoom = adjacentRooms[0]?.name || (isExterior ? "Exterior Space" : "Not available from source");
  const rightRoom = adjacentRooms[1]?.name || (isExterior ? "Conditioned Space" : adjacentRooms.length === 1 ? "Corridor / Circulation" : "Not available from source");

  // Openings
  const openingsCount = d.openingsCount ?? 0;
  const openingDeductionSf = Math.round((d.openingDeductionSf || 0) * 100) / 100;

  // QTO Calculation
  const sidesToHang = d.sidesToHang ?? (isExterior ? 1 : 2);
  const layersSideA = d.layersSideA ?? 1;
  const layersSideB = d.layersSideB ?? (sidesToHang >= 2 ? 1 : 0);
  const totalLayers = layersSideA + layersSideB;

  const grossHangAreaSf = Math.round((d.grossSf || (wallFaceAreaSf * totalLayers)) * 100) / 100;
  const netHangAreaSf = Math.round((d.netSf || Math.max(0, grossHangAreaSf - openingDeductionSf)) * 100) / 100;

  const qtoEligible = d.qtoEligible !== false && d.status !== "rejected";
  const qtoReason = qtoEligible
    ? `Approved architectural wall • Valid geometry (${lengthFt.toFixed(1)} ft) • Valid height (${heightFt.toFixed(1)} ft ${heightProvenance}) • Valid thickness (${thicknessIn.toFixed(2)}") • No blocking classification`
    : (d.qtoBlockReason || d.rejectionReason || "Excluded by QTO validation gate");

  const wasteFactorPct = Math.round((WASTE_FACTOR - 1) * 100); // sourced from the frozen DrywallEngine's WASTE_FACTOR
  const sheetCoverageSf = 32; // 4x8 ft sheet = 32 SF
  const requiredSheets = netHangAreaSf > 0 ? Math.ceil((netHangAreaSf * WASTE_FACTOR) / sheetCoverageSf) : 0;

  const calculationFormula = `${lengthFt.toFixed(2)} ft × ${heightFt.toFixed(2)} ft × ${totalLayers} layer${totalLayers > 1 ? "s" : ""} = ${grossHangAreaSf.toFixed(2)} SF Gross${
    openingDeductionSf > 0 ? ` − ${openingDeductionSf.toFixed(2)} SF Openings` : ""
  } = ${netHangAreaSf.toFixed(2)} SF Net Hang Area → ⌈${netHangAreaSf.toFixed(2)} × ${WASTE_FACTOR.toFixed(2)} ÷ 32⌉ = ${requiredSheets} sheets (4×8)`;

  const openingsSummary = openingsCount > 0
    ? `${openingsCount} opening${openingsCount > 1 ? "s" : ""}, ${openingDeductionSf.toFixed(2)} SF total deducted`
    : "No openings detected on this wall run";

  return {
    wallId: d.id,
    displayCode,
    wallTag,
    wallTagDisplay,
    categoryCode,
    categoryColor: catConfig.color,
    categoryLabel: catConfig.label,

    sheetCode: activeSheet?.code || "Not available from source",
    pageNumber: activeSheet?.pageNumber != null ? activeSheet.pageNumber : "Not available from source",
    drawingTitle: activeSheet?.name || "Not available from source",
    source: d.evidence?.source === "manual_entry" ? "Manual Entry" : "AI Detection + Rules",
    confidencePct: Math.round((d.confidence ?? 0.95) * 100),
    status: d.status,
    statusLabel: d.status.charAt(0).toUpperCase() + d.status.slice(1),

    lengthFt,
    heightFt,
    heightProvenance,
    heightVerificationState,
    thicknessIn,
    thicknessSource,
    thicknessVerificationState,
    wallFaceAreaSf,
    volumeCf,

    assemblyTag,
    assemblyVerified,
    assemblyDescription,
    scheduleSheet,
    detailReference,
    detailReferenceStatus,
    studDepthIn,
    studGauge,
    boardTypeSideA,
    boardTypeSideB,
    fireRatingHr,
    soundRatingStc,
    insulation,
    fieldProvenance,
    conflicts,
    scheduleSheetRefSheetId,
    detailReferenceSheetId,

    leftRoom,
    rightRoom,
    adjacentRooms,
    adjacentSpacesCount: adjacentRooms.length,
    openingsCount,
    openingDeductionSf,
    columnRelationship: "None detected",

    qtoEligible,
    qtoReason,
    sidesToHang,
    layersSideA,
    layersSideB,
    totalLayers,
    grossHangAreaSf,
    netHangAreaSf,
    sheetCoverageSf,
    wasteFactorPct,
    requiredSheets,
    calculationFormula,
    openingsSummary,
  };
}
