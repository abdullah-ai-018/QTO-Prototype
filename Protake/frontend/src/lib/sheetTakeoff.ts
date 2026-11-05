/**
 * lib/sheetTakeoff.ts
 *
 * Per-sheet drywall takeoff calculation.
 * - When the active sheet is non-eligible → all current-sheet values are 0.
 * - computeDrywall() (from estimating.ts) is called with sheet-filtered
 *   detections only — never with the full project detection set.
 *
 * DO NOT modify the computeDrywall() engine in estimating.ts.
 */

import type { Detection, Sheet } from "@/types";
import type { DrywallSettings } from "@/lib/estimating";
import { computeDrywall } from "@/lib/estimating";
import type { PageTradeTakeoffResponse } from "@/api/backendApi";

// ─────────────────────────────────────────────────────────────────────────────
// Page types that are never takeoff-eligible
// ─────────────────────────────────────────────────────────────────────────────
const NON_TAKEOFF_PAGE_TYPES = new Set([
  "text_specification",
  "empty_blank",
  "non_architectural",
  "finish_schedule",
  "door_schedule",
  "window_schedule",
  "room_finish_plan",
]);

/**
 * Returns true if the sheet should be included in a per-sheet drywall takeoff.
 *
 * Precedence (most authoritative first):
 *  1. Backend classifier result (sheet.isTakeoffEligible === false → always skip)
 *  2. pageType in NON_TAKEOFF_PAGE_TYPES → skip
 *  3. Default → eligible (treat unknown as eligible)
 */
export function isTakeoffEligible(sheet: Sheet | null | undefined): boolean {
  if (!sheet) return false;

  // 1. Explicit backend decision
  if (sheet.isTakeoffEligible === false) return false;

  // 2. Page type classification
  if (sheet.pageType && NON_TAKEOFF_PAGE_TYPES.has(sheet.pageType)) return false;

  // 3. Default → eligible
  return true;
}

/**
 * Human-readable reason why this sheet is not eligible for takeoff.
 */
export function getEligibilityReason(sheet: Sheet | null | undefined): string {
  if (!sheet) return "No sheet selected";
  if (sheet.isTakeoffEligible === false) {
    return sheet.skipReason ?? "Classified as non-takeoff by blueprint processor";
  }
  if (sheet.pageType && NON_TAKEOFF_PAGE_TYPES.has(sheet.pageType)) {
    const labels: Record<string, string> = {
      text_specification: "Text specification sheet",
      empty_blank: "Empty / blank page",
      non_architectural: "Non-architectural drawing",
      finish_schedule: "Finish schedule (schedule authority only)",
      door_schedule: "Door schedule",
      window_schedule: "Window schedule",
      room_finish_plan: "Room finish plan / schedule authority only",
    };
    return labels[sheet.pageType] ?? `Non-takeoff page type: ${sheet.pageType}`;
  }
  return "";
}

// ─────────────────────────────────────────────────────────────────────────────
// Per-sheet takeoff result shape
// ─────────────────────────────────────────────────────────────────────────────
export interface SheetLineItem {
  item: string;
  qty: string;
  unit: string;
  unitCost: string;
  total: string;
}

export interface SheetTakeoffResult {
  eligible: boolean;
  eligibilityReason: string;

  /** Wall detection count for this sheet only */
  wallCount: number;

  /** Net hang area in SF for this sheet. Null when the source evidence for
      this figure was absent from the backend response — never a fabricated
      0 standing in for missing data. */
  netHangAreaSf: number | null;
  /** Ceiling area in SF for this sheet. Same null-means-missing rule as netHangAreaSf. */
  ceilingAreaSf: number | null;
  /** Total drywall area (wall net + ceiling) in SF. Null if either input is null. */
  totalDrywallAreaSf: number | null;

  /** 4×8 drywall panel count for this sheet */
  sheets: number;
  wallSheets: number;
  ceilingSheets: number;

  laborHours: number;
  directCost: number;
  materialCost: number;
  laborCost: number;

  /** 0-100 */
  materialPct: number;
  /** 0-100 */
  laborPct: number;

  /** Rows for the TOP LINE ITEMS table */
  topLineItems: SheetLineItem[];
}

/** A zeroed-out result used when the sheet is not eligible for takeoff. */
function zeroResult(reason: string): SheetTakeoffResult {
  return {
    eligible: false,
    eligibilityReason: reason,
    wallCount: 0,
    netHangAreaSf: 0,
    ceilingAreaSf: 0,
    totalDrywallAreaSf: 0,
    sheets: 0,
    wallSheets: 0,
    ceilingSheets: 0,
    laborHours: 0,
    directCost: 0,
    materialCost: 0,
    laborCost: 0,
    materialPct: 0,
    laborPct: 0,
    topLineItems: [],
  };
}

// Display-layer unit costs (kept separate from estimating.ts internals)
const DRYWALL_SHEET_UNIT_COST = 24.8;
const COMPOUND_UNIT_COST = 16.25;
const TAPE_UNIT_COST = 0.09;
const SCREW_UNIT_COST = 0.02;

function fmt(value: number, decimals = 2): string {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/**
 * Compute the takeoff for the active sheet only.
 *
 * @param activeSheet     The currently-displayed sheet.
 * @param allDetections   Full state.detections — filtered to sheet internally.
 * @param settings        User-configurable drywall assembly settings.
 */
export function computeSheetTakeoff(
  activeSheet: Sheet | null | undefined,
  allDetections: Detection[],
  settings: DrywallSettings,
): SheetTakeoffResult {
  if (!activeSheet) return zeroResult("No sheet selected");

  const eligible = isTakeoffEligible(activeSheet);
  const reason = getEligibilityReason(activeSheet);
  if (!eligible) return zeroResult(reason);

  // ── Scope detections to this sheet ──────────────────────────────────────
  const sheetDetections = allDetections.filter(
    (d) => d.sheetId === activeSheet.id,
  );

  // ── Wall count ───────────────────────────────────────────────────────────
  const wallCount = sheetDetections.filter(
    (d) => d.kind === "wall" && d.status !== "rejected",
  ).length;

  // ── Call the frozen drywall engine with sheet-scoped data ────────────────
  const drywallResult = computeDrywall(sheetDetections, settings);
  const {
    materialQuantity: totalSheets,
    laborHours,
    directCost,
  } = drywallResult.metrics;

  // Extract area metrics from the engine line items
  const liMap = Object.fromEntries(
    drywallResult.lineItems.map((li) => [li.label, li.qty]),
  );
  const netHangAreaSf = (liMap["Net Wall Drywall Subtotal"] as number) ?? 0;
  const ceilingAreaSf = (liMap["Ceiling Drywall Subtotal"] as number) ?? 0;
  const totalDrywallAreaSf =
    (liMap["Total Drywall Surface Area"] as number) ?? 0;

  // Proportional split into wall vs ceiling sheets
  const wallAreaPct =
    totalDrywallAreaSf > 0 ? netHangAreaSf / totalDrywallAreaSf : 0;
  const wallSheets = Math.round(totalSheets * wallAreaPct);
  const ceilingSheets = Math.max(0, totalSheets - wallSheets);

  // Cost split (81.1% / 18.9% matching project ratio)
  const materialCost = Math.round(directCost * 0.811);
  const laborCost = Math.max(0, directCost - materialCost);
  const materialPct =
    directCost > 0
      ? Math.round((materialCost / directCost) * 1000) / 10
      : 0;
  const laborPct =
    directCost > 0
      ? Math.round((laborCost / directCost) * 1000) / 10
      : 0;

  // ── Line items ───────────────────────────────────────────────────────────
  const compoundBuckets = Math.ceil(totalDrywallAreaSf / 370);
  const screws = totalSheets * 32;
  const tapeFt = Math.round(totalDrywallAreaSf * 0.437);

  const topLineItems: SheetLineItem[] =
    totalSheets === 0
      ? []
      : [
          {
            item: "Drywall Wall Sheets (4×8)",
            qty: wallSheets.toLocaleString(),
            unit: "sheets",
            unitCost: `$${DRYWALL_SHEET_UNIT_COST.toFixed(2)}`,
            total: `$${fmt(wallSheets * DRYWALL_SHEET_UNIT_COST)}`,
          },
          {
            item: "Drywall Ceiling Sheets (4×8)",
            qty: ceilingSheets.toLocaleString(),
            unit: "sheets",
            unitCost: `$${DRYWALL_SHEET_UNIT_COST.toFixed(2)}`,
            total: `$${fmt(ceilingSheets * DRYWALL_SHEET_UNIT_COST)}`,
          },
          {
            item: "Joint Compound",
            qty: compoundBuckets.toLocaleString(),
            unit: "buckets",
            unitCost: `$${COMPOUND_UNIT_COST.toFixed(2)}`,
            total: `$${fmt(compoundBuckets * COMPOUND_UNIT_COST)}`,
          },
          {
            item: "Joint Tape",
            qty: tapeFt.toLocaleString(),
            unit: "ft",
            unitCost: `$${TAPE_UNIT_COST.toFixed(2)}`,
            total: `$${fmt(tapeFt * TAPE_UNIT_COST)}`,
          },
          {
            item: "Screws",
            qty: screws.toLocaleString(),
            unit: "pcs",
            unitCost: `$${SCREW_UNIT_COST.toFixed(2)}`,
            total: `$${fmt(screws * SCREW_UNIT_COST)}`,
          },
        ];

  return {
    eligible: true,
    eligibilityReason: "",
    wallCount,
    netHangAreaSf,
    ceilingAreaSf,
    totalDrywallAreaSf,
    sheets: totalSheets,
    wallSheets,
    ceilingSheets,
    laborHours,
    directCost,
    materialCost,
    laborCost,
    materialPct,
    laborPct,
    topLineItems,
  };
}

/**
 * Builds a SheetTakeoffResult from the backend's page-scoped takeoff
 * (GET .../pages/{page_id}/takeoffs/{trade}) — the same TradeEngine and
 * evidence/formula_breakdown provenance as the project-level takeoff,
 * filtered to one page, instead of computeSheetTakeoff()'s client-side
 * recomputation above. Prefer this whenever the backend call succeeds;
 * fall back to computeSheetTakeoff() only when it's unavailable (see
 * AppContext.tsx), and label that fallback state visibly in the UI.
 */
export function buildSheetTakeoffFromBackend(
  pageTakeoff: PageTradeTakeoffResponse,
  wallCount: number,
): SheetTakeoffResult {
  const qtoGating = (pageTakeoff.evidence?.qto_gating ?? {}) as {
    wall_hang_area_sqft?: number;
    ceiling_area_sqft?: number;
  };
  // Distinguish "key present with a real value (including a genuine 0 SF
  // sheet)" from "key absent because the backend's qto_gating evidence
  // wasn't returned" — the latter must surface as null/"Not available from
  // source" in the UI, never a silently fabricated 0.
  const netHangAreaSf = "wall_hang_area_sqft" in qtoGating ? qtoGating.wall_hang_area_sqft! : null;
  const ceilingAreaSf = "ceiling_area_sqft" in qtoGating ? qtoGating.ceiling_area_sqft! : null;
  const totalDrywallAreaSf = netHangAreaSf != null && ceilingAreaSf != null ? netHangAreaSf + ceilingAreaSf : null;

  const wallSheets = pageTakeoff.items.find((i) => i.label.startsWith("Drywall Wall Sheets"))?.quantity ?? 0;
  const ceilingSheets = pageTakeoff.items.find((i) => i.label.startsWith("Drywall Ceiling Sheets"))?.quantity ?? 0;

  const { material_cost: materialCost, labor_cost: laborCost, direct_cost: directCost } = pageTakeoff;
  const materialPct = directCost > 0 ? Math.round((materialCost / directCost) * 1000) / 10 : 0;
  const laborPct = directCost > 0 ? Math.round((laborCost / directCost) * 1000) / 10 : 0;

  const topLineItems: SheetLineItem[] = pageTakeoff.items
    .filter((i) => i.unit !== "hrs") // labor is shown as its own KPI, not a material line item
    .map((i) => ({
      item: i.label,
      qty: i.quantity.toLocaleString(),
      unit: i.unit,
      unitCost: `$${i.unit_cost.toFixed(2)}`,
      total: `$${fmt(i.total_cost)}`,
    }));

  return {
    eligible: true,
    eligibilityReason: "",
    wallCount,
    netHangAreaSf,
    ceilingAreaSf,
    totalDrywallAreaSf,
    sheets: pageTakeoff.material_quantity,
    wallSheets,
    ceilingSheets,
    laborHours: pageTakeoff.labor_hours,
    directCost,
    materialCost,
    laborCost,
    materialPct,
    laborPct,
    topLineItems,
  };
}
