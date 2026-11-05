import { useState, useMemo } from "react";
import { WALL_CATEGORY_COLORS, getCanonicalWallCategory, CanonicalWallCategory } from "@/lib/colors";
import { useApp } from "@/state/AppContext";
import { Filter, Eye, EyeOff, ChevronDown, ChevronUp, Layers } from "lucide-react";

export default function WallCanvasLegend() {
  const { state, dispatch } = useApp();
  const [collapsed, setCollapsed] = useState(false);

  // Compute live wall counts per category for the current active sheet
  const activeWalls = useMemo(() => {
    return state.detections.filter(
      (d) => d.sheetId === state.activeSheetId && d.kind === "wall" && d.status !== "rejected"
    );
  }, [state.detections, state.activeSheetId]);

  const categoryCounts = useMemo(() => {
    const counts: Record<CanonicalWallCategory, number> = {
      INTERIOR_PARTITION: 0,
      EXTERIOR_PERIMETER: 0,
      STRUCTURAL_BEARING: 0,
      STAIR_CORE: 0,
      CORRIDOR: 0,
      WET_CORE: 0,
      DEMISING: 0,
      SHAFT: 0,
      NEEDS_REVIEW: 0,
    };

    activeWalls.forEach((w) => {
      const code = getCanonicalWallCategory(w.wallTypeCode, w.wallType, w.wallTag, w.status, w.confidence, w.classification);
      if (counts[code] !== undefined) {
        counts[code]++;
      } else {
        counts.NEEDS_REVIEW++;
      }
    });

    return counts;
  }, [activeWalls]);

  const categories: Array<{ key: CanonicalWallCategory; shortLabel: string; color: string; label: string }> = [
    { key: "INTERIOR_PARTITION", shortLabel: "Interior", color: WALL_CATEGORY_COLORS.INTERIOR_PARTITION.color, label: "Interior Partition" },
    { key: "EXTERIOR_PERIMETER", shortLabel: "Exterior", color: WALL_CATEGORY_COLORS.EXTERIOR_PERIMETER.color, label: "Exterior / Perimeter" },
    { key: "STRUCTURAL_BEARING", shortLabel: "Structural", color: WALL_CATEGORY_COLORS.STRUCTURAL_BEARING.color, label: "Structural / Bearing" },
    { key: "STAIR_CORE", shortLabel: "Stair/Core", color: WALL_CATEGORY_COLORS.STAIR_CORE.color, label: "Stair / Core" },
    { key: "CORRIDOR", shortLabel: "Corridor", color: WALL_CATEGORY_COLORS.CORRIDOR.color, label: "Corridor Wall" },
    { key: "WET_CORE", shortLabel: "Wet Core", color: WALL_CATEGORY_COLORS.WET_CORE.color, label: "Wet Core" },
    { key: "DEMISING", shortLabel: "Demising", color: WALL_CATEGORY_COLORS.DEMISING.color, label: "Demising Wall" },
    { key: "SHAFT", shortLabel: "Shaft", color: WALL_CATEGORY_COLORS.SHAFT.color, label: "Shaft Wall" },
    { key: "NEEDS_REVIEW", shortLabel: "Review", color: WALL_CATEGORY_COLORS.NEEDS_REVIEW.color, label: "Needs Review" },
  ];

  const currentFilter = state.wallCategoryFilter;

  return (
    <div className="absolute bottom-12 left-4 z-20 bg-[var(--color-panel)]/95 border border-[var(--color-border)] rounded-xl shadow-2xl backdrop-blur-md text-[11px] select-none pointer-events-auto w-[320px] overflow-hidden transition-all duration-200 font-sans">
      {/* Header bar */}
      <div className="px-3 py-2 bg-white/[0.03] border-b border-white/10 flex items-center justify-between">
        <div className="flex items-center gap-1.5 font-semibold text-[var(--color-text-primary)] text-xs">
          <Layers size={13} className="text-[var(--color-primary)]" />
          <span>Wall Classification</span>
          <span className="text-[10px] font-mono text-[var(--color-text-secondary)] font-normal">
            ({activeWalls.length})
          </span>
        </div>
        <div className="flex items-center gap-1">
          {currentFilter && (
            <button
              onClick={() => dispatch({ type: "SET_WALL_CATEGORY_FILTER", filter: null })}
              className="text-[9px] px-1.5 py-0.5 rounded bg-white/10 text-cyan-400 hover:bg-white/20 transition-colors cursor-pointer"
              title="Reset isolation filter"
            >
              Reset
            </button>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-1 text-[var(--color-text-secondary)] hover:text-white rounded hover:bg-white/10 transition-colors cursor-pointer"
            title={collapsed ? "Expand legend" : "Collapse legend"}
          >
            {collapsed ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {!collapsed && (
        <div className="p-2.5 space-y-2.5">
          {/* Quick Filter Bar */}
          <div className="space-y-1">
            <div className="text-[9px] font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider flex items-center gap-1">
              <Filter size={10} />
              <span>Isolate Category</span>
            </div>
            <div className="flex flex-wrap gap-1">
              <button
                onClick={() => dispatch({ type: "SET_WALL_CATEGORY_FILTER", filter: null })}
                className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors cursor-pointer ${
                  currentFilter === null
                    ? "bg-white/20 text-white font-bold border border-white/30"
                    : "bg-black/30 text-[var(--color-text-secondary)] hover:bg-white/10 border border-transparent"
                }`}
              >
                All
              </button>
              {categories.map((cat) => {
                const isSelected = currentFilter === cat.key;
                const count = categoryCounts[cat.key] || 0;
                return (
                  <button
                    key={`filter-${cat.key}`}
                    onClick={() => dispatch({ type: "SET_WALL_CATEGORY_FILTER", filter: isSelected ? null : cat.key })}
                    className={`px-2 py-0.5 rounded text-[10px] font-medium transition-all cursor-pointer flex items-center gap-1 ${
                      isSelected
                        ? "text-white font-bold border shadow-sm"
                        : "bg-black/30 text-[var(--color-text-secondary)] hover:bg-white/10 border border-transparent"
                    }`}
                    style={
                      isSelected
                        ? { backgroundColor: `${cat.color}33`, borderColor: cat.color, color: cat.color }
                        : {}
                    }
                  >
                    <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: cat.color }} />
                    <span>{cat.shortLabel}</span>
                    {count > 0 && <span className="text-[9px] opacity-70 font-mono">({count})</span>}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Category List with Toggle & Count */}
          <div className="space-y-1 pt-1 border-t border-white/10">
            <div className="text-[9px] font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider">
              Category Breakdown
            </div>
            <div className="space-y-0.5 max-h-[160px] overflow-y-auto pr-0.5 scrollbar-custom">
              {categories.map((cat) => {
                const count = categoryCounts[cat.key] || 0;
                const isHidden = !!state.hiddenWallCategories[cat.key];
                const isIsolated = currentFilter === cat.key;

                return (
                  <div
                    key={cat.key}
                    className={`flex items-center justify-between px-2 py-1 rounded-md transition-colors ${
                      isIsolated ? "bg-white/[0.08]" : "hover:bg-white/[0.04]"
                    }`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className="w-2.5 h-2.5 rounded-full shrink-0 shadow-sm transition-transform"
                        style={{
                          backgroundColor: cat.color,
                          boxShadow: isIsolated ? `0 0 8px ${cat.color}` : undefined,
                        }}
                      />
                      <span
                        className={`truncate font-medium ${
                          isHidden ? "line-through text-gray-500" : "text-[var(--color-text-primary)]"
                        }`}
                      >
                        {cat.label}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <span className="font-mono text-[10px] text-[var(--color-text-secondary)] bg-white/5 px-1.5 py-0.5 rounded">
                        {count}
                      </span>
                      <button
                        onClick={() => dispatch({ type: "TOGGLE_WALL_CATEGORY_VISIBILITY", category: cat.key })}
                        className="p-1 text-[var(--color-text-secondary)] hover:text-white rounded transition-colors cursor-pointer"
                        title={isHidden ? `Show ${cat.label}` : `Hide ${cat.label}`}
                      >
                        {isHidden ? <EyeOff size={12} className="text-amber-400" /> : <Eye size={12} />}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
