export type TradeId = "drywall" | "painting" | "flooring" | "roofing" | "furniture" | "openings";

export type ToolId =
  | "select"
  | "pan"
  | "area"
  | "magic-fill"
  | "callout"
  | "sticky-note"
  | "linear"
  | "polygon"
  | "count"
  | "calibrate"
  | "ask-ai";

export interface CalloutAnnotation {
  id: string;
  sheetId: string;
  startX: number; // target point (arrow head)
  startY: number;
  endX: number; // text box position
  endY: number;
  text: string;
}

export interface StickyNoteAnnotation {
  id: string;
  sheetId: string;
  x: number;
  y: number;
  text: string;
  color: string;
}

export type DetectionStatus = "pending" | "approved" | "rejected";

/**
 * Audit trail written when a detection is approved through the
 * APPROVE_ALL_OVERRIDE path (Auto-Approve's "Including Review" escape
 * hatch) rather than the normal gated APPROVE_ALL. Present only on
 * detections that were NEEDS_REVIEW/unresolved/conflicting at the moment
 * of the override — a plain approval (individual or gated bulk) never
 * sets this. `reviewer` falls back to "unspecified_reviewer" when no real
 * signed-in user identity is available in app state (see
 * AppContext.currentUserName) rather than fabricating a name.
 */
export interface ApprovalOverrideRecord {
  reviewer: string;
  timestamp: string; // ISO 8601, from new Date().toISOString()
  previousStatus: DetectionStatus;
  reason: string;
  override: true;
}

export type DetectionKind =
  | "room"
  | "wall"
  | "door"
  | "window"
  | "column"
  | "symbol"
  | "object"
  // Plumbing/wardrobe fixtures (bathtub, shower, sinks, vanity, toilet, robes).
  | "fixture"
  | "stairs"
  // Sheet metadata (scale callout, title block, dimension string) — not a
  // takeoff item, kept visible rather than discarded.
  | "annotation";

export interface Point {
  x: number;
  y: number;
}

export interface Detection {
  id: string;
  sheetId: string;
  kind: DetectionKind;
  name: string;
  /**
   * The single trade this detection is attributable to, or null when it
   * isn't attributable to one. A room polygon is normally null: its floor
   * feeds flooring, its walls feed drywall and painting, and its ceiling
   * feeds roofing — all at once. Only detections that genuinely belong to
   * one trade (an OCR'd finish callout, a user-drawn takeoff) carry a value.
   *
   * This is a display/grouping label only. Quantities are never filtered by
   * it — see lib/estimating.ts.
   */
  trade: TradeId | null;
  /**
   * Backend room classification. "exterior_covered" marks a covered
   * exterior area (porch, deck) — it has real floor and roof area but no
   * enclosing walls, so it must be excluded from drywall and painting
   * quantities. Null/undefined for an ordinary enclosed room.
   */
  roomType?: string | null;
  points: Point[]; // polygon in normalized [0,1] sheet space
  areaSqFt: number;
  perimeterFt: number;
  /**
   * Wall thickness in feet, for `kind === "wall"` only. Measured from the
   * drawing when `thicknessMeasured` is true, otherwise the backend's
   * assumed stud-wall default — the UI must keep the two distinguishable,
   * since an estimator pricing off a wall width needs to know which it is.
   */
  thicknessFt?: number;
  thicknessMeasured?: boolean;
  /**
   * For `kind === "wall"` only: which side of the building envelope this
   * wall sits on. Drives both its canvas color (see lib/colors.ts) and the
   * drywall takeoff's linear-feet-per-type split (see
   * lib/estimating.ts computeDrywall) — an internal wall is drywalled on
   * both faces, an external wall only on the interior face. Undefined for
   * non-wall detections, and treated as "exterior" by default for legacy
   * wall detections that predate this field.
   */
  wallType?: "interior" | "exterior";
  wallTypeCode?: string | null;
  segmentsCount?: number;
  openingsCount?: number;
  confidence: number; // 0-1
  status: DetectionStatus;
  clippedSegments?: Point[][];
  wallPolygon?: Point[];
  assemblyTag?: string | null;
  assemblyDescription?: string | null;
  sidesToHang?: number;
  heightFt?: number;
  heightProvenance?: string;
  grossSf?: number;
  openingDeductionSf?: number;
  netSf?: number;
  qtoEligible?: boolean;
  qtoBlockReason?: string | null;
  decisionState?: string;
  wallTag?: string | null;
  classification?: string | null;
  thicknessIn?: number;
  thicknessSource?: string;
  layersSideA?: number;
  layersSideB?: number;
  assemblyVerified?: boolean;
  rejectionReason?: string | null;
  evidence?: Record<string, any>;
  /** Set only when this detection was approved via APPROVE_ALL_OVERRIDE
   *  while it was NEEDS_REVIEW/unresolved. See ApprovalOverrideRecord. */
  approvalOverride?: ApprovalOverrideRecord | null;
}

export interface BackendArchitecturalWall {
  id: string;
  page_id: number;
  start_norm: { x: number; y: number };
  end_norm: { x: number; y: number };
  clipped_segments_norm: Array<[{ x: number; y: number }, { x: number; y: number }]>;
  wall_polygon_norm?: Array<[number, number]>;
  length_ft: number;
  height_ft: number;
  height_provenance: string;
  thickness_in: number;
  thickness_source: string;
  classification: string;
  wall_tag?: string | null;
  assembly_tag?: string | null;
  assembly_description?: string | null;
  sides_to_hang: number;
  layers_side_a: number;
  layers_side_b: number;
  schedule_sheet?: string | null;
  assembly_verified: boolean;
  gross_sf: number;
  openings_count: number;
  opening_deduction_sf: number;
  net_sf: number;
  decision_state: string;
  qto_eligible: boolean;
  qto_block_reason?: string | null;
  confidence: number;
  status: string;
  rejection_reason?: string | null;
  evidence?: Record<string, any>;
  openings?: Array<{
    id: string;
    opening_type: string;
    width_ft: number;
    height_ft: number;
    area_sqft: number;
  }>;
}


export interface Measurement {
  id: string;
  sheetId: string;
  tool: Extract<ToolId, "area" | "linear" | "polygon" | "count">;
  points: Point[];
  label: string;
  valueLabel: string;
  createdAt: number;
}

export interface Sheet {
  id: string;
  name: string;
  code: string; // e.g. A101
  pageIndex: number; // page in the loaded pdf
  pageNumber?: number;
  thumbnailUrl?: string;
  // Rasterized page pixel size. Detection polygons are normalized against
  // these, so the canvas must adopt this aspect ratio or shapes come out
  // stretched — see components/blueprint/stageSize.ts.
  widthPx?: number;
  heightPx?: number;
  // Backend page-classifier fields (undefined = unknown, treat as eligible)
  pageType?: string | null; // floor_plan | roof_plan | elevation | section | rcp | text_specification | empty_blank | non_architectural
  isTakeoffEligible?: boolean; // false = text/empty/non-architectural — skip in default navigation
  skipReason?: string | null;
  dbPageId?: number;
  scale_source?: string | null;
  // Richer backend classifier fields (app/models/page.py) — undefined when
  // the page never made it through classification. When present, these are
  // authoritative and should be preferred over any local heuristic guess.
  discipline?: string | null; // Architectural | Structural | Mechanical | Electrical | Plumbing | Civil | General
  primaryTitle?: string | null;
  classificationConfidence?: number | null;
  geometryAuthority?: string | null; // PARTITION_WALLS | CEILING_GWB | ROOF_SURFACES | DEMOLITION | CONTEXT_ONLY | NONE
}

export interface RoomNode {
  id: string;
  name: string;
}

export interface HistoryEntry {
  id: string;
  version: string;
  actor: string;
  action: string;
  timestamp: number;
}

export interface AssistantProposedAction {
  action: "approve_detection" | "reject_detection" | "rename_room" | "set_room_status" | "generate_estimate";
  detection_id?: number | null;
  room_id?: number | null;
  label?: string | null;
  kind?: string | null;
  current_status?: string | null;
  new_status?: string | null;
  current_name?: string | null;
  new_name?: string | null;
  page_number?: number | null;
  reason?: string | null;
  blueprint_id?: number | null;
  approved_room_count?: number | null;
  approved_room_area_sqft?: number | null;
  approved_wall_count?: number | null;
  approved_wall_area_sqft?: number | null;
  overhead_pct?: number | null;
  profit_pct?: number | null;
  contingency_pct?: number | null;
  state?: "pending" | "confirmed" | "cancelled" | "error";
  errorMessage?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  suggestion?: {
    title: string;
    applied?: boolean;
    dismissed?: boolean;
  };
  proposedActions?: AssistantProposedAction[];
  timestamp: number;
}

export interface TradeMetrics {
  materialQuantity: number;
  materialUnit: string;
  laborHours: number;
  directCost: number;
  // From the backend's per-trade validator (app/trades/validation.py) —
  // absent when computed by the local client-side fallback engine
  // (lib/estimating.ts), which has no equivalent validation pass.
  status?: "validated" | "needs_review" | "error";
  confidence?: number;
  validationReasons?: string[];
}

export type UploadStage =
  | "idle"
  | "uploading"
  | "processing"
  | "detecting"
  | "complete";

export interface ProjectFile {
  name: string;
  sizeBytes: number;
  numPages: number;
  objectUrl?: string;
  isSample?: boolean;
  base64?: string;
}

export type CalibrationUnit = "ft";

export interface CalibrationState {
  // pixels-per-foot at 100% zoom, per sheet
  [sheetId: string]: number;
}

export interface ScaleWarningItem {
  page_ids: number[];
  reason: string;
  scale_source: string;
}

export interface RoomReviewWarningItem {
  page_ids: number[];
  needs_review_count: number;
  reason: string;
  warning_type: string;
}

export interface Signoff {
  trade: TradeId;
  signedOff: boolean;
  reviewer: string;
  notes: string;
  timestamp: number;
}

