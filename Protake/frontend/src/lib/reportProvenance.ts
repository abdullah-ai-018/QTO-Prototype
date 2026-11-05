// Pure, testable helpers for the Report modal's "provenance" display and
// line-item navigation decisions. Extracted out of ReportModal.tsx so the
// decision logic (real data vs. honest "unavailable" fallback) can be unit
// tested without a React renderer.
//
// Context: TradeBreakdown.lineItems (see lib/estimating.ts) is always an
// aggregate computed across every active detection for a trade — summed
// linear feet, sheet counts, labor hours, etc. Neither the local engine nor
// the backend's /live-breakdown conversion (see state/AppContext.tsx) attach
// a detectionId/wallId/sheetId/confidence to an individual line item today.
// These helpers are written against an optional-fields shape so that if a
// future data source *does* start attaching real per-item provenance, the
// report will pick it up automatically — but until then they must not
// fabricate one.

export const NOT_AVAILABLE_FROM_SOURCE = "Not available from source";

export interface ReportLineItem {
  label: string;
  qty: number;
  unit: string;
  /** Real per-item provenance fields — optional because no current data
   * source populates them. Present for forward compatibility only. */
  detectionId?: string;
  wallId?: string;
  sheetId?: string;
  sheetLabel?: string;
  /** 0-1 */
  confidence?: number;
}

export interface LineItemNavigationTarget {
  sheetId: string;
  detectionId: string;
}

export type ReportNavigationAction =
  | { type: "SET_ACTIVE_SHEET"; sheetId: string }
  | { type: "SELECT_DETECTION"; id: string | null };

/** Only returns a target when the line item genuinely carries one — never guesses. */
export function getLineItemNavigationTarget(li: ReportLineItem): LineItemNavigationTarget | null {
  const detectionId = li.detectionId || li.wallId;
  if (li.sheetId && detectionId) {
    return { sheetId: li.sheetId, detectionId };
  }
  return null;
}

/**
 * The dispatch actions to run when a line item is clicked, or null when the
 * item cannot be traced to real geometry. Callers should append their own
 * CLOSE_REPORT dispatch after these, and only show a "highlighted source"
 * toast when this returns non-null.
 */
export function buildLineItemNavigationActions(li: ReportLineItem): ReportNavigationAction[] | null {
  const target = getLineItemNavigationTarget(li);
  if (!target) return null;
  return [
    { type: "SET_ACTIVE_SHEET", sheetId: target.sheetId },
    { type: "SELECT_DETECTION", id: target.detectionId },
  ];
}

/** Real "Proof: Sheet X • Conf Y%" text, or the honest fallback. */
export function getLineItemProofDisplay(li: ReportLineItem): string {
  if (li.sheetLabel && typeof li.confidence === "number") {
    return `Proof: Sheet ${li.sheetLabel} • Conf ${Math.round(li.confidence * 100)}%`;
  }
  return `Proof: ${NOT_AVAILABLE_FROM_SOURCE}`;
}

export function computePlateHeightDisplay(
  wallHeightFt: number | undefined,
  defaultHeightFt: number
): { display: string; isDefault: boolean } {
  const display = typeof wallHeightFt === "number" ? `${wallHeightFt.toFixed(2)} FT` : NOT_AVAILABLE_FROM_SOURCE;
  const isDefault = wallHeightFt === defaultHeightFt;
  return { display, isDefault };
}

export function computeAssemblyDisplay(walls: { assemblyDescription?: string | null }[]): string {
  const withAssembly = walls.filter((w) => !!w.assemblyDescription);
  const unique = Array.from(new Set(withAssembly.map((w) => w.assemblyDescription as string)));
  if (unique.length === 0) return NOT_AVAILABLE_FROM_SOURCE;
  if (unique.length === 1) return unique[0];
  return `${unique.length} distinct assemblies across ${withAssembly.length} walls`;
}

export function computeOpeningDeductionsDisplay(
  walls: { openingDeductionSf?: number }[],
  localComputedSf?: number
): string {
  const withDeduction = walls.filter((w) => typeof w.openingDeductionSf === "number");
  if (withDeduction.length > 0) {
    const total = withDeduction.reduce((sum, w) => sum + (w.openingDeductionSf || 0), 0);
    return `-${Math.round(total).toLocaleString()} SF`;
  }
  if (typeof localComputedSf === "number") {
    return `-${Math.round(localComputedSf).toLocaleString()} SF`;
  }
  return NOT_AVAILABLE_FROM_SOURCE;
}
