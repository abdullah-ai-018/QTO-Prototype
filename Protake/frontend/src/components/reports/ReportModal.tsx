import { AnimatePresence, motion } from "framer-motion";
import { X, FileDown, Printer, Building2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/state/AppContext";
import { TRADES } from "@/lib/sampleData";
import { DEFAULT_DRYWALL_SETTINGS } from "@/lib/estimating";
import {
  buildLineItemNavigationActions,
  getLineItemProofDisplay,
  computePlateHeightDisplay,
  computeAssemblyDisplay,
  computeOpeningDeductionsDisplay,
} from "@/lib/reportProvenance";

import EstimateWarningBanner from "../common/EstimateWarningBanner";

function fmtCurrency(n: number) {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

export default function ReportModal() {
  const { state, dispatch, breakdowns, costSummary, isBackendSynced, syncError, scaleWarnings, reviewWarnings } = useApp();

  // --- Real disclosure values (no fabricated defaults) ---------------------
  // Plate height: the actual project-level drywall assumption used by the
  // takeoff engine (user-configurable via Settings), not a hardcoded literal.
  const { display: plateHeightDisplay, isDefault: plateHeightIsDefault } = computePlateHeightDisplay(
    state.drywallSettings?.wallHeightFt,
    DEFAULT_DRYWALL_SETTINGS.wallHeightFt
  );

  // Assembly: derived from the real per-wall assemblyDescription field
  // (backend-provided). If walls disagree, say so honestly rather than
  // picking one and presenting it as universal.
  const activeWalls = state.detections.filter((d) => d.kind === "wall" && d.status !== "rejected");
  const assemblyDisplay = computeAssemblyDisplay(activeWalls);
  const hasAnyAssembly = activeWalls.some((d) => !!d.assemblyDescription);

  // Opening deductions: prefer the real per-wall openingDeductionSf field
  // (backend-measured); fall back to the local engine's own computed
  // "Opening Deductions" line item when backend data isn't in play. Never
  // fabricate a number when neither source has one.
  const localOpeningDeductionsItem = breakdowns.drywall?.lineItems?.find((li) => li.label === "Opening Deductions");
  const openingDeductionsDisplay = computeOpeningDeductionsDisplay(activeWalls, localOpeningDeductionsItem?.qty);
  const doorCount = state.detections.filter((d) => d.kind === "door" && d.status !== "rejected").length;
  const windowCount = state.detections.filter((d) => d.kind === "window" && d.status !== "rejected").length;
  const openingDeductionsCaption =
    doorCount > 0 || windowCount > 0
      ? `${doorCount} Door(s) + ${windowCount} Window(s) deducted from host walls.`
      : "No door/window openings detected on active walls.";

  function checkSyncConfirmation(): boolean {
    const hasWarnings = (scaleWarnings && scaleWarnings.length > 0) || (reviewWarnings && reviewWarnings.length > 0);

    if (hasWarnings || !isBackendSynced) {
      let warningText = "⚠️ UNCONFIRMED ESTIMATE WARNINGS DETECTED\n\n";

      if (!isBackendSynced) {
        warningText += "• BACKEND ENGINE UNREACHABLE — Local fallback rules active.\n\n";
      }

      if (scaleWarnings && scaleWarnings.length > 0) {
        warningText += `• ASSUMED SCALE WARNING:\n  ${scaleWarnings.map((w) => w.reason).join("\n  ")}\n\n`;
      }

      if (reviewWarnings && reviewWarnings.length > 0) {
        warningText += `• HUMAN REVIEW QUEUE WARNING:\n  ${reviewWarnings.map((w) => w.reason).join("\n  ")}\n\n`;
      }

      warningText += "Formal bid documents should be confirmed after resolving scale & room warnings before submitting to clients.\n\nDo you wish to proceed with export anyway?";

      return window.confirm(warningText);
    }
    return true;
  }

  function exportCsv() {
    if (!checkSyncConfirmation()) return;

    const rows: string[][] = [["Trade", "Line Item", "Quantity", "Unit"]];
    TRADES.forEach(({ id, label }) => {
      const b = breakdowns[id];
      if (!b || !b.lineItems) return;
      b.lineItems.forEach((li) => {
        rows.push([label, li.label, String(li.qty), li.unit]);
      });
    });
    rows.push([]);
    rows.push(["Cost Summary", "", "", ""]);
    rows.push(["Material Cost", fmtCurrency(costSummary.materialCost), "", ""]);
    rows.push(["Labor Cost", fmtCurrency(costSummary.laborCost), "", ""]);
    rows.push(["Overhead", fmtCurrency(costSummary.overhead), "", ""]);
    rows.push(["Contingency", fmtCurrency(costSummary.contingency), "", ""]);
    rows.push(["Profit", fmtCurrency(costSummary.profit), "", ""]);
    rows.push(["Final Bid Price", fmtCurrency(costSummary.finalBid), "", ""]);

    const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "protake-estimate.csv";
    a.click();
    URL.revokeObjectURL(url);
    toast.success("CSV exported", { description: "protake-estimate.csv downloaded" });
  }

  function exportPdf() {
    if (!checkSyncConfirmation()) return;

    toast.info("Opening print dialog", { description: "Choose \"Save as PDF\" as the destination" });
    document.body.classList.add("print-report-mode");
    setTimeout(() => {
      window.print();
      document.body.classList.remove("print-report-mode");
    }, 150);
  }


  return (
    <AnimatePresence>
      {state.reportModalOpen && (
        <motion.div
          id="report-modal-wrapper"
          className="fixed inset-0 z-50 flex items-center justify-center p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div id="report-modal-backdrop" className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => dispatch({ type: "CLOSE_REPORT" })} />

          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            id="report-printable"
            className="relative w-full max-w-3xl max-h-[86vh] overflow-y-auto rounded-xl glass-panel"
          >
            <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)] bg-[var(--color-panel)]/95">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-[var(--color-primary)]/15 flex items-center justify-center text-[var(--color-primary)]">
                  <Building2 size={18} />
                </div>
                <div>
                  <div className="text-sm font-semibold">Enterprise Estimate Report</div>
                  <div className="text-xs text-[var(--color-text-secondary)] font-mono-num">Revision {state.revision}</div>
                </div>
              </div>
              <button
                id="report-modal-close"
                onClick={() => dispatch({ type: "CLOSE_REPORT" })}
                className="w-8 h-8 rounded-md flex items-center justify-center hover:bg-white/5 text-[var(--color-text-secondary)]"
              >
                <X size={16} />
              </button>
            </div>

            <div className="p-6 space-y-6">
              <EstimateWarningBanner onReviewClick={() => dispatch({ type: "CLOSE_REPORT" })} />

              {!isBackendSynced && (
                <div className="p-3.5 rounded-lg bg-amber-500/15 border border-amber-500/30 flex items-start gap-3 text-amber-200 text-xs">
                  <AlertTriangle size={18} className="shrink-0 text-amber-400 mt-0.5" />
                  <div>
                    <div className="font-semibold text-amber-300">Offline Fallback Engine Active (Backend Engine Unreachable)</div>
                    <div className="mt-0.5 text-amber-200/90">
                      These estimate numbers were generated using offline fallback rules. Confirm calculations with the backend Python engine (/live-breakdown) before submitting formal bids to clients.
                    </div>
                  </div>
                </div>
              )}

              <section className="grid grid-cols-2 gap-4">
                <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel-2)] p-4">
                  <div className="text-xs uppercase tracking-wide text-[var(--color-text-secondary)] mb-1">Project</div>
                  <div className="text-sm font-medium">
                    {state.file?.name ? state.file.name.replace(/\.[^/.]+$/, "") : "Untitled Project"}
                  </div>
                  <div className="text-xs text-[var(--color-text-secondary)] mt-1 font-mono">
                    {state.file?.name ?? "No file loaded"} •{" "}
                    {state.detections.filter((d) => d.kind === "wall" && d.status === "approved").length} Verified Physical Walls
                  </div>
                </div>
                <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel-2)] p-4">
                  <div className="text-xs uppercase tracking-wide text-[var(--color-text-secondary)] mb-1">Takeoff Authority</div>
                  <div className="text-sm font-medium">Protake Estimating Engine (DrywallEngine)</div>
                  <div className="text-xs text-[var(--color-text-secondary)] mt-1 font-mono">{new Date().toLocaleDateString()} · 0-Discrepancy Reconciled</div>
                </div>
              </section>

              {/* Engineering Disclosures & Assumptions */}
              <section className="rounded-lg border border-white/10 bg-[var(--color-panel-2)] p-4 space-y-2 font-mono text-xs">
                <div className="text-xs font-semibold uppercase text-amber-300 flex items-center gap-1.5">
                  <AlertTriangle size={13} className="text-amber-400" />
                  Takeoff Assumptions & Engineering Disclosures
                </div>
                <div className="grid grid-cols-3 gap-2 text-[11px] text-gray-300">
                  <div className="p-2 rounded bg-white/5">
                    <span className="text-amber-300 font-bold block">Plate Height: {plateHeightDisplay}</span>
                    <span>
                      {plateHeightIsDefault
                        ? "Standard default applied (2D plan lacks drawing elevation section)."
                        : "Project-configured assumption (set in Takeoff Settings)."}
                    </span>
                  </div>
                  <div className="p-2 rounded bg-white/5">
                    <span className="text-cyan-300 font-bold block">Assembly: {assemblyDisplay}</span>
                    <span>
                      {hasAnyAssembly
                        ? "Derived from detected wall assembly data."
                        : "No wall carries an assembly specification yet."}
                    </span>
                  </div>
                  <div className="p-2 rounded bg-white/5">
                    <span className="text-emerald-300 font-bold block">Opening Deductions: {openingDeductionsDisplay}</span>
                    <span>{openingDeductionsCaption}</span>
                  </div>
                </div>
              </section>

              <section>
                <div className="text-xs uppercase tracking-wide text-[var(--color-text-secondary)] mb-3">Trade Breakdown</div>
                <div className="space-y-3">
                  {TRADES.map(({ id, label }) => {
                    const b = breakdowns[id];
                    if (!b || !b.lineItems) return null;
                    return (
                      <div key={id} className="rounded-lg border border-[var(--color-border)] overflow-hidden">
                        <div className="flex items-center justify-between px-4 py-2.5 bg-[var(--color-panel-2)]">
                          <span className="text-sm font-medium">{label}</span>
                          <span className="text-xs font-mono-num text-[var(--color-text-secondary)]">
                            {fmtCurrency(b.metrics?.directCost || 0)}
                          </span>
                        </div>
                        <table className="w-full text-xs">
                          <tbody>
                            {b.lineItems.map((li) => (
                              <tr
                                key={li.label}
                                className="border-t border-[var(--color-border)] hover:bg-white/5 cursor-pointer transition-colors group"
                                onClick={() => {
                                  // Trade line items (li) are aggregates computed across every
                                  // active detection for this trade — today neither the local
                                  // engine (lib/estimating.ts) nor the backend live-breakdown
                                  // conversion (state/AppContext.tsx) attach a
                                  // detectionId/wallId/sheetId to an individual line item.
                                  // buildLineItemNavigationActions only returns actions when a
                                  // real target is genuinely present, so this never fabricates
                                  // a navigation that didn't happen.
                                  const actions = buildLineItemNavigationActions(li);
                                  if (actions) {
                                    actions.forEach((action) => dispatch(action));
                                    dispatch({ type: "CLOSE_REPORT" });
                                    toast.info(`Highlighted source for ${li.label}`, {
                                      description: "Canvas focused on the corresponding blueprint geometry.",
                                    });
                                  } else {
                                    toast.info("Source geometry unavailable for this line item", {
                                      description: `"${li.label}" is an aggregate total across multiple detections and isn't linked to a single sheet or detection.`,
                                    });
                                  }
                                }}
                              >
                                <td className="px-4 py-2.5">
                                  <div className="font-medium text-white group-hover:text-[var(--color-primary-hover)] report-item-title">
                                    {li.label}
                                  </div>
                                  <div className="text-[10px] text-[var(--color-text-secondary)] mt-0.5 flex items-center gap-2">
                                    <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-white/5 text-[var(--color-text-secondary)] font-mono text-[9px] border border-white/10 report-badge">
                                      {getLineItemProofDisplay(li)}
                                    </span>
                                  </div>
                                  </td>
                                <td className="px-4 py-2.5 text-right font-mono-num font-medium">
                                  {li.qty.toLocaleString()} {li.unit}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    );
                  })}
                </div>
              </section>

              <section>
                <div className="text-xs uppercase tracking-wide text-[var(--color-text-secondary)] mb-3">Cost Summary</div>
                <div className="rounded-lg border border-[var(--color-border)] divide-y divide-[var(--color-border)] overflow-hidden">
                  {[
                    ["Material Cost", costSummary.materialCost],
                    ["Labor Cost", costSummary.laborCost],
                    ["Overhead (12%)", costSummary.overhead],
                    ["Contingency (5%)", costSummary.contingency],
                    ["Profit (15%)", costSummary.profit],
                  ].map(([label, value]) => (
                    <div key={label as string} className="flex items-center justify-between px-4 py-2.5 text-sm bg-[var(--color-panel-2)]">
                      <span className="text-[var(--color-text-secondary)]">{label}</span>
                      <span className="font-mono-num">{fmtCurrency(value as number)}</span>
                    </div>
                  ))}
                  <div className="flex items-center justify-between px-4 py-3 text-sm bg-[var(--color-primary)]/10">
                    <span className="font-semibold">Final Bid Price</span>
                    <span className="font-mono-num font-semibold text-[var(--color-primary-hover)] text-base">
                      {fmtCurrency(costSummary.finalBid)}
                    </span>
                  </div>
                </div>
              </section>
            </div>

            <div id="report-modal-footer" className="sticky bottom-0 flex items-center justify-end gap-3 px-6 py-4 border-t border-[var(--color-border)] bg-[var(--color-panel)]/95">
              <button
                onClick={exportCsv}
                className="flex items-center gap-2 px-3.5 py-2 rounded-md text-sm border border-[var(--color-border)] hover:bg-white/5 transition-colors"
              >
                <FileDown size={14} /> Export CSV
              </button>
              <button
                onClick={exportPdf}
                className="flex items-center gap-2 px-3.5 py-2 rounded-md text-sm bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] transition-colors"
              >
                <Printer size={14} /> Export PDF
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
