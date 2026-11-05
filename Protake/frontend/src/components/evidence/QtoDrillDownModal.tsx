import React, { useState, useEffect, useMemo } from "react";
import {
  X,
  Search,
  Ruler,
  FileSpreadsheet,
  Info,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { useApp } from "@/state/AppContext";
import { formatWallThickness } from "@/lib/units";
import {
  BackendApiService,
  type TradeTakeoffResponse,
  type WallLedgerResponse,
  type WallLedgerEntry,
} from "@/api/backendApi";

interface QtoDrillDownModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTab?: "summary" | "walls" | "openings" | "labor";
}

type LoadState = "idle" | "loading" | "ready" | "empty" | "error";

// Maps a wall_ledger wall_id ("drywall-wall-123") back to the frontend
// detection id ("backend-wall-123") so "Focus" buttons still work.
function ledgerIdToDetectionId(wallId: string): string {
  const numeric = wallId.replace(/^drywall-wall-/, "");
  return `backend-wall-${numeric}`;
}

export default function QtoDrillDownModal({ isOpen, onClose, initialTab = "summary" }: QtoDrillDownModalProps) {
  const { state, dispatch } = useApp();
  const [activeTab, setActiveTab] = useState<"summary" | "walls" | "openings" | "labor">(initialTab);
  const [search, setSearch] = useState("");

  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [takeoff, setTakeoff] = useState<TradeTakeoffResponse | null>(null);
  const [ledger, setLedger] = useState<WallLedgerResponse | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    if (!state.projectId || !state.blueprintId) {
      setLoadState("error");
      setErrorMessage("No project/blueprint loaded.");
      return;
    }

    let cancelled = false;
    setLoadState("loading");
    setErrorMessage(null);

    Promise.all([
      BackendApiService.fetchTradeTakeoff(state.projectId, state.blueprintId, "drywall"),
      BackendApiService.fetchDrywallWallLedger(state.projectId, state.blueprintId),
    ])
      .then(([takeoffRes, ledgerRes]) => {
        if (cancelled) return;
        setTakeoff(takeoffRes);
        setLedger(ledgerRes);
        setLoadState("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        const status = err?.status ?? err?.response?.status;
        if (status === 404) {
          setLoadState("empty");
        } else {
          setLoadState("error");
          setErrorMessage(err instanceof Error ? err.message : "Failed to load drywall takeoff.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isOpen, state.projectId, state.blueprintId]);

  const wallRows = ledger?.wall_ledger ?? [];

  const filteredWalls = useMemo(() => {
    if (!search) return wallRows;
    const s = search.toLowerCase();
    return wallRows.filter(
      (r) => r.wall_id.toLowerCase().includes(s) || (r.assembly_tag ?? "").toLowerCase().includes(s) || (r.wall_tag ?? "").toLowerCase().includes(s)
    );
  }, [wallRows, search]);

  const evidence = (takeoff?.evidence ?? {}) as Record<string, any>;
  const qtoGating = evidence.qto_gating ?? {};
  const framingQto = evidence.framing_qto ?? {};
  const independentRecompute = evidence.independent_qto_recomputation ?? {};
  const crossSheet = evidence.cross_sheet_reconciliation ?? {};

  const openingsAgg = useMemo(() => {
    const withOpenings = wallRows.filter((r) => r.openings_count > 0);
    const totalOpenings = wallRows.reduce((sum, r) => sum + r.openings_count, 0);
    const totalDeduction = wallRows.reduce((sum, r) => sum + r.opening_deduction_sf, 0);
    return { withOpenings, totalOpenings, totalDeduction };
  }, [wallRows]);

  if (!isOpen) return null;

  const recomputeAgrees = independentRecompute && typeof independentRecompute.agreement === "boolean"
    ? independentRecompute.agreement
    : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-4">
      <div className="flex flex-col w-full max-w-6xl h-[88vh] rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">

        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)] bg-[var(--color-panel-2)] shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-[var(--color-primary)]/15 text-[var(--color-primary-hover)]">
              <FileSpreadsheet size={22} />
            </div>
            <div>
              <h2 className="text-base font-bold text-[var(--color-text-primary)] flex items-center gap-2">
                Drywall Takeoff — Engineering Audit Ledger & Provenance
                {loadState === "ready" && recomputeAgrees !== null && (
                  <span
                    className={`text-xs px-2.5 py-0.5 rounded-full border font-mono font-medium ${
                      recomputeAgrees
                        ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                        : "bg-amber-500/15 text-amber-400 border-amber-500/30"
                    }`}
                  >
                    {recomputeAgrees ? "Independent Recompute Agrees" : "Recompute Mismatch — Review Required"}
                  </span>
                )}
              </h2>
              <p className="text-xs text-[var(--color-text-secondary)] font-mono">
                {loadState === "ready"
                  ? `Blueprint ${state.blueprintId} · ${ledger?.walls_included_in_qto ?? 0} Walls in QTO / ${ledger?.walls_excluded_from_qto ?? 0} Excluded · ${openingsAgg.totalOpenings} Openings`
                  : "Loading real takeoff data from backend…"}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-[var(--color-text-secondary)] hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Loading / Empty / Error states */}
        {loadState === "loading" && (
          <div className="flex-1 flex items-center justify-center gap-2 text-[var(--color-text-secondary)]">
            <Loader2 size={18} className="animate-spin" />
            <span className="text-sm">Loading takeoff from backend…</span>
          </div>
        )}

        {loadState === "empty" && (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center px-8">
            <AlertTriangle size={28} className="text-amber-400" />
            <p className="text-sm text-[var(--color-text-primary)] font-semibold">No drywall takeoff has been computed for this blueprint yet.</p>
            <p className="text-xs text-[var(--color-text-secondary)] max-w-md">
              Run the drywall takeoff (POST /takeoffs/drywall) first — this panel only displays backend-computed,
              provenance-backed values and does not calculate quantities itself.
            </p>
          </div>
        )}

        {loadState === "error" && (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center px-8">
            <AlertTriangle size={28} className="text-rose-400" />
            <p className="text-sm text-[var(--color-text-primary)] font-semibold">Failed to load takeoff data.</p>
            <p className="text-xs text-[var(--color-text-secondary)]">{errorMessage}</p>
          </div>
        )}

        {loadState === "ready" && takeoff && ledger && (
          <>
            {/* KPI Strip — every value read directly from the backend response */}
            <div className="grid grid-cols-4 md:grid-cols-7 gap-2 px-6 py-3 border-b border-[var(--color-border)] bg-black/30 text-xs font-mono shrink-0">
              <div className="p-2 rounded bg-white/5 cursor-pointer hover:bg-white/10 transition-colors" onClick={() => setActiveTab("walls")}>
                <div className="text-[10px] text-gray-400">Total Walls</div>
                <div className="text-sm font-bold text-[var(--color-text-primary)]">{ledger.total_walls_analyzed} Walls</div>
                <div className="text-[9px] text-emerald-400">{ledger.walls_included_in_qto} Eligible / {ledger.walls_excluded_from_qto} Excluded</div>
              </div>
              <div className="p-2 rounded bg-white/5">
                <div className="text-[10px] text-gray-400">Wall Area (Net)</div>
                <div className="text-sm font-bold text-[var(--color-text-primary)]">{(qtoGating.wall_area_sqft ?? 0).toLocaleString()} SF</div>
                <div className="text-[9px] text-gray-500">{qtoGating.assumed_height_used ? "Height Assumed" : "Height Verified"}</div>
              </div>
              <div className="p-2 rounded bg-rose-500/10 border border-rose-500/20 cursor-pointer hover:bg-rose-500/15 transition-colors" onClick={() => setActiveTab("openings")}>
                <div className="text-[10px] text-rose-400">Opening Deduct</div>
                <div className="text-sm font-bold text-rose-400">-{openingsAgg.totalDeduction.toLocaleString()} SF</div>
                <div className="text-[9px] text-rose-300/70">{openingsAgg.totalOpenings} openings, from ledger</div>
              </div>
              <div className="p-2 rounded bg-cyan-500/10 border border-cyan-500/20">
                <div className="text-[10px] text-cyan-400">Ceiling Area</div>
                <div className="text-sm font-bold text-cyan-400">+{(qtoGating.ceiling_area_sqft ?? 0).toLocaleString()} SF</div>
                <div className="text-[9px] text-cyan-300/70">Separate waste %</div>
              </div>
              <div className="p-2 rounded bg-white/5">
                <div className="text-[10px] text-gray-400">Material Qty</div>
                <div className="text-sm font-bold text-[var(--color-text-primary)]">{takeoff.material_quantity.toLocaleString()} {takeoff.material_unit}</div>
                <div className="text-[9px] text-gray-500">from TradeTakeoffRead</div>
              </div>
              <div className="p-2 rounded bg-white/5">
                <div className="text-[10px] text-gray-400">Direct Cost</div>
                <div className="text-sm font-bold text-[var(--color-primary-hover)]">${takeoff.direct_cost.toLocaleString()}</div>
                <div className="text-[9px] text-gray-500">material + labor</div>
              </div>
              <div className={`p-2 rounded border ${takeoff.status === "validated" ? "bg-emerald-500/15 border-emerald-500/30" : "bg-amber-500/15 border-amber-500/30"}`}>
                <div className={`text-[10px] font-semibold ${takeoff.status === "validated" ? "text-emerald-400" : "text-amber-400"}`}>Status</div>
                <div className={`text-base font-bold ${takeoff.status === "validated" ? "text-emerald-400" : "text-amber-400"}`}>{takeoff.status}</div>
                <div className={`text-[9px] ${takeoff.status === "validated" ? "text-emerald-300/70" : "text-amber-300/70"}`}>{Math.round(takeoff.confidence * 100)}% confidence</div>
              </div>
            </div>

            {/* Tab Navigation & Search */}
            <div className="flex items-center justify-between px-6 py-2.5 border-b border-[var(--color-border)] bg-[var(--color-panel-2)] shrink-0">
              <div className="flex items-center gap-2 text-xs">
                <button
                  onClick={() => setActiveTab("summary")}
                  className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                    activeTab === "summary" ? "bg-[var(--color-primary)] text-white font-semibold" : "text-[var(--color-text-secondary)] hover:bg-white/5"
                  }`}
                >
                  Summary & Provenance
                </button>
                <button
                  onClick={() => setActiveTab("walls")}
                  className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                    activeTab === "walls" ? "bg-[var(--color-primary)] text-white font-semibold" : "text-[var(--color-text-secondary)] hover:bg-white/5"
                  }`}
                >
                  Wall-by-Wall Ledger ({wallRows.length})
                </button>
                <button
                  onClick={() => setActiveTab("openings")}
                  className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                    activeTab === "openings" ? "bg-[var(--color-primary)] text-white font-semibold" : "text-[var(--color-text-secondary)] hover:bg-white/5"
                  }`}
                >
                  Opening Deductions ({openingsAgg.withOpenings.length} walls)
                </button>
                <button
                  onClick={() => setActiveTab("labor")}
                  className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
                    activeTab === "labor" ? "bg-[var(--color-primary)] text-white font-semibold" : "text-[var(--color-text-secondary)] hover:bg-white/5"
                  }`}
                >
                  Labor & Costs
                </button>
              </div>

              {(activeTab === "walls" || activeTab === "openings") && (
                <div className="relative w-72">
                  <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search Wall ID, tag, or assembly..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-full bg-black/40 border border-white/10 rounded-md pl-8 pr-3 py-1 text-xs text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-primary)] font-mono"
                  />
                </div>
              )}
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">

              {/* Tab 1: Summary & Provenance */}
              {activeTab === "summary" && (
                <div className="space-y-4 text-xs">
                  <div className="rounded-lg border border-white/10 bg-black/25 p-4 space-y-3">
                    <h3 className="font-bold text-sm text-[var(--color-text-primary)] flex items-center gap-2">
                      <Ruler size={16} className="text-cyan-400" />
                      QTO Gating (from backend evidence.qto_gating)
                    </h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 font-mono text-xs">
                      <div className="p-2.5 rounded bg-black/30 border border-white/5">
                        <div className="text-gray-400 text-[10px]">Total Walls</div>
                        <div className="text-sm font-semibold text-[var(--color-text-primary)]">{qtoGating.total_architectural_walls ?? "—"}</div>
                      </div>
                      <div className="p-2.5 rounded bg-black/30 border border-white/5">
                        <div className="text-gray-400 text-[10px]">QTO Eligible</div>
                        <div className="text-sm font-semibold text-emerald-400">{qtoGating.qto_eligible_walls ?? "—"}</div>
                      </div>
                      <div className="p-2.5 rounded bg-black/30 border border-white/5">
                        <div className="text-gray-400 text-[10px]">QTO Blocked</div>
                        <div className="text-sm font-semibold text-amber-400">{qtoGating.qto_blocked_walls ?? "—"}</div>
                      </div>
                      <div className="p-2.5 rounded bg-black/30 border border-white/5">
                        <div className="text-gray-400 text-[10px]">Opening Count</div>
                        <div className="text-sm font-semibold text-[var(--color-text-primary)]">{qtoGating.opening_count ?? "—"}</div>
                      </div>
                    </div>
                    {Object.keys(ledger.exclusion_summary).length > 0 && (
                      <div className="p-3 rounded bg-amber-500/10 border border-amber-500/20 space-y-1">
                        <div className="text-[10px] uppercase tracking-wide text-amber-400 font-semibold">Excluded Wall Reasons</div>
                        {Object.entries(ledger.exclusion_summary).map(([reason, count]) => (
                          <div key={reason} className="flex justify-between text-[11px] text-gray-300">
                            <span>{reason}</span>
                            <span className="font-semibold text-amber-300">{count}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="rounded-lg border border-white/10 bg-black/25 p-4 space-y-2.5">
                    <h4 className="font-semibold text-xs text-[var(--color-text-primary)] uppercase tracking-wide flex items-center gap-2">
                      <Info size={14} className="text-amber-400" />
                      Height, Assembly & Cross-Sheet Provenance
                    </h4>
                    <div className="grid grid-cols-3 gap-3 font-mono text-xs">
                      <div className="p-3 rounded bg-white/5 space-y-1">
                        <div className={`font-semibold text-[11px] ${qtoGating.assumed_height_used ? "text-amber-300" : "text-emerald-300"}`}>Plate Height</div>
                        <div className="text-gray-300">
                          {qtoGating.assumed_height_used
                            ? `${qtoGating.assumed_height_ft ?? "9.0"} FT applied — no RCP/section/schedule evidence found for this project.`
                            : "Resolved from RCP, partition schedule, or section callouts across the sheet set."}
                        </div>
                        <div className="text-[9px] text-gray-500 font-normal">
                          [{qtoGating.assumed_height_used ? "ASSUMED — PROJECT DEFAULT" : "VERIFIED — PROJECT EVIDENCE"}]
                        </div>
                      </div>
                      <div className="p-3 rounded bg-white/5 space-y-1">
                        <div className="text-cyan-300 font-semibold text-[11px]">Cross-Sheet Reconciliation</div>
                        <div className="text-gray-300">
                          {crossSheet.sheets_indexed ?? 0} sheets indexed · {crossSheet.partition_schedules_found ?? 0} partition schedules · {crossSheet.door_schedules_found ?? 0} door schedules found.
                        </div>
                        <div className="text-[9px] text-gray-500 font-normal">[FROM ProjectBlueprintIndex]</div>
                      </div>
                      <div className="p-3 rounded bg-white/5 space-y-1">
                        <div className="text-purple-300 font-semibold text-[11px]">Independent Recomputation</div>
                        <div className="text-gray-300">
                          Primary: {(independentRecompute.primary_wall_area_sqft ?? 0).toLocaleString()} SF vs. Independent: {(independentRecompute.independent_wall_area_sqft ?? 0).toLocaleString()} SF
                        </div>
                        <div className={`text-[9px] font-normal ${recomputeAgrees ? "text-emerald-400" : "text-amber-400"}`}>
                          [{recomputeAgrees === null ? "NOT AVAILABLE" : recomputeAgrees ? "AGREES" : "MISMATCH"}]
                        </div>
                      </div>
                    </div>
                  </div>

                  {takeoff.validation_reasons && takeoff.validation_reasons.length > 0 && (
                    <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 space-y-1.5">
                      <h4 className="font-semibold text-xs text-amber-400 uppercase tracking-wide">Validation Reasons</h4>
                      {takeoff.validation_reasons.map((reason, i) => (
                        <div key={i} className="text-[11px] text-gray-300 font-mono">• {reason}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Tab 2: Wall-by-Wall Ledger */}
              {activeTab === "walls" && (
                <div className="border border-white/10 rounded-lg overflow-hidden bg-black/30">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-black/60 text-gray-400 uppercase text-[10px] border-b border-white/10">
                      <tr>
                        <th className="p-2.5">Wall ID</th>
                        <th className="p-2.5">Assembly</th>
                        <th className="p-2.5 text-right">Length</th>
                        <th className="p-2.5 text-right">Thick</th>
                        <th className="p-2.5 text-right">Height</th>
                        <th className="p-2.5 text-center">Sides</th>
                        <th className="p-2.5 text-right">Gross SF</th>
                        <th className="p-2.5 text-right text-rose-400">Deduct SF</th>
                        <th className="p-2.5 text-right text-cyan-400 font-bold">Net SF</th>
                        <th className="p-2.5 text-center">QTO</th>
                        <th className="p-2.5 text-center">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {filteredWalls.map((row: WallLedgerEntry) => (
                        <tr key={row.wall_id} className="hover:bg-white/5 transition-colors">
                          <td className="p-2.5 font-bold text-[var(--color-primary-hover)]">
                            {row.wall_id.replace("drywall-wall-", "W-")}
                            {row.wall_tag && <span className="ml-1.5 text-[9px] text-gray-500">[{row.wall_tag}]</span>}
                          </td>
                          <td className="p-2.5 text-gray-300">
                            {row.assembly_tag ?? "—"}
                            <span className={`ml-1.5 text-[9px] px-1.5 py-0.2 rounded ${row.assembly_verified ? "bg-emerald-500/15 text-emerald-300" : "bg-gray-500/20 text-gray-400"}`}>
                              {row.assembly_verified ? "VERIFIED" : "UNVERIFIED"}
                            </span>
                          </td>
                          <td className="p-2.5 text-right">{row.length_ft.toFixed(2)}'</td>
                          <td className="p-2.5 text-right text-gray-400">{formatWallThickness(row.thickness_in / 12, state.unitSystem)}</td>
                          <td className="p-2.5 text-right">
                            {row.height_ft.toFixed(1)}'
                            <span className={`ml-1 text-[9px] ${row.height_provenance === "VERIFIED" ? "text-emerald-400" : "text-amber-400"}`}>
                              {row.height_provenance === "VERIFIED" ? "✓" : "~"}
                            </span>
                          </td>
                          <td className="p-2.5 text-center">{row.sides_to_hang}</td>
                          <td className="p-2.5 text-right">{row.gross_sf.toFixed(1)}</td>
                          <td className="p-2.5 text-right text-rose-400 font-medium">
                            {row.opening_deduction_sf > 0 ? `-${row.opening_deduction_sf.toFixed(1)}` : "—"}
                          </td>
                          <td className="p-2.5 text-right text-cyan-400 font-bold">{row.net_sf.toFixed(1)}</td>
                          <td className="p-2.5 text-center">
                            {row.qto_eligible ? (
                              <span className="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400 text-[10px]">Included</span>
                            ) : (
                              <span className="px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 text-[10px]" title={row.qto_block_reason ?? undefined}>
                                Excluded
                              </span>
                            )}
                          </td>
                          <td className="p-2.5 text-center">
                            <button
                              onClick={() => {
                                dispatch({ type: "SELECT_DETECTION", id: ledgerIdToDetectionId(row.wall_id) });
                                onClose();
                              }}
                              className="px-2.5 py-1 rounded bg-white/10 hover:bg-[var(--color-primary)] text-white text-[10px] transition-colors cursor-pointer"
                            >
                              Focus
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Tab 3: Opening Deductions (per-wall aggregate — the backend does not
                  yet expose a per-opening ledger; see Phase 6 of the migration plan) */}
              {activeTab === "openings" && (
                <div className="space-y-3">
                  <div className="text-[11px] text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-lg p-3">
                    The backend currently reports opening deductions aggregated per host wall, not as an individually
                    host-bound opening ledger. Each row below is one wall with ≥1 opening; per-opening detail will
                    land once the opening host-binding work (migration Phase 6) ships.
                  </div>
                  <div className="border border-white/10 rounded-lg overflow-hidden bg-black/30">
                    <table className="w-full text-left text-xs font-mono">
                      <thead className="bg-black/60 text-gray-400 uppercase text-[10px] border-b border-white/10">
                        <tr>
                          <th className="p-2.5">Host Wall ID</th>
                          <th className="p-2.5 text-center">Opening Count</th>
                          <th className="p-2.5 text-right text-rose-400 font-bold">Deduction SF</th>
                          <th className="p-2.5 text-center">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {openingsAgg.withOpenings.map((row) => (
                          <tr key={row.wall_id} className="hover:bg-white/5 transition-colors">
                            <td className="p-2.5 font-bold text-cyan-400">{row.wall_id.replace("drywall-wall-", "W-")}</td>
                            <td className="p-2.5 text-center">{row.openings_count}</td>
                            <td className="p-2.5 text-right text-rose-400 font-bold">-{row.opening_deduction_sf.toFixed(1)}</td>
                            <td className="p-2.5 text-center">
                              <button
                                onClick={() => {
                                  dispatch({ type: "SELECT_DETECTION", id: ledgerIdToDetectionId(row.wall_id) });
                                  onClose();
                                }}
                                className="px-2.5 py-1 rounded bg-white/10 hover:bg-[var(--color-primary)] text-white text-[10px] transition-colors cursor-pointer"
                              >
                                Focus
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Tab 4: Labor & Costs */}
              {activeTab === "labor" && (
                <div className="space-y-4 text-xs font-mono">
                  <div className="grid grid-cols-3 gap-3">
                    <div className="p-3.5 rounded-lg border border-white/10 bg-black/25 space-y-1">
                      <div className="text-gray-400 text-[11px]">Material Quantity</div>
                      <div className="text-lg font-bold text-cyan-400">{takeoff.material_quantity.toLocaleString()} {takeoff.material_unit}</div>
                    </div>
                    <div className="p-3.5 rounded-lg border border-white/10 bg-black/25 space-y-1">
                      <div className="text-gray-400 text-[11px]">Labor Hours</div>
                      <div className="text-lg font-bold text-amber-400">{takeoff.labor_hours.toLocaleString()} hrs</div>
                    </div>
                    <div className="p-3.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 space-y-1">
                      <div className="text-emerald-400 font-semibold text-[11px]">Direct Cost</div>
                      <div className="text-xl font-bold text-emerald-400">${takeoff.direct_cost.toLocaleString()}</div>
                    </div>
                  </div>

                  <div className="rounded-lg border border-white/10 bg-black/25 p-4 space-y-2">
                    <div className="text-xs font-semibold uppercase text-gray-400">Cost Breakdown (from TradeTakeoffRead)</div>
                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <div className="p-2.5 rounded bg-white/5">
                        <div className="text-gray-400">Material Cost</div>
                        <div className="text-sm font-bold text-white">${takeoff.material_cost.toLocaleString()}</div>
                      </div>
                      <div className="p-2.5 rounded bg-white/5">
                        <div className="text-gray-400">Labor Cost</div>
                        <div className="text-sm font-bold text-white">${takeoff.labor_cost.toLocaleString()}</div>
                      </div>
                      <div className="p-2.5 rounded bg-emerald-500/15 border border-emerald-500/30">
                        <div className="text-emerald-400 font-semibold">Total Direct Cost</div>
                        <div className="text-base font-bold text-emerald-400">${takeoff.direct_cost.toLocaleString()}</div>
                      </div>
                    </div>
                  </div>

                  {takeoff.items && takeoff.items.length > 0 && (
                    <div className="rounded-lg border border-white/10 bg-black/25 p-4 space-y-2">
                      <div className="text-xs font-semibold uppercase text-gray-400">Line Items</div>
                      <div className="space-y-1.5">
                        {takeoff.items.map((item) => (
                          <div key={item.id} className="p-2.5 rounded bg-white/5 space-y-0.5">
                            <div className="flex justify-between items-center">
                              <span className="text-gray-300">{item.label}</span>
                              <span className="text-white font-semibold">{item.quantity.toLocaleString()} {item.unit} · ${item.total_cost.toLocaleString()}</span>
                            </div>
                            {item.formula_breakdown && (
                              <div className="text-[10px] text-gray-500">{item.formula_breakdown}</div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {Object.keys(framingQto).length > 0 && (
                    <div className="rounded-lg border border-white/10 bg-black/25 p-4 space-y-2">
                      <div className="text-xs font-semibold uppercase text-gray-400">Framing QTO</div>
                      <pre className="text-[10px] text-gray-400 whitespace-pre-wrap">{JSON.stringify(framingQto, null, 2)}</pre>
                    </div>
                  )}
                </div>
              )}

            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between px-6 py-3 border-t border-[var(--color-border)] bg-[var(--color-panel-2)] text-xs shrink-0">
              <div className="text-[var(--color-text-secondary)] font-mono text-[11px]">
                Takeoff #{takeoff.id} · engine v{takeoff.engine_version ?? "?"} · {ledger.walls_included_in_qto} walls in QTO
              </div>
              <button
                onClick={onClose}
                className="px-5 py-2 rounded-md bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)] font-semibold transition-colors cursor-pointer"
              >
                Close Audit Ledger
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
