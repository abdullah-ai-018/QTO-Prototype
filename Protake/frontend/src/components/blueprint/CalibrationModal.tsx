import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Crosshair, X } from "lucide-react";
import { METERS_TO_FEET } from "@/lib/units";

interface CalibrationModalProps {
  open: boolean;
  onConfirm: (feet: number) => void;
  onCancel: () => void;
}

export default function CalibrationModal({ open, onConfirm, onCancel }: CalibrationModalProps) {
  const [value, setValue] = useState("10");
  const [unit, setUnit] = useState<"ft" | "m">("ft");
  const entered = Number(value);
  const feet = unit === "m" ? entered * METERS_TO_FEET : entered;
  const valid = value.trim() !== "" && !Number.isNaN(entered) && entered > 0;

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            className="relative w-full max-w-sm mx-4 rounded-xl glass-panel glow-primary overflow-hidden"
          >
            <div className="flex items-center gap-2.5 px-4 py-3 border-b border-[var(--color-border)]">
              <div className="w-7 h-7 rounded-md bg-[var(--color-primary)]/15 flex items-center justify-center text-[var(--color-primary-hover)]">
                <Crosshair size={14} />
              </div>
              <div className="flex-1">
                <div className="text-sm font-semibold">Calibrate Scale</div>
              </div>
              <button
                onClick={onCancel}
                className="w-7 h-7 rounded-md flex items-center justify-center hover:bg-white/5 text-[var(--color-text-secondary)]"
              >
                <X size={14} />
              </button>
            </div>

            <div className="p-4 space-y-3">
              <p className="text-xs text-[var(--color-text-secondary)]">
                Enter the real-world distance the reference line you just drew represents.
              </p>
              <div className="flex items-center gap-2">
                <input
                  autoFocus
                  type="number"
                  min={0}
                  step="0.1"
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && valid) onConfirm(feet);
                    if (e.key === "Escape") onCancel();
                  }}
                  className="flex-1 bg-[var(--color-panel-2)] border border-[var(--color-border)] rounded-md px-3 py-2 text-sm font-mono-num outline-none focus:border-[var(--color-primary)]/50"
                />
                <div className="flex items-center rounded-md border border-[var(--color-border)] overflow-hidden text-xs">
                  {(["ft", "m"] as const).map((u) => (
                    <button
                      key={u}
                      type="button"
                      onClick={() => setUnit(u)}
                      className={`px-2.5 py-2 transition-colors ${
                        unit === u
                          ? "bg-[var(--color-primary)] text-white"
                          : "text-[var(--color-text-secondary)] hover:bg-white/5"
                      }`}
                    >
                      {u}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[var(--color-border)]">
              <button
                onClick={onCancel}
                className="px-3 py-1.5 rounded-md text-xs border border-[var(--color-border)] hover:bg-white/5 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => valid && onConfirm(feet)}
                disabled={!valid}
                className="px-3 py-1.5 rounded-md text-xs bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Apply Calibration
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
