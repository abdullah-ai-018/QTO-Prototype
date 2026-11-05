import React, { useState } from "react";
import { Ruler, UserCheck, ShieldAlert, ArrowRight, X, ChevronDown, ChevronUp } from "lucide-react";
import { useApp } from "@/state/AppContext";

interface EstimateWarningBannerProps {
  className?: string;
  onReviewClick?: () => void;
}

export default function EstimateWarningBanner({ className = "", onReviewClick }: EstimateWarningBannerProps) {
  const { scaleWarnings, reviewWarnings, dispatch } = useApp();
  const [dismissed, setDismissed] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const hasScaleWarnings = scaleWarnings && scaleWarnings.length > 0;
  const hasReviewWarnings = reviewWarnings && reviewWarnings.length > 0;

  if (dismissed || (!hasScaleWarnings && !hasReviewWarnings)) {
    return null;
  }

  const totalNeedsReviewRooms = reviewWarnings ? reviewWarnings.reduce((acc, w) => acc + (w.needs_review_count || 1), 0) : 0;

  const handleReviewScale = () => {
    if (onReviewClick) {
      onReviewClick();
    } else {
      dispatch({ type: "SET_TOOL", tool: "calibrate" });
    }
  };

  const handleReviewRooms = () => {
    if (onReviewClick) {
      onReviewClick();
    } else {
      dispatch({ type: "SET_RIGHT_TAB", tab: "detected" });
    }
  };

  return (
    <div
      className={`rounded-lg border border-amber-500/30 bg-amber-950/40 px-3 py-2 text-amber-200 text-xs mb-2 transition-all ${className}`}
      id="estimate-warning-banner"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <ShieldAlert size={14} className="text-amber-400 shrink-0" />
          <span className="font-semibold text-amber-300 uppercase tracking-wide text-[10px] shrink-0">
            Audit Notice:
          </span>
          <span className="truncate text-[11px] text-amber-200/90 font-medium">
            {hasScaleWarnings && hasReviewWarnings
              ? `${scaleWarnings.length} page(s) on assumed scale · ${totalNeedsReviewRooms} room(s) pending review`
              : hasScaleWarnings
              ? `${scaleWarnings.length} page(s) rely on assumed scale (${scaleWarnings[0]?.scale_source || "default"})`
              : `${totalNeedsReviewRooms} room(s) routed to human review queue`}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {hasScaleWarnings && (
            <button
              onClick={handleReviewScale}
              className="px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 text-[10px] font-medium border border-amber-400/30 transition-colors cursor-pointer"
            >
              Calibrate Scale
            </button>
          )}
          {hasReviewWarnings && (
            <button
              onClick={handleReviewRooms}
              className="px-2 py-0.5 rounded bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-200 text-[10px] font-medium border border-yellow-400/30 transition-colors cursor-pointer"
            >
              Review Rooms
            </button>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="p-1 text-amber-400/70 hover:text-amber-200 transition-colors cursor-pointer"
            title={expanded ? "Collapse details" : "Expand details"}
          >
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
          <button
            onClick={() => setDismissed(true)}
            className="p-1 text-amber-400/70 hover:text-white transition-colors cursor-pointer"
            title="Dismiss notice"
          >
            <X size={12} />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-2 pt-2 border-t border-amber-500/20 space-y-1 text-[11px] font-mono text-amber-100/90">
          {hasScaleWarnings && scaleWarnings.map((w, i) => (
            <div key={i} className="flex items-start gap-1.5">
              <Ruler size={12} className="text-amber-400 mt-0.5 shrink-0" />
              <span>{w.reason}</span>
            </div>
          ))}
          {hasReviewWarnings && reviewWarnings.map((w, i) => (
            <div key={i} className="flex items-start gap-1.5">
              <UserCheck size={12} className="text-yellow-400 mt-0.5 shrink-0" />
              <span>{w.reason}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
