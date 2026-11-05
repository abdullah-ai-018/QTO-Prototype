import React from "react";

export default function Tooltip({
  children,
  content,
  direction = "up",
}: {
  children: React.ReactNode;
  content: string;
  /**
   * Which way the tooltip opens relative to its trigger. Default "up" is
   * right for most cases, but a trigger sitting at the very top of a
   * scrollable panel (e.g. the first KPI card in SummaryPanel) has nowhere
   * for an upward tooltip to render — it gets clipped by the panel's own
   * bounds/overflow. Pass "down" there instead.
   */
  direction?: "up" | "down";
}) {
  if (!content) return <>{children}</>;
  const positionClasses =
    direction === "down" ? "top-full mt-1.5" : "bottom-full mb-1.5";
  return (
    <span className="group relative inline-flex items-center">
      {children}
      <span
        className={`pointer-events-none absolute ${positionClasses} left-1/2 z-50 -translate-x-1/2 whitespace-pre-line text-left min-w-[180px] max-w-sm rounded-md bg-slate-950/95 px-2.5 py-1.5 text-[10px] text-white opacity-0 transition-opacity duration-150 group-hover:opacity-100 shadow-[0_4px_20px_rgba(0,0,0,0.6)] border border-white/10 font-sans font-medium tracking-normal normal-case pointer-events-none select-none`}
      >
        {content}
      </span>
    </span>
  );
}
