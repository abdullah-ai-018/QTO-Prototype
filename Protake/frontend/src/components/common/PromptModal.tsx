import { useState, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Type, X } from "lucide-react";

interface PromptModalProps {
  open: boolean;
  title: string;
  description: string;
  placeholder?: string;
  defaultValue?: string;
  onConfirm: (value: string) => void;
  onCancel: () => void;
}

export default function PromptModal({
  open,
  title,
  description,
  placeholder,
  defaultValue = "",
  onConfirm,
  onCancel,
}: PromptModalProps) {
  const [value, setValue] = useState(defaultValue);

  useEffect(() => {
    if (open) {
      setValue(defaultValue);
    }
  }, [open, defaultValue]);

  const handleConfirm = () => {
    onConfirm(value);
  };

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
                <Type size={14} />
              </div>
              <div className="flex-1">
                <div className="text-sm font-semibold">{title}</div>
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
                {description}
              </p>
              <input
                autoFocus
                type="text"
                placeholder={placeholder}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleConfirm();
                  if (e.key === "Escape") onCancel();
                }}
                className="w-full bg-[var(--color-panel-2)] border border-[var(--color-border)] rounded-md px-3 py-2 text-sm outline-none focus:border-[var(--color-primary)]/50"
              />
            </div>

            <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-[var(--color-border)]">
              <button
                onClick={onCancel}
                className="px-3 py-1.5 rounded-md text-xs border border-[var(--color-border)] hover:bg-white/5 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirm}
                className="px-3 py-1.5 rounded-md text-xs bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] transition-colors text-white"
              >
                Submit
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
