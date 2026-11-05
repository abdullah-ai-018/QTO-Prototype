export default function ScanOverlay({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-md">
      <div className="absolute inset-x-0 top-0 h-1/12 animate-scan">
        <div className="h-px w-full bg-[var(--color-primary-hover)] shadow-[0_0_20px_4px_rgba(59,130,246,0.9)]" />
        <div className="h-24 w-full bg-gradient-to-b from-[var(--color-primary)]/25 to-transparent" />
      </div>
      <div className="absolute top-3 left-3 flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-black/60 border border-[var(--color-primary)]/40 text-[11px] text-[var(--color-primary-hover)] font-mono-num">
        <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-primary-hover)] animate-pulse-glow" />
        AI SCANNING…
      </div>
    </div>
  );
}
