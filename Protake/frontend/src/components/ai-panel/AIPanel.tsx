import { useEffect } from "react";
import { motion } from "framer-motion";
import { Boxes, Sparkles, History as HistoryIcon, ShieldCheck, List, type LucideIcon } from "lucide-react";
import { useApp } from "@/state/AppContext";
import type { RightTab } from "@/state/appState";
import { useResizablePanel } from "@/hooks/useResizablePanel";
import DetectedObjectsTab from "./DetectedObjectsTab";
import AssistantTab from "./AssistantTab";
import HistoryTab from "./HistoryTab";
import VerificationTab from "./VerificationTab";
import ScheduleTab from "./ScheduleTab";

const TABS: { id: RightTab; label: string; icon: LucideIcon }[] = [
  { id: "detected", label: "Detected", icon: Boxes },
  { id: "schedule", label: "Schedule", icon: List },
  { id: "verify", label: "Verify", icon: ShieldCheck },
  { id: "assistant", label: "Assistant", icon: Sparkles },
  { id: "history", label: "History", icon: HistoryIcon },
];

import SelectedWallInspector from "./SelectedWallInspector";

export default function AIPanel() {
  const { state, dispatch } = useApp();
  const { size: panelWidth, isDragging: isResizing, handleProps } = useResizablePanel("inspector-width", {
    min: 280,
    max: 480,
    defaultSize: 330,
    axis: "horizontal",
    invert: true, // handle sits on the LEFT edge of this right-docked panel
  });

  useEffect(() => {
    if (state.rightTab === "schedule" && state.summaryTab !== "openings") {
      dispatch({ type: "SET_RIGHT_TAB", tab: "detected" });
    }
  }, [state.rightTab, state.summaryTab, dispatch]);

  const pendingCount = state.detections.filter(
    (d) => d.sheetId === state.activeSheetId && d.status === "pending" && d.kind !== "door" && d.kind !== "window"
  ).length;

  const selectedWall = state.detections.find(
    (d) => d.id === state.selectedDetectionId && d.kind === "wall"
  );

  const visibleTabs = TABS.filter((t) => {
    if (t.id === "schedule") {
      return state.summaryTab === "openings";
    }
    return true;
  });

  return (
    <aside
      style={{ width: `${panelWidth}px` }}
      className="shrink-0 border-l border-white/10 bg-[#0B0E14] flex flex-col min-h-0 relative"
    >
      <div
        onPointerDown={handleProps.onPointerDown}
        className={`absolute top-0 left-0 w-1 h-full cursor-ew-resize hover:bg-blue-500/50 transition-colors z-10 group ${isResizing ? "bg-blue-500/50" : ""}`}
      >
        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-12 bg-blue-500/30 group-hover:bg-blue-500/70 rounded-r transition-colors" />
      </div>
      <div className="flex items-center border-b border-white/10 bg-[#111622]">
        {visibleTabs.map((t) => {
          const Icon = t.icon;
          const active = state.rightTab === t.id;
          return (
             <button
              key={t.id}
              onClick={() => dispatch({ type: "SET_RIGHT_TAB", tab: t.id })}
              className={`relative flex-1 flex flex-col items-center justify-center gap-0.5 py-2 text-[9px] font-medium transition-colors cursor-pointer ${
                active ? "text-white font-semibold" : "text-gray-400 hover:text-white"
              }`}
            >
              <Icon size={13} className="shrink-0" />
              <span>{t.label}</span>
              {t.id === "detected" && pendingCount > 0 && (
                <span className="absolute top-1 right-1.5 min-w-[13px] h-[13px] px-0.5 rounded-full bg-[var(--color-warning)] text-black text-[8px] font-semibold flex items-center justify-center">
                  {pendingCount}
                </span>
              )}
              {active && (
                <motion.span
                  layoutId="activeRightTab"
                  className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full bg-[var(--color-primary)] shadow-sm shadow-[var(--color-primary)]"
                  transition={{ type: "spring", stiffness: 500, damping: 35 }}
                />
              )}
            </button>
          );
        })}
      </div>

      {state.rightTab === "detected" && (selectedWall ? <SelectedWallInspector detection={selectedWall} /> : <DetectedObjectsTab />)}
      {state.rightTab === "schedule" && <ScheduleTab />}
      {state.rightTab === "verify" && <VerificationTab />}
      {state.rightTab === "assistant" && <AssistantTab />}
      {state.rightTab === "history" && <HistoryTab />}
    </aside>
  );
}
