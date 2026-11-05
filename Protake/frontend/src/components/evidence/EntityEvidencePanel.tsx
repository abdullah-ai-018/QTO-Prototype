import React, { useEffect, useState } from "react";
import {
  Layers,
  Ruler,
  Info,
  Copy,
  Check,
  Calculator,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/state/AppContext";
import type { Detection } from "@/types";
import { formatLength, formatWallThickness } from "@/lib/units";
import { boundingBoxDimensionsFt, DEFAULT_SCALE } from "@/lib/geometry";
import { BackendApiService, type WallLedgerEntry } from "@/api/backendApi";

interface EntityEvidencePanelProps {
  detection: Detection;
  onClose?: () => void;
  isFloating?: boolean;
}

type LoadState = "idle" | "loading" | "ready" | "empty" | "error";

export default function EntityEvidencePanel({ detection: d, onClose, isFloating = false }: EntityEvidencePanelProps) {
  const { state } = useApp();
  const [copied, setCopied] = useState(false);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [ledgerEntry, setLedgerEntry] = useState<WallLedgerEntry | null>(null);

  const scale = state.calibration[d.sheetId] ?? DEFAULT_SCALE;
  const bbox = boundingBoxDimensionsFt(d.points, scale);
  const activeSheet = state.sheets.find((s) => s.id === d.sheetId);

  const isWall = d.kind === "wall";
  const isDoor = d.kind === "door";
  const isWindow = d.kind === "window";
  const isOpening = isDoor || isWindow;

  useEffect(() => {
    if (!isWall) return;
    if (!state.projectId || !state.blueprintId) {
      setLoadState("error");
      return;
    }
    const numericId = d.id.replace(/\D/g, "");
    let cancelled = false;
    setLoadState("loading");
    BackendApiService.fetchDrywallWallLedger(state.projectId, state.blueprintId)
      .then((res) => {
        if (cancelled) return;
        const entry = res.wall_ledger.find((w) => w.wall_id === `drywall-wall-${numericId}`);
        if (entry) {
          setLedgerEntry(entry);
          setLoadState("ready");
        } else {
          setLoadState("empty");
        }
      })
      .catch((err) => {
        if (cancelled) return;
        const status = err?.status ?? err?.response?.status;
        setLoadState(status === 404 ? "empty" : "error");
      });
    return () => {
      cancelled = true;
    };
  }, [isWall, d.id, state.projectId, state.blueprintId]);

  const copyProofToClipboard = () => {
    let text: string;
    if (isWall && ledgerEntry) {
      text =
        `Wall ${ledgerEntry.wall_id.replace("drywall-wall-", "W-")} (${activeSheet?.name || `Page ${(activeSheet?.pageIndex ?? 0) + 1}`})\n` +
        `Length: ${ledgerEntry.length_ft.toFixed(2)} LF [CAD GEOMETRY]\n` +
        `Height: ${ledgerEntry.height_ft.toFixed(2)} FT [${ledgerEntry.height_provenance}]\n` +
        `Thickness: ${(ledgerEntry.thickness_in / 12).toFixed(3)} FT [${ledgerEntry.thickness_source.toUpperCase()}]\n` +
        `Sides to Hang: ${ledgerEntry.sides_to_hang}\n` +
        `Assembly: ${ledgerEntry.assembly_tag ?? "unresolved"} — ${ledgerEntry.assembly_description ?? "n/a"} [${ledgerEntry.assembly_verified ? "VERIFIED" : "UNVERIFIED"}]\n` +
        `Gross Area: ${ledgerEntry.gross_sf.toFixed(2)} SF\n` +
        `Opening Deductions (${ledgerEntry.openings_count}): -${ledgerEntry.opening_deduction_sf.toFixed(2)} SF\n` +
        `Net Drywall Area: ${ledgerEntry.net_sf.toFixed(2)} SF\n` +
        `QTO Status: ${ledgerEntry.qto_eligible ? "Included" : `Excluded — ${ledgerEntry.qto_block_reason ?? "unspecified"}`}`;
    } else {
      text =
        `${d.name || d.id} (${d.kind})\n` +
        `Detected bbox: ${bbox.widthFt.toFixed(2)}' × ${bbox.heightFt.toFixed(2)}' [CAD GEOMETRY]\n` +
        `Host-wall association and drywall deduction are computed server-side during the drywall takeoff — ` +
        `open the Wall-by-Wall Ledger to see this opening's effect on its host wall.`;
    }

    navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success("Calculation proof copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={`rounded-xl border border-[var(--color-primary)]/40 bg-[var(--color-panel-2)] p-4 space-y-3.5 text-xs shadow-2xl backdrop-blur-md glow-primary ${isFloating ? "max-w-md w-full" : "w-full"}`}>
      {/* Header with Title, Sheet Ref & Badges */}
      <div className="flex items-start justify-between gap-2 border-b border-white/10 pb-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="font-mono font-bold text-base text-[var(--color-primary-hover)] flex items-center gap-1.5">
              <Calculator size={15} className="text-cyan-400" />
              {isWall ? (ledgerEntry ? ledgerEntry.wall_id.replace("drywall-wall-", "Wall W-") : `Wall ${d.id.replace("backend-wall-", "W-")}`) : d.name || d.id}
            </span>
            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 uppercase">
              {d.status}
            </span>
          </div>
          <p className="text-[11px] text-[var(--color-text-secondary)] font-mono">
            {activeSheet ? `${activeSheet.name || `Page ${activeSheet.pageIndex + 1}`} · ` : ""}
            {isWall
              ? (d.wallTypeCode?.replace(/_/g, " ") || "Wall")
              : `${d.kind.toUpperCase()} · Architectural Opening`}
          </p>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={copyProofToClipboard}
            disabled={isWall && loadState !== "ready"}
            className="p-1.5 rounded-md text-gray-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
            title="Copy full engineering calculation proof"
          >
            {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 rounded-md text-gray-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Wall: real ledger data from backend */}
      {isWall && loadState === "loading" && (
        <div className="flex items-center justify-center gap-2 py-6 text-[var(--color-text-secondary)]">
          <Loader2 size={16} className="animate-spin" />
          <span className="text-xs">Loading wall provenance from backend…</span>
        </div>
      )}

      {isWall && loadState === "empty" && (
        <div className="flex flex-col items-center gap-2 py-6 text-center px-4">
          <AlertTriangle size={20} className="text-amber-400" />
          <p className="text-xs text-[var(--color-text-secondary)]">
            No drywall takeoff evidence found for this wall yet. Run the drywall takeoff to generate provenance.
          </p>
        </div>
      )}

      {isWall && loadState === "error" && (
        <div className="flex flex-col items-center gap-2 py-6 text-center px-4">
          <AlertTriangle size={20} className="text-rose-400" />
          <p className="text-xs text-[var(--color-text-secondary)]">Failed to load wall evidence from backend.</p>
        </div>
      )}

      {isWall && loadState === "ready" && ledgerEntry && (
        <>
          <div className="space-y-2 bg-black/30 rounded-lg p-3 border border-white/5 font-mono text-[11px]">
            <div className="text-[10px] uppercase tracking-wider font-bold text-gray-400 flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-cyan-400">
                <Layers size={12} /> Dimensions & Source Evidence
              </span>
              <span className="text-[9px] text-gray-500 font-normal">CALIBRATED ({scale.toFixed(6)} FT/PX)</span>
            </div>

            <div className="space-y-1.5 pt-1">
              <div className="flex justify-between items-center text-[var(--color-text-secondary)]">
                <span>Centerline Length:</span>
                <span className="text-[var(--color-text-primary)] font-semibold flex items-center gap-1.5">
                  {formatLength(ledgerEntry.length_ft, state.unitSystem)}
                  <span className="text-[9px] px-1.5 py-0.2 rounded bg-cyan-500/15 text-cyan-300 font-medium">CAD GEOMETRY</span>
                </span>
              </div>

              <div className="flex justify-between items-center text-[var(--color-text-secondary)]">
                <span>Plate Height:</span>
                <span className={`font-semibold flex items-center gap-1.5 ${ledgerEntry.height_provenance === "VERIFIED" ? "text-emerald-400" : "text-amber-400"}`}>
                  {ledgerEntry.height_ft.toFixed(2)} FT
                  <span className={`text-[9px] px-1.5 py-0.2 rounded font-medium ${ledgerEntry.height_provenance === "VERIFIED" ? "bg-emerald-500/20 text-emerald-300" : "bg-amber-500/20 text-amber-300"}`}>
                    {ledgerEntry.height_provenance}
                  </span>
                </span>
              </div>

              <div className="flex justify-between items-center text-[var(--color-text-secondary)]">
                <span>Thickness:</span>
                <span className="text-[var(--color-text-primary)] font-semibold flex items-center gap-1.5">
                  {formatWallThickness(ledgerEntry.thickness_in / 12, state.unitSystem)}
                  <span className="text-[9px] px-1.5 py-0.2 rounded bg-gray-500/20 text-gray-300 font-medium uppercase">
                    {ledgerEntry.thickness_source}
                  </span>
                </span>
              </div>

              <div className="flex justify-between items-center text-[var(--color-text-secondary)]">
                <span>Drywall Sides:</span>
                <span className="text-[var(--color-text-primary)] font-semibold flex items-center gap-1.5">
                  {ledgerEntry.sides_to_hang} {ledgerEntry.sides_to_hang === 2 ? "(Both Faces)" : ledgerEntry.sides_to_hang === 1 ? "(Single Face)" : "(None)"}
                </span>
              </div>

              <div className="flex justify-between items-center text-[var(--color-text-secondary)]">
                <span>Assembly Spec:</span>
                <span className={`font-semibold flex items-center gap-1.5 ${ledgerEntry.assembly_tag ? "text-emerald-400" : "text-amber-400"}`}>
                  {ledgerEntry.assembly_description ?? ledgerEntry.assembly_tag ?? "Unresolved"}
                  <span className={`text-[9px] px-1.5 py-0.2 rounded font-medium ${ledgerEntry.assembly_verified ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/20 text-amber-300"}`}>
                    {ledgerEntry.assembly_verified ? "VERIFIED" : "UNVERIFIED"}
                  </span>
                </span>
              </div>
            </div>
          </div>

          <div className="space-y-2.5 bg-[var(--color-panel)] rounded-lg p-3 border border-white/10">
            <div className="text-[10px] uppercase tracking-wider font-bold text-emerald-400 flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <Ruler size={12} /> Backend-Computed Takeoff
              </span>
              <span className={`text-[9px] px-2 py-0.5 rounded font-mono font-semibold border ${ledgerEntry.qto_eligible ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" : "bg-amber-500/15 text-amber-300 border-amber-500/30"}`}>
                {ledgerEntry.qto_eligible ? "QTO INCLUDED" : "QTO EXCLUDED"}
              </span>
            </div>

            <div className="space-y-2 text-[11px] font-mono text-[var(--color-text-secondary)]">
              <div className="p-2 rounded bg-black/20 border border-white/5 flex justify-between items-center">
                <span>Gross Wall Area:</span>
                <span className="text-cyan-400 font-bold">{ledgerEntry.gross_sf.toFixed(2)} SF</span>
              </div>
              <div className="p-2 rounded bg-rose-500/5 border border-rose-500/20 flex justify-between items-center">
                <span className="text-rose-400">Opening Deductions ({ledgerEntry.openings_count}):</span>
                <span className="text-rose-400 font-semibold">-{ledgerEntry.opening_deduction_sf.toFixed(2)} SF</span>
              </div>
              <div className="p-2 rounded bg-cyan-500/10 border border-cyan-500/30 flex justify-between items-center font-bold">
                <span className="text-gray-300">Net Drywall Area:</span>
                <span className="text-cyan-400">{ledgerEntry.net_sf.toFixed(2)} SF</span>
              </div>
              {!ledgerEntry.qto_eligible && ledgerEntry.qto_block_reason && (
                <div className="p-2 rounded bg-amber-500/10 border border-amber-500/20 text-amber-300 text-[10px]">
                  Excluded from QTO: {ledgerEntry.qto_block_reason}
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {/* Opening: only real detected geometry, no fabricated deduction */}
      {isOpening && (
        <div className="space-y-2.5">
          <div className="space-y-2 bg-black/30 rounded-lg p-3 border border-white/5 font-mono text-[11px]">
            <div className="text-[10px] uppercase tracking-wider font-bold text-gray-400 flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-cyan-400">
                <Layers size={12} /> Detected Geometry
              </span>
              <span className="text-[9px] text-gray-500 font-normal">CALIBRATED ({scale.toFixed(6)} FT/PX)</span>
            </div>
            <div className="flex justify-between items-center text-[var(--color-text-secondary)] pt-1">
              <span>Detected Bounding Box:</span>
              <span className="text-[var(--color-text-primary)] font-semibold flex items-center gap-1.5">
                {bbox.widthFt.toFixed(2)}' × {bbox.heightFt.toFixed(2)}'
                <span className="text-[9px] px-1.5 py-0.2 rounded bg-cyan-500/15 text-cyan-300 font-medium">DETECTED BBOX</span>
              </span>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-start gap-2">
            <Info size={14} className="text-amber-400 shrink-0 mt-0.5" />
            <p className="text-[11px] text-amber-200 leading-relaxed">
              Host-wall association and drywall deduction for this opening are computed server-side during the
              drywall takeoff, not in this panel. Open the Wall-by-Wall Ledger for the host wall's real deduction.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
