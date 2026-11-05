import { AnimatePresence, motion } from "framer-motion";
import { X, ClipboardCheck } from "lucide-react";
import { useApp } from "@/state/AppContext";
import EligibilityDashboard from "./EligibilityDashboard";

/**
 * Modal shell around EligibilityDashboard — the dashboard component itself
 * has no visibility control of its own, so this owns the open/close state
 * (state.eligibilityDashboardOpen) and overlay chrome, matching the
 * ReportModal/SettingsModal pattern. Reachable from MenuBar/Toolbar via
 * OPEN_ELIGIBILITY_DASHBOARD.
 */
export default function EligibilityDashboardModal() {
  const { state, dispatch } = useApp();

  function close() {
    dispatch({ type: "CLOSE_ELIGIBILITY_DASHBOARD" });
  }

  return (
    <AnimatePresence>
      {state.eligibilityDashboardOpen && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center p-6"
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
            className="relative w-full max-w-6xl max-h-[90vh] overflow-y-auto rounded-xl glass-panel glow-primary"
          >
            <div className="sticky top-0 z-10 flex items-center gap-2.5 px-4 py-3 border-b border-[var(--color-border)] bg-[var(--color-panel)]">
              <div className="w-7 h-7 rounded-md bg-[var(--color-primary)]/15 flex items-center justify-center text-[var(--color-primary-hover)]">
                <ClipboardCheck size={14} />
              </div>
              <div className="flex-1">
                <div className="text-sm font-semibold">Sheet Eligibility Dashboard</div>
                <div className="text-[11px] text-[var(--color-text-secondary)]">
                  Takeoff-eligibility evidence and classification for every sheet in this project
                </div>
              </div>
              <button
                onClick={close}
                className="w-7 h-7 rounded-md flex items-center justify-center hover:bg-white/5 text-[var(--color-text-secondary)]"
              >
                <X size={14} />
              </button>
            </div>
            <div className="p-4">
              <EligibilityDashboard />
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
