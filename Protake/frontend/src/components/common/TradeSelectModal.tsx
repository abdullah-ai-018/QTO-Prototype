import { AnimatePresence, motion } from "framer-motion";
import { X, Layers, SquareStack, Home } from "lucide-react";
import type { TradeId } from "@/types";

interface TradeSelectModalProps {
  open: boolean;
  onClose: () => void;
  onSelect: (trade: TradeId | "all") => void;
}

const TRADES = [
  { id: "drywall", label: "Drywall", icon: SquareStack, desc: "Gypsum board, framing, and drywall assemblies", color: "text-cyan-400 bg-cyan-500/10 border border-cyan-500/20" },
  { id: "flooring", label: "Flooring", icon: Layers, desc: "Floor coverings, tiling, carpets, and wood", color: "text-cyan-400 bg-cyan-500/10 border border-cyan-500/20" },
  { id: "roofing", label: "Roofing", icon: Home, desc: "Roof tiles, ceiling sheets, and structural coverings", color: "text-cyan-400 bg-cyan-500/10 border border-cyan-500/20" },
] as const;

export default function TradeSelectModal({ open, onClose, onSelect }: TradeSelectModalProps) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

          {/* Modal Card */}
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.15 }}
            className="relative w-full max-w-xl rounded-xl glass-panel glow-primary overflow-hidden bg-[var(--color-panel)] border border-[var(--color-border)] text-white"
          >
            {/* Header */}
            <div className="flex items-center gap-2.5 px-5 py-4 border-b border-[var(--color-border)] bg-[var(--color-panel)]">
              <div className="w-8 h-8 rounded-md bg-[var(--color-primary)]/15 flex items-center justify-center text-[var(--color-primary-hover)]">
                <Layers size={14} />
              </div>
              <div className="flex-grow">
                <div className="text-sm font-semibold">Select QTO Trade</div>
                <div className="text-[11px] text-[var(--color-text-secondary)]">Which trade do you want Quantity Take-Off (QTO) for?</div>
              </div>
              <button
                onClick={onClose}
                className="w-7 h-7 rounded-md flex items-center justify-center hover:bg-white/5 text-[var(--color-text-secondary)] hover:text-white transition-colors cursor-pointer"
              >
                <X size={14} />
              </button>
            </div>

            {/* Body */}
            <div className="p-5 space-y-4 bg-[var(--color-panel)]">
              <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">
                Choose the target trade to initialize your workspace. Only the selected trade's data will be loaded and evaluated. Detections and costs for other trades will be hidden to keep your workspace focused.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {TRADES.map((t) => {
                  const Icon = t.icon;
                  return (
                    <button
                      key={t.id}
                      onClick={() => onSelect(t.id as TradeId)}
                      className="flex flex-col items-start gap-3 p-3.5 rounded-lg border border-[var(--color-border)] bg-white/5 hover:bg-white/10 hover:border-[var(--color-primary)]/50 transition-all group cursor-pointer text-left"
                    >
                      <div className={`w-10 h-10 shrink-0 rounded-md flex items-center justify-center ${t.color} group-hover:scale-105 transition-transform`}>
                        <Icon size={20} />
                      </div>
                      <div className="space-y-1">
                        <div className="text-xs font-semibold text-white group-hover:text-[var(--color-primary-hover)] transition-colors">
                          {t.label}
                        </div>
                        <div className="text-[10px] text-[var(--color-text-secondary)] leading-normal line-clamp-3">
                          {t.desc}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between gap-2 px-5 py-4 border-t border-[var(--color-border)] bg-[var(--color-panel)]">
              <button
                onClick={onClose}
                className="px-3.5 py-2 rounded-md text-xs border border-[var(--color-border)] hover:bg-white/5 text-[var(--color-text-secondary)] hover:text-white transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={() => onSelect("all")}
                className="px-4 py-2 rounded-md text-xs font-semibold bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] transition-colors text-white cursor-pointer"
              >
                Show All Trades (Default)
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
