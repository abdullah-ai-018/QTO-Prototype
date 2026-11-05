import { createContext, useContext, useMemo, useReducer, useRef, useCallback, useState, useEffect, type Dispatch, type ReactNode } from "react";
import { appReducer, initialState, type AppAction, type AppState } from "./appState";
import { computeAllTrades, computeCostSummary, type CostSummary, type TradeBreakdown } from "@/lib/estimating";
import { computeSheetTakeoff, buildSheetTakeoffFromBackend, type SheetTakeoffResult } from "@/lib/sheetTakeoff";
import { BackendApiService, type PageTradeTakeoffResponse } from "@/api/backendApi";
import { parseBackendDetectionId } from "@/lib/backendConversion";
import type { TradeId, ScaleWarningItem, RoomReviewWarningItem } from "@/types";

interface AppContextValue {
  state: AppState;
  dispatch: Dispatch<AppAction>;
  breakdowns: Record<TradeId, TradeBreakdown>;
  costSummary: CostSummary;
  // NEW: Sheet-scoped takeoff data for the active sheet only
  sheetTakeoff: SheetTakeoffResult;
  canUndo: boolean;
  canRedo: boolean;
  isBackendSynced: boolean;
  syncError: string | null;
  scaleWarnings: ScaleWarningItem[];
  reviewWarnings: RoomReviewWarningItem[];
  /** Real signed-in user's display name, for attributing audit/history entries. Null until the session resolves. */
  currentUserName: string | null;
  /**
   * Where `sheetTakeoff` actually came from — "backend_validated" means it's
   * the real page-scoped TradeEngine result (same provenance as project
   * totals); "client_estimate" means the backend call was unavailable and
   * this is the local, unaudited computeDrywall() approximation. The UI
   * must visibly label which one is showing (see spec: never present a
   * client estimate as if it carried backend validation).
   */
  sheetTakeoffSource: "backend_validated" | "client_estimate";
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, rawDispatch] = useReducer(appReducer, initialState);
  const [backendBreakdowns, setBackendBreakdowns] = useState<Record<TradeId, TradeBreakdown> | null>(null);
  const [isBackendSynced, setIsBackendSynced] = useState<boolean>(false);
  const [syncError, setSyncError] = useState<string | null>(null);

  const [backendScaleWarnings, setBackendScaleWarnings] = useState<ScaleWarningItem[] | null>(null);
  const [backendReviewWarnings, setBackendReviewWarnings] = useState<RoomReviewWarningItem[] | null>(null);
  const [currentUserName, setCurrentUserName] = useState<string | null>(null);
  const [backendPageTakeoff, setBackendPageTakeoff] = useState<PageTradeTakeoffResponse | null>(null);
  const [backendPageTakeoffKey, setBackendPageTakeoffKey] = useState<string | null>(null);

  // Resolve the real signed-in session's identity once, for audit/history
  // attribution — never a hardcoded name.
  useEffect(() => {
    let isMounted = true;
    BackendApiService.fetchCurrentUser().then((user) => {
      if (isMounted && user) setCurrentUserName(user.full_name || user.email);
    });
    return () => {
      isMounted = false;
    };
  }, []);

  // Keep a stable ref of the state to avoid recreating the dispatch function on every state update
  const stateRef = useRef(state);
  stateRef.current = state;

  // Fetch live trade breakdowns and estimates from backend whenever project/blueprint or detections change
  useEffect(() => {
    if (!state.projectId || !state.blueprintId) {
      setBackendBreakdowns(null);
      setIsBackendSynced(false);
      setSyncError(null);
      setBackendScaleWarnings(null);
      setBackendReviewWarnings(null);
      return;
    }

    let isMounted = true;
    BackendApiService.fetchLiveTradeBreakdown(state.projectId, state.blueprintId)
      .then((items) => {
        if (!isMounted) return;
        const converted: Partial<Record<TradeId, TradeBreakdown>> = {};
        for (const item of items) {
          const tId = item.trade as TradeId;
          converted[tId] = {
            trade: tId,
            metrics: {
              materialQuantity: item.material_quantity,
              materialUnit: item.material_unit,
              laborHours: item.labor_hours,
              directCost: item.direct_cost,
              status: item.status,
              confidence: item.confidence,
              validationReasons: item.validation_reasons,
            },
            lineItems: (item.line_items || []).map((li: any) => ({
              label: li.label,
              qty: li.quantity,
              unit: li.unit,
              unitCost: li.unit_cost,
              totalCost: li.total_cost,
            })),
          };
        }
        setBackendBreakdowns(converted as Record<TradeId, TradeBreakdown>);
        setIsBackendSynced(true);
        setSyncError(null);
      })
      .catch((err) => {
        if (!isMounted) return;
        console.warn("[Protake Live Breakdown Sync] Backend offline or fetch error, falling back to local engine:", err);
        setBackendBreakdowns(null);
        setIsBackendSynced(false);
        setSyncError(err instanceof Error ? err.message : "Backend unreachable");
      });

    // Also fetch estimate warnings from backend
    BackendApiService.fetchLatestEstimate(state.projectId)
      .then((est) => {
        if (!isMounted || !est) return;
        if (est.scale_warnings) setBackendScaleWarnings(est.scale_warnings);
        if (est.review_warnings) setBackendReviewWarnings(est.review_warnings);
      })
      .catch(() => {
        // Fallback to local warnings if endpoint fails
      });

    return () => {
      isMounted = false;
    };
  }, [state.projectId, state.blueprintId, state.detections]);

  // Derived Local Scale Warnings (Fallback & Real-time UI reaction)
  const localScaleWarnings = useMemo<ScaleWarningItem[]>(() => {
    const uncalibratedSheets = state.sheets.filter((s) => {
      const isCalibratedInState = !!state.calibration[s.id];
      const isAssumedInModel = s.scale_source === "assumed_default";
      return isAssumedInModel || !isCalibratedInState;
    });

    if (uncalibratedSheets.length === 0) return [];

    const pageNames = uncalibratedSheets.slice(0, 5).map((s, i) => `page ${i + 1} (${s.name || s.code})`).join(", ");
    const more = uncalibratedSheets.length > 5 ? ` and ${uncalibratedSheets.length - 5} more` : "";

    return [
      {
        page_ids: uncalibratedSheets.map((s) => s.dbPageId || 1),
        reason: `${uncalibratedSheets.length} page(s) rely on assumed default scale: ${pageNames}${more}. Room/wall counts and spatial quantities may be inaccurate until scale is calibrated.`,
        scale_source: "assumed_default",
      },
    ];
  }, [state.sheets, state.calibration]);

  // Derived Local Room Review Warnings (Fallback & Real-time UI reaction)
  const localReviewWarnings = useMemo<RoomReviewWarningItem[]>(() => {
    const needsReviewRooms = state.detections.filter(
      (d) => d.kind === "room" && (d.status === "pending" || (d as any).status === "needs_review")
    );

    if (needsReviewRooms.length === 0) return [];

    const affectedSheetIds = Array.from(new Set(needsReviewRooms.map((r) => r.sheetId)));
    const affectedSheets = state.sheets.filter((s) => affectedSheetIds.includes(s.id));
    const pageNames = affectedSheets.slice(0, 5).map((s, i) => `page ${i + 1} (${s.name || s.code})`).join(", ");
    const more = affectedSheets.length > 5 ? ` and ${affectedSheets.length - 5} more` : "";

    return [
      {
        page_ids: affectedSheets.map((s) => s.dbPageId || 1),
        needs_review_count: needsReviewRooms.length,
        reason: `${affectedSheets.length} page(s) contain ${needsReviewRooms.length} room(s) routed to the Human Review Queue: ${pageNames}${more}. Inspect room polygons in the UI review queue before approving takeoff estimates.`,
        warning_type: "needs_human_review",
      },
    ];
  }, [state.detections, state.sheets]);

  const scaleWarnings = useMemo(() => {
    if (backendScaleWarnings && backendScaleWarnings.length > 0) {
      return backendScaleWarnings;
    }
    return localScaleWarnings;
  }, [backendScaleWarnings, localScaleWarnings]);

  const reviewWarnings = useMemo(() => {
    if (backendReviewWarnings && backendReviewWarnings.length > 0) {
      return backendReviewWarnings;
    }
    return localReviewWarnings;
  }, [backendReviewWarnings, localReviewWarnings]);

  const syncDetectionStatus = useCallback((id: string, actionType: "APPROVE_DETECTION" | "REJECT_DETECTION") => {
    const currentState = stateRef.current;
    const d = currentState.detections.find((x) => x.id === id);
    if (!d) return;

    const status = actionType === "APPROVE_DETECTION" ? "approved" : "rejected";
    const parsed = parseBackendDetectionId(d.id);
    if (!parsed) return;

    if (parsed.source === "room") {
      BackendApiService.updateRoom(parsed.backendId, { status }).catch((err) =>
        console.error("[Protake Sync] Room status update failed:", err)
      );
    } else if (parsed.source === "wall" || parsed.source === "archwall") {
      BackendApiService.updateWall(parsed.backendId, { status }).catch((err) =>
        console.error("[Protake Sync] Wall status update failed:", err)
      );
    } else {
      const apiCall =
        status === "approved"
          ? BackendApiService.approveDetection(Number(parsed.backendId))
          : BackendApiService.rejectDetection(Number(parsed.backendId));
      apiCall.catch((err) =>
        console.error("[Protake Sync] Detection status update failed:", err)
      );
    }
  }, []);

  const dispatch = useCallback((action: AppAction) => {
    // 1. Perform local/UI state update synchronously
    rawDispatch(action);

    // 2. Perform backend API syncing asynchronously
    if (action.type === "APPROVE_DETECTION" || action.type === "REJECT_DETECTION") {
      syncDetectionStatus(action.id, action.type);
    } else if (action.type === "APPROVE_ALL" || action.type === "APPROVE_ALL_OVERRIDE" || action.type === "REJECT_ALL") {
      const currentState = stateRef.current;
      const activeSheetId = currentState.activeSheetId;
      if (!activeSheetId) return;

      const sheet = currentState.sheets.find((s) => s.id === activeSheetId);
      if (!sheet || !sheet.dbPageId) return;

      const status = action.type === "REJECT_ALL" ? "rejected" : "approved";
      BackendApiService.bulkReviewPage(sheet.dbPageId, status).catch((err) =>
        console.error(`[Protake Sync] Bulk ${status} page failed:`, err)
      );
    }
  }, []);

  // Blueprint-wide, not scoped to state.activeSheetId: this is the local
  // (offline/pre-sync) fallback engine that approximates what the backend's
  // /live-breakdown reports, which is itself always blueprint-wide. Scoping
  // it to only the active sheet made summary totals silently shrink or grow
  // whenever a user switched sheets, even though the backend numbers it's
  // meant to approximate never changed with sheet selection.
  const localBreakdowns = useMemo(() => {
    const activeDetections = state.detections.filter((d) => d.status !== "rejected");
    return computeAllTrades(activeDetections, state.drywallSettings, state.focusedTradeId);
  }, [state.detections, state.drywallSettings, state.focusedTradeId]);

  const breakdowns = useMemo(() => {
    if (isBackendSynced && backendBreakdowns && Object.keys(backendBreakdowns).length > 0) {
      return { ...localBreakdowns, ...backendBreakdowns };
    }
    return localBreakdowns;
  }, [isBackendSynced, backendBreakdowns, localBreakdowns]);

  const costSummary = useMemo(() => {
    const activeTradeId = (state.summaryTab === "drywall" || state.summaryTab === "painting" || state.summaryTab === "flooring" || state.summaryTab === "roofing" || state.summaryTab === "furniture" || state.summaryTab === "openings") ? state.summaryTab : null;
    return computeCostSummary(breakdowns, activeTradeId);
  }, [breakdowns, state.summaryTab]);

  const activeSheetForTakeoff = state.sheets.find((s) => s.id === state.activeSheetId);

  // Client-side estimate — always computed as the fallback/eligibility gate.
  const localSheetTakeoff = useMemo(() => {
    return computeSheetTakeoff(activeSheetForTakeoff, state.detections, state.drywallSettings);
  }, [activeSheetForTakeoff, state.detections, state.drywallSettings]);

  // Backend-validated, page-scoped takeoff — same TradeEngine + evidence as
  // the project totals, filtered to the active sheet's page. Refetches
  // whenever the active sheet or the underlying detections change.
  useEffect(() => {
    const dbPageId = activeSheetForTakeoff?.dbPageId;
    if (!state.projectId || !state.blueprintId || !dbPageId) {
      setBackendPageTakeoff(null);
      setBackendPageTakeoffKey(null);
      return;
    }
    const key = `${state.projectId}:${state.blueprintId}:${dbPageId}`;
    let isMounted = true;
    BackendApiService.fetchPageTakeoff(state.projectId, state.blueprintId, dbPageId, "drywall")
      .then((res) => {
        if (!isMounted) return;
        setBackendPageTakeoff(res);
        setBackendPageTakeoffKey(key);
      })
      .catch(() => {
        if (!isMounted) return;
        setBackendPageTakeoff(null);
        setBackendPageTakeoffKey(null);
      });
    return () => {
      isMounted = false;
    };
  }, [state.projectId, state.blueprintId, activeSheetForTakeoff, state.detections]);

  const backendKeyForActiveSheet =
    state.projectId && state.blueprintId && activeSheetForTakeoff?.dbPageId
      ? `${state.projectId}:${state.blueprintId}:${activeSheetForTakeoff.dbPageId}`
      : null;

  // Only trust the backend result when it's for THIS sheet (not a stale fetch
  // from before the user switched) and the sheet is actually takeoff-eligible
  // — an ineligible sheet must show zeros with a reason, never backend numbers.
  const sheetTakeoffSource: "backend_validated" | "client_estimate" =
    backendPageTakeoff && backendPageTakeoffKey === backendKeyForActiveSheet && localSheetTakeoff.eligible
      ? "backend_validated"
      : "client_estimate";

  const sheetTakeoff = useMemo(() => {
    if (sheetTakeoffSource === "backend_validated" && backendPageTakeoff) {
      return buildSheetTakeoffFromBackend(backendPageTakeoff, localSheetTakeoff.wallCount);
    }
    return localSheetTakeoff;
  }, [sheetTakeoffSource, backendPageTakeoff, localSheetTakeoff]);

  const value = useMemo(
    () => ({
      state,
      dispatch,
      breakdowns,
      costSummary,
      sheetTakeoff,
      canUndo: state.past.length > 0,
      canRedo: state.future.length > 0,
      isBackendSynced,
      syncError,
      scaleWarnings,
      reviewWarnings,
      currentUserName,
      sheetTakeoffSource,
    }),
    [state, dispatch, breakdowns, costSummary, sheetTakeoff, isBackendSynced, syncError, scaleWarnings, reviewWarnings, currentUserName, sheetTakeoffSource]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}

export type { AppState, AppAction } from "./appState";


