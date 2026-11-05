import { useEffect } from "react";
import { toast } from "sonner";
import { useApp } from "@/state/AppContext";
import { saveProject } from "@/lib/project";
import type { ToolId } from "@/types";

const TOOL_KEYS: Record<string, ToolId> = {
  v: "select",
  h: "pan",
  a: "area",
  l: "linear",
  p: "polygon",
  c: "count",
  x: "calibrate",
  k: "ask-ai",
};

export default function GlobalShortcuts() {
  const { state, dispatch, canUndo, canRedo } = useApp();

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const meta = e.metaKey || e.ctrlKey;
      const target = e.target as HTMLElement;
      const typing = ["INPUT", "TEXTAREA"].includes(target?.tagName) || target?.isContentEditable;

      if (meta && e.key.toLowerCase() === "k") {
        e.preventDefault();
        dispatch({ type: state.commandPaletteOpen ? "CLOSE_COMMAND_PALETTE" : "OPEN_COMMAND_PALETTE" });
        return;
      }

      if (state.commandPaletteOpen) {
        if (e.key === "Escape") dispatch({ type: "CLOSE_COMMAND_PALETTE" });
        return;
      }

      if (typing) return;

      if (meta && e.key.toLowerCase() === "z" && !e.shiftKey) {
        e.preventDefault();
        if (canUndo) {
          dispatch({ type: "UNDO" });
          toast("Undo", { description: "Reverted last action" });
        }
        return;
      }
      if (meta && (e.key.toLowerCase() === "y" || (e.key.toLowerCase() === "z" && e.shiftKey))) {
        e.preventDefault();
        if (canRedo) {
          dispatch({ type: "REDO" });
          toast("Redo", { description: "Re-applied action" });
        }
        return;
      }
      if (meta && e.key.toLowerCase() === "s") {
        e.preventDefault();
        saveProject(state);
        return;
      }

      if (state.uploadStage !== "complete") return;

      if (e.key === "Escape") {
        if (state.reportModalOpen) dispatch({ type: "CLOSE_REPORT" });
        dispatch({ type: "SELECT_DETECTION", id: null });
        return;
      }

      const tool = TOOL_KEYS[e.key.toLowerCase()];
      if (tool) {
        dispatch({ type: "SET_TOOL", tool });
      }

      if (e.key === "g") dispatch({ type: "TOGGLE_GRID" });
      if (e.key === "s" && !meta) dispatch({ type: "TOGGLE_SNAP" });
      if (e.key === "=" || e.key === "+") dispatch({ type: "SET_ZOOM", zoom: state.zoom + 0.25 });
      if (e.key === "-") dispatch({ type: "SET_ZOOM", zoom: state.zoom - 0.25 });
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [state.commandPaletteOpen, state.zoom, state.uploadStage, state.reportModalOpen, state.revision, canUndo, canRedo, dispatch]);

  return null;
}
