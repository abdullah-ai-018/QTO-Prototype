import { apiRequest, apiRequestObjectUrl, getAuthToken, setAuthToken } from "./apiClient";
import type { AssistantProposedAction, BackendArchitecturalWall, TradeId } from "@/types";
import { runWithConcurrency } from "@/lib/concurrency";

// A real multi-page blueprint firing one request per page with no limit
// (4 endpoints x 18 pages = 72 at once) can push a dev-grade backend's
// per-request latency from milliseconds into the 8-14+ second range under
// the resulting queueing, which was the confirmed root cause of "real
// blueprint geometry never finishes loading." All per-blueprint fan-outs
// below share this cap.
const PAGE_FETCH_CONCURRENCY = 4;

// Generic pagination envelope — matches app/utils/pagination.py's Page[T].
export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// Matches app/schemas/audit.py's AuditLogRead — one row per tracked field
// change on any entity (wall, room, detection, estimate), with real
// before/after values, not a summarized/fabricated description.
export interface AuditLogEntry {
  id: number;
  project_id: number;
  user_id: number;
  entity_type: string;
  entity_id: number;
  action: string;
  field_name: string | null;
  previous_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  reason: string | null;
  version: string;
  is_undone: boolean;
  created_at: string;
}

// Matches app/schemas/takeoff.py's TradeTakeoffRead — the persisted,
// per-trade counterpart to the live (non-persisted) breakdown above.
export interface TradeTakeoffResponse {
  id: number;
  project_id: number;
  blueprint_id: number;
  trade: TradeId;
  material_quantity: number;
  material_unit: string;
  labor_hours: number;
  material_cost: number;
  labor_cost: number;
  direct_cost: number;
  status: "validated" | "needs_review" | "error";
  confidence: number;
  evidence: Record<string, unknown> | null;
  validation_reasons: string[] | null;
  geometry_version: string | null;
  scale_version: string | null;
  engine_version: string | null;
  items: Array<{
    id: number;
    label: string;
    quantity: number;
    unit: string;
    unit_cost: number;
    total_cost: number;
    source_proof: Record<string, unknown> | null;
    formula_breakdown: string | null;
  }>;
}

// Matches app/schemas/takeoff.py's PageTradeTakeoffRead — the non-persisted,
// sheet-scoped counterpart to TradeTakeoffResponse above. Runs through the
// same engine and carries the same evidence/formula_breakdown provenance,
// just filtered to one page's approved geometry.
export interface PageTradeTakeoffResponse {
  page_id: number;
  blueprint_id: number;
  trade: TradeId;
  material_quantity: number;
  material_unit: string;
  labor_hours: number;
  material_cost: number;
  labor_cost: number;
  direct_cost: number;
  status: "validated" | "needs_review" | "error";
  confidence: number;
  evidence: Record<string, unknown> | null;
  validation_reasons: string[] | null;
  items: Array<{
    label: string;
    quantity: number;
    unit: string;
    unit_cost: number;
    total_cost: number;
    source_proof: Record<string, unknown> | null;
    formula_breakdown: string | null;
  }>;
}

// Matches the dict returned by GET .../takeoffs/drywall/wall-ledger.
// One entry per ArchitecturalWall, built server-side in DrywallEngine —
// this is the real provenance source for the wall-by-wall breakdown, not
// a client-side recomputation from raw detections.
export interface WallLedgerEntry {
  wall_id: string;
  page_id: number;
  status: string;
  qto_eligible: boolean;
  qto_block_reason: string | null;
  start_norm: Record<string, number>;
  end_norm: Record<string, number>;
  length_ft: number;
  height_ft: number;
  height_provenance: "VERIFIED" | "ASSUMED";
  thickness_in: number;
  thickness_source: string;
  wall_tag: string | null;
  assembly_tag: string | null;
  assembly_description: string | null;
  sides_to_hang: number;
  layers_side_a: number | null;
  layers_side_b: number | null;
  schedule_sheet: string | null;
  assembly_verified: boolean;
  gross_sf: number;
  openings_count: number;
  opening_deduction_sf: number;
  net_sf: number;
  classification: string;
  decision_state: string;
  confidence?: number;
}

export interface WallLedgerResponse {
  takeoff_id: number;
  blueprint_id: number;
  total_walls_analyzed: number;
  walls_included_in_qto: number;
  walls_excluded_from_qto: number;
  independent_qto_recomputation: Record<string, unknown>;
  framing_qto: Record<string, unknown>;
  wall_ledger: WallLedgerEntry[];
  exclusion_summary: Record<string, number>;
}

export interface Project {
  id: number;
  name: string;
  code: string | null;
  client_name: string | null;
  address: string | null;
  created_at: string;
  unit_system?: "imperial" | "metric";
}

export interface BlueprintUploadResponse {
  blueprint: {
    id: number;
    project_id: number;
    filename: string;
    page_count: number;
    created_at: string;
  };
  message: string;
}

// Matches app/schemas/page.py's PageRead exactly. This previously carried
// several fields the backend has never sent (scale_factor, scale_unit,
// thumbnail_url, image_url) alongside `width`/`height` typos — every
// consumer reading those got `undefined` silently. The image itself isn't
// a field at all: GET /pages/{id}/image and /pages/{id}/thumbnail return
// the binary file directly (see fetchPageImageObjectUrl below).
export interface BackendPage {
  id: number;
  blueprint_id: number;
  page_number: number;
  sheet_code: string | null;
  sheet_name: string | null;
  width_px: number;
  height_px: number;
  dpi: number;
  scale_ft_per_px: number | null;
  geometry_processed: boolean;
  ocr_processed: boolean;
  ai_validated: boolean;
  // Page classifier fields (from geometry engine analysis)
  page_type?: string | null;           // floor_plan | roof_plan | elevation | section | rcp | text_specification | empty_blank | non_architectural
  is_takeoff_eligible?: boolean;       // false = skip this page (empty/text/electrical)
  skip_reason?: string | null;         // human-readable skip reason
  // Richer classifier fields (app/models/page.py) — null when the page
  // never made it through classification.
  discipline?: string | null;
  primary_title?: string | null;
  classification_confidence?: number | null;
  geometry_authority?: string | null;
}

export type BlueprintProcessingStatus = "uploaded" | "processing" | "processed" | "failed";

export interface BlueprintStatus {
  id: number;
  project_id: number;
  num_pages: number;
  pages_processed: number;
  status: BlueprintProcessingStatus;
  processing_error: string | null;
  // What the background worker is doing right now (e.g. "Detecting rooms
  // & walls (page 2 of 5)…"). `pages_processed` alone only moves once a
  // whole page finishes, which can take 1-3 minutes — this is what lets
  // the UI show real, live progress instead of sitting frozen that whole
  // time and then jumping.
  current_stage: string | null;
}

export interface BackendRoom {
  id: number;
  page_id: number;
  name: string;
  room_type: string | null;
  polygon_norm: number[][];
  bbox_norm: { x: number; y: number; width: number; height: number };
  centroid_norm: { x: number; y: number };
  area_sqft: number;
  perimeter_ft: number;
  confidence: number;
  source: string;
  status: string;
}

export interface BackendWall {
  id: number;
  page_id: number;
  room_id: number | null;
  start_norm: { x: number; y: number };
  end_norm: { x: number; y: number };
  length_ft: number;
  height_ft: number;
  thickness_ft: number;
  // True when thickness_ft was measured off the drawing's own wall stroke,
  // false when it is the backend's assumed stud-wall default. Surfaced in
  // the UI so an estimator never mistakes an assumption for a measurement.
  thickness_measured: boolean;
  wall_type: string; // "interior" | "exterior"
  wall_type_code: string | null;
  confidence: number;
  source: string;
  status: string;
  area_sqft: number;
}

// Mirrors app/schemas/detection.py::DetectionRead. These come from the AI
// validation pass, which emits room/wall findings too — those duplicate the
// geometry engine's own rooms/walls tables, so only symbol kinds get
// rendered (see backendConversion.SYMBOL_DETECTION_KINDS).
export interface BackendDetection {
  id: number;
  page_id: number;
  kind: string; // room | wall | door | window | column | symbol | object
  label: string;
  trade: string | null;
  polygon_norm: number[][];
  bbox_norm: { minX: number; minY: number; maxX: number; maxY: number };
  confidence: number;
  source: string;
  status: string;
  linked_room_id: number | null;
  linked_wall_id: number | null;
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

export interface EstimateSummary {
  id: number;
  project_id: number;
  blueprint_id?: number | null;
  version: string;
  status: string;
  material_cost: number;
  labor_cost: number;
  direct_cost: number;
  overhead_amount: number;
  profit_amount: number;
  contingency_amount: number;
  final_bid_price: number;
  scale_warnings?: ScaleWarningItem[] | null;
  review_warnings?: RoomReviewWarningItem[] | null;
}

// Matches app/schemas/user.py's UserRead — the authenticated session's real
// identity, used to attribute audit-log/history entries instead of a
// hardcoded name.
export interface CurrentUser {
  id: number;
  email: string;
  full_name: string;
}

// Concurrent callers (e.g. a multi-page blueprint hydrating 18 pages'
// worth of thumbnails/geometry in parallel) must share ONE in-flight
// auth resolution rather than each independently racing through their own
// /auth/me -> /auth/login -> /auth/register sequence. Without this, a
// Session caching: Once a valid token exists, avoid redundant /auth/me roundtrips
let inFlightAuth: Promise<void> | null = null;
let isAuthVerified = false;

export class BackendApiService {
  /** The signed-in user's identity, or null if no session is active. */
  static async fetchCurrentUser(): Promise<CurrentUser | null> {
    try {
      await this.ensureAuth();
      return await apiRequest<CurrentUser>("/auth/me");
    } catch {
      return null;
    }
  }

  // Ensure active session with backend (Register/Login Guest User automatically if needed)
  static async ensureAuth(force = false): Promise<void> {
    const token = getAuthToken();
    if (token && isAuthVerified && !force) {
      return;
    }
    if (inFlightAuth) return inFlightAuth;
    inFlightAuth = BackendApiService.resolveAuth().finally(() => {
      inFlightAuth = null;
    });
    return inFlightAuth;
  }

  private static async resolveAuth(): Promise<void> {
    const existingToken = getAuthToken();
    if (existingToken) {
      try {
        await apiRequest("/auth/me");
        isAuthVerified = true;
        return;
      } catch {
        // Token invalid, clear and refresh
        setAuthToken(null);
        isAuthVerified = false;
      }
    }
    try {
      const authData = await apiRequest<{ access_token: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: "guest@protake.app", password: "GuestPassword123!" }),
      });
      setAuthToken(authData.access_token);
      isAuthVerified = true;
    } catch {
      // Create user if login fails
      const regData = await apiRequest<{ access_token: string }>("/auth/register", {
        method: "POST",
        body: JSON.stringify({
          email: "guest@protake.app",
          password: "GuestPassword123!",
          full_name: "Guest Estimator",
        }),
      });
      setAuthToken(regData.access_token);
      isAuthVerified = true;
    }
  }

  // Create active Takeoff Project with explicit selected trade
  static async createProject(name: string, selectedTrade?: string): Promise<Project> {
    await this.ensureAuth();
    const payload: { name: string; selected_trade?: string } = { name };
    if (selectedTrade && selectedTrade !== "all") {
      payload.selected_trade = selectedTrade;
    }
    const project = await apiRequest<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (selectedTrade && selectedTrade !== "all") {
      try {
        await apiRequest(`/projects/${project.id}/trade-configs`, {
          method: "PUT",
          body: JSON.stringify({ trade: selectedTrade }),
        });
      } catch {
        // Best effort
      }
    }
    return project;
  }

  // Upload PDF Blueprint to FastAPI backend
  static async uploadBlueprint(projectId: number, file: File): Promise<BlueprintUploadResponse> {
    await this.ensureAuth();
    const formData = new FormData();
    formData.append("file", file);

    return apiRequest<BlueprintUploadResponse>(`/projects/${projectId}/blueprints`, {
      method: "POST",
      body: formData,
    });
  }

  // Kick off rasterization + geometry analysis in the background with explicit trade context
  static async processBlueprint(blueprintId: number, selectedTrade?: string): Promise<BlueprintStatus> {
    await this.ensureAuth();
    const query = selectedTrade && selectedTrade !== "all" ? `?selected_trade=${encodeURIComponent(selectedTrade)}` : "";
    return apiRequest<BlueprintStatus>(`/blueprints/${blueprintId}/process${query}`, {
      method: "POST",
    });
  }

  // Lightweight status check — cheap enough to poll every second or two.
  static async getBlueprintStatus(blueprintId: number): Promise<BlueprintStatus> {
    await this.ensureAuth();
    return apiRequest<BlueprintStatus>(`/blueprints/${blueprintId}`);
  }

  // Fetch the page list once processing has finished.
  static async fetchBlueprintPages(blueprintId: number): Promise<BackendPage[]> {
    await this.ensureAuth();
    const res = await apiRequest<{ items: BackendPage[]; total: number }>(
      `/blueprints/${blueprintId}/pages?page_size=200`
    );
    return res.items ?? [];
  }

  // The rasterized page image is served as a binary file, not a JSON field
  // (there is no `image_path`/`image_url` on BackendPage) — this fetches it
  // with the same auth as every other call and returns a blob: URL that
  // <img>/Konva can load directly.
  static async fetchPageImageObjectUrl(pageId: number): Promise<string> {
    await this.ensureAuth();
    return apiRequestObjectUrl(`/pages/${pageId}/image`);
  }

  static async fetchPageThumbnailObjectUrl(pageId: number): Promise<string> {
    await this.ensureAuth();
    return apiRequestObjectUrl(`/pages/${pageId}/thumbnail`);
  }

  // Polls blueprint status until the background job finishes (processed or
  // failed), reporting progress as it goes, then returns the final page
  // list. Large sheet sets can legitimately take minutes — there is no
  // client-side timeout here, only a page-by-page progress signal.
  //
  // A single Python process is doing this CPU-heavy work (Hough transform,
  // OCR) on a background thread, which can starve the event loop for
  // 10-30s+ at a time on a big sheet — long enough for an individual poll
  // to time out even though the job itself is healthy. A transient poll
  // failure is therefore not treated as job failure; only MAX_CONSECUTIVE_
  // POLL_FAILURES in a row gives up, so a real dead backend still surfaces
  // an error instead of polling forever.
  static async waitForBlueprintProcessing(
    blueprintId: number,
    onProgress?: (pagesProcessed: number, numPages: number, currentStage: string | null) => void,
    pollIntervalMs = 800
  ): Promise<BackendPage[]> {
    const MAX_CONSECUTIVE_POLL_FAILURES = 8;
    let consecutiveFailures = 0;

    while (true) {
      let status: BlueprintStatus;
      try {
        status = await this.getBlueprintStatus(blueprintId);
        consecutiveFailures = 0;
      } catch (err) {
        consecutiveFailures += 1;
        if (consecutiveFailures >= MAX_CONSECUTIVE_POLL_FAILURES) {
          throw err instanceof Error ? err : new Error("Lost contact with the backend while processing");
        }
        await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
        continue;
      }

      onProgress?.(status.pages_processed, status.num_pages, status.current_stage);

      if (status.status === "processed") {
        return this.fetchBlueprintPages(blueprintId);
      }
      if (status.status === "failed") {
        throw new Error(status.processing_error || "Blueprint processing failed");
      }
      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
    }
  }

  // Fetch detected rooms for a single page (geometry engine results)
  static async fetchPageRooms(pageId: number): Promise<BackendRoom[]> {
    await this.ensureAuth();
    // A single page_size=200 request silently truncates a page with 200+
    // rooms (200 is the server's max, not a guarantee it's everything) — the
    // exact class of bug that made the walls fetch fail outright at 1000.
    // Paging until a short page confirms there's nothing left avoids both
    // failure modes.
    const PAGE_SIZE = 200;
    const all: BackendRoom[] = [];
    for (let page = 1; ; page++) {
      const res = await apiRequest<{ items: BackendRoom[]; total: number }>(
        `/pages/${pageId}/rooms?page_size=${PAGE_SIZE}&page=${page}`
      );
      const items = res.items ?? [];
      all.push(...items);
      if (items.length < PAGE_SIZE) break;
    }
    return all;
  }

  // Fetch all rooms across all pages of a blueprint
  // Automatically skips non-eligible pages (empty, text-only, electrical)
  static async fetchAllBlueprintRooms(
    blueprintId: number,
    pages: BackendPage[]
  ): Promise<{ pageId: number; rooms: BackendRoom[]; pageIndex: number }[]> {
    // Filter to only architectural / takeoff-eligible pages
    const eligiblePages = pages.filter(
      (p) => p.is_takeoff_eligible !== false  // undefined = assume eligible (old pages without classifier)
    );

    if (eligiblePages.length === 0) {
      console.info("[Protake] No takeoff-eligible pages found — all pages are text/empty/non-architectural");
      return [];
    }

    console.info(
      `[Protake] Processing ${eligiblePages.length}/${pages.length} eligible pages ` +
      `(${pages.length - eligiblePages.length} skipped: empty/text/electrical)`
    );

    const out: { pageId: number; rooms: BackendRoom[]; pageIndex: number }[] = [];
    await runWithConcurrency(eligiblePages, PAGE_FETCH_CONCURRENCY, async (page, i) => {
      out.push({ pageId: page.id, pageIndex: i, rooms: await this.fetchPageRooms(page.id) });
    });
    return out;
  }

  // Fetch every detected wall for a single page (geometry engine results).
  //
  // The server caps page_size at 200 (app/utils/pagination.py's
  // `le=200`) — requesting 1000 doesn't get clamped, it gets rejected
  // outright with a 422. A detailed plan can easily have more than 200
  // walls (a real one hit 231), so this pages through with the server's
  // max page size until a short page signals there's nothing left, rather
  // than assuming one request covers everything.
  static async fetchPageWalls(pageId: number): Promise<BackendWall[]> {
    await this.ensureAuth();
    const PAGE_SIZE = 200;
    const all: BackendWall[] = [];
    for (let page = 1; ; page++) {
      const res = await apiRequest<{ items: BackendWall[]; total: number }>(
        `/pages/${pageId}/walls?page_size=${PAGE_SIZE}&page=${page}`
      );
      const items = res.items ?? [];
      all.push(...items);
      if (items.length < PAGE_SIZE) break;
    }
    return all;
  }

  // Fetch canonical ArchitecturalWalls for a single page
  static async fetchPageArchitecturalWalls(pageId: number): Promise<BackendArchitecturalWall[]> {
    await this.ensureAuth();
    const PAGE_SIZE = 200;
    const all: BackendArchitecturalWall[] = [];
    for (let page = 1; ; page++) {
      const res = await apiRequest<{ items: BackendArchitecturalWall[]; total: number }>(
        `/pages/${pageId}/architectural-walls?page_size=${PAGE_SIZE}&page=${page}`
      );
      const items = res.items ?? [];
      all.push(...items);
      if (items.length < PAGE_SIZE) break;
    }
    return all;
  }

  // Fetch all canonical architectural walls across every takeoff-eligible page of a blueprint.
  static async fetchAllBlueprintArchitecturalWalls(
    pages: BackendPage[]
  ): Promise<{ pageId: number; archWalls: BackendArchitecturalWall[] }[]> {
    const eligiblePages = pages.filter((p) => p.is_takeoff_eligible !== false);
    if (eligiblePages.length === 0) return [];

    const out: { pageId: number; archWalls: BackendArchitecturalWall[] }[] = [];
    await runWithConcurrency(eligiblePages, PAGE_FETCH_CONCURRENCY, async (page) => {
      out.push({ pageId: page.id, archWalls: await this.fetchPageArchitecturalWalls(page.id) });
    });
    return out;
  }

  // Fetch all walls across every takeoff-eligible page of a blueprint.
  static async fetchAllBlueprintWalls(
    pages: BackendPage[]
  ): Promise<{ pageId: number; walls: BackendWall[] }[]> {
    const eligiblePages = pages.filter((p) => p.is_takeoff_eligible !== false);
    if (eligiblePages.length === 0) return [];

    const out: { pageId: number; walls: BackendWall[] }[] = [];
    await runWithConcurrency(eligiblePages, PAGE_FETCH_CONCURRENCY, async (page) => {
      out.push({ pageId: page.id, walls: await this.fetchPageWalls(page.id) });
    });
    return out;
  }


  // Symbol detections (doors, windows, fixtures) from the trained YOLO
  // segmentation pass. Same pagination contract as walls/rooms.
  static async fetchPageDetections(pageId: number): Promise<BackendDetection[]> {
    await this.ensureAuth();
    const PAGE_SIZE = 200;
    const all: BackendDetection[] = [];
    for (let page = 1; ; page++) {
      const res = await apiRequest<{ items: BackendDetection[]; total: number }>(
        `/pages/${pageId}/detections?page_size=${PAGE_SIZE}&page=${page}`
      );
      const items = res.items ?? [];
      all.push(...items);
      if (items.length < PAGE_SIZE) break;
    }
    return all;
  }

  // Fetch all symbol detections across every takeoff-eligible page.
  static async fetchAllBlueprintDetections(
    pages: BackendPage[]
  ): Promise<{ pageId: number; detections: BackendDetection[] }[]> {
    const eligiblePages = pages.filter((p) => p.is_takeoff_eligible !== false);
    if (eligiblePages.length === 0) return [];

    const out: { pageId: number; detections: BackendDetection[] }[] = [];
    await runWithConcurrency(eligiblePages, PAGE_FETCH_CONCURRENCY, async (page) => {
      out.push({ pageId: page.id, detections: await this.fetchPageDetections(page.id) });
    });
    return out;
  }

  // Fetches one page's full geometry (rooms + architectural walls + legacy
  // walls + symbol detections) as a single unit — the building block for
  // priority/batched loading (see lib/concurrency.ts + Workspace.tsx),
  // replacing the old pattern of 4 separate all-pages-at-once fan-outs.
  // Any sub-fetch failing rejects the whole page (never silently
  // substitutes an empty array for a real failure) so the caller can mark
  // this page's geometry honestly unavailable instead of "genuinely zero."
  static async fetchPageGeometry(pageId: number): Promise<{
    rooms: BackendRoom[];
    archWalls: BackendArchitecturalWall[];
    walls: BackendWall[];
    detections: BackendDetection[];
  }> {
    const [rooms, archWalls, detections] = await Promise.all([
      this.fetchPageRooms(pageId),
      this.fetchPageArchitecturalWalls(pageId),
      this.fetchPageDetections(pageId),
    ]);
    let walls: BackendWall[] = [];
    if (archWalls.length === 0) {
      walls = await this.fetchPageWalls(pageId);
    }
    return { rooms, archWalls, walls, detections };
  }

  // Generate / Compute live Estimate with custom Markups
  static async generateEstimate(
    projectId: number,
    blueprintId: number,
    overheadPct: number = 10,
    profitPct: number = 15,
    contingencyPct: number = 5
  ): Promise<EstimateSummary> {
    await this.ensureAuth();
    return apiRequest<EstimateSummary>(`/projects/${projectId}/estimates`, {
      method: "POST",
      body: JSON.stringify({
        blueprint_id: blueprintId,
        overhead_pct: overheadPct,
        profit_pct: profitPct,
        contingency_pct: contingencyPct,
      }),
    });
  }

  // Fetch Latest Estimate for Project
  static async fetchLatestEstimate(projectId: number): Promise<EstimateSummary | null> {
    await this.ensureAuth();
    try {
      const res = await apiRequest<{ items: EstimateSummary[] }>(`/projects/${projectId}/estimates`);
      if (res && res.items && res.items.length > 0) {
        return res.items[0];
      }
    } catch (e) {
      console.warn("[BackendApiService] Could not fetch estimate warnings:", e);
    }
    return null;
  }

  // Query Caddie AI Assistant via FastAPI backend
  static async queryAssistant(
    projectId: number,
    message: string,
    history: Array<{ role: "user" | "assistant"; content: string }> = [],
    selectedContext?: {
      source: "room" | "wall" | "detection" | "archwall";
      backend_id: number | string;
      name: string;
      kind: string;
      area_sqft?: number;
      perimeter_ft?: number;
      confidence: number;
      status: string;
      sheet_name?: string;
    } | null,
    activeTool?: string
  ): Promise<{
    reply: string;
    suggestions: Array<{ title: string; trade?: string }>;
    proposed_actions: AssistantProposedAction[];
  }> {
    await this.ensureAuth();
    return apiRequest<{
      reply: string;
      suggestions: Array<{ title: string; trade?: string }>;
      proposed_actions: AssistantProposedAction[];
    }>("/assistant/query", {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        message,
        history,
        selected_context: selectedContext ?? null,
        active_tool: activeTool ?? null,
      }),
    });
  }

  // Fetch QA Check Readiness & Pre-estimate Validation Flags
  static async fetchQaCheck(blueprintId: number): Promise<{ blueprint_id: number; flags: Array<{ level: string; message: string }> }> {
    await this.ensureAuth();
    return apiRequest<{ blueprint_id: number; flags: Array<{ level: string; message: string }> }>(`/qa/blueprints/${blueprintId}/qa-check`);
  }

  // Fetch Cross-Validation (Schedule vs AI/Geometry Discrepancies)
  static async fetchCrossValidation(blueprintId: number): Promise<{ blueprint_id: number; flags: Array<{ schedule_type: string; schedule_quantity: number; ai_quantity: number; discrepancy: number; message: string }> }> {
    await this.ensureAuth();
    return apiRequest<{ blueprint_id: number; flags: Array<{ schedule_type: string; schedule_quantity: number; ai_quantity: number; discrepancy: number; message: string }> }>(`/qa/blueprints/${blueprintId}/cross-validation`);
  }

  // Trigger Multi-Model Auto-Approve Consensus Gateway
  static async runConsensus(blueprintId: number): Promise<{ blueprint_id: number; auto_approved_count: number; pending_count: number; details: string[] }> {
    await this.ensureAuth();
    return apiRequest<{ blueprint_id: number; auto_approved_count: number; pending_count: number; details: string[] }>(`/qa/blueprints/${blueprintId}/consensus`, {
      method: "POST",
    });
  }

  // Update room status and/or name or other attributes
  static async updateRoom(
    roomId: number | string,
    payload: Partial<BackendRoom>
  ): Promise<BackendRoom> {
    await this.ensureAuth();
    return apiRequest<BackendRoom>(`/rooms/${roomId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  // Update wall attributes
  static async updateWall(wallId: number | string, payload: Partial<BackendWall>): Promise<BackendWall> {
    await this.ensureAuth();
    return apiRequest<BackendWall>(`/walls/${wallId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  // Update detection attributes
  static async updateDetection(
    detectionId: number | string,
    payload: Partial<BackendDetection>
  ): Promise<BackendDetection> {
    await this.ensureAuth();
    return apiRequest<BackendDetection>(`/detections/${detectionId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  // Approve a YOLO detection
  static async approveDetection(detectionId: number | string, reason: string | null = null): Promise<BackendDetection> {
    await this.ensureAuth();
    return apiRequest<BackendDetection>(`/detections/${detectionId}/approve`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  }

  // Reject a YOLO detection
  static async rejectDetection(detectionId: number | string, reason: string | null = null): Promise<BackendDetection> {
    await this.ensureAuth();
    return apiRequest<BackendDetection>(`/detections/${detectionId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  }

  // Bulk review all pending rooms, walls, and detections on a page
  static async bulkReviewPage(pageId: number, status: "approved" | "rejected", reason: string | null = null): Promise<{ rooms_updated: number; walls_updated: number; detections_updated: number }> {
    await this.ensureAuth();
    return apiRequest<{ rooms_updated: number; walls_updated: number; detections_updated: number }>(`/pages/${pageId}/bulk-review`, {
      method: "POST",
      body: JSON.stringify({ status, reason }),
    });
  }

  // Lookup Civil Construction Assembly Specification (P1, W3, F1, C1)
  static async fetchAssemblySpec(code: string): Promise<{ code: string; category: string; title: string; description: string; material_components: string[] }> {
    return apiRequest<{ code: string; category: string; title: string; description: string; material_components: string[] }>(`/qa/specs/${code}`);
  }

  // List all Takeoff Projects
  static async listProjects(pageSize = 10): Promise<{ items: Project[]; total: number }> {
    await this.ensureAuth();
    return apiRequest<{ items: Project[]; total: number }>(`/projects?page_size=${pageSize}`);
  }

  // Fetch non-persisted live trade breakdown directly from backend geometry recomputation
  static async fetchLiveTradeBreakdown(
    projectId: number,
    blueprintId: number
  ): Promise<Array<{
    trade: string;
    material_quantity: number;
    material_unit: string;
    labor_hours: number;
    direct_cost: number;
    // Present once the backend's trade-isolation validator runs (always,
    // as of this endpoint's current version) — optional here so older
    // cached responses or a rolled-back backend don't break parsing.
    status?: "validated" | "needs_review" | "error";
    confidence?: number;
    validation_reasons?: string[];
    line_items: Array<{
      id: number;
      trade: string;
      category: string;
      label: string;
      quantity: number;
      unit: string;
      unit_cost: number;
      total_cost: number;
    }>;
  }>> {
    await this.ensureAuth();
    return apiRequest(`/projects/${projectId}/blueprints/${blueprintId}/live-breakdown`);
  }

  // Compute + persist a new isolated takeoff snapshot for a single trade.
  // Never rejects on a trade-engine crash — the response comes back with
  // status: "error" instead (still HTTP 201), so a caller asking about
  // one trade is never broken by another trade's failure.
  static async computeTradeTakeoff(
    projectId: number,
    blueprintId: number,
    trade: TradeId
  ): Promise<TradeTakeoffResponse> {
    await this.ensureAuth();
    return apiRequest(`/projects/${projectId}/blueprints/${blueprintId}/takeoffs/${trade}`, { method: "POST" });
  }

  // Read the most recently persisted takeoff snapshot for one trade
  // (no recompute — call computeTradeTakeoff first if none exists yet).
  static async fetchTradeTakeoff(
    projectId: number,
    blueprintId: number,
    trade: TradeId
  ): Promise<TradeTakeoffResponse> {
    await this.ensureAuth();
    return apiRequest(`/projects/${projectId}/blueprints/${blueprintId}/takeoffs/${trade}`);
  }

  // Non-persisted, instant recompute of one trade's quantities scoped to a
  // single page (sheet) — matches GET .../pages/{page_id}/takeoffs/{trade}.
  // This is the backend-validated counterpart to the "current sheet" figure
  // shown in the UI: same engine, same formula_breakdown/evidence, just
  // filtered to one page instead of the whole blueprint.
  static async fetchPageTakeoff(
    projectId: number,
    blueprintId: number,
    pageId: number,
    trade: TradeId
  ): Promise<PageTradeTakeoffResponse> {
    await this.ensureAuth();
    return apiRequest(`/projects/${projectId}/blueprints/${blueprintId}/pages/${pageId}/takeoffs/${trade}`);
  }

  // Real per-wall reconciliation ledger from the most recently persisted
  // drywall takeoff — matches app/api/v1/endpoints/takeoffs.py's
  // get_drywall_wall_ledger(). One entry per ArchitecturalWall with genuine
  // provenance (height/assembly verified vs assumed), not client-derived math.
  static async fetchDrywallWallLedger(
    projectId: number,
    blueprintId: number
  ): Promise<WallLedgerResponse> {
    await this.ensureAuth();
    return apiRequest(`/projects/${projectId}/blueprints/${blueprintId}/takeoffs/drywall/wall-ledger`);
  }

  // List blueprints for a project
  static async listBlueprints(projectId: number, pageSize = 10): Promise<{ items: any[]; total: number }> {
    await this.ensureAuth();
    return apiRequest<{ items: any[]; total: number }>(`/projects/${projectId}/blueprints?page_size=${pageSize}`);
  }

  // Real, persisted, cross-session change history — matches
  // app/schemas/audit.py's AuditLogRead / GET .../audit-log. Unlike
  // AppState.history (this browser session's local ADD_HISTORY entries),
  // this is the backend's durable audit trail: every tracked field change
  // to any wall/room/detection/estimate, with before/after values.
  static async fetchAuditLog(projectId: number, pageSize = 100): Promise<Paginated<AuditLogEntry>> {
    await this.ensureAuth();
    return apiRequest(`/projects/${projectId}/audit-log?page_size=${pageSize}&sort_by=created_at&sort_dir=desc`);
  }


  // Wall-Context AI Assistant Investigation
  static async queryWallContext(
    projectId: number,
    wallId: string,
    message: string,
    history: Array<{ role: string; content: string }> = [],
    selectedWallData?: any,
    blueprintId?: number,
    pageId?: number
  ): Promise<WallContextQueryResponse> {
    await this.ensureAuth();
    return apiRequest<WallContextQueryResponse>(`/assistant/wall-context`, {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        wall_id: wallId,
        message,
        history,
        selected_wall_data: selectedWallData,
        blueprint_id: blueprintId,
        page_id: pageId,
      }),
    });
  }

  // =========================================================================
  // IFC / BIM Engine APIs
  // =========================================================================

  /** Uploads an IFC building model (.ifc, .ifcxml, .ifczip). */
  static async uploadIfc(file: File, projectId?: number): Promise<IfcUploadResponse> {
    await this.ensureAuth();
    const formData = new FormData();
    formData.append("file", file);
    if (projectId) {
      formData.append("project_id", String(projectId));
    }
    return apiRequest<IfcUploadResponse>("/ifc/upload", {
      method: "POST",
      body: formData,
    });
  }

  /** Gets metadata and validation report for an uploaded IFC document. */
  static async getIfcDocument(documentId: string): Promise<any> {
    await this.ensureAuth();
    return apiRequest<any>(`/ifc/${documentId}`);
  }

  /** Parses and normalizes IFC elements into a Canonical BIM Model. */
  static async parseIfc(documentId: string): Promise<any> {
    await this.ensureAuth();
    return apiRequest<any>(`/ifc/${documentId}/parse`, {
      method: "POST",
    });
  }

  /** Retrieves the Canonical BIM Model (Project, Storeys, Spaces, Walls, Openings). */
  static async getCanonicalModel(documentId: string): Promise<any> {
    await this.ensureAuth();
    return apiRequest<any>(`/ifc/${documentId}/canonical`);
  }

  /** Calculates deterministic, auditable multi-trade QTO with 100% IFC GUID provenance. */
  static async calculateIfcTakeoff(documentId: string, wasteFactor: number = 0.10, trade: string = "drywall"): Promise<IfcTakeoffResponse> {
    await this.ensureAuth();
    return apiRequest<IfcTakeoffResponse>(`/ifc/${documentId}/takeoff?waste_factor=${wasteFactor}&trade=${encodeURIComponent(trade)}`, {
      method: "POST",
    });
  }

  /** Inspects a specific BIM element by its IFC GUID. */
  static async inspectIfcElement(documentId: string, elementGuid: string): Promise<any> {
    await this.ensureAuth();
    return apiRequest<any>(`/ifc/${documentId}/elements/${elementGuid}`);
  }

  /** Downloads the full auditable QTO Bill of Quantities Excel workbook. */
  static async exportIfcExcel(documentId: string): Promise<Blob> {
    await this.ensureAuth();
    const token = getAuthToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const response = await fetch(`/api/v1/ifc/${documentId}/export/excel`, { headers });
    if (!response.ok) throw new Error("Failed to export QTO Excel workbook");
    return response.blob();
  }

  // =========================================================================
  // Architectural PDF Vector Engine & Native Reconstruction API
  // =========================================================================

  /** Uploads architectural vector PDF, extracts native geometry and computes shared QTO. */
  static async uploadPdfFile(file: File, projectId?: number, targetPage?: number): Promise<any> {
    await this.ensureAuth();
    const formData = new FormData();
    formData.append("file", file);
    if (projectId != null) formData.append("project_id", projectId.toString());
    if (targetPage != null) formData.append("target_page", targetPage.toString());

    return apiRequest<any>(
      "/pdf/upload",
      {
        method: "POST",
        body: formData,
      },
      600_000
    );
  }

  /** Retrieves document status, hash, and capabilities. */
  static async getPdfDocument(documentId: string): Promise<any> {
    await this.ensureAuth();
    return apiRequest<any>(`/pdf/${documentId}`);
  }

  /** Lists pages/sheets in the PDF. */
  static async getPdfPages(documentId: string): Promise<any> {
    await this.ensureAuth();
    return apiRequest<any>(`/pdf/${documentId}/pages`);
  }

  /** Retrieves sheet details and layer counts. */
  static async getPdfPageDetails(documentId: string, pageNum: number): Promise<any> {
    await this.ensureAuth();
    return apiRequest<any>(`/pdf/${documentId}/pages/${pageNum}`);
  }

  /** Retrieves complete native vector geometry, dimensions, text, and semantic objects for canvas rendering. */
  static async getPdfGeometry(documentId: string, pageNum?: number, layer?: string): Promise<PdfGeometryResponse> {
    await this.ensureAuth();
    let url = `/pdf/${documentId}/geometry`;
    const params = new URLSearchParams();
    if (pageNum != null) params.set("page_num", pageNum.toString());
    if (layer != null) params.set("layer", layer);
    const qs = params.toString();
    if (qs) url += `?${qs}`;
    return apiRequest<PdfGeometryResponse>(url);
  }

  /** Retrieves reconstructed roof planes and slopes. */
  static async getPdfRoofing(documentId: string): Promise<any> {
    await this.ensureAuth();
    return apiRequest<any>(`/pdf/${documentId}/roofing`);
  }

  /** Retrieves shared auditable QTO summary (converged on BIMRoofingEngine). */
  static async getPdfQto(documentId: string): Promise<any> {
    await this.ensureAuth();
    return apiRequest<any>(`/pdf/${documentId}/qto`);
  }

  /** Retrieves auditable GeometryValidationReport. */
  static async getPdfValidation(documentId: string): Promise<any> {
    await this.ensureAuth();
    return apiRequest<any>(`/pdf/${documentId}/validation`);
  }

  /** Retrieves multi-page 10-sheet canonical reconciliation table. */
  static async getPdfReconciliation(documentId: string): Promise<any> {
    await this.ensureAuth();
    return apiRequest<any>(`/pdf/${documentId}/reconciliation`);
  }

  /** Phase 7: Retrieves project-level multi-trade QTO with duplicate prevention across all sheets. */
  static async getPdfProjectQto(documentId: string): Promise<any> {
    await this.ensureAuth();
    return apiRequest<any>(`/pdf/${documentId}/qto/project`);
  }

  /** Phase 7: Retrieves auditable Bill of Quantities (BOQ) derived from verified element QTO. */
  static async getPdfBoq(documentId: string): Promise<any> {
    await this.ensureAuth();
    return apiRequest<any>(`/pdf/${documentId}/boq`);
  }

  /** Phase 7: Retrieves Sheet Audit Matrix table across all sheets. */
  static async getPdfSheetAuditMatrix(documentId: string): Promise<any> {
    await this.ensureAuth();
    return apiRequest<any>(`/pdf/${documentId}/sheet-audit-matrix`);
  }

  /** Phase 7: Retrieves element-level QTO audit table with measurements, gross, deductions, and provenance. */
  static async getPdfQtoAuditTable(documentId: string): Promise<any> {
    await this.ensureAuth();
    return apiRequest<any>(`/pdf/${documentId}/qto/audit-table`);
  }

  /** Returns raster preview URL for optional canvas visual comparison layer. */
  static getPdfPageRenderUrl(documentId: string, pageNum: number, dpi: number = 150): string {
    return `/api/v1/pdf/${documentId}/page-render/${pageNum}?dpi=${dpi}`;
  }
}

export interface PdfGeometryResponse {
  document_id: string;
  page_number: number;
  sheet_number: string;
  sheet_title: string;
  drawing_type?: string;
  discipline?: string;
  units?: string;
  width_pt: number;
  height_pt: number;
  rotation: number;
  scale: {
    scale_status: string;
    scale_string: string | null;
    scale_detected?: string | null;
    scale_validated?: string | null;
    scale_display?: string | null;
    scale_evidence_type?: string | null;
    ratio: number | null;
    ft_per_pt: number | null;
    unit?: string;
    provenance: string;
    notes: string[];
  };
  regions?: Array<{
    region_id: string;
    page_number: number;
    bbox_pdf: number[];
    drawing_type: string;
    title: string;
    region_category?: string;
    takeoff_eligible?: boolean;
    scale?: any;
    units?: string;
  }>;
  cross_page_references?: Array<{
    reference_id: string;
    source_page: number;
    target_page: number;
    reference_type: string;
    marker_text: string;
    description: string;
  }>;
  takeoff_summary?: {
    page_number: number;
    sheet_title: string;
    drawing_type: string;
    drywall_sf: number;
    flooring_sf: number;
    roofing_sf: number;
    drywall_status: string;
    flooring_status: string;
    roofing_status: string;
    plumbing_status?: string;
    gating_decision: string;
    gating_notes: string[];
    native_objects_count?: number;
    canonical_objects_count?: number;
    takeoff_objects_count?: number;
    excluded_objects_count?: number;
    review_objects_count?: number;
    items: Array<{
      item_id: string;
      item_code?: string;
      item?: string;
      canonical_object_id?: string;
      source_page?: number;
      source_sheet?: string;
      source_region?: string;
      source_object_id?: string;
      trade: string;
      category: string;
      name: string;
      description?: string;
      material?: string;
      scope_status?: string;
      measurement_basis?: string;
      gross_quantity?: number;
      gross?: number;
      deduction_quantity?: number;
      deduction?: number;
      net_quantity?: number;
      net?: number;
      quantity: number;
      unit: string;
      confidence?: number;
      status: string;
      provenance?: string;
      provenance_notes: string[];
      source_object_ids: string[];
      validation_status?: string;
      calculation_details?: Record<string, any>;
    }>;
  };
  layers: Array<{
    name: string;
    display_name: string;
    object_count: number;
    color: string;
    is_visible: boolean;
  }>;
  semantic_objects: Array<{
    id: string;
    source_object_id?: string;
    page_number: number;
    object_type: string;
    layer: string;
    source_type?: string;
    semantic_type?: string;
    trade_scope?: string;
    qto_eligible?: boolean;
    qto_reason?: string;
    source_vector_ids: string[];
    source_text_ids: string[];
    source_points_pdf: number[][];
    normalized_points: number[][];
    transformed_points_ft: number[][];
    bbox_pdf: number[];
    transformed_bbox_ft: number[] | null;
    label: string | null;
    properties: Record<string, any>;
    classification_status: string;
    confidence: number;
    provenance: string;
    qto_reference_id: string | null;
  }>;
  dimension_objects: Array<{
    id: string;
    page_number: number;
    text_object_id?: string | null;
    dimension_text: string;
    measured_value: number | null;
    unit: string | null;
    start_pt: number[];
    end_pt: number[];
    start_pt_ft: number[] | null;
    end_pt_ft: number[] | null;
    measured_points_distance: number;
    measured_length_ft: number | null;
    measured_length_mm: number | null;
    dimension_line_id: string | null;
    witness_line_ids: string[];
    associated_geometry_ids: string[];
    association_status: string;
    provenance: string;
  }>;
  text_objects: Array<{
    id: string;
    page_number: number;
    text: string;
    semantic_role: string;
    layer?: string;
    bbox_pdf: number[];
    origin_pdf: number[];
    font_name: string | null;
    font_size: number;
    rotation_deg: number;
    is_duplicate?: boolean;
    display_priority?: number;
    overlap_group_id?: string | null;
    is_suppressed_in_clean_mode?: boolean;
  }>;
  relationships: Array<{
    relationship_id: string;
    page_number: number;
    relationship_type: string;
    source_object_id: string;
    target_object_id: string;
    method: string;
    distance_pt: number;
    is_contained: boolean;
    confidence: number;
    status: string;
    provenance: string;
    notes?: string;
  }>;
  roof_planes: Array<any>;
  native_geometry?: Array<any>;
  reconciliation_table?: {
    text: { native: number; canonical: number; rendered: number; notes: string };
    dimensions: { native_candidates?: number; native?: number; canonical: number; rendered: number; notes: string };
    plumbing_symbols?: { native: number; canonical: number; rendered: number; notes: string };
    legend?: { native: number; canonical: number; rendered: number; notes: string };
    detail_regions?: { detected: number; canonical: number; rendered: number; notes: string };
    notes?: { native: number; canonical: number; rendered: number; notes: string };
    geometry: { native: number; canonical: number; rendered: number; notes: string };
    roof?: { native_candidates: number; canonical: number; rendered: number; notes: string };
  };
}

export interface IfcValidationReport {
  status: string;
  schema: string;
  is_valid: boolean;
  project_name: string | null;
  counts: {
    buildings: number;
    storeys: number;
    walls: number;
    spaces: number;
    doors: number;
    windows: number;
    openings: number;
  };
  issues: Array<{
    severity: string;
    code: string;
    message: string;
    entity_guid: string | null;
  }>;
}

export interface IfcUploadResponse {
  id: string;
  filename: string;
  schema: string;
  status: string;
  source_hash?: string;
  validation_report: IfcValidationReport;
}

export interface IfcTakeoffResponse {
  document_id: string;
  status: string;
  source_hash?: string;
  qto: {
    engine_version: string;
    model_sha256?: string;
    source_hash?: string;
    snapshot_created_at?: string;
    total_gross_wall_area_sqft: number;
    total_opening_deduction_sqft: number;
    total_net_drywall_area_sqft: number;
    board_area_equivalent_sqft: number;
    estimated_drywall_sheets_4x8: number;
    estimated_drywall_sheets_4x10: number;
    estimated_drywall_sheets_4x12: number;
    total_studs_count: number;
    total_track_linear_ft: number;
    total_screws_count: number;
    total_joint_compound_gallons: number;
    total_joint_tape_linear_ft: number;
    total_insulation_sqft: number;
    total_walls_evaluated: number;
    eligible_walls_count: number;
    excluded_walls_count: number;
    review_required_walls_count: number;
    line_items: Array<{
      item_id: string;
      trade: string;
      category: string;
      item_code: string;
      description: string;
      unit: string;
      quantity: number;
      source_guid: string;
      provenance: {
        ifc_guid: string;
        storey_name: string;
        wall_name: string;
        wall_classification: string;
        length_ft: number;
        finish_height_ft: number;
        side_a_gross_sqft: number;
        side_b_gross_sqft: number;
        openings_count: number;
        openings_deduction_sqft: number;
        net_drywall_sqft: number;
        formula: string;
        status: string;
      };
    }>;
  };
}

export interface WallContextEvidence {
  field: string;
  value: string;
  status: "VERIFIED" | "ASSUMED" | "DETECTED" | "INFERRED" | "NOT_AVAILABLE" | "CONFLICT";
  source_sheet?: string | null;
  source_page?: number | null;
  source_detail?: string | null;
  evidence_text?: string | null;
  confidence: number;
}

export interface WallContextAction {
  type: "FOCUS_SOURCE" | "OPEN_SCHEDULE" | "VIEW_DETAIL" | "HIGHLIGHT_WALL";
  sheet_code?: string | null;
  page_number?: number | null;
  detail?: string | null;
  detection_id?: string | null;
  label: string;
  description?: string | null;
}

export interface WallContextQueryResponse {
  answer: string;
  wall_id: string;
  display_code: string;
  category_label: string;
  confidence: number;
  status: string;
  qto_eligible: boolean;
  evidence: WallContextEvidence[];
  sources: Array<{ sheet: string; page?: number | null; type: string; description: string }>;
  warnings: string[];
  actions: WallContextAction[];
  generated_at: string;
}



