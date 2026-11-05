import { Compass, Plus, Minus, Maximize2, AlertTriangle } from "lucide-react";
import { useApp } from "@/state/AppContext";

// Scale sources that the backend has independently verified (dimension calibration,
// printed notation on the sheet, reference object, or explicit user input).
// Any other value — including null / undefined / "assumed_default" — means the
// engine picked a plausible default that has NEVER been cross-checked against the
// actual drawing.  The UI must surface this clearly (Acceptance #3).
const VERIFIED_SCALE_SOURCES = new Set([
  "measured",               // dimension-string calibration (SCALE_SOURCE_MEASURED)
  "printed_notation",       // SCALE_SOURCE_PRINTED
  "reference_object_calibration", // SCALE_SOURCE_REFERENCE_OBJECT
  "user_calibrated",        // SCALE_SOURCE_USER
  "dimension_measurement",
]);

export default function HUD({
  cursor,
  zoom,
}: {
  cursor: { x: number; y: number } | null;
  zoom: number;
}) {
  const { state, dispatch } = useApp();

  // Determine whether the active sheet has a verified scale
  const activeSheet = state.sheets.find((s) => s.id === state.activeSheetId);
  const scaleSource = activeSheet?.scale_source;
  const isScaleVerified = scaleSource != null && VERIFIED_SCALE_SOURCES.has(scaleSource);
  const showScaleWarning = !isScaleVerified;

  const ftX = cursor ? Math.round(cursor.x * 140) : 84;
  const inX = cursor ? Math.round((cursor.x * 140 * 12) % 12) : 2;
  const ftY = cursor ? Math.round(cursor.y * 140) : 36;
  const inY = cursor ? Math.round((cursor.y * 140 * 12) % 12) : 8;

  const zoomPct = Math.round(zoom * 100);

  return (
    <>
      {/* UNVERIFIED SCALE warning — shown whenever scale has not been independently confirmed.
          Acceptance #3: must be visible before any export of assumed-scale quantities. */}
      {showScaleWarning && (
        <div
          className="absolute top-3 left-1/2 -translate-x-1/2 z-30 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/20 border border-amber-400/60 shadow-xl backdrop-blur-md text-[10px] font-bold text-amber-300 select-none animate-in fade-in duration-200"
          title={`Scale source: ${scaleSource || "none — no calibration performed"}. QTO quantities derived from this sheet should not be exported as verified.`}
        >
          <AlertTriangle size={12} className="shrink-0 text-amber-400" />
          UNVERIFIED SCALE — calibrate before export
        </div>
      )}

      {/* Bottom-Left Coordinate & Scale Badge */}
      <div className="absolute bottom-4 left-4 z-20 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#0B0E14]/90 border border-white/10 shadow-xl backdrop-blur-md text-[10px] font-mono text-gray-300 select-none">
        <div>
          X: <span className="text-white font-bold">{ftX}'-{inX}"</span> Y: <span className="text-white font-bold">{ftY}'-{inY}"</span>
        </div>
        <div className="w-px h-3 bg-white/20" />
        <div className={`font-bold ${isScaleVerified ? "text-cyan-400" : "text-amber-400"}`}>
          {isScaleVerified
            ? `1/8" = 1'-0"` // TODO: format from actual scale_ft_per_px when surfaced
            : "⚠ UNVERIFIED"}
        </div>
      </div>

      {/* Bottom-Center Scale Bar & North Arrow */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-3 px-3 py-1.5 rounded-lg bg-[#0B0E14]/90 border border-white/10 shadow-xl backdrop-blur-md text-[9px] font-mono text-gray-300 select-none">
        <div className="flex flex-col items-center">
          <div className="flex justify-between w-28 text-[8px] text-gray-400">
            <span>0'</span>
            <span>4'</span>
            <span>8'</span>
            <span>16'</span>
          </div>
          <div className="w-28 h-1 bg-white/20 relative rounded-sm flex">
            <div className="w-1/4 h-full bg-white rounded-l-sm" />
            <div className="w-1/4 h-full bg-black/40" />
            <div className="w-1/2 h-full bg-white rounded-r-sm" />
          </div>
        </div>

        <div className="w-px h-5 bg-white/15" />

        {/* North Arrow */}
        <div className="flex items-center gap-1 font-sans font-bold text-[10px] text-white">
          <div className="w-4 h-4 rounded-full bg-white/10 flex items-center justify-center border border-white/20">
            <Compass size={11} className="text-cyan-400" />
          </div>
          <span>N</span>
        </div>
      </div>

      {/* Bottom-Right Zoom Controls */}
      <div className="absolute bottom-4 right-4 z-20 flex items-center gap-1 p-1 rounded-lg bg-[#0B0E14]/90 border border-white/10 shadow-xl backdrop-blur-md text-xs font-mono text-gray-300 select-none">
        <span className="px-2 py-1 text-white font-bold text-[11px] min-w-[46px] text-center">
          {zoomPct}%
        </span>
        <button
          onClick={() => dispatch({ type: "SET_ZOOM", zoom: Math.min(4, zoom * 1.2) })}
          className="p-1.5 rounded hover:bg-white/10 text-gray-300 hover:text-white transition-colors cursor-pointer"
          title="Zoom in"
        >
          <Plus size={13} />
        </button>
        <button
          onClick={() => dispatch({ type: "SET_ZOOM", zoom: Math.max(0.25, zoom / 1.2) })}
          className="p-1.5 rounded hover:bg-white/10 text-gray-300 hover:text-white transition-colors cursor-pointer"
          title="Zoom out"
        >
          <Minus size={13} />
        </button>
        <button
          onClick={() => dispatch({ type: "SET_ZOOM", zoom: 1 })}
          className="p-1.5 rounded hover:bg-white/10 text-gray-300 hover:text-white transition-colors cursor-pointer"
          title="Reset Zoom (100%)"
        >
          <Maximize2 size={13} />
        </button>
      </div>
    </>
  );
}

