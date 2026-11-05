export default function MiniMap({
  left,
  top,
  width,
  height,
}: {
  left: number;
  top: number;
  width: number;
  height: number;
}) {
  return (
    <div className="absolute top-3 right-3 z-20 w-32 h-20 rounded-lg glass-panel overflow-hidden">
      <div className="relative w-full h-full blueprint-grid opacity-70">
        <div
          className="absolute border border-[var(--color-primary-hover)] bg-[var(--color-primary)]/10"
          style={{
            left: `${left * 100}%`,
            top: `${top * 100}%`,
            width: `${width * 100}%`,
            height: `${height * 100}%`,
          }}
        />
      </div>
      <span className="absolute bottom-1 left-1.5 text-[9px] text-[var(--color-text-secondary)] font-mono-num">
        MAP
      </span>
    </div>
  );
}

