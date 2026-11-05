import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  MousePointer2,
  Hand,
  Square,
  Ruler,
  Hexagon,
  ListChecks,
  Crosshair,
  ZoomIn,
  ZoomOut,
  FileDown,
  Save,
  Undo2,
  Redo2,
  FileText,
  Search,
  BotMessageSquare,
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/state/AppContext";
import { saveProject } from "@/lib/project";
import type { ToolId } from "@/types";

interface Command {
  id: string;
  label: string;
  group: string;
  icon: LucideIcon;
  shortcut?: string;
  run: () => void;
}

export default function CommandPalette() {
  const { state, dispatch, canUndo, canRedo } = useApp();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  const setTool = (tool: ToolId) => dispatch({ type: "SET_TOOL", tool });

  const commands: Command[] = useMemo(
    () => [
      { id: "tool-select", label: "Select Tool", group: "Tools", icon: MousePointer2, shortcut: "V", run: () => setTool("select") },
      { id: "tool-pan", label: "Pan Tool", group: "Tools", icon: Hand, shortcut: "H", run: () => setTool("pan") },
      { id: "tool-ask-ai", label: "Ask AI Tool", group: "Tools", icon: BotMessageSquare, shortcut: "K", run: () => setTool("ask-ai") },
      { id: "tool-area", label: "Area Measure", group: "Tools", icon: Square, shortcut: "A", run: () => setTool("area") },
      { id: "tool-linear", label: "Linear Measure", group: "Tools", icon: Ruler, shortcut: "L", run: () => setTool("linear") },
      { id: "tool-polygon", label: "Polygon Tool", group: "Tools", icon: Hexagon, shortcut: "P", run: () => setTool("polygon") },
      { id: "tool-count", label: "Count Tool", group: "Tools", icon: ListChecks, shortcut: "C", run: () => setTool("count") },
      { id: "tool-calibrate", label: "Calibrate Scale", group: "Tools", icon: Crosshair, shortcut: "X", run: () => setTool("calibrate") },
      { id: "zoom-in", label: "Zoom In", group: "View", icon: ZoomIn, shortcut: "+", run: () => dispatch({ type: "SET_ZOOM", zoom: state.zoom + 0.25 }) },
      { id: "zoom-out", label: "Zoom Out", group: "View", icon: ZoomOut, shortcut: "-", run: () => dispatch({ type: "SET_ZOOM", zoom: state.zoom - 0.25 }) },
      {
        id: "undo",
        label: "Undo",
        group: "Edit",
        icon: Undo2,
        shortcut: "⌘Z",
        run: () => canUndo && dispatch({ type: "UNDO" }),
      },
      {
        id: "redo",
        label: "Redo",
        group: "Edit",
        icon: Redo2,
        shortcut: "⌘⇧Z",
        run: () => canRedo && dispatch({ type: "REDO" }),
      },
      {
        id: "save",
        label: "Save Project",
        group: "Project",
        icon: Save,
        shortcut: "⌘S",
        run: () => saveProject(state),
      },
      {
        id: "report",
        label: "Generate Estimate Report",
        group: "Project",
        icon: FileText,
        run: () => dispatch({ type: "OPEN_REPORT" }),
      },
      {
        id: "export",
        label: "Export Takeoff (CSV)",
        group: "Project",
        icon: FileDown,
        run: () => toast.info("Preparing export…", { description: "Your CSV will download shortly" }),
      },
    ],
    [state.zoom, state.revision, canUndo, canRedo, dispatch]
  );

  const filtered = commands.filter((c) => c.label.toLowerCase().includes(query.toLowerCase()));

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  useEffect(() => {
    if (!state.commandPaletteOpen) setQuery("");
  }, [state.commandPaletteOpen]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (!state.commandPaletteOpen) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const cmd = filtered[activeIndex];
        if (cmd) {
          cmd.run();
          dispatch({ type: "CLOSE_COMMAND_PALETTE" });
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [state.commandPaletteOpen, filtered, activeIndex, dispatch]);

  return (
    <AnimatePresence>
      {state.commandPaletteOpen && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center pt-[14vh]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => dispatch({ type: "CLOSE_COMMAND_PALETTE" })}
          />
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            className="relative w-full max-w-xl mx-4 rounded-xl glass-panel glow-primary overflow-hidden"
          >
            <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--color-border)]">
              <Search size={16} className="text-[var(--color-text-secondary)]" />
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Type a command or search…"
                className="flex-1 bg-transparent outline-none text-sm placeholder:text-[var(--color-text-secondary)]"
              />
              <kbd className="key">ESC</kbd>
            </div>
            <div className="max-h-80 overflow-y-auto py-2">
              {filtered.length === 0 && (
                <div className="px-4 py-8 text-center text-sm text-[var(--color-text-secondary)]">No matching commands</div>
              )}
              {filtered.map((cmd, i) => {
                const Icon = cmd.icon;
                return (
                  <button
                    key={cmd.id}
                    onMouseEnter={() => setActiveIndex(i)}
                    onClick={() => {
                      cmd.run();
                      dispatch({ type: "CLOSE_COMMAND_PALETTE" });
                    }}
                    className={`w-full flex items-center gap-3 px-4 py-2 text-sm transition-colors ${
                      i === activeIndex ? "bg-[var(--color-primary)]/15 text-[var(--color-text-primary)]" : "text-[var(--color-text-secondary)]"
                    }`}
                  >
                    <Icon size={15} />
                    <span className="flex-1 text-left">{cmd.label}</span>
                    <span className="text-[10px] text-[var(--color-text-secondary)]">{cmd.group}</span>
                    {cmd.shortcut && <kbd className="key">{cmd.shortcut}</kbd>}
                  </button>
                );
              })}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
