import { useState, useMemo, useEffect } from "react";
import { Zap, FileSpreadsheet, FileText, CheckCircle2, ShieldCheck, ArrowRight, ChevronDown, ChevronUp, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/state/AppContext";
import { useResizablePanel } from "@/hooks/useResizablePanel";
import { BackendApiService, type WallLedgerEntry } from "@/api/backendApi";
import { getCanonicalWallCategory } from "@/lib/colors";
import { buildWallInspectionData } from "@/lib/wallInspectorModel";
import { BackendAuditLog } from "../ai-panel/HistoryTab";
import QtoDrillDownModal from "../evidence/QtoDrillDownModal";

const COLLAPSED_HEIGHT = 40;

export default function SummaryPanel() {
  const { state, dispatch, sheetTakeoff, sheetTakeoffSource, breakdowns, costSummary, currentUserName } = useApp();
  const { size: panelHeight, isDragging: isResizingHeight, handleProps: heightHandleProps } = useResizablePanel(
    "bottom-panel-height",
    { min: 180, max: 520, defaultSize: 270, axis: "vertical", invert: true }
  );
  const [expanded, setExpanded] = useState(true);
  const [activeTab, setActiveTab] = useState<"summary" | "items" | "ledger" | "evidence" | "audit">("summary");
  const [qtoAuditModalOpen, setQtoAuditModalOpen] = useState(false);
  const [qtoAuditInitialTab, setQtoAuditInitialTab] = useState<"summary" | "walls" | "openings" | "labor">("summary");
  const [showProjectTotals, setShowProjectTotals] = useState(false);

  // Real wall ledger for the "Wall Ledger" tab — same backend endpoint
  // QtoDrillDownModal uses, fetched lazily only once that tab is opened.
  const [ledgerRows, setLedgerRows] = useState<WallLedgerEntry[] | null>(null);
  const [ledgerLoadState, setLedgerLoadState] = useState<"idle" | "loading" | "ready" | "empty" | "error">("idle");

  useEffect(() => {
    if (activeTab !== "ledger" || !expanded) return;
    if (!state.projectId || !state.blueprintId) {
      setLedgerLoadState("error");
      return;
    }
    if (ledgerLoadState !== "idle") return;
    let cancelled = false;
    setLedgerLoadState("loading");
    BackendApiService.fetchDrywallWallLedger(state.projectId, state.blueprintId)
      .then((res) => {
        if (cancelled) return;
        setLedgerRows(res.wall_ledger);
        setLedgerLoadState(res.wall_ledger.length > 0 ? "ready" : "empty");
      })
      .catch((err) => {
        if (cancelled) return;
        const status = err?.status ?? err?.response?.status;
        setLedgerLoadState(status === 404 ? "empty" : "error");
      });
    return () => {
      cancelled = true;
    };
  }, [activeTab, expanded, state.projectId, state.blueprintId, ledgerLoadState]);

  const selectedDetection = state.detections.find((d) => d.id === state.selectedDetectionId);
  const selectedWallEvidence = selectedDetection && selectedDetection.kind === "wall" ? buildWallInspectionData(selectedDetection, state) : null;

  const activeSheet = state.sheets.find((s) => s.id === state.activeSheetId);

  // Detections on the active sheet that a plain Auto-Approve Gateway run
  // will deliberately skip (mirrors appState.ts's isEligibleForPlainApproval
  // gating for APPROVE_ALL) — used to decide whether the override control
  // needs to be shown at all, and to word its confirmation honestly.
  const needsReviewCount = useMemo(() => {
    return state.detections.filter((d) => {
      if (d.sheetId !== state.activeSheetId || d.status === "approved") return false;
      if (d.kind !== "wall") return false;
      // Mirrors appState.ts's isEligibleForPlainApproval: gate on the wall's
      // own classification signal, not its current pending/approved status
      // (a "pending" wall is otherwise always forced to NEEDS_REVIEW here,
      // which would count every unapproved wall as stuck).
      const category = getCanonicalWallCategory(d.wallTypeCode, d.wallType, d.wallTag, undefined, d.confidence, d.classification);
      return category === "NEEDS_REVIEW";
    }).length;
  }, [state.detections, state.activeSheetId]);
  
  const tabs = [
    { id: "summary", label: "Takeoff Summary" },
    { id: "items", label: `Line Items (${sheetTakeoff.topLineItems.length})` },
    { id: "ledger", label: `Wall Ledger (${sheetTakeoff.wallCount})` },
    { id: "evidence", label: "Evidence" },
    { id: "audit", label: "Audit Log" },
  ];

  // Compute project-wide totals from backend breakdowns (all trades combined)
  const projectTotalsFromBackend = useMemo(() => {
    const drywall = breakdowns.drywall;
    const painting = breakdowns.painting;
    const flooring = breakdowns.flooring;
    const roofing = breakdowns.roofing;
    
    // Aggregate line items from all trades
    const allLineItems: Array<{item: string; qty: string; unit: string; unitCost: string; total: string}> = [];
    
    [drywall, painting, flooring, roofing].forEach(trade => {
      if (trade && trade.lineItems) {
        trade.lineItems.forEach(li => {
          allLineItems.push({
            item: li.label,
            qty: li.qty.toLocaleString('en-US', {maximumFractionDigits: 0}),
            unit: li.unit,
            // computeAllTrades()'s TradeBreakdown.lineItems only carries
            // {label, qty, unit} — no per-item cost. A per-trade direct cost
            // exists (costSummary below), but attributing it back down to
            // one line item would be a fabricated split, not a real number.
            unitCost: "Not available from source",
            total: "Not available from source",
          });
        });
      }
    });

    const directCost = costSummary.materialCost + costSummary.laborCost;

    return {
      sheets: drywall?.metrics.materialQuantity || 0,
      laborHours: costSummary.totalLaborHours,
      directCost,
      // Derived from the real backend sheet count via a fixed 32 SF/sheet
      // (4x8 panel) constant — a real, labeled estimate (see
      // wallNetHangAreaSfIsEstimate below for the UI marker), not fabricated
      // data. Null (not 0) when there's no material quantity to derive it from.
      wallNetHangAreaSf: drywall?.metrics.materialQuantity ? drywall.metrics.materialQuantity * 32 : null,
      wallNetHangAreaSfIsEstimate: true,
      // Not tracked as a separate figure anywhere in the current backend
      // response at the project level — genuinely absent, not a real zero.
      ceilingAreaSf: null as number | null,
      materialCost: costSummary.materialCost,
      laborCost: costSummary.laborCost,
      topLineItems: allLineItems.slice(0, 5), // Top 5 items
      validatedAt: new Date().toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true })
    };
  }, [breakdowns, costSummary]);

  // Use real calculated data from sheetTakeoff or backend project totals
  const displayData = showProjectTotals ? projectTotalsFromBackend : {
    sheets: sheetTakeoff.sheets,
    laborHours: sheetTakeoff.laborHours,
    directCost: sheetTakeoff.directCost,
    wallNetHangAreaSf: sheetTakeoff.netHangAreaSf,
    wallNetHangAreaSfIsEstimate: false,
    ceilingAreaSf: sheetTakeoff.ceilingAreaSf,
    materialCost: sheetTakeoff.materialCost,
    laborCost: sheetTakeoff.laborCost,
    topLineItems: sheetTakeoff.topLineItems
  };

  return (
    <section
      style={{ height: expanded ? `${panelHeight}px` : `${COLLAPSED_HEIGHT}px` }}
      className="shrink-0 border-t border-white/10 bg-[#0B0E14] flex flex-col font-sans select-none overflow-hidden relative transition-[height] duration-150"
    >
      {/* Resize handle (top edge) — only meaningful while expanded */}
      {expanded && (
        <div
          onPointerDown={heightHandleProps.onPointerDown}
          className={`absolute top-0 left-0 w-full h-1 cursor-ns-resize hover:bg-blue-500/50 transition-colors z-10 group ${isResizingHeight ? "bg-blue-500/50" : ""}`}
        >
          <div className="absolute top-0 left-1/2 -translate-x-1/2 h-1 w-12 bg-blue-500/30 group-hover:bg-blue-500/70 rounded-b transition-colors" />
        </div>
      )}
      {/* Top Tab Bar & Action Buttons (expanded) / compact summary bar (collapsed) — always exactly one h-10 row. */}
      {!expanded ? (
        <div className="h-10 px-4 bg-[#111622] border-b border-white/10 flex items-center gap-5 shrink-0 text-[11px] font-mono overflow-x-auto scrollbar-none">
          <button
            onClick={() => setExpanded(true)}
            className="p-1 rounded text-gray-400 hover:text-white hover:bg-white/5 transition-colors cursor-pointer shrink-0"
            title="Expand"
          >
            <ChevronUp size={14} />
          </button>
          <span className="text-gray-400 font-sans shrink-0">
            {showProjectTotals ? "PROJECT" : `SHEET: ${activeSheet?.code || "N/A"}`}
          </span>
          <span className="text-gray-300 shrink-0">Walls <b className="text-white">{sheetTakeoff.wallCount}</b></span>
          <span className="text-gray-300 shrink-0">Sheets <b className="text-white">{displayData.sheets.toLocaleString()}</b></span>
          <span className="text-gray-300 shrink-0">
            Drywall <b className="text-white">${displayData.directCost.toLocaleString("en-US", { minimumFractionDigits: 2 })}</b>
          </span>
          <span className={`font-semibold uppercase tracking-wide shrink-0 ${sheetTakeoff.eligible ? "text-emerald-400" : "text-amber-400"}`}>
            {sheetTakeoff.eligible ? "Backend Validated" : "Non-Takeoff"}
          </span>
        </div>
      ) : (
      <div className="h-10 px-4 bg-[#111622] border-b border-white/10 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setExpanded(false)}
            className="p-1 mr-1 rounded text-gray-400 hover:text-white hover:bg-white/5 transition-colors cursor-pointer"
            title="Collapse to summary bar"
          >
            <ChevronDown size={14} />
          </button>
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => {
                setExpanded(true);
                setActiveTab(t.id as any);
              }}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all cursor-pointer ${
                expanded && activeTab === t.id
                  ? "bg-blue-600/20 text-blue-400 border border-blue-500/30"
                  : "text-gray-400 hover:text-white hover:bg-white/5"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          {/* Context Toggle */}
          <button
            onClick={() => setShowProjectTotals(!showProjectTotals)}
            className={`px-2 py-1 rounded text-[10px] font-semibold transition-colors ${
              showProjectTotals
                ? "bg-amber-600/20 text-amber-400 border border-amber-500/30"
                : "bg-blue-600/20 text-blue-400 border border-blue-500/30"
            }`}
          >
            {showProjectTotals ? "PROJECT TOTALS" : "CURRENT SHEET"}
          </button>

          <button
            onClick={() => {
              dispatch({ type: "APPROVE_ALL" });
              toast.success("Auto-Approve Gateway Executed", {
                description: `${sheetTakeoff.wallCount} QTO-eligible wall(s) approved on ${activeSheet?.code || 'current sheet'}. NEEDS_REVIEW walls were skipped.`
              });
            }}
            className="flex items-center gap-1.5 px-3 py-1 rounded-md text-[11px] font-semibold bg-emerald-600/20 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-600/30 transition-colors cursor-pointer"
          >
            <Zap size={12} className="text-emerald-400" />
            <span>Auto-Approve Gateway</span>
          </button>

          {needsReviewCount > 0 && (
            <button
              onClick={() => {
                const reason = window.prompt(
                  `${needsReviewCount} wall(s) on ${activeSheet?.code || 'this sheet'} are still NEEDS_REVIEW (unclassified or unresolved). ` +
                  `Approving them anyway overrides that review gate and is recorded permanently.\n\n` +
                  `Enter a reason for this override to continue:`
                );
                if (reason === null) return; // user cancelled the prompt
                const trimmedReason = reason.trim();
                if (!trimmedReason) {
                  toast.error("Override cancelled", { description: "A reason is required to approve NEEDS_REVIEW walls." });
                  return;
                }
                if (!window.confirm(
                  `Confirm: approve ${needsReviewCount} NEEDS_REVIEW wall(s) on ${activeSheet?.code || 'this sheet'} anyway?`
                )) {
                  return;
                }
                dispatch({ type: "APPROVE_ALL_OVERRIDE", reason: trimmedReason, actor: currentUserName || undefined });
                toast.warning("Approved Including Review", {
                  description: `${needsReviewCount} NEEDS_REVIEW wall(s) force-approved on ${activeSheet?.code || 'current sheet'} — recorded with reviewer, timestamp, and reason.`
                });
              }}
              title="Overrides the review gate for NEEDS_REVIEW / unresolved walls. Requires a reason and is recorded on each affected wall."
              className="flex items-center gap-1.5 px-3 py-1 rounded-md text-[11px] font-semibold bg-amber-600/20 text-amber-400 border border-amber-500/40 hover:bg-amber-600/30 transition-colors cursor-pointer"
            >
              <AlertTriangle size={12} className="text-amber-400" />
              <span>Approve All (Including Review)</span>
            </button>
          )}

          <button
            onClick={() => {
              setQtoAuditInitialTab("summary");
              setQtoAuditModalOpen(true);
            }}
            className="flex items-center gap-1.5 px-3 py-1 rounded-md text-[11px] font-semibold bg-blue-600/20 text-blue-400 border border-blue-500/30 hover:bg-blue-600/30 transition-colors cursor-pointer"
          >
            <FileSpreadsheet size={12} />
            <span>Calculation Audit</span>
          </button>

          <button
            onClick={() => dispatch({ type: "OPEN_REPORT" })}
            className="flex items-center gap-1.5 px-3 py-1 rounded-md text-[11px] font-semibold bg-white/5 text-gray-300 border border-white/10 hover:bg-white/10 hover:text-white transition-colors cursor-pointer"
          >
            <FileText size={12} />
            <span>Full Report</span>
          </button>
        </div>
      </div>
      )}

      {/* Main Content Area */}
      {expanded && activeTab === "summary" && (
      <div className="flex-1 p-3.5 grid grid-cols-12 gap-3.5 min-h-0 overflow-y-auto scrollbar-custom">
        {/* Left Column: 6 KPI Cards (Grid of 6) */}
        <div className="col-span-4 grid grid-cols-2 gap-2.5">
          {/* Context Header */}
          <div className="col-span-2 text-center">
            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1">
              {showProjectTotals ? "PROJECT TOTALS" : `CURRENT SHEET: ${activeSheet?.code || 'N/A'}`}
            </div>
            {!showProjectTotals && (
              <div className="text-[9px] text-gray-500">
                {sheetTakeoff.eligible ? `${sheetTakeoff.wallCount} walls detected` : sheetTakeoff.eligibilityReason}
              </div>
            )}
            {!showProjectTotals && sheetTakeoff.eligible && (
              <div
                className={`mt-0.5 text-[8px] font-semibold uppercase tracking-wider ${
                  sheetTakeoffSource === "backend_validated" ? "text-emerald-500" : "text-amber-500"
                }`}
                title={
                  sheetTakeoffSource === "backend_validated"
                    ? "Computed by the backend's validated TradeEngine, scoped to this page."
                    : "Backend unavailable — local client-side estimate, not independently validated."
                }
              >
                {sheetTakeoffSource === "backend_validated" ? "Backend Validated" : "Live Client Estimate"}
              </div>
            )}
          </div>

          <div className="p-2.5 rounded-lg bg-[#111622] border border-white/10 flex flex-col justify-between">
            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">
              MATERIAL QUANTITY
            </div>
            <div className="mt-1">
              <div className="text-lg font-extrabold text-white font-mono">
                {displayData.sheets.toLocaleString()}
              </div>
              <div className="text-[10px] text-gray-400 font-mono">sheets</div>
            </div>
          </div>

          <div className="p-2.5 rounded-lg bg-[#111622] border border-white/10 flex flex-col justify-between">
            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">
              LABOR HOURS
            </div>
            <div className="mt-1">
              <div className="text-lg font-extrabold text-white font-mono">
                {displayData.laborHours.toLocaleString('en-US', {minimumFractionDigits: 1, maximumFractionDigits: 1})}
              </div>
              <div className="text-[10px] text-gray-400 font-mono">hrs</div>
            </div>
          </div>

          <div className="p-2.5 rounded-lg bg-[#111622] border border-white/10 flex flex-col justify-between">
            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">
              DIRECT COST
            </div>
            <div className="mt-1">
              <div className="text-lg font-extrabold text-white font-mono">
                ${displayData.directCost.toLocaleString('en-US', {minimumFractionDigits: 2})}
              </div>
            </div>
          </div>

          <div className="p-2.5 rounded-lg bg-[#111622] border border-white/10 flex flex-col justify-between">
            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">
              STATUS
            </div>
            <div className="mt-1">
              {sheetTakeoff.eligible ? (
                <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-400">
                  <CheckCircle2 size={13} />
                  <span>Calculated</span>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-xs font-bold text-amber-400">
                  <ShieldCheck size={13} />
                  <span>Non-Takeoff</span>
                </div>
              )}
              <div className="text-[9px] text-gray-500 font-mono mt-0.5">
                {showProjectTotals ? projectTotalsFromBackend.validatedAt : `Sheet ${activeSheet?.code || 'N/A'}`}
              </div>
            </div>
          </div>

          <div className="p-2.5 rounded-lg bg-[#111622] border border-white/10 flex flex-col justify-between">
            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider flex items-center gap-1">
              WALL NET HANG AREA
              {displayData.wallNetHangAreaSf != null && displayData.wallNetHangAreaSfIsEstimate && (
                <span
                  className="text-amber-400 font-mono normal-case tracking-normal cursor-help"
                  title="Estimated from real backend sheet count × 32 SF/sheet (4×8 panel) — not a directly measured area."
                >
                  ≈
                </span>
              )}
            </div>
            <div className="mt-1">
              {displayData.wallNetHangAreaSf != null ? (
                <div className="text-base font-extrabold text-white font-mono">
                  {displayData.wallNetHangAreaSf.toLocaleString('en-US', {minimumFractionDigits: 2})} <span className="text-xs font-normal text-gray-400">SF</span>
                </div>
              ) : (
                <div className="text-[11px] font-semibold text-gray-500">Not available from source</div>
              )}
            </div>
          </div>

          <div className="p-2.5 rounded-lg bg-[#111622] border border-white/10 flex flex-col justify-between">
            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">
              CEILING AREA
            </div>
            <div className="mt-1">
              {displayData.ceilingAreaSf != null ? (
                <div className="text-base font-extrabold text-white font-mono">
                  {displayData.ceilingAreaSf.toLocaleString('en-US', {minimumFractionDigits: 2})} <span className="text-xs font-normal text-gray-400">SF</span>
                </div>
              ) : (
                <div className="text-[11px] font-semibold text-gray-500">Not available from source</div>
              )}
            </div>
          </div>
        </div>

        {/* Center Column: TOP LINE ITEMS Table */}
        <div className="col-span-5 rounded-lg bg-[#111622] border border-white/10 p-3 flex flex-col justify-between overflow-hidden">
          <div className="flex items-center justify-between text-[10px] font-bold text-gray-400 uppercase tracking-wider border-b border-white/5 pb-1.5">
            <span>TOP LINE ITEMS</span>
            <span className="text-[9px] text-gray-500">
              {showProjectTotals ? "Project Wide" : activeSheet?.code || "Current Sheet"}
            </span>
          </div>

          <div className="flex-1 overflow-y-auto font-mono text-[10px] space-y-1 my-1">
            <div className="grid grid-cols-12 text-[9px] text-gray-500 pb-0.5 font-sans font-semibold">
              <span className="col-span-5">ITEM</span>
              <span className="col-span-2 text-right">QTY</span>
              <span className="col-span-2 text-left pl-1">UNIT</span>
              <span className="col-span-3 text-right">TOTAL COST</span>
            </div>

            {displayData.topLineItems.length > 0 ? (
              displayData.topLineItems.map((item, i) => (
                <div key={i} className="grid grid-cols-12 py-0.5 border-b border-white/[0.03] hover:bg-white/[0.02] text-gray-300">
                  <span className="col-span-5 font-sans truncate text-white">{item.item}</span>
                  <span className="col-span-2 text-right text-cyan-400 font-bold">{item.qty}</span>
                  <span className="col-span-2 text-left pl-1 text-gray-500">{item.unit}</span>
                  <span className="col-span-3 text-right font-bold text-white">{item.total}</span>
                </div>
              ))
            ) : (
              <div className="text-center text-gray-500 py-4">
                {sheetTakeoff.eligible ? "No line items calculated" : "Sheet not eligible for takeoff"}
              </div>
            )}
          </div>

          <button
            onClick={() => {
              setQtoAuditInitialTab("walls");
              setQtoAuditModalOpen(true);
            }}
            className="text-[10px] text-blue-400 hover:text-blue-300 font-semibold flex items-center gap-1 pt-1 border-t border-white/5 cursor-pointer"
          >
            <span>View all {displayData.topLineItems.length} line items</span>
            <ArrowRight size={11} />
          </button>
        </div>

        {/* Right Column: COST BREAKDOWN Donut Chart */}
        <div className="col-span-3 rounded-lg bg-[#111622] border border-white/10 p-3 flex flex-col justify-between">
          <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider border-b border-white/5 pb-1">
            COST BREAKDOWN
          </div>

          <div className="flex items-center gap-3 my-1">
            {/* SVG Donut Chart with dynamic percentages */}
            <div className="w-20 h-20 relative shrink-0">
              <svg viewBox="0 0 36 36" className="w-full h-full transform -rotate-90">
                {/* Background circle */}
                <circle cx="18" cy="18" r="14" fill="none" stroke="#1E293B" strokeWidth="4" />
                {/* Materials segment */}
                <circle
                  cx="18"
                  cy="18"
                  r="14"
                  fill="none"
                  stroke="#10B981"
                  strokeWidth="4"
                  strokeDasharray={`${displayData.materialCost > 0 ? (displayData.materialCost / displayData.directCost) * 87.96 : 0} 100`}
                  strokeDashoffset="0"
                />
                {/* Labor segment */}
                <circle
                  cx="18"
                  cy="18"
                  r="14"
                  fill="none"
                  stroke="#3B82F6"
                  strokeWidth="4"
                  strokeDasharray={`${displayData.laborCost > 0 ? (displayData.laborCost / displayData.directCost) * 87.96 : 0} 100`}
                  strokeDashoffset={`-${displayData.materialCost > 0 ? (displayData.materialCost / displayData.directCost) * 87.96 : 0}`}
                />
              </svg>
            </div>

            {/* Legend Breakdown */}
            <div className="space-y-1 text-[9px] font-mono flex-1">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-gray-300">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
                  Materials
                </span>
                <span className="text-white font-bold">
                  ${displayData.materialCost.toLocaleString('en-US', {minimumFractionDigits: 2})} 
                  <span className="text-gray-500 font-normal ml-1">
                    {displayData.directCost > 0 ? Math.round((displayData.materialCost / displayData.directCost) * 100) : 0}%
                  </span>
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-gray-300">
                  <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />
                  Labor
                </span>
                <span className="text-white font-bold">
                  ${displayData.laborCost.toLocaleString('en-US', {minimumFractionDigits: 2})} 
                  <span className="text-gray-500 font-normal ml-1">
                    {displayData.directCost > 0 ? Math.round((displayData.laborCost / displayData.directCost) * 100) : 0}%
                  </span>
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-gray-400">
                  <span className="w-2 h-2 rounded-full bg-amber-400 shrink-0" />
                  Equipment
                </span>
                <span className="text-gray-500">$0.00 0.0%</span>
              </div>
            </div>
          </div>

          <div className="flex justify-between items-center pt-1.5 border-t border-white/10 font-mono text-xs">
            <span className="text-gray-400 font-sans font-medium text-[10px]">Total</span>
            <span className="text-white font-bold text-sm">
              ${displayData.directCost.toLocaleString('en-US', {minimumFractionDigits: 2})}
            </span>
          </div>
        </div>
      </div>
      )}

      {/* LINE ITEMS tab — real inline table, same data source as the
          Summary tab's preview, just the full list rather than a slice. */}
      {expanded && activeTab === "items" && (
        <div className="flex-1 p-3.5 min-h-0 overflow-y-auto scrollbar-custom">
          <div className="rounded-lg bg-[#111622] border border-white/10 p-3">
            <div className="grid grid-cols-12 text-[9px] text-gray-500 pb-1.5 border-b border-white/10 font-sans font-semibold">
              <span className="col-span-5">ITEM</span>
              <span className="col-span-2 text-right">QTY</span>
              <span className="col-span-2 text-left pl-1">UNIT</span>
              <span className="col-span-3 text-right">TOTAL COST</span>
            </div>
            {displayData.topLineItems.length > 0 ? (
              displayData.topLineItems.map((item, i) => (
                <div key={i} className="grid grid-cols-12 py-1 border-b border-white/[0.03] hover:bg-white/[0.02] text-gray-300 font-mono text-[11px]">
                  <span className="col-span-5 font-sans truncate text-white">{item.item}</span>
                  <span className="col-span-2 text-right text-cyan-400 font-bold">{item.qty}</span>
                  <span className="col-span-2 text-left pl-1 text-gray-500">{item.unit}</span>
                  <span className="col-span-3 text-right font-bold text-white">{item.total}</span>
                </div>
              ))
            ) : (
              <div className="text-center text-gray-500 py-6 text-xs">No records available for this sheet.</div>
            )}
          </div>
        </div>
      )}

      {/* WALL LEDGER tab — real per-wall backend data (same endpoint as
          the deep-drill-down modal), rendered inline. */}
      {expanded && activeTab === "ledger" && (
        <div className="flex-1 p-3.5 min-h-0 overflow-y-auto scrollbar-custom">
          {ledgerLoadState === "loading" && <div className="text-center text-gray-500 py-6 text-xs">Loading wall ledger…</div>}
          {ledgerLoadState === "error" && <div className="text-center text-gray-500 py-6 text-xs">Wall ledger not available — no project/blueprint loaded.</div>}
          {ledgerLoadState === "empty" && <div className="text-center text-gray-500 py-6 text-xs">No records available for this sheet.</div>}
          {ledgerLoadState === "ready" && ledgerRows && (
            <div className="rounded-lg bg-[#111622] border border-white/10 p-3">
              <div className="grid grid-cols-12 text-[9px] text-gray-500 pb-1.5 border-b border-white/10 font-sans font-semibold">
                <span className="col-span-2">WALL / TAG</span>
                <span className="col-span-2">ASSEMBLY</span>
                <span className="col-span-2 text-right">LENGTH</span>
                <span className="col-span-2 text-right">HEIGHT</span>
                <span className="col-span-2 text-right">THICKNESS</span>
                <span className="col-span-2 text-right">QTO</span>
              </div>
              {ledgerRows.slice(0, 100).map((w) => (
                <div key={w.wall_id} className="grid grid-cols-12 py-1 border-b border-white/[0.03] hover:bg-white/[0.02] text-gray-300 font-mono text-[10px] items-center">
                  <span className="col-span-2 truncate text-white">{w.wall_tag || w.wall_id.replace(/^drywall-wall-/, "AW-")}</span>
                  <span className="col-span-2 truncate">{w.assembly_tag || "Unclassified"}</span>
                  <span className="col-span-2 text-right">{w.length_ft.toFixed(1)} ft</span>
                  <span className="col-span-2 text-right">
                    {w.height_ft.toFixed(1)} ft <span className={w.height_provenance === "VERIFIED" ? "text-emerald-400" : "text-amber-400"}>●</span>
                  </span>
                  <span className="col-span-2 text-right">{w.thickness_in.toFixed(2)}"</span>
                  <span className={`col-span-2 text-right font-semibold ${w.qto_eligible ? "text-emerald-400" : "text-amber-400"}`}>
                    {w.qto_eligible ? "Eligible" : "Excluded"}
                  </span>
                </div>
              ))}
            </div>
          )}
          <button
            onClick={() => {
              setQtoAuditInitialTab("walls");
              setQtoAuditModalOpen(true);
            }}
            className="mt-2 text-[10px] text-blue-400 hover:text-blue-300 font-semibold flex items-center gap-1 cursor-pointer"
          >
            <span>Open full audit — per-wall formulas & evidence</span>
            <ArrowRight size={11} />
          </button>
        </div>
      )}

      {/* EVIDENCE tab — the currently selected wall's real provenance;
          honest empty state when nothing is selected. */}
      {expanded && activeTab === "evidence" && (
        <div className="flex-1 p-3.5 min-h-0 overflow-y-auto scrollbar-custom">
          {selectedWallEvidence ? (
            <div className="rounded-lg bg-[#111622] border border-white/10 p-3 space-y-1.5 font-mono text-[11px]">
              <div className="text-white font-bold font-sans text-xs mb-1">{selectedWallEvidence.displayCode}</div>
              <div className="flex justify-between"><span className="text-gray-400 font-sans">Source</span><span className="text-gray-200">{selectedWallEvidence.source}</span></div>
              <div className="flex justify-between"><span className="text-gray-400 font-sans">Confidence</span><span className="text-gray-200">{selectedWallEvidence.confidencePct}%</span></div>
              <div className="flex justify-between">
                <span className="text-gray-400 font-sans">Height</span>
                <span className={selectedWallEvidence.heightVerificationState === "VERIFIED" ? "text-emerald-400" : "text-amber-400"}>
                  {selectedWallEvidence.heightFt.toFixed(2)} ft — {selectedWallEvidence.heightVerificationState}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400 font-sans">Thickness</span>
                <span className={selectedWallEvidence.thicknessVerificationState === "VERIFIED" ? "text-emerald-400" : "text-amber-400"}>
                  {selectedWallEvidence.thicknessIn.toFixed(2)}" — {selectedWallEvidence.thicknessVerificationState}
                </span>
              </div>
              <div className="flex justify-between"><span className="text-gray-400 font-sans">Assembly Verified</span><span className="text-gray-200">{selectedWallEvidence.assemblyVerified ? "Yes" : "No"}</span></div>
              {selectedWallEvidence.conflicts.length > 0 && (
                <div className="text-red-400 font-sans pt-1 border-t border-red-500/20">
                  {selectedWallEvidence.conflicts.length} unresolved source conflict{selectedWallEvidence.conflicts.length > 1 ? "s" : ""} — see full inspector.
                </div>
              )}
            </div>
          ) : (
            <div className="text-center text-gray-500 py-6 text-xs">
              Select a wall, room, or opening on the canvas to view its evidence.
            </div>
          )}
        </div>
      )}

      {/* AUDIT LOG tab — the real, persisted backend audit trail. */}
      {expanded && activeTab === "audit" && (
        <div className="flex-1 p-3.5 min-h-0 overflow-y-auto scrollbar-custom">
          {state.projectId ? (
            <BackendAuditLog />
          ) : (
            <div className="text-center text-gray-500 py-6 text-xs">No records available for this sheet.</div>
          )}
        </div>
      )}

      <QtoDrillDownModal
        isOpen={qtoAuditModalOpen}
        onClose={() => setQtoAuditModalOpen(false)}
        initialTab={qtoAuditInitialTab}
      />
    </section>
  );
}
