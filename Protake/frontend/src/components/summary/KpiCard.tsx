import { motion } from "framer-motion";
import { Info, type LucideIcon } from "lucide-react";
import Tooltip from "../ui/Tooltip";

export default function KpiCard({
  label,
  value,
  unit,
  accent,
  icon: Icon,
  formula,
}: {
  label: string;
  value: string;
  unit?: string;
  accent?: string;
  icon: LucideIcon;
  formula?: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel-2)] p-4 flex flex-col gap-2 min-w-[180px]">
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-wide text-[var(--color-text-secondary)] flex items-center gap-1">
          {label}
          {formula && (
            <Tooltip content={formula} direction="down">
              <Info size={11} className="opacity-50 hover:opacity-100 cursor-help" />
            </Tooltip>
          )}
        </span>
        <Icon size={14} className={accent ?? "text-[var(--color-text-secondary)]"} />
      </div>
      <motion.div
        key={value}
        initial={{ opacity: 0.4, y: 2 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="text-xl font-semibold font-mono-num"
      >
        {value}
        {unit && <span className="text-xs text-[var(--color-text-secondary)] ml-1 font-sans">{unit}</span>}
      </motion.div>
    </div>
  );
}
