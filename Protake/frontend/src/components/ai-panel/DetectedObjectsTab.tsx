import { useRef, useEffect, useState, useMemo } from "react";
import { Check, X, CheckCheck, XCircle, Layers, Info } from "lucide-react";
import { useApp } from "@/state/AppContext";
import { toast } from "sonner";
import { formatArea, formatLength, formatWallThickness } from "@/lib/units";
import { boundingBoxDimensionsFt, DEFAULT_SCALE } from "@/lib/geometry";
import type { Detection } from "@/types";
import Tooltip from "../ui/Tooltip";
import { parseBackendDetectionId } from "@/lib/backendConversion";
import { BackendApiService } from "@/api/backendApi";
import { getDoorWindowCodes } from "@/lib/tradeVisualization";
import EntityEvidencePanel from "../evidence/EntityEvidencePanel";

const STATUS_STYLE: Record<Detection["status"], string> = {
  pending: "text-[var(--color-warning)] bg-[var(--color-warning)]/10",
  approved: "text-[var(--color-success)] bg-[var(--color-success)]/10",
  rejected: "text-[var(--color-danger)] bg-[var(--color-danger)]/10",
};

const SYMBOL_KINDS = new Set<Detection["kind"]>([
  "door",
  "window",
  "column",
  "fixture",
  "stairs",
  "annotation",
  "symbol",
  "object",
]);

function isSymbol(d: Detection) {
  return SYMBOL_KINDS.has(d.kind);
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 90 ? "var(--color-success)" : pct >= 75 ? "var(--color-warning)" : "var(--color-danger)";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1 rounded-full bg-white/5 overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="text-[10px] font-mono-num" style={{ color }}>
        {pct}%
      </span>
    </div>
  );
}

export default function DetectedObjectsTab() {
  const { state, dispatch, currentUserName } = useApp();
  // Doors & windows are shown exclusively in the Schedule tab
  let detections = state.detections.filter(
    (d) => d.sheetId === state.activeSheetId && d.kind !== "door" && d.kind !== "window"
  );

  const codes = getDoorWindowCodes(detections, state.calibration);

  const codeCounts = useMemo(() => {
    const counts: Record<string, { code: string; count: number; name: string; dims: string }> = {};
    detections.forEach((d) => {
      const code = codes[d.id];
      if (code) {
        const scale = state.calibration[d.sheetId] ?? DEFAULT_SCALE;
        const bbox = boundingBoxDimensionsFt(d.points, scale);
        const dims = `${formatLength(bbox.widthFt, state.unitSystem)} × ${formatLength(bbox.heightFt, state.unitSystem)}`;
        if (!counts[code]) {
          counts[code] = { code, count: 0, name: d.kind === "door" ? "Door" : "Window", dims };
        }
        counts[code].count += 1;
      }
    });
    return Object.values(counts).sort((a, b) => a.code.localeCompare(b.code));
  }, [detections, codes, state.calibration, state.unitSystem]);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editRoomType, setEditRoomType] = useState("");
  const [editFloorFinish, setEditFloorFinish] = useState("");
  const [editWallFinish, setEditWallFinish] = useState("");
  const [editCeilingFinish, setEditCeilingFinish] = useState("");
  const [editAreaSqFt, setEditAreaSqFt] = useState("");
  const [editPerimeterFt, setEditPerimeterFt] = useState("");
  const [editThicknessFt, setEditThicknessFt] = useState("");
  const [editHeightFt, setEditHeightFt] = useState("");
  const [editWallType, setEditWallType] = useState<"interior" | "exterior">("interior");
  const [editTrade, setEditTrade] = useState("");

  function startEditing(d: Detection) {
    setEditingId(d.id);
    setEditName(d.name || "");
    setEditRoomType(d.roomType || "");
    setEditAreaSqFt(d.areaSqFt ? String(d.areaSqFt) : "");
    setEditPerimeterFt(d.perimeterFt ? String(d.perimeterFt) : "");
    setEditThicknessFt(d.thicknessFt ? String(d.thicknessFt) : "");
    setEditHeightFt(d.perimeterFt && d.areaSqFt ? String(d.areaSqFt / d.perimeterFt) : "9");
    setEditWallType(d.wallType === "exterior" ? "exterior" : "interior");
    setEditTrade(d.trade || "");
  }

  async function handleSave(d: Detection) {
    const parsed = parseBackendDetectionId(d.id);
    if (!parsed) {
      toast.error("Cannot save local/sample detection");
      return;
    }

    const { source, backendId } = parsed;
    const changes: Partial<Detection> = {};

    try {
      if (source === "room") {
        const payload = {
          name: editName,
          room_type: editRoomType || null,
          area_sqft: editAreaSqFt ? Number(editAreaSqFt) : undefined,
          perimeter_ft: editPerimeterFt ? Number(editPerimeterFt) : undefined,
        };
        await BackendApiService.updateRoom(backendId, payload);
        changes.name = editName;
        changes.roomType = editRoomType || null;
        if (editAreaSqFt) changes.areaSqFt = Number(editAreaSqFt);
        if (editPerimeterFt) changes.perimeterFt = Number(editPerimeterFt);
      } else if (source === "wall") {
        const payload = {
          wall_type: editWallType,
          thickness_ft: editThicknessFt ? Number(editThicknessFt) : undefined,
          height_ft: editHeightFt ? Number(editHeightFt) : undefined,
          length_ft: editPerimeterFt ? Number(editPerimeterFt) : undefined,
        };
        await BackendApiService.updateWall(backendId, payload);
        changes.wallType = editWallType;
        if (editThicknessFt) changes.thicknessFt = Number(editThicknessFt);
        if (editPerimeterFt) {
          changes.perimeterFt = Number(editPerimeterFt);
          const h = editHeightFt ? Number(editHeightFt) : 9;
          const sides = editWallType === "interior" ? 2 : 1;
          changes.areaSqFt = Number(editPerimeterFt) * h * sides;
        }
      } else {
        const payload = {
          label: editName,
          trade: editTrade || null,
        };
        await BackendApiService.updateDetection(backendId, payload as any);
        changes.name = editName;
        changes.trade = (editTrade as any) || null;
      }

      dispatch({ type: "UPDATE_DETECTION", id: d.id, fields: changes });
      dispatch({
        type: "ADD_HISTORY",
        entry: {
          id: `h-${Date.now()}`,
          version: state.revision,
          actor: currentUserName || "Unknown user",
          action: `Edited ${d.name}`,
          timestamp: Date.now(),
        },
      });
      toast.success(`Successfully saved changes for ${editName}`);
      setEditingId(null);
    } catch (error) {
      console.error("[Edit Save Failed]", error);
      toast.error("Failed to save changes to database");
    }
  }

  if (state.focusedDetectionId) {
    detections = detections.filter((d) => d.id === state.focusedDetectionId);
  } else {
    const activeTradeId = (state.summaryTab === "drywall" || state.summaryTab === "painting" || state.summaryTab === "flooring" || state.summaryTab === "roofing" || state.summaryTab === "furniture" || state.summaryTab === "openings") ? state.summaryTab : null;
    if (activeTradeId) {
      detections = detections.filter((d) => {
        if (d.kind === "room") {
          return false;
        }
        if (activeTradeId === "painting") {
          return d.kind === "wall" || d.kind === "door" || d.kind === "window";
        }
        return d.trade === activeTradeId;
      });
    }
  }
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (state.selectedDetectionId && containerRef.current) {
      const element = containerRef.current.querySelector(
        `[data-detection-id="${state.selectedDetectionId}"]`
      );
      if (element) {
        element.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
  }, [state.selectedDetectionId]);

  function approve(d: Detection) {
    dispatch({ type: "APPROVE_DETECTION", id: d.id });
    dispatch({ type: "ADD_HISTORY", entry: { id: `h-${Date.now()}`, version: state.revision, actor: currentUserName || "Unknown user", action: `Approved ${d.name}`, timestamp: Date.now() } });
    toast.success(`Approved ${d.name}`);
  }
  function reject(d: Detection) {
    dispatch({ type: "REJECT_DETECTION", id: d.id });
    dispatch({ type: "ADD_HISTORY", entry: { id: `h-${Date.now()}`, version: state.revision, actor: currentUserName || "Unknown user", action: `Rejected ${d.name}`, timestamp: Date.now() } });
    toast(`Rejected ${d.name}`);
  }

  if (detections.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2 text-center px-6 text-[var(--color-text-secondary)]">
        <Layers size={22} className="opacity-50" />
        <p className="text-xs">No detections on this sheet yet. Run AI Scan from the blueprint toolbar.</p>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[var(--color-border)]">
        <button
          onClick={() => {
            dispatch({ type: "APPROVE_ALL" });
            toast.success("Approved all pending detections");
          }}
          className="flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-md text-[11px] bg-[var(--color-success)]/10 text-[var(--color-success)] hover:bg-[var(--color-success)]/20 transition-colors"
        >
          <CheckCheck size={13} /> Approve All
        </button>
        <button
          onClick={() => {
            dispatch({ type: "REJECT_ALL" });
            toast("Rejected all pending detections");
          }}
          className="flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-md text-[11px] bg-[var(--color-danger)]/10 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/20 transition-colors"
        >
          <XCircle size={13} /> Reject All
        </button>
      </div>
      {state.summaryTab === "openings" && codeCounts.length > 0 && (
        <div className="px-3.5 py-3 bg-[var(--color-panel-2)]/60 backdrop-blur-md border-b border-[var(--color-border)]">
          <div className="text-[10px] font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <Layers size={11} className="text-[var(--color-primary)] animate-pulse" />
            <span>Blueprint Schedule Summary</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {codeCounts.map((item: { code: string; count: number; name: string; dims: string }) => {
              const isDoor = item.code.toUpperCase().startsWith("D") || item.code.toUpperCase().startsWith("WD");
              return (
                <Tooltip key={item.code} content={`${item.name} Type ${item.code} (${item.dims})`}>
                  <div className="relative group overflow-hidden bg-black/35 border border-white/5 hover:border-[var(--color-primary)]/40 rounded-lg p-2 flex flex-col justify-between transition-all duration-200 cursor-help hover:-translate-y-[1px] hover:shadow-lg hover:shadow-black/20">
                    <div className={`absolute top-0 right-0 w-8 h-8 rounded-bl-full opacity-[0.06] transition-all duration-200 ${isDoor ? "bg-cyan-400 group-hover:scale-110" : "bg-emerald-400 group-hover:scale-110"
                      }`} />

                    <div className="flex items-center justify-between gap-1">
                      <span className={`font-mono text-[10px] font-bold px-1.5 py-0.5 rounded ${isDoor ? "bg-cyan-500/10 text-cyan-400" : "bg-emerald-500/10 text-emerald-400"
                        }`}>
                        {item.code}
                      </span>
                      <span className="font-bold text-xs text-[var(--color-text-primary)] font-mono-num">
                        {item.count} pcs
                      </span>
                    </div>

                    <div className="text-[9px] text-[var(--color-text-secondary)] truncate mt-1.5 group-hover:text-[var(--color-text-primary)] transition-colors">
                      {item.dims}
                    </div>
                  </div>
                </Tooltip>
              );
            })}
          </div>
        </div>
      )}

      <div ref={containerRef} className="flex-1 overflow-y-auto p-2.5 space-y-2">
        {(() => {
          const sel = state.detections.find((d) => d.id === state.selectedDetectionId);
          if (sel && (sel.kind === "wall" || sel.kind === "door" || sel.kind === "window")) {
            return (
              <div className="mb-3">
                <EntityEvidencePanel detection={sel} />
              </div>
            );
          }
          return null;
        })()}
        {detections.map((d) => {
          // Feet-per-normalized-unit for this object's sheet — calibrated
          // if the user ran the Calibrate tool, otherwise the same nominal
          // DEFAULT_SCALE every measurement tool already falls back to.
          // Used to give every kind of object (not just rooms/walls) a real
          // bounding-box Width × Height, since a door/window/fixture
          // previously showed no dimensions at all.
          const scale = state.calibration[d.sheetId] ?? DEFAULT_SCALE;
          const bbox = boundingBoxDimensionsFt(d.points, scale);
          return (
            <div
              key={d.id}
              data-detection-id={d.id}
              role="button"
              tabIndex={0}
              onClick={() => dispatch({ type: "SELECT_DETECTION", id: d.id })}
              onKeyDown={(e) => e.key === "Enter" && dispatch({ type: "SELECT_DETECTION", id: d.id })}
              className={`w-full text-left rounded-lg border p-3 transition-colors cursor-pointer ${d.id === state.selectedDetectionId
                ? "border-[var(--color-primary)] bg-[var(--color-primary)]/10 glow-primary"
                : "border-[var(--color-border)] bg-[var(--color-panel-2)] hover:border-[var(--color-text-secondary)]/40"
                }`}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium truncate flex items-center gap-1.5">
                    <span className="truncate">{d.name}</span>
                    {codes[d.id] && (
                      <span className="shrink-0 text-[9px] bg-[var(--color-primary)]/20 text-[var(--color-primary)] px-1 rounded font-semibold font-mono">
                        {codes[d.id]}
                      </span>
                    )}
                  </div>
                  <div className="text-[10px] text-[var(--color-text-secondary)] capitalize">
                    {d.roomType === "exterior_covered"
                      ? "covered exterior · no drywall/paint"
                      : d.kind === "annotation"
                        ? `${d.kind} · sheet reference, not a takeoff item`
                        : isSymbol(d)
                          ? `${d.kind} · AI detected symbol`
                          : `${d.trade ?? "all trades"} · ${d.kind}`}
                  </div>
                </div>
                <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded-full capitalize ${STATUS_STYLE[d.status]}`}>
                  {d.status}
                </span>
              </div>

              {editingId === d.id ? (
                <div className="space-y-2 mt-2 bg-black/10 p-2.5 rounded-md border border-white/5" onClick={(e) => e.stopPropagation()}>
                  <div>
                    <label className="text-[10px] text-[var(--color-text-secondary)] block mb-0.5 font-medium">Name / Label</label>
                    <input
                      type="text"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      className="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-primary)]"
                    />
                  </div>
                  {d.kind === "room" && (
                    <>
                      <div>
                        <label className="text-[10px] text-[var(--color-text-secondary)] block mb-0.5 font-medium">Room Type</label>
                        <select
                          value={editRoomType || ""}
                          onChange={(e) => setEditRoomType(e.target.value)}
                          className="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-[var(--color-text-primary)] capitalize focus:outline-none focus:border-[var(--color-primary)]"
                        >
                          <option value="">Standard Enclosed</option>
                          <option value="exterior_covered">Covered Exterior (Porch/Deck)</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-[10px] text-[var(--color-text-secondary)] block mb-0.5 font-medium">Area (Sq Ft)</label>
                        <input
                          type="number"
                          value={editAreaSqFt}
                          onChange={(e) => setEditAreaSqFt(e.target.value)}
                          className="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-primary)]"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] text-[var(--color-text-secondary)] block mb-0.5 font-medium">Perimeter (Ft)</label>
                        <input
                          type="number"
                          value={editPerimeterFt}
                          onChange={(e) => setEditPerimeterFt(e.target.value)}
                          className="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-primary)]"
                        />
                      </div>
                    </>
                  )}
                  {d.kind === "wall" && (
                    <>
                      <div>
                        <label className="text-[10px] text-[var(--color-text-secondary)] block mb-0.5 font-medium">Wall Type</label>
                        <select
                          value={editWallType}
                          onChange={(e) => setEditWallType(e.target.value as "interior" | "exterior")}
                          className="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-[var(--color-text-primary)] capitalize focus:outline-none focus:border-[var(--color-primary)]"
                        >
                          <option value="interior">Interior</option>
                          <option value="exterior">Exterior</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-[10px] text-[var(--color-text-secondary)] block mb-0.5 font-medium">Thickness (Ft)</label>
                        <input
                          type="number"
                          step="0.01"
                          value={editThicknessFt}
                          onChange={(e) => setEditThicknessFt(e.target.value)}
                          className="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-primary)]"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] text-[var(--color-text-secondary)] block mb-0.5 font-medium">Height (Ft)</label>
                        <input
                          type="number"
                          step="0.5"
                          value={editHeightFt}
                          onChange={(e) => setEditHeightFt(e.target.value)}
                          className="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-primary)]"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] text-[var(--color-text-secondary)] block mb-0.5 font-medium">Length (Ft)</label>
                        <input
                          type="number"
                          step="0.5"
                          value={editPerimeterFt}
                          onChange={(e) => setEditPerimeterFt(e.target.value)}
                          className="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-primary)]"
                        />
                      </div>
                    </>
                  )}
                  {!d.kind || (d.kind !== "room" && d.kind !== "wall") && (
                    <div>
                      <label className="text-[10px] text-[var(--color-text-secondary)] block mb-0.5 font-medium">Trade</label>
                      <select
                        value={editTrade || ""}
                        onChange={(e) => setEditTrade(e.target.value)}
                        className="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-xs text-[var(--color-text-primary)] capitalize focus:outline-none focus:border-[var(--color-primary)]"
                      >
                        <option value="">None (All Trades)</option>
                        <option value="drywall">Drywall</option>
                        <option value="painting">Painting</option>
                        <option value="flooring">Flooring</option>
                        <option value="roofing">Roofing</option>
                        <option value="furniture">Furniture</option>
                        <option value="openings">Openings</option>
                      </select>
                    </div>
                  )}
                  <div className="flex items-center gap-2 mt-3">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleSave(d);
                      }}
                      className="flex-1 flex items-center justify-center gap-1 py-1 px-2 rounded bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)] text-[11px] font-medium cursor-pointer"
                    >
                      Save
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingId(null);
                      }}
                      className="flex-1 flex items-center justify-center gap-1 py-1 px-2 rounded bg-white/10 text-[var(--color-text-primary)] hover:bg-white/15 text-[11px] cursor-pointer"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  {isSymbol(d) ? (
                    d.trade === "furniture" ? (
                      <div className="bg-black/20 rounded-md p-2.5 mb-2 space-y-2 text-[11px] font-mono-num border border-white/5">
                        <div className="space-y-0.5">
                          <div className="flex items-center justify-between text-[var(--color-text-secondary)]">
                            <span>Item Type:</span>
                            <span className="text-emerald-400 font-semibold capitalize">{d.kind}</span>
                          </div>
                          <div className="flex items-center justify-between text-[#94a3b8] pl-3 text-[10px]">
                            <span className="flex items-center gap-1">
                              ↳ Dimensions:
                              <Tooltip content="Bounding box of the detected footprint, converted using this sheet's calibrated scale (or the default nominal scale if uncalibrated).">
                                <Info size={9} className="opacity-50 hover:opacity-100 cursor-help" />
                              </Tooltip>
                            </span>
                            <span>{formatLength(bbox.widthFt, state.unitSystem)} × {formatLength(bbox.heightFt, state.unitSystem)}</span>
                          </div>
                          <div className="flex items-center justify-between text-[#94a3b8] pl-3 text-[10px]">
                            <span className="flex items-center gap-1">
                              ↳ Piece Count:
                              <Tooltip content="Count = 1 pc per detected item">
                                <Info size={9} className="opacity-50 hover:opacity-100 cursor-help" />
                              </Tooltip>
                            </span>
                            <span>1 pc</span>
                          </div>
                          <div className="flex items-center justify-between text-[#94a3b8] pl-3 text-[10px]">
                            <span className="flex items-center gap-1">
                              ↳ Assembly Labor:
                              <Tooltip content="Assembly Labor = 0.75 hrs per furniture item">
                                <Info size={9} className="opacity-50 hover:opacity-100 cursor-help" />
                              </Tooltip>
                            </span>
                            <span>0.75 hrs</span>
                          </div>
                          <div className="flex items-center justify-between text-[#94a3b8] pl-3 text-[10px]">
                            <span className="flex items-center gap-1">
                              ↳ Est. Unit Cost:
                              <Tooltip content="Estimated Supply Cost = $320 per furniture piece">
                                <Info size={9} className="opacity-50 hover:opacity-100 cursor-help" />
                              </Tooltip>
                            </span>
                            <span>$320</span>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="bg-black/20 rounded-md p-2 mb-2 space-y-1 text-[11px] font-mono-num">
                        <div className="flex items-center justify-between text-[var(--color-text-secondary)]">
                          <span className="flex items-center gap-1">
                            Dimensions:
                            <Tooltip content="Bounding box of the detected footprint, converted using this sheet's calibrated scale (or the default nominal scale if uncalibrated).">
                              <Info size={9} className="opacity-50 hover:opacity-100 cursor-help" />
                            </Tooltip>
                          </span>
                          <span className="text-[var(--color-text-primary)] font-semibold">
                            {formatLength(bbox.widthFt, state.unitSystem)} × {formatLength(bbox.heightFt, state.unitSystem)}
                          </span>
                        </div>
                        {(d.kind === "door" || d.kind === "window") && (
                          <div className="flex items-center justify-between text-[#94a3b8] text-[10px]">
                            <span className="flex items-center gap-1">
                              ↳ Standard Assumed Size:
                              <Tooltip content="Industry-standard opening size used for the door/window deductions subtracted from wall & paint area elsewhere in the takeoff.">
                                <Info size={9} className="opacity-50 hover:opacity-100 cursor-help" />
                              </Tooltip>
                            </span>
                            <span>{d.kind === "door" ? "3 ft × 7 ft (21 sq ft)" : "3 ft × 5 ft (15 sq ft)"}</span>
                          </div>
                        )}
                        <div className="text-[10px] text-[var(--color-text-secondary)] pt-0.5">
                          Symbol detection — no area/volume takeoff. Approve to keep it on the sheet.
                        </div>
                      </div>
                    )
                  ) : d.kind === "wall" ? (
                    <div className="bg-black/20 rounded-md p-2 mb-2 space-y-1 text-[11px] font-mono-num">
                      <div className="flex items-center justify-between text-[var(--color-text-secondary)]">
                        <span className="flex items-center gap-1">
                          Length:
                          <Tooltip content="Length = Distance between start and end wall nodes">
                            <Info size={9} className="opacity-50 hover:opacity-100 cursor-help" />
                          </Tooltip>
                        </span>
                        <span className="text-[var(--color-text-primary)] font-semibold">
                          {formatLength(d.perimeterFt, state.unitSystem)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[var(--color-text-secondary)]">
                        <span className="flex items-center gap-1">
                          Wall Type:
                          <Tooltip content="Internal walls are drywalled on both faces; external walls on the interior face only — see Settings.">
                            <Info size={9} className="opacity-50 hover:opacity-100 cursor-help" />
                          </Tooltip>
                        </span>
                        <span className="flex items-center gap-1.5 font-semibold capitalize">
                          <span
                            className="w-2 h-2 rounded-full shrink-0"
                            style={{ backgroundColor: d.wallType === "interior" ? "#22D3EE" : "#F43F5E" }}
                          />
                          {d.wallType ?? "exterior"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[var(--color-text-secondary)]">
                        <span className="flex items-center gap-1">
                          Thickness:
                          <Tooltip content="Thickness = Measured wall width (or 5/12 ft default)">
                            <Info size={9} className="opacity-50 hover:opacity-100 cursor-help" />
                          </Tooltip>
                        </span>
                        <span
                          className={d.thicknessMeasured ? "text-cyan-400 font-semibold" : "text-[var(--color-text-secondary)]"}
                          title={
                            d.thicknessMeasured
                              ? "Measured from the drawing's own wall faces"
                              : "Assumed default — this drawing's wall faces could not be measured"
                          }
                        >
                          {d.thicknessFt != null ? formatWallThickness(d.thicknessFt, state.unitSystem) : "—"}
                          {d.thicknessMeasured ? "" : " (assumed)"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[var(--color-text-secondary)]">
                        <span className="flex items-center gap-1">
                          Height:
                          <Tooltip content="Height = Wall Face Area ÷ Length — exact, derived from this wall's own measured face area rather than an assumed constant.">
                            <Info size={9} className="opacity-50 hover:opacity-100 cursor-help" />
                          </Tooltip>
                        </span>
                        <span className="text-[var(--color-text-primary)] font-semibold">
                          {d.perimeterFt > 0 ? formatLength(d.areaSqFt / d.perimeterFt, state.unitSystem) : "—"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[var(--color-text-secondary)]">
                        <span className="flex items-center gap-1">
                          Wall Face Area:
                          <Tooltip content={`Wall Face Area = ${Math.round(d.perimeterFt)} ft length × ${d.perimeterFt > 0 ? (d.areaSqFt / d.perimeterFt).toFixed(1) : "?"} ft height = ${Math.round(d.areaSqFt)} sq ft`}>
                            <Info size={9} className="opacity-50 hover:opacity-100 cursor-help" />
                          </Tooltip>
                        </span>
                        <span className="text-purple-400 font-semibold">{formatArea(d.areaSqFt, state.unitSystem)}</span>
                      </div>
                    </div>
                  ) : (
                    <div className="bg-black/20 rounded-md p-2.5 mb-2 space-y-2.5 text-[11px] font-mono-num border border-white/5">
                      <div className="space-y-0.5">
                        <div className="flex items-center justify-between text-[var(--color-text-secondary)]">
                          <span className="flex items-center gap-1 font-semibold text-blue-400">
                            Floor Area:
                            <Tooltip content="Enclosed area from this room's own detected polygon geometry.">
                              <Info size={9} className="opacity-50 hover:opacity-100 cursor-help" />
                            </Tooltip>
                          </span>
                          <span className="text-[var(--color-text-primary)] font-semibold">{formatArea(d.areaSqFt, state.unitSystem)}</span>
                        </div>
                        <div className="flex items-center justify-between text-[#94a3b8] pl-3 text-[10px]">
                          <span className="flex items-center gap-1">
                            ↳ Dimensions (bbox):
                            <Tooltip content="Bounding box of the room's footprint, converted using this sheet's calibrated scale (or the default nominal scale if uncalibrated). An upper bound, not the true footprint, for a non-rectangular room.">
                              <Info size={9} className="opacity-50 hover:opacity-100 cursor-help" />
                            </Tooltip>
                          </span>
                          <span>{formatLength(bbox.widthFt, state.unitSystem)} × {formatLength(bbox.heightFt, state.unitSystem)}</span>
                        </div>
                        <div className="flex items-center justify-between text-[#94a3b8] pl-3 text-[10px]">
                          <span className="flex items-center gap-1">
                            ↳ Perimeter:
                            <Tooltip content="Measured perimeter of this room's detected polygon.">
                              <Info size={9} className="opacity-50 hover:opacity-100 cursor-help" />
                            </Tooltip>
                          </span>
                          <span>{Math.round(d.perimeterFt)} ft</span>
                        </div>
                      </div>

                      {/* Material quantities (drywall/paint/flooring/roofing sheets,
                          buckets, gallons, screws) are NOT computed here. Deriving
                          them from just this room's area/perimeter with a fixed 9 ft
                          height ignores the project's actual resolved height, waste
                          factor, opening deductions, and assembly — all of which the
                          real per-trade takeoff engines already account for. Showing
                          a different, cruder number here would silently disagree with
                          the authoritative one in the trade's own takeoff. */}
                      <div className="text-[10px] text-[var(--color-text-secondary)] border-t border-white/5 pt-1.5">
                        Material quantities (sheets, gallons, buckets) are computed from the full project's
                        resolved height, waste, and assembly in each trade's takeoff — not shown per-room here.
                      </div>
                    </div>
                  )}

                  <ConfidenceBar value={d.confidence} />

                  <div className="flex items-center gap-2 mt-2.5">
                    {d.status === "pending" && (
                      <>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            approve(d);
                          }}
                          className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-md text-[11px] bg-[var(--color-success)]/10 text-[var(--color-success)] hover:bg-[var(--color-success)]/20 cursor-pointer"
                        >
                          <Check size={12} /> Approve
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            reject(d);
                          }}
                          className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-md text-[11px] bg-[var(--color-danger)]/10 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/20 cursor-pointer"
                        >
                          <X size={12} /> Reject
                        </button>
                      </>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        startEditing(d);
                      }}
                      className={`flex-1 flex items-center justify-center gap-1 py-1.5 rounded-md text-[11px] bg-white/5 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-white/10 cursor-pointer`}
                    >
                      Edit
                    </button>
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
