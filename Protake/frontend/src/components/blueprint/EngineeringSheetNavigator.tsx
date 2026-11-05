/**
 * components/blueprint/EngineeringSheetNavigator.tsx
 *
 * Single sheet-navigation surface for the app (mounted inside the left
 * Sidebar). Shows real per-sheet classification, eligibility, and
 * engineering validation status, sourced from useSheetContext() (which
 * itself prefers real backend discipline/type/eligibility fields and only
 * falls back to string-matching when the backend hasn't classified a page
 * yet — see lib/sheetContext.ts).
 */

import { ChevronLeft, ChevronRight, CheckCircle, AlertTriangle, XCircle, Info, FileText, FileX, Loader2 } from "lucide-react";
import { useApp } from "@/state/AppContext";
import { useSheetContext, useActiveSheetContext } from "@/state/SheetContextProvider";
import type { DrawingDiscipline, TakeoffEligibilityLevel } from "@/lib/sheetContext";

const DRAWING_TYPE_LABEL: Record<string, string> = {
  floor_plan: "Floor Plan",
  roof_plan: "Roof Plan",
  ceiling_plan: "Ceiling Plan",
  elevation: "Elevation",
  section: "Section",
  detail: "Detail",
  schedule: "Schedule",
  specification: "Specification",
  title_sheet: "Title Sheet",
  site_plan: "Site Plan",
  unknown: "Not classified",
};

const ELIGIBILITY_LABEL: Record<TakeoffEligibilityLevel, string> = {
  fully_eligible: "Takeoff Eligible",
  partial_eligible: "Partially Eligible",
  reference_only: "Reference Sheet",
  not_eligible: "Not Takeoff Eligible",
  unknown: "Needs Review",
};

interface Props {
  filterDiscipline: DrawingDiscipline | "all";
  onFilterDisciplineChange: (v: DrawingDiscipline | "all") => void;
  showOnlyEligible: boolean;
  onShowOnlyEligibleChange: (v: boolean) => void;
}

export default function EngineeringSheetNavigator({
  filterDiscipline,
  onFilterDisciplineChange,
  showOnlyEligible,
  onShowOnlyEligibleChange,
}: Props) {
  const { state, dispatch } = useApp();
  const {
    allSheetContexts,
    projectSummary,
    getNextEligibleSheet,
    getPreviousEligibleSheet,
  } = useSheetContext();

  const activeSheetContext = useActiveSheetContext();

  const filteredContexts = Object.values(allSheetContexts)
    .filter((context) => {
      if (filterDiscipline !== "all" && context.discipline !== filterDiscipline) return false;
      if (showOnlyEligible && context.eligibilityLevel !== "fully_eligible" && context.eligibilityLevel !== "partial_eligible") return false;
      return true;
    })
    .sort((a, b) => a.sheetNumber - b.sheetNumber);

  const handleSheetSelect = (sheetId: string) => dispatch({ type: "SET_ACTIVE_SHEET", sheetId });

  const handleNextEligible = () => {
    if (!activeSheetContext) return;
    const next = getNextEligibleSheet(activeSheetContext.sheetId);
    if (next) handleSheetSelect(next.sheetId);
  };
  const handlePreviousEligible = () => {
    if (!activeSheetContext) return;
    const prev = getPreviousEligibleSheet(activeSheetContext.sheetId);
    if (prev) handleSheetSelect(prev.sheetId);
  };

  const getEligibilityIcon = (level: TakeoffEligibilityLevel) => {
    switch (level) {
      case "fully_eligible": return <CheckCircle size={11} className="text-emerald-400 shrink-0" />;
      case "partial_eligible": return <CheckCircle size={11} className="text-yellow-400 shrink-0" />;
      case "reference_only": return <Info size={11} className="text-blue-400 shrink-0" />;
      case "not_eligible": return <XCircle size={11} className="text-gray-500 shrink-0" />;
      default: return <AlertTriangle size={11} className="text-red-400 shrink-0" />;
    }
  };

  const getDisciplineColor = (discipline: DrawingDiscipline): string => {
    switch (discipline) {
      case "architectural": return "bg-blue-500";
      case "structural": return "bg-purple-500";
      case "mechanical": return "bg-orange-500";
      case "electrical": return "bg-yellow-500";
      case "plumbing": return "bg-cyan-500";
      case "fire_protection": return "bg-red-500";
      default: return "bg-gray-500";
    }
  };

  return (
    <div className="space-y-2">
      {/* Summary + prev/next */}
      <div className="flex items-center justify-between text-[9px] text-gray-400 px-0.5">
        <span>
          {projectSummary.totalSheets} sheets
          {projectSummary.needsReview > 0 && (
            <span className="text-amber-400"> · {projectSummary.needsReview} need review</span>
          )}
        </span>
        <div className="flex items-center gap-0.5">
          <button
            onClick={handlePreviousEligible}
            disabled={!activeSheetContext || !getPreviousEligibleSheet(activeSheetContext.sheetId)}
            className="p-0.5 rounded text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
            title="Previous eligible sheet"
          >
            <ChevronLeft size={13} />
          </button>
          <button
            onClick={handleNextEligible}
            disabled={!activeSheetContext || !getNextEligibleSheet(activeSheetContext.sheetId)}
            className="p-0.5 rounded text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
            title="Next eligible sheet"
          >
            <ChevronRight size={13} />
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-1.5">
        <select
          value={filterDiscipline}
          onChange={(e) => onFilterDisciplineChange(e.target.value as DrawingDiscipline | "all")}
          className="flex-1 min-w-0 bg-[#1A1F2E] border border-white/10 rounded px-1.5 py-1 text-[10px] text-gray-300"
        >
          <option value="all">All Disciplines</option>
          <option value="architectural">Architectural</option>
          <option value="structural">Structural</option>
          <option value="mechanical">Mechanical</option>
          <option value="electrical">Electrical</option>
          <option value="plumbing">Plumbing</option>
        </select>
        <label className="flex items-center gap-1 text-[9px] text-gray-400 shrink-0">
          <input
            type="checkbox"
            checked={showOnlyEligible}
            onChange={(e) => onShowOnlyEligibleChange(e.target.checked)}
            className="w-3 h-3"
          />
          Eligible
        </label>
      </div>

      {/* Sheet list — real per-sheet classification, thumbnail, eligibility */}
      <div className="space-y-1 max-h-72 overflow-y-auto scrollbar-custom pr-0.5">
        {filteredContexts.map((context) => {
          const sheet = state.sheets.find((s) => s.id === context.sheetId);
          const isActive = context.sheetId === state.activeSheetId;
          const needsAttention = context.engineeringStatus === "needs_review" || context.eligibilityLevel === "unknown";

          return (
            <button
              key={context.sheetId}
              onClick={() => handleSheetSelect(context.sheetId)}
              title={`${context.sheetCode} - ${context.sheetTitle}`}
              className={`w-full flex items-center gap-2 p-1.5 rounded-lg border text-left transition-all ${
                isActive
                  ? "bg-blue-600/15 border-blue-500/40"
                  : needsAttention
                  ? "bg-amber-600/5 border-amber-500/20 hover:bg-amber-600/10"
                  : "bg-[#111622] border-white/10 hover:border-white/20"
              }`}
            >
              <div className="w-8 h-8 rounded shrink-0 overflow-hidden bg-black/30 border border-white/10 flex items-center justify-center">
                {sheet?.thumbnailUrl ? (
                  <img src={sheet.thumbnailUrl} alt={context.sheetCode} className="w-full h-full object-cover" />
                ) : sheet?.isTakeoffEligible === false ? (
                  <FileX size={13} className="text-gray-500" />
                ) : (
                  <FileText size={13} className="text-gray-500" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${getDisciplineColor(context.discipline)}`} />
                  <span className={`text-[11px] font-bold font-mono truncate ${isActive ? "text-white" : "text-gray-200"}`}>
                    {context.sheetCode}
                  </span>
                  {state.sheetGeometryState[context.sheetId] === "loading" && (
                    <Loader2 size={10} className="text-blue-400 animate-spin shrink-0" />
                  )}
                </div>
                <div className="text-[9px] text-gray-400 truncate">
                  {DRAWING_TYPE_LABEL[context.drawingType] ?? context.drawingType}
                  {context.discipline !== "unknown" && (
                    <span className="capitalize"> · {context.discipline}</span>
                  )}
                </div>
              </div>
              <div className="flex flex-col items-end gap-0.5 shrink-0">
                {getEligibilityIcon(context.eligibilityLevel)}
                {context.wallCount > 0 && (
                  <span className="text-[8px] text-gray-500 font-mono">{context.wallCount}w</span>
                )}
              </div>
            </button>
          );
        })}
        {filteredContexts.length === 0 && (
          <div className="text-center text-[10px] text-gray-500 py-3">No sheets match the current filters</div>
        )}
      </div>

      {activeSheetContext && (
        <div className="pt-1.5 border-t border-white/5 text-[9px] text-gray-500">
          <span className="text-gray-400 font-semibold">{ELIGIBILITY_LABEL[activeSheetContext.eligibilityLevel]}</span>
          {activeSheetContext.eligibilityReason && <span> — {activeSheetContext.eligibilityReason}</span>}
        </div>
      )}
    </div>
  );
}
