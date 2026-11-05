import { useMemo } from "react";
import { Check, X, Edit3, AlertCircle, Link2, Sparkles, ArrowRight } from "lucide-react";
import { useApp } from "@/state/AppContext";
import type { Detection } from "@/types";
import { buildWallInspectionData } from "@/lib/wallInspectorModel";
import Wall3DGeometryPreview from "@/components/blueprint/Wall3DGeometryPreview";
import { toast } from "sonner";

interface Props {
  detection: Detection;
}

export default function SelectedWallInspector({ detection: d }: Props) {
  const { state, dispatch, currentUserName } = useApp();

  const data = useMemo(() => {
    return buildWallInspectionData(d, state);
  }, [d, state]);

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-[#0B0E14] text-[11px] text-[#C9D1D9] select-none font-sans overflow-hidden">
      {/* Header */}
      <div className="p-3.5 border-b border-white/10 bg-[#111622]/90 flex items-start justify-between gap-2 shrink-0">
        <div className="space-y-1 min-w-0">
          <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">
            SELECTED WALL
          </div>
          <div className="text-base font-bold text-white font-mono flex items-center gap-2">
            <span>{data.displayCode}</span>
            {data.wallTag && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-white/10 text-cyan-400 font-bold border border-white/10">
                {data.wallTag}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 flex-wrap pt-0.5">
            <span
              className="px-2 py-0.5 rounded text-[10px] font-semibold border flex items-center gap-1"
              style={{
                backgroundColor: `${data.categoryColor}20`,
                borderColor: `${data.categoryColor}40`,
                color: data.categoryColor,
              }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: data.categoryColor }} />
              {data.categoryLabel}
            </span>
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                data.qtoEligible
                  ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                  : "bg-amber-500/15 text-amber-400 border-amber-500/30"
              }`}
            >
              {data.qtoEligible ? "✓ QTO Eligible" : "⚠ Excluded from QTO"}
            </span>
          </div>
        </div>

        {/* Data-driven Mini 3D Isometric Wall Icon */}
        <Wall3DGeometryPreview
          compact
          detection={d}
          lengthFt={data.lengthFt}
          heightFt={data.heightFt}
          thicknessIn={data.thicknessIn}
          categoryCode={data.categoryCode}
          categoryColor={data.categoryColor}
          categoryLabel={data.categoryLabel}
        />
      </div>

      {/* Scrollable Content Body */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-4 scrollbar-custom">
        {/* Conflict banner — schedule vs. detail-sheet disagreement. Never
            silently resolved; both disputed values shown with their exact
            source, most prominent item in the panel. */}
        {data.conflicts.length > 0 && (
          <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/40 space-y-1.5">
            <div className="flex items-center gap-1.5 text-[10px] font-bold text-red-400 uppercase tracking-wider">
              <AlertCircle size={12} />
              Conflict — Needs Review
            </div>
            {data.conflicts.map((c, i) => (
              <div key={i} className="text-[10px] font-mono space-y-0.5">
                <div className="text-gray-400">{c.field}:</div>
                {c.sources.map((s, j) => (
                  <div key={j} className="flex items-center justify-between text-red-200/90 pl-2">
                    <span>{s.value} — {s.method.replace(/_/g, " ")}</span>
                    <span className="text-red-300 font-semibold">{s.source}</span>
                  </div>
                ))}
              </div>
            ))}
            <div className="text-[9px] text-red-200/70 font-sans leading-relaxed pt-0.5 border-t border-red-500/20">
              Two real sources disagree — the system did not choose one automatically. Verify against the drawings and resolve manually.
            </div>
          </div>
        )}

        {/* Review & Triage Notice — for NEEDS_REVIEW or QTO-blocked walls */}
        {data.categoryCode === "NEEDS_REVIEW" && (
          <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/40 space-y-1.5">
            <div className="flex items-center gap-1.5 text-[10px] font-bold text-amber-400 uppercase tracking-wider">
              <AlertCircle size={12} />
              Review Required — Evidence Incomplete
            </div>
            <div className="text-[10px] font-mono text-gray-300 space-y-1">
              <div className="flex justify-between">
                <span className="text-gray-400 font-sans">Confidence:</span>
                <span className="text-amber-300 font-bold">{data.confidencePct}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400 font-sans">Primary Reason:</span>
                <span className="text-amber-200 font-sans text-right">{data.qtoReason}</span>
              </div>
              <div className="text-[9px] text-amber-200/70 font-sans leading-relaxed pt-1 border-t border-amber-500/20">
                This wall is flagged for estimator review because drawing evidence is ambiguous or incomplete. It remains gray on canvas and will not produce confirmed takeoff quantities until reviewed.
              </div>
            </div>
          </div>
        )}

        {/* 1. BASIC INFORMATION & PROVENANCE */}
        <div className="space-y-1.5">
          <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider flex items-center justify-between border-b border-white/5 pb-1">
            <span>DRAWING & PROVENANCE</span>
          </div>
          <div className="space-y-1 font-mono text-[10px]">
            <div className="flex justify-between py-0.5">
              <span className="text-gray-400 font-sans">Wall ID</span>
              <span className="text-white font-bold">{data.displayCode}</span>
            </div>
            <div className="flex justify-between py-0.5">
              <span className="text-gray-400 font-sans">Sheet / Page</span>
              <span className="text-gray-300">
                {data.sheetCode} • Page {data.pageNumber}
              </span>
            </div>
            <div className="flex justify-between py-0.5 items-center">
              <span className="text-gray-400 font-sans">Classification</span>
              <span className="flex items-center gap-1 font-semibold" style={{ color: data.categoryColor }}>
                <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: data.categoryColor }} />
                {data.categoryLabel}
              </span>
            </div>
            <div className="flex justify-between py-0.5">
              <span className="text-gray-400 font-sans">Wall Tag (Drawing)</span>
              <span className={data.wallTag ? "text-cyan-400 font-bold" : "text-gray-500"}>
                {data.wallTagDisplay}
              </span>
            </div>
            <div className="flex justify-between py-0.5">
              <span className="text-gray-400 font-sans">Source</span>
              <span className="text-gray-300">{data.source}</span>
            </div>
            <div className="flex justify-between py-0.5">
              <span className="text-gray-400 font-sans">Approval</span>
              <span
                className={
                  data.status === "approved"
                    ? "text-emerald-400 font-bold"
                    : data.status === "rejected"
                    ? "text-rose-400 font-bold"
                    : "text-amber-400 font-bold"
                }
              >
                {data.statusLabel}
              </span>
            </div>
            <div className="flex items-center justify-between pt-1">
              <span className="text-gray-400 font-sans">Confidence Score</span>
              <div className="flex items-center gap-2">
                <div className="w-20 h-1.5 rounded-full bg-white/10 overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-emerald-500 to-cyan-400 rounded-full"
                    style={{ width: `${data.confidencePct}%` }}
                  />
                </div>
                <span className="text-emerald-400 font-bold">{data.confidencePct}%</span>
              </div>
            </div>
          </div>
        </div>

        {/* 2. GEOMETRY */}
        <div className="space-y-2">
          <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider flex items-center justify-between border-b border-white/5 pb-1">
            <span>GEOMETRY & 3D PROFILE</span>
          </div>

          {/* Key Metrics Grid — every dimension carries an explicit
              VERIFIED/ASSUMED state next to its value, never silently
              implied. Length is always measured directly from the wall's
              own drawn geometry, so it has no separate source concept. */}
          <div className="grid grid-cols-3 gap-1.5 font-mono text-[10px] text-center">
            <div className="p-1.5 rounded bg-black/30 border border-white/5">
              <div className="text-[9px] text-gray-400 font-sans">Length</div>
              <div className="text-white font-bold mt-0.5">{data.lengthFt.toFixed(2)} ft</div>
              <div className="text-[7px] font-bold tracking-wide text-emerald-400 mt-0.5">VERIFIED</div>
            </div>
            <div className="p-1.5 rounded bg-black/30 border border-white/5">
              <div className="text-[9px] text-gray-400 font-sans">Height</div>
              <div className="text-cyan-400 font-bold mt-0.5">{data.heightFt.toFixed(2)} ft</div>
              <div className={`text-[7px] font-bold tracking-wide mt-0.5 ${data.heightVerificationState === "VERIFIED" ? "text-emerald-400" : "text-amber-400"}`}>
                {data.heightVerificationState}
              </div>
            </div>
            <div className="p-1.5 rounded bg-black/30 border border-white/5">
              <div className="text-[9px] text-gray-400 font-sans">Thickness</div>
              <div className="text-amber-300 font-bold mt-0.5">{data.thicknessIn.toFixed(2)}"</div>
              <div className={`text-[7px] font-bold tracking-wide mt-0.5 ${data.thicknessVerificationState === "VERIFIED" ? "text-emerald-400" : "text-amber-400"}`}>
                {data.thicknessVerificationState}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-1.5 font-mono text-[8px] text-center text-gray-500 -mt-1">
            <div />
            <div className="truncate" title={data.heightProvenance}>{data.heightProvenance.replace(/_/g, " ")}</div>
            <div className="truncate" title={data.thicknessSource}>{data.thicknessSource}</div>
          </div>

          <div className="grid grid-cols-2 gap-1.5 font-mono text-[10px]">
            <div className="flex justify-between p-1.5 rounded bg-black/20 border border-white/5">
              <span className="text-gray-400 font-sans">Face Area (1 Side)</span>
              <span className="text-cyan-400 font-bold">{data.wallFaceAreaSf.toFixed(2)} SF</span>
            </div>
            <div className="flex justify-between p-1.5 rounded bg-black/20 border border-white/5">
              <span className="text-gray-400 font-sans">Volume</span>
              <span className="text-gray-300">{data.volumeCf.toFixed(2)} CF</span>
            </div>
          </div>

          {/* Shared 3D Data-driven Geometry Preview */}
          <Wall3DGeometryPreview
            detection={d}
            lengthFt={data.lengthFt}
            heightFt={data.heightFt}
            thicknessIn={data.thicknessIn}
            categoryCode={data.categoryCode}
            categoryColor={data.categoryColor}
            categoryLabel={data.categoryLabel}
            wallTag={data.wallTag}
          />
        </div>

        {/* 3. CONSTRUCTION ASSEMBLY */}
        <div className="space-y-1.5">
          <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider flex items-center justify-between border-b border-white/5 pb-1">
            <span>CONSTRUCTION ASSEMBLY</span>
          </div>

          <div className="space-y-1 font-mono text-[10px]">
            <div className="flex justify-between py-0.5">
              <span className="text-gray-400 font-sans">Assembly</span>
              <span className="text-white font-bold truncate max-w-[170px]">{data.assemblyTag}</span>
            </div>
            <div className="flex justify-between py-0.5">
              <span className="text-gray-400 font-sans">Assembly Verified</span>
              <span className={data.assemblyVerified ? "text-emerald-400 font-bold" : "text-amber-400"}>
                {data.assemblyVerified ? "Yes (Schedule)" : "No (Unclassified)"}
              </span>
            </div>
            <div className="p-2 rounded bg-black/30 border border-white/5 text-[10px] font-sans text-gray-300 leading-relaxed mt-1">
              {data.assemblyDescription}
            </div>

            {/* Granular assembly fields — extracted from schedule and/or
                resolved detail sheet, honest "Not available from source"
                where nothing was confidently extracted. */}
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 pt-1.5 mt-1 border-t border-white/5">
              <div className="flex justify-between">
                <span className="text-gray-500 font-sans">Stud</span>
                <span className="text-gray-200 truncate max-w-[110px]">
                  {data.studDepthIn != null ? `${data.studDepthIn}"` : "Not available from source"}
                  {data.studGauge ? ` / ${data.studGauge}` : ""}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 font-sans">GWB (A)</span>
                <span className="text-gray-200 truncate max-w-[110px]">{data.boardTypeSideA ?? "Not available from source"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 font-sans">GWB (B)</span>
                <span className="text-gray-200 truncate max-w-[110px]">{data.boardTypeSideB ?? "Not available from source"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 font-sans">Sides</span>
                <span className="text-gray-200">{data.sidesToHang}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 font-sans">Fire Rating</span>
                <span className="text-gray-200">{data.fireRatingHr != null ? `${data.fireRatingHr} HR` : "Not available from source"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 font-sans">Acoustic (STC)</span>
                <span className="text-gray-200">{data.soundRatingStc != null ? data.soundRatingStc : "Not available from source"}</span>
              </div>
              <div className="col-span-2 flex justify-between">
                <span className="text-gray-500 font-sans">Insulation</span>
                <span className="text-gray-200">{data.insulation ?? "Not available from source"}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Field-level provenance — exactly which sheet/detail each
            engineering input came from, and how it was extracted. Only
            shown when at least one field has real resolved provenance. */}
        {Object.keys(data.fieldProvenance).length > 0 && (
          <div className="space-y-1.5">
            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider flex items-center justify-between border-b border-white/5 pb-1">
              <span>PROVENANCE</span>
            </div>
            <div className="space-y-0.5 font-mono text-[9px]">
              {Object.entries(data.fieldProvenance).map(([field, p]) => (
                <div key={field} className="flex items-center justify-between text-gray-300 py-0.5">
                  <span className="text-gray-500">{field.replace(/_/g, " ")}</span>
                  <span className="truncate max-w-[180px] text-right">
                    {p.value} — {p.sourceSheet ?? "?"}{p.sourceDetail ? `/Detail ${p.sourceDetail}` : ""} ({Math.round(p.confidence * 100)}%)
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 4. RELATIONSHIPS */}
        <div className="space-y-1.5">
          <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider flex items-center justify-between border-b border-white/5 pb-1">
            <span>RELATIONSHIPS</span>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1 font-mono text-[10px]">
              <div className="flex justify-between py-0.5">
                <span className="text-gray-400 font-sans">Left Room</span>
                <span className="text-white truncate max-w-[85px]">{data.leftRoom}</span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-gray-400 font-sans">Right Room</span>
                <span className="text-white truncate max-w-[85px]">{data.rightRoom}</span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-gray-400 font-sans">Adjacent Spaces</span>
                <span className="text-cyan-400 font-bold">{data.adjacentSpacesCount}</span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-gray-400 font-sans">Doors/Openings</span>
                <span className="text-amber-300 font-bold">{data.openingsCount}</span>
              </div>
              <div className="flex justify-between py-0.5">
                <span className="text-gray-400 font-sans">Columns</span>
                <span className="text-gray-400">{data.columnRelationship}</span>
              </div>
            </div>

            {/* Room Adjacency Diagram Graphic */}
            <div className="rounded-lg bg-black/40 border border-white/10 p-2 flex items-center justify-center relative overflow-hidden shadow-inner">
              <div className="flex items-center gap-1.5 font-mono text-[9px]">
                <div className="px-2 py-2 rounded bg-blue-500/15 border border-blue-500/30 text-blue-300 font-bold text-center max-w-[60px] truncate">
                  {data.adjacentRooms[0]?.id || "L"}
                </div>
                <div className="w-1.5 h-10 bg-cyan-400 rounded-full shadow-[0_0_8px_#06B6D4]" />
                <div className="px-2 py-2 rounded bg-indigo-500/15 border border-indigo-500/30 text-indigo-300 font-bold text-center max-w-[60px] truncate">
                  {data.adjacentRooms[1]?.id || "R"}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* 5. REFERENCES — schedule sheet / detail callout / section
            reference, each a clickable chip that jumps to the resolved
            sheet when it's part of the currently loaded drawing set.
            Unresolved references stay plain text, never a fake link. */}
        <div className="space-y-1.5">
          <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider flex items-center justify-between border-b border-white/5 pb-1">
            <span>REFERENCES</span>
          </div>
          <div className="space-y-1 font-mono text-[10px]">
            <div className="flex justify-between py-0.5 items-center">
              <span className="text-gray-400 font-sans">Schedule Sheet</span>
              {data.scheduleSheetRefSheetId ? (
                <button
                  onClick={() => dispatch({ type: "SET_ACTIVE_SHEET", sheetId: data.scheduleSheetRefSheetId! })}
                  className="flex items-center gap-1 text-cyan-400 hover:text-cyan-300 font-bold underline decoration-dotted underline-offset-2 cursor-pointer"
                  title={`Go to ${data.scheduleSheet}`}
                >
                  <Link2 size={10} />
                  {data.scheduleSheet}
                </button>
              ) : (
                <span className="text-gray-300 truncate max-w-[170px]">{data.scheduleSheet}</span>
              )}
            </div>
            <div className="flex justify-between py-0.5 items-center">
              <span className="text-gray-400 font-sans">Detail Reference</span>
              {data.detailReference ? (
                data.detailReferenceSheetId ? (
                  <button
                    onClick={() => dispatch({ type: "SET_ACTIVE_SHEET", sheetId: data.detailReferenceSheetId! })}
                    className={`flex items-center gap-1 font-bold underline decoration-dotted underline-offset-2 cursor-pointer ${
                      data.detailReferenceStatus === "CONFLICT" ? "text-red-400 hover:text-red-300" : "text-emerald-400 hover:text-emerald-300"
                    }`}
                    title={`Go to detail sheet ${data.detailReference}`}
                  >
                    <Link2 size={10} />
                    {data.detailReference}
                    {data.detailReferenceStatus === "CONFLICT" ? " (conflict)" : ""}
                  </button>
                ) : (
                  <span className="text-red-400 font-bold">
                    {data.detailReference} (unresolved)
                  </span>
                )
              ) : (
                <span className="text-gray-500">Not available from source</span>
              )}
            </div>
            <div className="flex justify-between py-0.5">
              <span className="text-gray-400 font-sans">Section Reference</span>
              <span className="text-gray-500">Not available from source</span>
            </div>
          </div>
        </div>

        {/* 6. QTO & AUDITABLE CALCULATION */}
        <div className="space-y-1.5">
          <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider flex items-center justify-between border-b border-white/5 pb-1">
            <span>QTO & AUDITABLE CALCULATION</span>
          </div>

          <div className="space-y-1.5 font-mono text-[10px]">
            <div className="flex justify-between py-0.5">
              <span className="text-gray-400 font-sans">QTO Eligible</span>
              <span className={data.qtoEligible ? "text-emerald-400 font-bold" : "text-amber-400 font-bold"}>
                {data.qtoEligible ? "● Yes" : "● No"}
              </span>
            </div>
            <div className="flex justify-between py-0.5">
              <span className="text-gray-400 font-sans">Hanging Scope</span>
              <span className="text-white font-bold">{data.sidesToHang} {data.sidesToHang === 1 ? "Side" : "Sides"}</span>
            </div>
            <div className="flex justify-between py-0.5">
              <span className="text-gray-400 font-sans">Layers / Side</span>
              <span className="text-white">
                {data.layersSideA} Side A / {data.layersSideB} Side B ({data.totalLayers} Total)
              </span>
            </div>
            <div className="flex justify-between py-0.5">
              <span className="text-gray-400 font-sans">Gross Wall Face Area</span>
              <span className="text-cyan-400 font-bold">{data.grossHangAreaSf.toFixed(2)} SF</span>
            </div>
            <div className="flex justify-between py-0.5">
              <span className="text-gray-400 font-sans">Opening Deduction</span>
              <span className="text-rose-400 font-bold">−{data.openingDeductionSf.toFixed(2)} SF</span>
            </div>
            <div className="flex justify-between py-0.5 border-t border-white/5 pt-1">
              <span className="text-gray-400 font-sans">Net Wall Hang Area</span>
              <span className="text-emerald-400 font-bold">{data.netHangAreaSf.toFixed(2)} SF</span>
            </div>
            <div className="flex justify-between py-0.5">
              <span className="text-gray-400 font-sans">Required Sheets (4×8)</span>
              <span className="text-emerald-300 font-bold">
                {data.requiredSheets} sheets (incl. {data.wasteFactorPct}% waste)
              </span>
            </div>

            {/* Audit Calculation Box */}
            <div className="p-2.5 rounded-lg bg-emerald-950/30 border border-emerald-500/20 text-[9px] font-mono text-emerald-300 leading-relaxed mt-1.5 space-y-1">
              <div className="text-[10px] font-bold text-emerald-400 font-sans">
                Audit Calculation Breakdown:
              </div>
              <div className="text-gray-300">
                {data.calculationFormula}
              </div>
            </div>

            {/* QTO Gate Reason */}
            <div className="p-2 rounded bg-black/30 border border-white/5 text-[9px] font-sans text-gray-400">
              <span className="font-semibold text-gray-300">Gate Verification: </span>
              {data.qtoReason}
            </div>
          </div>
        </div>
      </div>

      {/* Ask AI Copilot Gateway */}
      <div className="px-3 py-2 bg-[#0E131F] border-t border-white/10 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-1.5 text-[10px] text-gray-400">
          <Sparkles size={12} className="text-amber-400" />
          <span>Need blueprint provenance?</span>
        </div>
        <button
          onClick={() => dispatch({ type: "SET_RIGHT_TAB", tab: "assistant" })}
          className="px-2 py-1 rounded bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/30 text-amber-300 text-[10px] font-semibold flex items-center gap-1 transition-colors cursor-pointer"
        >
          Ask AI Copilot
          <ArrowRight size={10} />
        </button>
      </div>

      {/* Action Buttons Bar */}
      <div className="p-3 border-t border-white/10 bg-[#111622] grid grid-cols-3 gap-2 shrink-0">
        <button
          onClick={() => {
            dispatch({ type: "APPROVE_DETECTION", id: d.id });
            dispatch({
              type: "ADD_HISTORY",
              entry: {
                id: `h-${Date.now()}`,
                version: state.revision,
                actor: currentUserName || "Unknown user",
                action: `Approved ${d.name}`,
                timestamp: Date.now(),
              },
            });
            toast.success(`Approved ${data.displayCode}`);
          }}
          className="py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-[10px] flex items-center justify-center gap-1 transition-colors cursor-pointer shadow-sm"
        >
          <Check size={12} />
          Approve Wall
        </button>

        <button
          onClick={() => {
            toast.info(`Edit mode for ${data.displayCode}`);
          }}
          className="py-1.5 rounded-md bg-white/10 hover:bg-white/15 text-white font-semibold text-[10px] flex items-center justify-center gap-1 border border-white/10 transition-colors cursor-pointer"
        >
          <Edit3 size={12} />
          Edit Wall
        </button>

        <button
          onClick={() => {
            dispatch({ type: "REJECT_DETECTION", id: d.id });
            dispatch({
              type: "ADD_HISTORY",
              entry: {
                id: `h-${Date.now()}`,
                version: state.revision,
                actor: currentUserName || "Unknown user",
                action: `Rejected ${d.name}`,
                timestamp: Date.now(),
              },
            });
            toast(`Rejected ${data.displayCode}`);
          }}
          className="py-1.5 rounded-md bg-rose-600/20 hover:bg-rose-600/30 text-rose-400 border border-rose-500/30 font-semibold text-[10px] flex items-center justify-center gap-1 transition-colors cursor-pointer"
        >
          <X size={12} />
          Reject Wall
        </button>
      </div>
    </div>
  );
}
