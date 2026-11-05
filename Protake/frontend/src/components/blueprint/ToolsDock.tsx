import { useState } from "react";
import {
  MousePointer2,
  Hand,
  Ruler,
  Square,
  Pentagon,
  Hash,
  Scale,
  MessageSquare,
  StickyNote,
  Sparkles,
  Filter,
  Layers,
  Maximize,
  Maximize2,
  Minimize2,
  ZoomIn,
  ZoomOut,
  Sliders,
  type LucideIcon,
} from "lucide-react";
import { useApp } from "@/state/AppContext";
import { WALL_CATEGORY_COLORS, type CanonicalWallCategory } from "@/lib/colors";
import type { ToolId } from "@/types";

const ISOLATE_CATEGORIES: Array<{ key: CanonicalWallCategory; label: string }> = [
  { key: "INTERIOR_PARTITION", label: "Interior Partition" },
  { key: "EXTERIOR_PERIMETER", label: "Exterior / Perimeter" },
  { key: "STRUCTURAL_BEARING", label: "Structural / Bearing" },
  { key: "STAIR_CORE", label: "Stair / Core" },
  { key: "CORRIDOR", label: "Corridor Wall" },
  { key: "WET_CORE", label: "Wet Core" },
  { key: "DEMISING", label: "Demising Wall" },
  { key: "SHAFT", label: "Shaft Wall" },
  { key: "NEEDS_REVIEW", label: "Needs Review" },
];

interface ToolsDockProps {
  legendOpen: boolean;
  onToggleLegend: () => void;
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onZoomFit: () => void;
  onZoomPreset: (scale: number) => void;
  layerOpacity: number;
  onLayerOpacityChange: (val: number) => void;
}

export default function ToolsDock({
  legendOpen,
  onToggleLegend,
  isFullscreen,
  onToggleFullscreen,
  onZoomIn,
  onZoomOut,
  onZoomFit,
  onZoomPreset,
  layerOpacity,
  onLayerOpacityChange,
}: ToolsDockProps) {
  const { state, dispatch } = useApp();
  const [isolatePickerOpen, setIsolatePickerOpen] = useState(false);
  const [showOpacitySlider, setShowOpacitySlider] = useState(false);

  // Grouped Estimating & Takeoff Tools
  const navTools: { id: ToolId; icon: LucideIcon; label: string; shortcut?: string }[] = [
    { id: "select", icon: MousePointer2, label: "Select", shortcut: "V" },
    { id: "pan", icon: Hand, label: "Pan", shortcut: "H" },
  ];

  const takeoffTools: { id: ToolId; icon: LucideIcon; label: string; hint: string }[] = [
    { id: "linear", icon: Ruler, label: "Linear (LF)", hint: "Measure wall length & linear footage" },
    { id: "magic-fill", icon: Square, label: "Area (SF)", hint: "Rectangle room & drywall surface area" },
    { id: "polygon", icon: Pentagon, label: "Polygon", hint: "Multi-point custom area & perimeter" },
    { id: "count", icon: Hash, label: "Count", hint: "Item & fixture count takeoff" },
    { id: "calibrate", icon: Scale, label: "Calibrate", hint: "Set drawing scale (ft/px)" },
  ];

  const annotationTools: { id: ToolId; icon: LucideIcon; label: string; hint: string }[] = [
    { id: "callout", icon: MessageSquare, label: "Callout", hint: "Engineering callout with leader line" },
    { id: "sticky-note", icon: StickyNote, label: "Note", hint: "Field & review sticky note" },
    { id: "ask-ai", icon: Sparkles, label: "Ask AI", hint: "Inspect wall specs with AI Copilot" },
  ];

  return (
    <>
      {/* 1. LEFT VERTICAL FLOATING ESTIMATING COMMAND BAR (Compact Height) */}
      <div className="absolute top-12 left-3 z-20 flex flex-col items-center gap-1 p-1 rounded-xl bg-[#0B0E14]/95 border border-white/10 shadow-2xl backdrop-blur-xl select-none">
        {/* Navigation Tools */}
        <div className="flex flex-col items-center gap-0.5">
          {navTools.map((t) => {
            const Icon = t.icon;
            const isActive = state.activeTool === t.id;
            return (
              <button
                key={t.id}
                onClick={() => dispatch({ type: "SET_TOOL", tool: t.id })}
                className={`w-7.5 h-7.5 flex items-center justify-center rounded-lg text-[11px] font-medium transition-all cursor-pointer ${isActive
                    ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                    : "text-gray-400 hover:text-white hover:bg-white/10"
                  }`}
                title={`${t.label} (${t.shortcut})`}
              >
                <Icon size={14} />
              </button>
            );
          })}
        </div>

        <div className="h-px w-4 bg-white/10 my-0.2" />

        {/* Primary Estimating & Takeoff Tools */}
        <div className="flex flex-col items-center gap-0.5">
          {takeoffTools.map((t) => {
            const Icon = t.icon;
            const isActive = state.activeTool === t.id;
            return (
              <button
                key={t.id}
                onClick={() => dispatch({ type: "SET_TOOL", tool: t.id })}
                className={`w-7.5 h-7.5 flex items-center justify-center rounded-lg text-[11px] font-medium transition-all cursor-pointer ${isActive
                    ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                    : "text-gray-300 hover:text-white hover:bg-white/10"
                  }`}
                title={`${t.label} — ${t.hint}`}
              >
                <Icon size={14} className={isActive ? "text-white" : "text-blue-400"} />
              </button>
            );
          })}
        </div>

        <div className="h-px w-4 bg-white/10 my-0.2" />

        {/* Annotations & AI */}
        <div className="flex flex-col items-center gap-0.5">
          {annotationTools.map((t) => {
            const Icon = t.icon;
            const isActive = state.activeTool === t.id;
            return (
              <button
                key={t.id}
                onClick={() => dispatch({ type: "SET_TOOL", tool: t.id })}
                className={`w-7.5 h-7.5 flex items-center justify-center rounded-lg text-[11px] font-medium transition-all cursor-pointer ${isActive
                    ? "bg-blue-600 text-white shadow-md shadow-blue-600/30"
                    : "text-gray-400 hover:text-white hover:bg-white/10"
                  }`}
                title={`${t.label} — ${t.hint}`}
              >
                <Icon size={13} className={t.id === "ask-ai" ? "text-amber-400" : ""} />
              </button>
            );
          })}
        </div>

        <div className="h-px w-4 bg-white/10 my-0.2" />

        {/* Layer Visibility & Isolation */}
        <div className="flex flex-col items-center gap-0.5 relative">
          {/* Category Isolation Dropdown */}
          <div className="relative">
            <button
              onClick={() => setIsolatePickerOpen((v) => !v)}
              className={`w-7.5 h-7.5 flex items-center justify-center rounded-lg text-[11px] font-medium transition-all cursor-pointer ${state.wallCategoryFilter !== null
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                  : "text-gray-400 hover:text-white hover:bg-white/10"
                }`}
              title="Isolate Wall Category"
            >
              <Filter size={13} />
            </button>

            {isolatePickerOpen && (
              <div className="absolute left-full top-0 ml-2 w-52 rounded-xl bg-[#0B0E14]/95 border border-white/10 shadow-2xl backdrop-blur-xl py-1.5 z-30">
                <div className="px-3 py-1 text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                  Isolate Wall Category
                </div>
                <button
                  onClick={() => {
                    dispatch({ type: "SET_WALL_CATEGORY_FILTER", filter: null });
                    setIsolatePickerOpen(false);
                  }}
                  className={`w-full text-left px-3 py-1.5 text-[11px] hover:bg-white/10 transition-colors ${state.wallCategoryFilter === null ? "text-white font-semibold bg-white/5" : "text-gray-300"
                    }`}
                >
                  Show All Categories
                </button>
                <div className="h-px bg-white/10 my-1" />
                {ISOLATE_CATEGORIES.map((cat) => (
                  <button
                    key={cat.key}
                    onClick={() => {
                      dispatch({
                        type: "SET_WALL_CATEGORY_FILTER",
                        filter: state.wallCategoryFilter === cat.key ? null : cat.key,
                      });
                      setIsolatePickerOpen(false);
                    }}
                    className={`w-full flex items-center gap-2 text-left px-3 py-1.5 text-[11px] hover:bg-white/10 transition-colors ${state.wallCategoryFilter === cat.key ? "text-white font-semibold bg-white/5" : "text-gray-300"
                      }`}
                  >
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0 shadow-sm"
                      style={{ backgroundColor: WALL_CATEGORY_COLORS[cat.key].color }}
                    />
                    <span className="truncate">{cat.label}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Opacity Control */}
          <div className="relative">
            <button
              onClick={() => setShowOpacitySlider((v) => !v)}
              className={`w-7.5 h-7.5 flex items-center justify-center rounded-lg text-[11px] font-medium transition-all cursor-pointer ${showOpacitySlider ? "bg-white/15 text-white" : "text-gray-400 hover:text-white hover:bg-white/10"
                }`}
              title={`Layer Opacity (${layerOpacity}%)`}
            >
              <Sliders size={13} />
            </button>

            {showOpacitySlider && (
              <div className="absolute left-full top-0 ml-2 p-3 rounded-xl bg-[#0B0E14]/95 border border-white/10 shadow-2xl backdrop-blur-xl flex flex-col gap-2 z-30 w-44">
                <div className="flex items-center justify-between text-[10px] font-semibold text-gray-300">
                  <span>Layer Opacity</span>
                  <span className="font-mono text-cyan-400 font-bold">{layerOpacity}%</span>
                </div>
                <input
                  type="range"
                  min="20"
                  max="100"
                  value={layerOpacity}
                  onChange={(e) => onLayerOpacityChange(Number(e.target.value))}
                  className="w-full h-1.5 bg-white/20 rounded-lg appearance-none cursor-pointer accent-blue-500"
                />
              </div>
            )}
          </div>

          {/* Legend Toggle */}
          <button
            onClick={onToggleLegend}
            className={`w-7.5 h-7.5 flex items-center justify-center rounded-lg text-[11px] font-medium transition-all cursor-pointer ${legendOpen ? "bg-blue-600 text-white" : "text-gray-400 hover:text-white hover:bg-white/10"
              }`}
            title="Toggle Category Legend"
          >
            <Layers size={13} />
          </button>
        </div>
      </div>

      {/* 2. FLOATING VIEWPORT & ZOOM CONTROLLER (Pinned cleanly at bottom-right) */}
      <div className="absolute bottom-6 right-6 z-20 flex items-center gap-0.5 p-1 rounded-xl bg-[#0B0E14]/92 border border-white/10 shadow-2xl backdrop-blur-xl select-none">
        <button
          onClick={onZoomFit}
          title="Fit to screen (fits entire drawing)"
          className="px-2 h-8 rounded-lg text-[10px] font-semibold text-gray-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
        >
          Fit
        </button>
        <button
          onClick={() => onZoomPreset(0.5)}
          title="50% zoom"
          className="px-1.5 h-8 rounded-lg text-[10px] font-semibold text-gray-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
        >
          50%
        </button>
        <button
          onClick={() => onZoomPreset(1)}
          title="100% zoom"
          className="px-1.5 h-8 rounded-lg text-[10px] font-semibold text-gray-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
        >
          100%
        </button>
        <button
          onClick={() => onZoomPreset(2)}
          title="200% zoom"
          className="px-1.5 h-8 rounded-lg text-[10px] font-semibold text-gray-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
        >
          200%
        </button>
        <button
          onClick={() => onZoomPreset(4)}
          title="400% zoom"
          className="px-1.5 h-8 rounded-lg text-[10px] font-semibold text-gray-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
        >
          400%
        </button>

        <div className="w-px h-4 bg-white/10 mx-0.5" />

        <div className="px-1.5 h-8 flex items-center text-[10px] font-mono font-bold text-cyan-400">
          {Math.round(state.zoom * 100)}%
        </div>

        <div className="w-px h-4 bg-white/10 mx-0.5" />

        <button
          onClick={onZoomOut}
          title="Zoom out (-10%)"
          className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
        >
          <ZoomOut size={13} />
        </button>
        <button
          onClick={onZoomIn}
          title="Zoom in (+10%)"
          className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
        >
          <ZoomIn size={13} />
        </button>

        <div className="w-px h-4 bg-white/10 mx-0.5" />

        <button
          onClick={onToggleFullscreen}
          title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
          className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-300 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
        >
          {isFullscreen ? <Minimize2 size={13} /> : <Maximize size={13} />}
        </button>
        <button
          onClick={() => dispatch({ type: "TOGGLE_FOCUS_MODE" })}
          title={state.focusMode ? "Exit focus mode (Esc)" : "Focus mode — expand canvas"}
          className={`w-8 h-8 flex items-center justify-center rounded-lg transition-colors cursor-pointer ${state.focusMode ? "text-blue-400 bg-blue-600/20" : "text-gray-300 hover:text-white hover:bg-white/10"
            }`}
        >
          <Maximize2 size={13} />
        </button>
      </div>
    </>
  );
}
