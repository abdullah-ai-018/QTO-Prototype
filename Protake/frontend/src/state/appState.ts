import type {
  CalloutAnnotation,
  StickyNoteAnnotation,
  CalibrationState,
  ChatMessage,
  Detection,
  HistoryEntry,
  Measurement,
  ProjectFile,
  Sheet,
  Signoff,
  ToolId,
  TradeId,
  UploadStage,
} from "@/types";
import type { UnitSystem } from "@/lib/units";
import { DEFAULT_DRYWALL_SETTINGS, type DrywallSettings } from "@/lib/estimating";
import { getCanonicalWallCategory } from "@/lib/colors";

export type RightTab = "detected" | "assistant" | "history" | "verify" | "schedule";
export type SummaryTab = TradeId | "labor" | "costs" | "grid";

export interface AppState {
  // The backend project ID the currently-open blueprint belongs to. Set
  // from the upload flow's own createProject() response, or from the
  // blueprint's own project_id field when reopening an existing blueprint
  // by URL. Was previously not tracked anywhere in state at all — every
  // caller that needed it (the AI Assistant) hardcoded project_id=1,
  // silently querying the wrong project for any other one.
  projectId: number | null;
  // The backend blueprint ID for the currently-open project — needed to
  // trigger estimate generation (POST /projects/{id}/estimates requires
  // it). Set alongside projectId from the same upload/hydrate flows.
  blueprintId: number | null;
  file: ProjectFile | null;
  uploadStage: UploadStage;
  uploadProgress: number;
  unitSystem: UnitSystem;

  sheets: Sheet[];
  activeSheetId: string | null;
  numPages: number;

  // Per-sheet geometry load status (frontend Sheet.id -> status), so the
  // UI can show "loading" / an honest "Geometry not available from
  // source" for one sheet without blocking the rest of the app on every
  // page in a large real blueprint finishing at once. Absent key = not
  // yet requested.
  sheetGeometryState: Record<string, "loading" | "ready" | "error">;

  activeTool: ToolId;
  zoom: number;
  gridEnabled: boolean;
  snapEnabled: boolean;
  aiScanEnabled: boolean;
  scanning: boolean;
  scanProgress: number;

  detections: Detection[];
  measurements: Measurement[];
  selectedDetectionId: string | null;

  chatMessages: ChatMessage[];
  history: HistoryEntry[];

  rightTab: RightTab;
  summaryTab: SummaryTab;

  reportModalOpen: boolean;
  commandPaletteOpen: boolean;
  settingsModalOpen: boolean;
  eligibilityDashboardOpen: boolean;

  // User-configurable drywall assembly assumptions (wall height, sides per
  // wall type) — see lib/estimating.ts computeDrywall. Not part of the
  // undo/redo takeoff history: a settings change isn't a takeoff edit.
  drywallSettings: DrywallSettings;

  calibration: CalibrationState;

  revision: string;

  callouts: CalloutAnnotation[];
  stickyNotes: StickyNoteAnnotation[];

  signoffs: Partial<Record<TradeId, Signoff>>;
  hiddenTrades: Partial<Record<TradeId, boolean>>;
  hiddenDetections: Record<string, boolean>;
  // Opts back into the full filled/prominent room-polygon view for trades
  // that de-emphasize rooms by default (drywall, painting, roofing — see
  // lib/tradeVisualization.ts). Rooms are never removed from the canvas,
  // only drawn subtly, so this is purely a display preference.
  showRoomGeometry: boolean;

  focusedTradeId: TradeId | null;
  focusedDetectionId: string | null;

  wallCategoryFilter: string | null;
  hiddenWallCategories: Record<string, boolean>;

  // Sidebar "Layers" panel visibility toggles — keyed by layer id
  // (arch_walls | rooms | openings | columns | annotations | dimensions |
  // mep). "grid" is intentionally NOT here: it's the existing
  // gridEnabled/TOGGLE_GRID flag, reused rather than duplicated.
  hiddenLayers: Record<string, boolean>;

  // Summary panel visibility toggle
  summaryPanelVisible: boolean;

  // Focus Mode: collapses Sidebar/AIPanel/SummaryPanel so the canvas takes
  // the full workspace. Distinct from the browser's native Fullscreen API
  // (tracked locally in BlueprintWorkspace.tsx) — this is an in-app layout
  // state, not a browser chrome state; the two can be combined.
  focusMode: boolean;

  past: TakeoffSnapshot[];
  future: TakeoffSnapshot[];
}

export interface TakeoffSnapshot {
  detections: Detection[];
  measurements: Measurement[];
  callouts: CalloutAnnotation[];
  stickyNotes: StickyNoteAnnotation[];
}

export const initialState: AppState = {
  projectId: null,
  blueprintId: null,
  file: null,
  uploadStage: "idle",
  uploadProgress: 0,
  unitSystem: "imperial",

  sheets: [],
  activeSheetId: null,
  numPages: 0,
  sheetGeometryState: {},

  activeTool: "select",
  zoom: 1,
  gridEnabled: true,
  snapEnabled: true,
  aiScanEnabled: true,
  scanning: false,
  scanProgress: 0,

  detections: [],
  measurements: [],
  selectedDetectionId: null,

  chatMessages: [],
  history: [],

  rightTab: "detected",
  summaryTab: "drywall",

  reportModalOpen: false,
  commandPaletteOpen: false,
  settingsModalOpen: false,
  eligibilityDashboardOpen: false,

  drywallSettings: DEFAULT_DRYWALL_SETTINGS,

  calibration: {},

  revision: "v1.00",

  callouts: [],
  stickyNotes: [],

  signoffs: {},
  hiddenTrades: {},
  hiddenDetections: {},
  showRoomGeometry: false,

  focusedTradeId: null,
  focusedDetectionId: null,

  wallCategoryFilter: null,
  hiddenWallCategories: {},
  hiddenLayers: {},

  summaryPanelVisible: true,
  focusMode: false,

  past: [],
  future: [],
};

export type AppAction =
  | { type: "SET_PROJECT_ID"; projectId: number | null }
  | { type: "SET_BLUEPRINT_ID"; blueprintId: number | null }
  | { type: "SET_FILE"; file: ProjectFile }
  | { type: "SET_UNIT_SYSTEM"; unitSystem: UnitSystem }
  | { type: "SET_UPLOAD_STAGE"; stage: UploadStage }
  | { type: "SET_UPLOAD_PROGRESS"; progress: number }
  | { type: "SET_SHEETS"; sheets: Sheet[] }
  | { type: "SET_NUM_PAGES"; numPages: number }
  | { type: "SET_ACTIVE_SHEET"; sheetId: string }
  | { type: "SET_TOOL"; tool: ToolId }
  | { type: "SET_ZOOM"; zoom: number }
  | { type: "TOGGLE_GRID" }
  | { type: "TOGGLE_SNAP" }
  | { type: "TOGGLE_AI_SCAN" }
  | { type: "TOGGLE_ROOM_GEOMETRY" }
  | { type: "START_SCAN" }
  | { type: "SET_SCAN_PROGRESS"; progress: number }
  | { type: "FINISH_SCAN"; detections: Detection[] }
  | { type: "APPROVE_DETECTION"; id: string; actor?: string }
  | { type: "REJECT_DETECTION"; id: string; actor?: string }
  | { type: "APPROVE_ALL" }
  // Explicit override for approving NEEDS_REVIEW/unresolved detections that
  // a plain APPROVE_ALL deliberately skips. `reason` is required so every
  // override carries a real justification, not just a blanket bypass.
  | { type: "APPROVE_ALL_OVERRIDE"; reason: string; actor?: string }
  | { type: "REJECT_ALL" }
  | { type: "SELECT_DETECTION"; id: string | null }
  | { type: "ADD_MEASUREMENT"; measurement: Measurement }
  | { type: "REMOVE_MEASUREMENT"; id: string }
  | { type: "ADD_CALLOUT"; callout: CalloutAnnotation }
  | { type: "ADD_STICKY_NOTE"; note: StickyNoteAnnotation }
  | { type: "ADD_CHAT_MESSAGE"; message: ChatMessage }
  | { type: "APPLY_SUGGESTION"; id: string }
  | { type: "DISMISS_SUGGESTION"; id: string }
  | {
      type: "UPDATE_PROPOSED_ACTION";
      messageId: string;
      actionIndex: number;
      state: "pending" | "confirmed" | "cancelled" | "error";
      errorMessage?: string;
    }
  | { type: "ADD_HISTORY"; entry: HistoryEntry }
  | { type: "SET_RIGHT_TAB"; tab: RightTab }
  | { type: "SET_SUMMARY_TAB"; tab: SummaryTab }
  | { type: "OPEN_REPORT" }
  | { type: "CLOSE_REPORT" }
  | { type: "OPEN_COMMAND_PALETTE" }
  | { type: "CLOSE_COMMAND_PALETTE" }
  | { type: "OPEN_SETTINGS" }
  | { type: "CLOSE_SETTINGS" }
  | { type: "OPEN_ELIGIBILITY_DASHBOARD" }
  | { type: "CLOSE_ELIGIBILITY_DASHBOARD" }
  | { type: "SET_DRYWALL_SETTINGS"; settings: Partial<DrywallSettings> }
  | { type: "SET_CALIBRATION"; sheetId: string; pxPerFt: number }
  | { type: "RENAME_DETECTION"; id: string; name: string }
  | { type: "UPDATE_DETECTION"; id: string; fields: Partial<Detection> }
  | { type: "SIGNOFF_TRADE"; trade: TradeId; reviewer: string; notes: string }
  | { type: "REVOKE_SIGNOFF"; trade: TradeId }
  | { type: "TOGGLE_TRADE_VISIBILITY"; trade: TradeId }
  | { type: "TOGGLE_TRADE_FOCUS"; trade: TradeId }
  | { type: "TOGGLE_DETECTION_FOCUS"; id: string }
  | { type: "TOGGLE_DETECTION_VISIBILITY"; id: string }
  | { type: "SET_DETECTIONS_VISIBILITY"; ids: string[]; visible: boolean }
  | { type: "UNDO" }
  | { type: "REDO" }
  | { type: "RESET_PROJECT" }
  | { type: "CLEAR_DETECTIONS" }
  | { type: "SET_DETECTIONS"; detections: Detection[] }
  | { type: "SET_SINGLE_ACTIVE_TRADE"; trade: TradeId }
  | { type: "SET_WALL_CATEGORY_FILTER"; filter: string | null }

  | { type: "TOGGLE_WALL_CATEGORY_VISIBILITY"; category: string }
  | { type: "TOGGLE_LAYER_VISIBILITY"; layerId: string }
  | { type: "RESET_WALL_CATEGORY_VISIBILITY" }
  | { type: "TOGGLE_SUMMARY_PANEL" }
  | { type: "TOGGLE_FOCUS_MODE" }
  | { type: "SET_FOCUS_MODE"; enabled: boolean }
  | { type: "SET_SHEET_GEOMETRY_STATE"; sheetId: string; state: "loading" | "ready" | "error" }
  | { type: "UPDATE_SHEET_THUMBNAIL"; sheetId: string; thumbnailUrl: string }
  | { type: "RESET_VISIBILITY" }
  | { type: "SET_ACTIVE_TRADE"; trade: TradeId }
  | { type: "RESTORE_PROJECT"; projectState: Partial<AppState> };

const UNDOABLE = new Set<AppAction["type"]>([
  "APPROVE_DETECTION",
  "REJECT_DETECTION",
  "APPROVE_ALL",
  "APPROVE_ALL_OVERRIDE",
  "REJECT_ALL",
  "ADD_MEASUREMENT",
  "REMOVE_MEASUREMENT",
  "RENAME_DETECTION",
  "UPDATE_DETECTION",
  "ADD_CALLOUT",
  "ADD_STICKY_NOTE",
]);

function snapshot(state: AppState): TakeoffSnapshot {
  return {
    detections: state.detections,
    measurements: state.measurements,
    callouts: state.callouts,
    stickyNotes: state.stickyNotes,
  };
}

// A detection is safe for a plain (non-override) bulk approval only when it
// isn't NEEDS_REVIEW/unclassified and doesn't carry an unresolved
// schedule-vs-detail conflict. Walls use the same canonical classification
// logic as the canvas/legend (getCanonicalWallCategory) so "what counts as
// NEEDS_REVIEW" stays consistent across the whole app instead of drifting.
function isEligibleForPlainApproval(d: Detection): boolean {
  if (d.kind === "wall") {
    // Deliberately do NOT pass d.status here. getCanonicalWallCategory
    // forces NEEDS_REVIEW for any "pending" wall regardless of
    // classification (that's the correct display rule: an unreviewed wall
    // shows gray until acted on) — but bulk-approving is exactly the act
    // that resolves "pending", so gating on the wall's current status would
    // make every not-yet-approved wall look unresolved and defeat Auto-
    // Approve entirely. What this gate actually needs is "does the wall's
    // own classification signal resolve to a real category" — confidence
    // still applies below regardless of status.
    const category = getCanonicalWallCategory(
      d.wallTypeCode,
      d.wallType,
      d.wallTag,
      undefined,
      d.confidence,
      d.classification
    );
    if (category === "NEEDS_REVIEW") return false;
  }
  const conflicts = (d.evidence?.conflicts as Array<{ status?: string }> | undefined) ?? [];
  if (conflicts.some((c) => c.status === "CONFLICT")) return false;
  return true;
}

function bumpRevision(rev: string): string {
  const [major, minor] = rev.replace("v", "").split(".").map(Number);
  const next = minor + 1;
  return `v${major}.${next.toString().padStart(2, "0")}`;
}

export function appReducer(state: AppState, action: AppAction): AppState {
  const withHistory = UNDOABLE.has(action.type)
    ? { past: [...state.past, snapshot(state)].slice(-50), future: [] }
    : {};

  switch (action.type) {
    case "SET_PROJECT_ID":
      return { ...state, projectId: action.projectId };
    case "SET_BLUEPRINT_ID":
      return { ...state, blueprintId: action.blueprintId };
    case "SET_FILE":
      return { ...state, file: action.file };
    case "SET_UNIT_SYSTEM":
      return { ...state, unitSystem: action.unitSystem };
    case "SET_UPLOAD_STAGE":
      return { ...state, uploadStage: action.stage };
    case "SET_UPLOAD_PROGRESS":
      return { ...state, uploadProgress: action.progress };
    case "SET_SHEETS": {
      // Jump straight to the first takeoff-eligible (drawing) sheet — skip
      // text/spec/empty pages by default, same as the rest of the pipeline.
      const firstEligible = action.sheets.find((s) => s.isTakeoffEligible !== false);
      return { ...state, sheets: action.sheets, activeSheetId: (firstEligible ?? action.sheets[0])?.id ?? null };
    }
    case "SET_NUM_PAGES":
      return { ...state, numPages: action.numPages };
    case "SET_ACTIVE_SHEET":
      return { ...state, activeSheetId: action.sheetId, selectedDetectionId: null };
    case "SET_TOOL":
      return { ...state, activeTool: action.tool };
    case "SET_ZOOM":
      return { ...state, zoom: Math.min(4, Math.max(0.25, action.zoom)) };
    case "TOGGLE_GRID":
      return { ...state, gridEnabled: !state.gridEnabled };
    case "TOGGLE_SNAP":
      return { ...state, snapEnabled: !state.snapEnabled };
    case "TOGGLE_AI_SCAN":
      return { ...state, aiScanEnabled: !state.aiScanEnabled };
    case "TOGGLE_ROOM_GEOMETRY":
      return { ...state, showRoomGeometry: !state.showRoomGeometry };
    case "START_SCAN":
      return { ...state, scanning: true, scanProgress: 0 };
    case "SET_SCAN_PROGRESS":
      return { ...state, scanProgress: action.progress };
    case "FINISH_SCAN":
      return {
        ...state,
        ...withHistory,
        scanning: false,
        scanProgress: 100,
        detections: [...state.detections, ...action.detections],
        revision: bumpRevision(state.revision),
      };
    case "CLEAR_DETECTIONS":
      return {
        ...state,
        detections: [],
        selectedDetectionId: null,
        focusedDetectionId: null,
        revision: bumpRevision(state.revision),
      };
    case "SET_DETECTIONS":
      return {
        ...state,
        detections: action.detections,
        selectedDetectionId: null,
        focusedDetectionId: null,
        revision: bumpRevision(state.revision),
      };
    case "APPROVE_DETECTION":

      return {
        ...state,
        ...withHistory,
        detections: state.detections.map((d) => (d.id === action.id ? { ...d, status: "approved" } : d)),
        revision: bumpRevision(state.revision),
      };
    case "REJECT_DETECTION":
      return {
        ...state,
        ...withHistory,
        detections: state.detections.map((d) => (d.id === action.id ? { ...d, status: "rejected" } : d)),
        revision: bumpRevision(state.revision),
      };
    case "APPROVE_ALL":
      // Gated: NEEDS_REVIEW/unclassified and unresolved-conflict detections
      // are deliberately skipped here. Use APPROVE_ALL_OVERRIDE to approve
      // those explicitly, with a recorded reason.
      return {
        ...state,
        ...withHistory,
        detections: state.detections.map((d) =>
          d.sheetId === state.activeSheetId && d.status !== "approved" && isEligibleForPlainApproval(d)
            ? { ...d, status: "approved" }
            : d
        ),
        revision: bumpRevision(state.revision),
      };
    case "APPROVE_ALL_OVERRIDE": {
      const timestamp = new Date().toISOString();
      const reviewer = action.actor || "unspecified_reviewer";
      const reason = action.reason;
      return {
        ...state,
        ...withHistory,
        detections: state.detections.map((d) => {
          if (d.sheetId !== state.activeSheetId || d.status === "approved") return d;
          const wasNeedsReview = !isEligibleForPlainApproval(d);
          if (!wasNeedsReview) {
            // Already eligible for a plain approval — approve it normally,
            // no override audit trail needed.
            return { ...d, status: "approved" };
          }
          // This detection was NEEDS_REVIEW/unresolved: the override is
          // actually doing something here, so record who did it, when,
          // what it was before, and why.
          return {
            ...d,
            status: "approved",
            approvalOverride: {
              reviewer,
              timestamp,
              previousStatus: d.status,
              reason,
              override: true,
            },
          };
        }),
        revision: bumpRevision(state.revision),
      };
    }
    case "REJECT_ALL":
      return {
        ...state,
        ...withHistory,
        detections: state.detections.map((d) =>
          d.sheetId === state.activeSheetId && d.status !== "rejected" ? { ...d, status: "rejected" } : d
        ),
        revision: bumpRevision(state.revision),
      };
    case "SELECT_DETECTION":
      return { ...state, selectedDetectionId: action.id };
    case "RENAME_DETECTION":
      return {
        ...state,
        ...withHistory,
        detections: state.detections.map((d) => (d.id === action.id ? { ...d, name: action.name } : d)),
      };
    case "UPDATE_DETECTION":
      return {
        ...state,
        ...withHistory,
        detections: state.detections.map((d) => (d.id === action.id ? { ...d, ...action.fields } : d)),
      };
    case "ADD_MEASUREMENT":
      return { ...state, ...withHistory, measurements: [...state.measurements, action.measurement] };
    case "REMOVE_MEASUREMENT":
      return { ...state, ...withHistory, measurements: state.measurements.filter((m) => m.id !== action.id) };
    case "ADD_CALLOUT":
      return { ...state, ...withHistory, callouts: [...state.callouts, action.callout] };
    case "ADD_STICKY_NOTE":
      return { ...state, ...withHistory, stickyNotes: [...state.stickyNotes, action.note] };
    case "ADD_CHAT_MESSAGE":
      return { ...state, chatMessages: [...state.chatMessages, action.message] };
    case "APPLY_SUGGESTION":
      return {
        ...state,
        chatMessages: state.chatMessages.map((m) =>
          m.id === action.id && m.suggestion ? { ...m, suggestion: { ...m.suggestion, applied: true } } : m
        ),
      };
    case "DISMISS_SUGGESTION":
      return {
        ...state,
        chatMessages: state.chatMessages.map((m) =>
          m.id === action.id && m.suggestion ? { ...m, suggestion: { ...m.suggestion, dismissed: true } } : m
        ),
      };
    case "UPDATE_PROPOSED_ACTION":
      return {
        ...state,
        chatMessages: state.chatMessages.map((m) => {
          if (m.id !== action.messageId || !m.proposedActions) return m;
          return {
            ...m,
            proposedActions: m.proposedActions.map((pa, i) =>
              i === action.actionIndex ? { ...pa, state: action.state, errorMessage: action.errorMessage } : pa
            ),
          };
        }),
      };
    case "ADD_HISTORY":
      return { ...state, history: [action.entry, ...state.history] };
    case "SET_RIGHT_TAB":
      return { ...state, rightTab: action.tab };
    case "SET_SUMMARY_TAB":
      return { ...state, summaryTab: action.tab };
    case "OPEN_REPORT":
      return { ...state, reportModalOpen: true };
    case "CLOSE_REPORT":
      return { ...state, reportModalOpen: false };
    case "OPEN_COMMAND_PALETTE":
      return { ...state, commandPaletteOpen: true };
    case "CLOSE_COMMAND_PALETTE":
      return { ...state, commandPaletteOpen: false };
    case "OPEN_SETTINGS":
      return { ...state, settingsModalOpen: true };
    case "CLOSE_SETTINGS":
      return { ...state, settingsModalOpen: false };
    case "OPEN_ELIGIBILITY_DASHBOARD":
      return { ...state, eligibilityDashboardOpen: true };
    case "CLOSE_ELIGIBILITY_DASHBOARD":
      return { ...state, eligibilityDashboardOpen: false };
    case "SET_DRYWALL_SETTINGS":
      return { ...state, drywallSettings: { ...state.drywallSettings, ...action.settings } };
    case "SET_CALIBRATION":
      return { ...state, calibration: { ...state.calibration, [action.sheetId]: action.pxPerFt } };
    case "SIGNOFF_TRADE":
      return {
        ...state,
        signoffs: {
          ...state.signoffs,
          [action.trade]: {
            trade: action.trade,
            signedOff: true,
            reviewer: action.reviewer,
            notes: action.notes,
            timestamp: Date.now(),
          },
        },
      };
    case "REVOKE_SIGNOFF": {
      const next = { ...state.signoffs };
      delete next[action.trade];
      return { ...state, signoffs: next };
    }
    case "TOGGLE_TRADE_VISIBILITY":
      return {
        ...state,
        hiddenTrades: {
          ...state.hiddenTrades,
          [action.trade]: !state.hiddenTrades[action.trade],
        },
      };
    case "TOGGLE_TRADE_FOCUS":
      return {
        ...state,
        focusedTradeId: state.focusedTradeId === action.trade ? null : action.trade,
        summaryTab: state.focusedTradeId === action.trade ? state.summaryTab : action.trade,
      };
    case "TOGGLE_DETECTION_FOCUS":
      return {
        ...state,
        focusedDetectionId: state.focusedDetectionId === action.id ? null : action.id,
      };
    case "TOGGLE_DETECTION_VISIBILITY":
      return {
        ...state,
        hiddenDetections: {
          ...state.hiddenDetections,
          [action.id]: !state.hiddenDetections[action.id],
        },
      };
    case "SET_DETECTIONS_VISIBILITY": {
      const nextHidden = { ...state.hiddenDetections };
      action.ids.forEach((id) => {
        if (action.visible) {
          delete nextHidden[id];
        } else {
          nextHidden[id] = true;
        }
      });
      return {
        ...state,
        hiddenDetections: nextHidden,
      };
    }
    case "UNDO": {
      if (state.past.length === 0) return state;
      const prev = state.past[state.past.length - 1];
      return {
        ...state,
        detections: prev.detections,
        measurements: prev.measurements,
        callouts: prev.callouts ?? state.callouts,
        stickyNotes: prev.stickyNotes ?? state.stickyNotes,
        past: state.past.slice(0, -1),
        future: [snapshot(state), ...state.future].slice(0, 50),
      };
    }
    case "REDO": {
      if (state.future.length === 0) return state;
      const next = state.future[0];
      return {
        ...state,
        detections: next.detections,
        measurements: next.measurements,
        callouts: next.callouts ?? state.callouts,
        stickyNotes: next.stickyNotes ?? state.stickyNotes,
        past: [...state.past, snapshot(state)].slice(-50),
        future: state.future.slice(1),
      };
    }
    case "RESET_PROJECT":
      return { ...initialState };
    case "RESTORE_PROJECT":
      return {
        ...state,
        ...action.projectState,
        past: [],
        future: [],
      };
    case "SET_ACTIVE_TRADE":
    case "SET_SINGLE_ACTIVE_TRADE": {
      const nextHidden: Partial<Record<TradeId, boolean>> = {};
      const trades: TradeId[] = ["drywall", "painting", "flooring", "roofing", "furniture", "openings"];
      trades.forEach((t) => {
        if (t !== action.trade) {
          nextHidden[t] = true;
        }
      });
      return {
        ...state,
        summaryTab: action.trade,
        hiddenTrades: nextHidden,
        focusedTradeId: action.trade,
      };
    }
    case "RESET_VISIBILITY":
      return {
        ...state,
        hiddenTrades: {},
        hiddenDetections: {},
        focusedTradeId: null,
        focusedDetectionId: null,
        selectedDetectionId: null,
      };
    case "SET_WALL_CATEGORY_FILTER":
      return {
        ...state,
        wallCategoryFilter: action.filter,
      };
    case "TOGGLE_WALL_CATEGORY_VISIBILITY": {
      return {
        ...state,
        hiddenWallCategories: {
          ...state.hiddenWallCategories,
          [action.category]: !state.hiddenWallCategories[action.category],
        },
      };
    }
    case "TOGGLE_LAYER_VISIBILITY": {
      return {
        ...state,
        hiddenLayers: {
          ...state.hiddenLayers,
          [action.layerId]: !state.hiddenLayers[action.layerId],
        },
      };
    }
    case "RESET_WALL_CATEGORY_VISIBILITY":
      return {
        ...state,
        wallCategoryFilter: null,
        hiddenWallCategories: {},
      };
    case "TOGGLE_SUMMARY_PANEL":
      return {
        ...state,
        summaryPanelVisible: !state.summaryPanelVisible,
      };
    case "TOGGLE_FOCUS_MODE":
      return {
        ...state,
        focusMode: !state.focusMode,
      };
    case "SET_FOCUS_MODE":
      return {
        ...state,
        focusMode: action.enabled,
      };
    case "SET_SHEET_GEOMETRY_STATE":
      return {
        ...state,
        sheetGeometryState: { ...state.sheetGeometryState, [action.sheetId]: action.state },
      };
    case "UPDATE_SHEET_THUMBNAIL":
      return {
        ...state,
        sheets: state.sheets.map((s) => (s.id === action.sheetId ? { ...s, thumbnailUrl: action.thumbnailUrl } : s)),
      };
    default:
      return state;
  }
}
