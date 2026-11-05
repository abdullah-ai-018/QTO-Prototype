import { useMemo } from "react";
import { X, Check, AlertCircle, ArrowUpRight, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/state/AppContext";
import type { Detection } from "@/types";
import { buildWallInspectionData } from "@/lib/wallInspectorModel";

interface Props {
  detection: Detection;
  cardPos: { x: number; y: number };
  /** The canvas container's own measured size — clamping against this
      (not window.innerWidth/Height) keeps the card inside the actual
      drawing viewport regardless of how the side panels are sized or
      whether Focus Mode has collapsed them. */
  containerWidth: number;
  containerHeight: number;
  onClose: () => void;
}

const CARD_W = 260;
const CARD_H_ESTIMATE = 210;

/**
 * Quick-glance card shown directly on the canvas at the clicked wall.
 * Deliberately minimal — full engineering detail (provenance per field,
 * assembly breakdown, QTO audit, references) lives in the right-side
 * inspector (SelectedWallInspector), which this card links to rather than
 * duplicating, so there is exactly one place a user reads the full record.
 */
export default function WallInspectionOverlay({ detection: d, cardPos, containerWidth, containerHeight, onClose }: Props) {
  const { state, dispatch, currentUserName } = useApp();
  const data = useMemo(() => buildWallInspectionData(d, state), [d, state]);

  const posX = Math.max(8, Math.min(cardPos.x - CARD_W / 2, containerWidth - CARD_W - 8));
  const posY = Math.max(8, Math.min(cardPos.y - CARD_H_ESTIMATE - 16, containerHeight - CARD_H_ESTIMATE - 8));

  return (
    <div
      className="absolute z-30 w-[260px] bg-[#0c1017]/95 border border-white/15 rounded-xl shadow-2xl backdrop-blur-xl text-xs text-[var(--color-text-primary)] select-none overflow-hidden animate-in fade-in zoom-in-95 duration-150 font-sans"
      style={{ left: posX, top: posY }}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="px-3 py-2 bg-white/[0.04] border-b border-white/10 flex items-center justify-between">
        <div className="flex items-center gap-1.5 min-w-0">
          <span
            className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{ backgroundColor: data.categoryColor, boxShadow: `0 0 8px ${data.categoryColor}` }}
          />
          <span className="text-[11px] font-bold text-white truncate">{data.categoryLabel}</span>
          {d.status === "approved" && (
            <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 text-[9px] font-bold border border-emerald-500/30">
              ✓ Approved
            </span>
          )}
          {d.status === "rejected" && (
            <span className="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-400 text-[9px] font-bold border border-rose-500/30">
              ✗ Rejected
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-0.5 text-gray-400 hover:text-white rounded hover:bg-white/10 transition-colors cursor-pointer shrink-0"
          title="Close"
        >
          <X size={13} />
        </button>
      </div>

      <div className="p-3 space-y-2">
        <div className="text-[10px] font-mono text-gray-400 flex items-center justify-between">
          <span>{data.displayCode} {data.wallTag ? `• [${data.wallTag}]` : ""}</span>
          <span className="text-cyan-400 font-bold">{data.lengthFt.toFixed(1)} LF</span>
        </div>

        {data.conflicts.length > 0 && (
          <div className="flex items-center gap-1 px-1.5 py-1 rounded bg-red-500/10 border border-red-500/40 text-[9px] text-red-300 font-semibold">
            <AlertCircle size={10} />
            <span>Discrepancy: {data.conflicts[0].field} ({data.conflicts[0].sources?.map(s => s.source).filter(Boolean).join(" vs ") || data.conflicts[0].status})</span>
          </div>
        )}

        <div className="grid grid-cols-2 gap-1.5 text-center font-mono">
          <div className="p-1.5 rounded-lg bg-black/40 border border-white/5">
            <div className="text-[8px] text-gray-500">Height</div>
            <div className="text-[11px] font-bold text-cyan-400">{data.heightFt.toFixed(2)} ft</div>
            <div className={`text-[7px] font-bold ${data.heightVerificationState === "VERIFIED" ? "text-emerald-400" : "text-amber-400"}`}>
              {data.heightVerificationState}
            </div>
          </div>
          <div className="p-1.5 rounded-lg bg-black/40 border border-white/5">
            <div className="text-[8px] text-gray-500">Thickness</div>
            <div className="text-[11px] font-bold text-amber-300">{data.thicknessIn.toFixed(2)}"</div>
            <div className={`text-[7px] font-bold ${data.thicknessVerificationState === "VERIFIED" ? "text-emerald-400" : "text-amber-400"}`}>
              {data.thicknessVerificationState}
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between text-[10px] font-mono px-0.5">
          <span className="text-gray-400">Net Hang Area</span>
          <span className="text-emerald-400 font-bold">{data.netHangAreaSf.toFixed(2)} SF</span>
        </div>

        <div className="grid grid-cols-2 gap-1.5">
          <button
            onClick={() => {
              dispatch({ type: "SET_RIGHT_TAB", tab: "assistant" });
              onClose();
            }}
            className="flex items-center justify-center gap-1 py-1.5 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 border border-amber-500/30 text-[10px] font-semibold text-amber-300 transition-colors cursor-pointer"
          >
            <Sparkles size={11} className="text-amber-400" />
            Ask AI Copilot
          </button>
          <button
            onClick={() => {
              dispatch({ type: "SET_RIGHT_TAB", tab: "detected" });
              onClose();
            }}
            className="flex items-center justify-center gap-1 py-1.5 rounded-lg bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/30 text-[10px] font-semibold text-blue-300 transition-colors cursor-pointer"
          >
            Full Inspector
            <ArrowUpRight size={11} />
          </button>
        </div>

        <div className="flex items-center gap-2 pt-0.5">
          <button
            onClick={() => {
              dispatch({ type: "APPROVE_DETECTION", id: d.id });
              dispatch({
                type: "ADD_HISTORY",
                entry: {
                  id: `h-${Date.now()}`,
                  version: state.revision,
                  actor: currentUserName || "Estimator",
                  action: `Approved ${data.displayCode}`,
                  timestamp: Date.now(),
                },
              });
              toast.success(`✓ Wall Approved: ${data.displayCode}`, {
                description: `${data.netHangAreaSf.toFixed(1)} SF added to QTO`
              });
              onClose();
            }}
            className={`flex-1 py-1.5 rounded-md font-semibold text-[10px] flex items-center justify-center gap-1 transition-colors cursor-pointer ${
              d.status === "approved"
                ? "bg-emerald-600 text-white shadow-md shadow-emerald-600/40 border border-emerald-500"
                : "bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/30"
            }`}
          >
            <Check size={12} />
            {d.status === "approved" ? "✓ Approved" : "Approve Wall"}
          </button>
          <button
            onClick={() => {
              dispatch({ type: "REJECT_DETECTION", id: d.id });
              dispatch({
                type: "ADD_HISTORY",
                entry: {
                  id: `h-${Date.now()}`,
                  version: state.revision,
                  actor: currentUserName || "Estimator",
                  action: `Rejected ${data.displayCode}`,
                  timestamp: Date.now(),
                },
              });
              toast.info(`✗ Wall Excluded: ${data.displayCode}`);
              onClose();
            }}
            className={`flex-1 py-1.5 rounded-md font-semibold text-[10px] flex items-center justify-center gap-1 transition-colors cursor-pointer ${
              d.status === "rejected"
                ? "bg-rose-600 text-white border border-rose-500"
                : "bg-rose-500/20 text-rose-400 hover:bg-rose-500/30 border border-rose-500/30"
            }`}
          >
            <X size={12} />
            {d.status === "rejected" ? "✗ Rejected" : "Reject Wall"}
          </button>
        </div>
      </div>
    </div>
  );
}
