import { useState, useMemo } from "react";
import { ChevronDown, ChevronRight, Check, X, Layers, DoorOpen } from "lucide-react";
import { useApp } from "@/state/AppContext";
import { toast } from "sonner";
import { formatLength } from "@/lib/units";
import { boundingBoxDimensionsFt, DEFAULT_SCALE } from "@/lib/geometry";
import type { Detection } from "@/types";
import { getDoorWindowCodes } from "@/lib/tradeVisualization";

export default function ScheduleTab() {
  const { state, dispatch } = useApp();
  const [expandedCodes, setExpandedCodes] = useState<Record<string, boolean>>({});

  const detections = useMemo(() =>
    state.detections.filter((d) =>
      d.sheetId === state.activeSheetId && (d.kind === "door" || d.kind === "window")
    ),
    [state.detections, state.activeSheetId]
  );

  const codes = useMemo(() =>
    getDoorWindowCodes(
      state.detections.filter((d) => d.sheetId === state.activeSheetId),
      state.calibration
    ),
    [state.detections, state.activeSheetId, state.calibration]
  );

  const grouped = useMemo(() => {
    const groups: Record<string, {
      code: string;
      kind: "door" | "window";
      dims: string;
      items: Detection[];
    }> = {};

    detections.forEach((d) => {
      const code = codes[d.id];
      if (!code) return;

      const scale = state.calibration[d.sheetId] ?? DEFAULT_SCALE;
      const bbox = boundingBoxDimensionsFt(d.points, scale);
      const dims = `${formatLength(bbox.widthFt, state.unitSystem)} × ${formatLength(bbox.heightFt, state.unitSystem)}`;

      if (!groups[code]) {
        groups[code] = { code, kind: d.kind as "door" | "window", dims, items: [] };
      }
      groups[code].items.push(d);
    });

    return Object.values(groups).sort((a, b) => {
      if (a.kind !== b.kind) return a.kind === "door" ? -1 : 1;
      return a.code.localeCompare(b.code, undefined, { numeric: true });
    });
  }, [detections, codes, state.calibration, state.unitSystem]);

  if (grouped.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center px-6 text-[var(--color-text-secondary)]">
        <DoorOpen size={28} className="opacity-30" />
        <div>
          <p className="text-xs font-medium">No openings detected</p>
          <p className="text-[10px] mt-0.5 opacity-70">Run AI Scan to detect doors & windows</p>
        </div>
      </div>
    );
  }

  const totalDoors = grouped.filter((g) => g.kind === "door").reduce((s, g) => s + g.items.length, 0);
  const totalWindows = grouped.filter((g) => g.kind === "window").reduce((s, g) => s + g.items.length, 0);

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      {/* Summary strip */}
      <div className="px-3 py-2 border-b border-[var(--color-border)] bg-black/20 flex items-center gap-3 text-[10px]">
        <Layers size={11} className="text-[var(--color-primary)] shrink-0" />
        <span className="text-[var(--color-text-secondary)] uppercase tracking-wider font-semibold">Schedule</span>
        <div className="ml-auto flex items-center gap-2">
          {totalDoors > 0 && (
            <span className="bg-cyan-500/15 text-cyan-400 px-1.5 py-0.5 rounded font-mono font-bold">
              {totalDoors}D
            </span>
          )}
          {totalWindows > 0 && (
            <span className="bg-emerald-500/15 text-emerald-400 px-1.5 py-0.5 rounded font-mono font-bold">
              {totalWindows}W
            </span>
          )}
        </div>
      </div>

      {/* Group list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {grouped.map((group) => {
          const isDoor = group.kind === "door";
          const expanded = !!expandedCodes[group.code];
          const approvedCount = group.items.filter((i) => i.status === "approved").length;
          const rejectedCount = group.items.filter((i) => i.status === "rejected").length;
          const pendingCount = group.items.length - approvedCount - rejectedCount;

          return (
            <div
              key={group.code}
              className="rounded-lg overflow-hidden border border-[var(--color-border)] bg-[var(--color-panel-2)]"
            >
              {/* Header row */}
              <button
                onClick={() => setExpandedCodes((p) => ({ ...p, [group.code]: !p[group.code] }))}
                className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-white/5 transition-colors text-left"
              >
                {/* Large code badge — dominant visual anchor */}
                <div className={`shrink-0 w-10 h-10 rounded-lg flex items-center justify-center font-mono font-bold text-sm ${
                  isDoor
                    ? "bg-cyan-500/15 text-cyan-400 ring-1 ring-cyan-500/25"
                    : "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/25"
                }`}>
                  {group.code}
                </div>

                {/* Details */}
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold text-[var(--color-text-primary)] leading-tight">
                    {isDoor ? "Door" : "Window"} Type {group.code}
                  </div>
                  <div className="text-[10px] text-[var(--color-text-secondary)] mt-0.5">{group.dims}</div>
                </div>

                {/* Count pill + chevron */}
                <div className="flex items-center gap-2 shrink-0">
                  <div className="flex items-center gap-1">
                    <span className="text-xs font-bold text-[var(--color-text-primary)]">{group.items.length}</span>
                    {pendingCount > 0 && (
                      <span className="bg-[var(--color-warning)] text-black text-[8px] font-bold px-1 rounded-full">
                        {pendingCount}
                      </span>
                    )}
                  </div>
                  {expanded
                    ? <ChevronDown size={13} className="text-[var(--color-text-secondary)]" />
                    : <ChevronRight size={13} className="text-[var(--color-text-secondary)]" />
                  }
                </div>
              </button>

              {/* Progress bar showing approval status */}
              {(approvedCount > 0 || rejectedCount > 0) && (
                <div className="h-0.5 flex">
                  <div
                    className="bg-[var(--color-success)]"
                    style={{ width: `${(approvedCount / group.items.length) * 100}%` }}
                  />
                  <div
                    className="bg-[var(--color-danger)]"
                    style={{ width: `${(rejectedCount / group.items.length) * 100}%` }}
                  />
                </div>
              )}

              {/* Expanded item list */}
              {expanded && (
                <div className="border-t border-[var(--color-border)] divide-y divide-white/[0.04]">
                  {group.items.map((item, idx) => {
                    const isSelected = item.id === state.selectedDetectionId;
                    return (
                      <div
                        key={item.id}
                        onClick={() => dispatch({ type: "SELECT_DETECTION", id: item.id })}
                        className={`flex items-center gap-2.5 px-3 py-2 cursor-pointer transition-colors hover:bg-white/5 ${
                          isSelected ? "bg-[var(--color-primary)]/10" : ""
                        }`}
                      >
                        <span className="text-[9px] w-4 text-center text-[var(--color-text-secondary)] font-mono shrink-0">
                          {idx + 1}
                        </span>

                        <div className="flex-1 min-w-0">
                          <div className="text-xs text-[var(--color-text-primary)] truncate">
                            {item.name || `${isDoor ? "Door" : "Window"} ${group.code}-${idx + 1}`}
                          </div>
                          <div className="text-[9px] text-[var(--color-text-secondary)]">
                            {Math.round(item.confidence * 100)}% confidence
                          </div>
                        </div>

                        <span className={`shrink-0 text-[8px] uppercase font-semibold px-1 py-0.5 rounded ${
                          item.status === "approved"
                            ? "bg-[var(--color-success)]/15 text-[var(--color-success)]"
                            : item.status === "rejected"
                              ? "bg-[var(--color-danger)]/15 text-[var(--color-danger)]"
                              : "bg-[var(--color-warning)]/15 text-[var(--color-warning)]"
                        }`}>
                          {item.status}
                        </span>

                        <div className="flex gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                          <button
                            onClick={() => {
                              dispatch({ type: "APPROVE_DETECTION", id: item.id });
                              toast.success(`Approved ${group.code}-${idx + 1}`);
                            }}
                            className="w-5 h-5 rounded flex items-center justify-center bg-[var(--color-success)]/10 text-[var(--color-success)] hover:bg-[var(--color-success)]/25 transition-colors"
                          >
                            <Check size={10} />
                          </button>
                          <button
                            onClick={() => {
                              dispatch({ type: "REJECT_DETECTION", id: item.id });
                              toast(`Rejected ${group.code}-${idx + 1}`);
                            }}
                            className="w-5 h-5 rounded flex items-center justify-center bg-[var(--color-danger)]/10 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/25 transition-colors"
                          >
                            <X size={10} />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
