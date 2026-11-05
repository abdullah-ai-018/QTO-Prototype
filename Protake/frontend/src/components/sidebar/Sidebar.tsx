import { useMemo, useState, useRef } from "react";
import {
  Layers,
  SquareStack,
  Paintbrush,
  Home,
  Eye,
  EyeOff,
  Map,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { useApp } from "@/state/AppContext";
import type { TradeId } from "@/types";
import type { DrawingDiscipline } from "@/lib/sheetContext";
import { useResizablePanel } from "@/hooks/useResizablePanel";
import EngineeringSheetNavigator from "@/components/blueprint/EngineeringSheetNavigator";

export default function Sidebar() {
  const { state, dispatch, breakdowns, sheetTakeoff } = useApp();
  const sidebarRef = useRef<HTMLDivElement>(null);
  const { size: sidebarWidth, isDragging: isResizing, handleProps } = useResizablePanel("sidebar-width", {
    min: 200,
    max: 400,
    defaultSize: 265,
    axis: "horizontal",
  });

  const [sheetFilterDiscipline, setSheetFilterDiscipline] = useState<DrawingDiscipline | "all">("all");
  const [sheetShowOnlyEligible, setSheetShowOnlyEligible] = useState(false);

  // Collapsible sections state
  const [expandedSections, setExpandedSections] = useState({
    sheets: true,
    summary: true,
    trades: true,
    layers: false,
  });

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const tradesList = useMemo(() => {
    return [
      {
        id: "drywall",
        label: "Drywall",
        icon: SquareStack,
        color: "#8B5CF6",
        count: breakdowns.drywall ? `${breakdowns.drywall.metrics.materialQuantity.toLocaleString()} ${breakdowns.drywall.metrics.materialUnit}` : "0 sheets",
        cost: breakdowns.drywall ? `$${breakdowns.drywall.metrics.directCost.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : "$0.00",
        hours: breakdowns.drywall ? `${breakdowns.drywall.metrics.laborHours.toFixed(1)} hrs` : "0.0 hrs",
        validated: breakdowns.drywall ? (breakdowns.drywall.metrics.status === "validated") : false,
        active: true
      },
      {
        id: "painting",
        label: "Painting",
        icon: Paintbrush,
        color: "#EC4899",
        count: breakdowns.painting ? `${breakdowns.painting.metrics.materialQuantity.toLocaleString()} ${breakdowns.painting.metrics.materialUnit}` : "0 gal",
        cost: breakdowns.painting ? `$${breakdowns.painting.metrics.directCost.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : "$0.00",
        hours: breakdowns.painting ? `${breakdowns.painting.metrics.laborHours.toFixed(1)} hrs` : "0.0 hrs",
        validated: breakdowns.painting ? (breakdowns.painting.metrics.status === "validated") : false,
        active: true
      },
      {
        id: "flooring",
        label: "Flooring",
        icon: Layers,
        color: "#10B981",
        count: breakdowns.flooring ? `${breakdowns.flooring.metrics.materialQuantity.toLocaleString()} ${breakdowns.flooring.metrics.materialUnit}` : "0 sqft",
        cost: breakdowns.flooring ? `$${breakdowns.flooring.metrics.directCost.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : "$0.00",
        hours: breakdowns.flooring ? `${breakdowns.flooring.metrics.laborHours.toFixed(1)} hrs` : "0.0 hrs",
        validated: breakdowns.flooring ? (breakdowns.flooring.metrics.status === "validated") : false,
        active: true
      },
      {
        id: "roofing",
        label: "Roofing",
        icon: Home,
        color: "#F97316",
        count: breakdowns.roofing ? `${breakdowns.roofing.metrics.materialQuantity.toLocaleString()} ${breakdowns.roofing.metrics.materialUnit}` : "0 sq",
        cost: breakdowns.roofing ? `$${breakdowns.roofing.metrics.directCost.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : "$0.00",
        hours: breakdowns.roofing ? `${breakdowns.roofing.metrics.laborHours.toFixed(1)} hrs` : "0.0 hrs",
        validated: breakdowns.roofing ? (breakdowns.roofing.metrics.status === "validated") : false,
        active: true
      },
    ];
  }, [breakdowns]);

  // Real per-layer counts for the active sheet — a layer with genuinely no
  // backing detections shows "No data detected" rather than a fake 0, and
  // its toggle is disabled since there's nothing for it to hide.
  const activeSheetDetections = useMemo(
    () => state.detections.filter((d) => d.sheetId === state.activeSheetId && d.status !== "rejected"),
    [state.detections, state.activeSheetId]
  );
  const activeSheetMeasurements = useMemo(
    () => state.measurements.filter((m) => m.sheetId === state.activeSheetId),
    [state.measurements, state.activeSheetId]
  );

  const layersList = useMemo(() => {
    const countByKind = (...kinds: string[]) =>
      activeSheetDetections.filter((d) => kinds.includes(d.kind)).length;
    return [
      { id: "arch_walls", label: "Architectural Walls", color: "#3B82F6", count: countByKind("wall"), hasData: true },
      { id: "rooms", label: "Rooms", color: "#06B6D4", count: countByKind("room"), hasData: true },
      { id: "openings", label: "Doors / Openings", color: "#10B981", count: countByKind("door", "window"), hasData: true },
      { id: "columns", label: "Columns", color: "#38BDF8", count: countByKind("column"), hasData: true },
      { id: "dimensions", label: "Dimensions", color: "#A855F7", count: activeSheetMeasurements.length, hasData: true },
      { id: "annotations", label: "Annotations", color: "#F97316", count: countByKind("annotation"), hasData: true },
      { id: "grid", label: "Grid", color: "#60A5FA", count: null, hasData: true },
      // No "mep" DetectionKind exists anywhere in the data model yet — this
      // toggle has nothing to control, so it's shown disabled and honest
      // rather than implying a working filter.
      { id: "mep", label: "MEP", color: "#818CF8", count: null, hasData: false },
    ];
  }, [activeSheetDetections, activeSheetMeasurements]);


  return (
    <>
      <aside 
        ref={sidebarRef}
        style={{ width: `${sidebarWidth}px` }}
        className="shrink-0 border-r border-white/10 bg-[#0B0E14] flex flex-col min-h-0 select-none overflow-y-auto scrollbar-custom font-sans relative"
      >
        {/* SHEETS SECTION — the single sheet-navigation surface in the app */}
        <div className="border-b border-white/10">
          <button
            onClick={() => toggleSection('sheets')}
            className="w-full p-2.5 flex items-center justify-between hover:bg-white/5 transition-colors"
          >
            <div className="flex items-center gap-1.5">
              <Map size={12} className="text-blue-400" />
              <span className="text-[10px] font-bold text-gray-300 uppercase tracking-wider">Sheets</span>
            </div>
            {expandedSections.sheets ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>

          {expandedSections.sheets && (
            <div className="px-2.5 pb-2.5">
              <EngineeringSheetNavigator
                filterDiscipline={sheetFilterDiscipline}
                onFilterDisciplineChange={setSheetFilterDiscipline}
                showOnlyEligible={sheetShowOnlyEligible}
                onShowOnlyEligibleChange={setSheetShowOnlyEligible}
              />
            </div>
          )}
        </div>

        {/* TAKEOFF SUMMARY SECTION */}
        <div className="border-b border-white/10">
          <button
            onClick={() => toggleSection('summary')}
            className="w-full p-2.5 flex items-center justify-between hover:bg-white/5 transition-colors"
          >
            <span className="text-[10px] font-bold text-gray-300 uppercase tracking-wider">Summary</span>
            {expandedSections.summary ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
          
          {expandedSections.summary && (
            <div className="px-2.5 pb-3 space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <div className="p-2 rounded bg-[#111622] border border-white/10">
                  <div className="text-[8px] text-gray-400 uppercase mb-1">Sheets</div>
                  <div className="text-lg font-bold text-white font-mono">{sheetTakeoff.sheets.toLocaleString()}</div>
                </div>
                
                <div className="p-2 rounded bg-[#111622] border border-white/10">
                  <div className="text-[8px] text-gray-400 uppercase mb-1">Area SF</div>
                  <div className={sheetTakeoff.netHangAreaSf != null ? "text-lg font-bold text-white font-mono" : "text-[10px] font-semibold text-gray-500"}>
                    {sheetTakeoff.netHangAreaSf != null
                      ? sheetTakeoff.netHangAreaSf.toLocaleString(undefined, { maximumFractionDigits: 0 })
                      : "Not available"}
                  </div>
                </div>

                <div className="p-2 rounded bg-[#111622] border border-white/10">
                  <div className="text-[8px] text-gray-400 uppercase mb-1">Cost</div>
                  <div className="text-sm font-bold text-white font-mono">
                    ${(sheetTakeoff.materialCost / 1000).toFixed(1)}k
                  </div>
                </div>

                <div className="p-2 rounded bg-[#111622] border border-white/10">
                  <div className="text-[8px] text-gray-400 uppercase mb-1">Hours</div>
                  <div className="text-sm font-bold text-white font-mono">
                    {sheetTakeoff.laborHours.toFixed(1)}
                  </div>
                </div>
              </div>

              {sheetTakeoff.eligible && (
                <div className="px-2 py-1 rounded text-[8px] bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-semibold text-center">
                  ✓ Validated
                </div>
              )}
            </div>
          )}
        </div>

        {/* TRADES SECTION */}
        <div className="border-b border-white/10">
          <button
            onClick={() => toggleSection('trades')}
            className="w-full p-2.5 flex items-center justify-between hover:bg-white/5 transition-colors"
          >
            <div className="flex items-center gap-1.5">
              <SquareStack size={12} className="text-blue-400" />
              <span className="text-[10px] font-bold text-gray-300 uppercase tracking-wider">Trades</span>
            </div>
            {expandedSections.trades ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>

          {expandedSections.trades && (
            <div className="px-2.5 pb-2.5 space-y-1">
              {tradesList.map((t) => {
                const isActive = state.summaryTab === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => dispatch({ type: "SET_SUMMARY_TAB", tab: t.id as TradeId })}
                    className={`w-full flex items-center justify-between px-2 py-1.5 rounded text-[11px] transition-all ${
                      isActive
                        ? "bg-blue-600/15 text-white font-semibold border border-blue-500/40"
                        : "text-gray-300 hover:bg-white/5 border border-transparent"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded" style={{ backgroundColor: t.color }} />
                      <span>{t.label}</span>
                    </div>
                    <span className="font-mono text-[9px] text-gray-400">{t.count}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* LAYERS SECTION */}
        <div className="border-b border-white/10">
          <button
            onClick={() => toggleSection('layers')}
            className="w-full p-2.5 flex items-center justify-between hover:bg-white/5 transition-colors"
          >
            <div className="flex items-center gap-1.5">
              <Layers size={12} className="text-cyan-400" />
              <span className="text-[10px] font-bold text-gray-300 uppercase tracking-wider">Layers</span>
            </div>
            {expandedSections.layers ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>

          {expandedSections.layers && (
            <div className="px-2.5 pb-2.5 space-y-0.5">
              {layersList.map((layer) => {
                const visible = layer.id === "grid" ? state.gridEnabled : !state.hiddenLayers[layer.id];
                const disabled = !layer.hasData;
                return (
                  <div
                    key={layer.id}
                    onClick={() => {
                      if (disabled) return;
                      layer.id === "grid"
                        ? dispatch({ type: "TOGGLE_GRID" })
                        : dispatch({ type: "TOGGLE_LAYER_VISIBILITY", layerId: layer.id });
                    }}
                    className={`flex items-center justify-between px-2 py-1 rounded text-[11px] transition-all ${
                      disabled ? "cursor-not-allowed opacity-50" : "hover:bg-white/5 cursor-pointer"
                    } ${visible ? "text-gray-200" : "text-gray-500"}`}
                    title={disabled ? "No data detected for this layer type" : undefined}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: layer.color, opacity: visible && !disabled ? 1 : 0.35 }}
                      />
                      <span className="truncate">{layer.label}</span>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {disabled ? (
                        <span className="text-[9px] text-gray-600 italic">No data detected</span>
                      ) : layer.count !== null ? (
                        <span className="font-mono text-[9px] text-gray-400">{layer.count}</span>
                      ) : null}
                      {!disabled && (visible ? (
                        <Eye size={12} className="text-blue-400 flex-shrink-0" />
                      ) : (
                        <EyeOff size={12} className="text-gray-600 flex-shrink-0" />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>


        {/* Resize handle */}
        <div
          onPointerDown={handleProps.onPointerDown}
          className={`absolute top-0 right-0 w-1 h-full cursor-ew-resize hover:bg-blue-500/50 transition-colors group ${isResizing ? "bg-blue-500/50" : ""}`}
        >
          <div className="absolute right-0 top-1/2 -translate-y-1/2 w-1 h-12 bg-blue-500/30 group-hover:bg-blue-500/70 rounded-l transition-colors" />
        </div>
      </aside>
    </>
  );
}
