import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Settings, X } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/state/AppContext";
import { DEFAULT_DRYWALL_SETTINGS } from "@/lib/estimating";

/**
 * Global takeoff settings — currently just the drywall assembly
 * assumptions (wall height, sides-per-wall-type multipliers), kept
 * user-configurable rather than hardcoded so the same tool supports
 * residential (2 sides internal / 1 external is typical), commercial, or a
 * custom assembly spec. Reachable from both navbars (MenuBar on the
 * landing page, Toolbar in the workspace) via OPEN_SETTINGS.
 */
export default function SettingsModal() {
  const { state, dispatch } = useApp();
  const [heightFt, setHeightFt] = useState(String(state.drywallSettings.wallHeightFt));
  const [internalSides, setInternalSides] = useState(String(state.drywallSettings.internalWallSides));
  const [externalSides, setExternalSides] = useState(String(state.drywallSettings.externalWallSides));

  useEffect(() => {
    if (state.settingsModalOpen) {
      setHeightFt(String(state.drywallSettings.wallHeightFt));
      setInternalSides(String(state.drywallSettings.internalWallSides));
      setExternalSides(String(state.drywallSettings.externalWallSides));
    }
  }, [state.settingsModalOpen, state.drywallSettings]);

  function close() {
    dispatch({ type: "CLOSE_SETTINGS" });
  }

  function save() {
    const height = Number(heightFt);
    const internal = Number(internalSides);
    const external = Number(externalSides);
    if (!Number.isFinite(height) || height <= 0 || !Number.isFinite(internal) || internal <= 0 || !Number.isFinite(external) || external <= 0) {
      toast.error("Invalid settings", { description: "Height and sides must be positive numbers." });
      return;
    }
    dispatch({
      type: "SET_DRYWALL_SETTINGS",
      settings: { wallHeightFt: height, internalWallSides: internal, externalWallSides: external },
    });
    toast.success("Settings saved", { description: "Drywall takeoff will recalculate with the new assembly assumptions." });
    close();
  }

  function resetDefaults() {
    setHeightFt(String(DEFAULT_DRYWALL_SETTINGS.wallHeightFt));
    setInternalSides(String(DEFAULT_DRYWALL_SETTINGS.internalWallSides));
    setExternalSides(String(DEFAULT_DRYWALL_SETTINGS.externalWallSides));
  }

  return (
    <AnimatePresence>
      {state.settingsModalOpen && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={close} />
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            className="relative w-full max-w-md mx-4 rounded-xl glass-panel glow-primary overflow-hidden"
          >
            <div className="flex items-center gap-2.5 px-4 py-3 border-b border-[var(--color-border)]">
              <div className="w-7 h-7 rounded-md bg-[var(--color-primary)]/15 flex items-center justify-center text-[var(--color-primary-hover)]">
                <Settings size={14} />
              </div>
              <div className="flex-1">
                <div className="text-sm font-semibold">Takeoff Settings</div>
                <div className="text-[11px] text-[var(--color-text-secondary)]">Drywall assembly assumptions</div>
              </div>
              <button
                onClick={close}
                className="w-7 h-7 rounded-md flex items-center justify-center hover:bg-white/5 text-[var(--color-text-secondary)]"
              >
                <X size={14} />
              </button>
            </div>

            <div className="p-4 space-y-4">
              <p className="text-xs text-[var(--color-text-secondary)]">
                Drywall Area = Wall Linear Feet × Wall Height × Sides. Internal walls are typically drywalled
                on both faces; external walls only on the interior face — adjust for residential, commercial,
                or a custom assembly spec.
              </p>

              <label className="block">
                <span className="text-xs font-medium text-[var(--color-text-primary)]">Wall Height (ft)</span>
                <input
                  type="number"
                  min="1"
                  step="0.5"
                  value={heightFt}
                  onChange={(e) => setHeightFt(e.target.value)}
                  className="mt-1 w-full bg-[var(--color-panel-2)] border border-[var(--color-border)] rounded-md px-3 py-2 text-sm outline-none focus:border-[var(--color-primary)]/50"
                />
              </label>

              <label className="block">
                <span className="text-xs font-medium text-[var(--color-text-primary)]">Internal Wall Sides</span>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={internalSides}
                  onChange={(e) => setInternalSides(e.target.value)}
                  className="mt-1 w-full bg-[var(--color-panel-2)] border border-[var(--color-border)] rounded-md px-3 py-2 text-sm outline-none focus:border-[var(--color-primary)]/50"
                />
                <span className="text-[10px] text-[var(--color-text-secondary)]">Default 2 — drywall hung on both faces</span>
              </label>

              <label className="block">
                <span className="text-xs font-medium text-[var(--color-text-primary)]">External Wall Sides</span>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={externalSides}
                  onChange={(e) => setExternalSides(e.target.value)}
                  className="mt-1 w-full bg-[var(--color-panel-2)] border border-[var(--color-border)] rounded-md px-3 py-2 text-sm outline-none focus:border-[var(--color-primary)]/50"
                />
                <span className="text-[10px] text-[var(--color-text-secondary)]">Default 1 — drywall hung on the interior face only</span>
              </label>
            </div>

            <div className="flex items-center justify-between gap-2 px-4 py-3 border-t border-[var(--color-border)]">
              <button
                onClick={resetDefaults}
                className="px-3 py-1.5 rounded-md text-xs border border-[var(--color-border)] hover:bg-white/5 transition-colors"
              >
                Reset Defaults
              </button>
              <div className="flex items-center gap-2">
                <button
                  onClick={close}
                  className="px-3 py-1.5 rounded-md text-xs border border-[var(--color-border)] hover:bg-white/5 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={save}
                  className="px-3 py-1.5 rounded-md text-xs bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] transition-colors text-white"
                >
                  Save
                </button>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
