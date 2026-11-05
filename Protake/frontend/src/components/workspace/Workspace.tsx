import { useEffect, useRef, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Layers, Loader2, Building2, Sparkles, Compass } from "lucide-react";
import Toolbar from "@/components/toolbar/Toolbar";
import Sidebar from "@/components/sidebar/Sidebar";
import BlueprintWorkspace from "@/components/blueprint/BlueprintWorkspace";
import AIPanel from "@/components/ai-panel/AIPanel";
import SummaryPanel from "@/components/summary/SummaryPanel";
import BIMTakeoffWorkspace from "@/components/bim/BIMTakeoffWorkspace";
import PDFTakeoffWorkspace from "@/components/pdf/PDFTakeoffWorkspace";
import { useApp } from "@/state/AppContext";
import { BackendApiService, type BackendPage } from "@/api/backendApi";
import { architecturalWallToDetection, isSymbolDetection, roomToDetection, symbolToDetection, wallToDetection } from "@/lib/backendConversion";
import { runWithConcurrency } from "@/lib/concurrency";

import { SAMPLE_SHEETS, generateSampleDetections } from "@/lib/sampleData";
import type { Detection, Sheet } from "@/types";

const PAGE_LOAD_CONCURRENCY = 4;

/** Converts one page's real backend geometry into frontend Detection[] —
    the same conversion rules the old all-pages-at-once hydration used,
    just scoped to a single page so it can be called progressively. */
function pageGeometryToDetections(
  sheetId: string,
  geometry: { rooms: any[]; archWalls: any[]; walls: any[]; detections: any[] },
): Detection[] {
  const out: Detection[] = [];
  geometry.rooms.forEach((room) => out.push(roomToDetection(room, sheetId)));
  if (geometry.archWalls.length > 0) {
    geometry.archWalls.forEach((aw) => out.push(architecturalWallToDetection(aw, sheetId)));
  } else {
    geometry.walls.forEach((wall) => out.push(wallToDetection(wall, sheetId)));
  }
  geometry.detections.filter(isSymbolDetection).forEach((d) => out.push(symbolToDetection(d, sheetId)));
  return out;
}

export default function Workspace() {
  const { state, dispatch } = useApp();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState("Connecting to workspace…");
  const [loadingProgress, setLoadingProgress] = useState(15);

  const blueprintIdParam = searchParams.get("blueprint_id");
  const ifcIdParam = searchParams.get("ifc_id");
  const pdfIdParam = searchParams.get("pdf_id");
  const tradeParam = searchParams.get("trade") || "drywall";
  const viewParam = searchParams.get("view") || "3D";

  // If this is an IFC Building Model Takeoff session, render the dedicated BIM Takeoff Workspace.
  if (ifcIdParam) {
    return <BIMTakeoffWorkspace key={ifcIdParam} ifcId={ifcIdParam} initialTrade={tradeParam as any} initialViewMode={viewParam as any} />;
  }

  // If this is an Architectural Vector PDF session, render the Native PDF Workspace.
  if (pdfIdParam) {
    return <PDFTakeoffWorkspace key={pdfIdParam} documentId={pdfIdParam} />;
  }

  // Track currently hydrated blueprint ID to avoid redundant refetches
  // while allowing rehydration whenever the URL blueprint_id changes.
  const hydratedBlueprintIdRef = useRef<number | string | null>(null);
  const stateBlueprintId = state.blueprintId;
  const stateProjectId = state.projectId;
  const stateFile = state.file;

  // Per-page geometry loading state, shared between the initial priority
  // load, the background batch, and the "user switched to an unloaded
  // sheet" effect below. loadedPageIds = geometry successfully fetched AND
  // already dispatched into state.detections (re-fetching would duplicate
  // it, since FINISH_SCAN appends). inFlightPageIds = currently fetching,
  // so the background batch and the active-sheet effect never race to
  // fetch + double-dispatch the same page.
  const loadedPageIdsRef = useRef<Set<number>>(new Set());
  const inFlightPageIdsRef = useRef<Set<number>>(new Set());
  const pageByIdRef = useRef<Map<number, BackendPage>>(new Map());
  const sheetIdForPageRef = useRef<Map<number, string>>(new Map());
  const dispatchRef = useRef(dispatch);
  dispatchRef.current = dispatch;

  /** Fetches + dispatches one page's geometry exactly once (cache- and
      in-flight-guarded), marking its sheetGeometryState throughout —
      "loading" while in flight, "ready" on success, "error" (never a
      fabricated fallback) if the real fetch genuinely fails. */
  async function loadPageGeometry(pageId: number): Promise<void> {
    if (loadedPageIdsRef.current.has(pageId) || inFlightPageIdsRef.current.has(pageId)) return;
    const sheetId = sheetIdForPageRef.current.get(pageId);
    if (!sheetId) return;

    inFlightPageIdsRef.current.add(pageId);
    dispatchRef.current({ type: "SET_SHEET_GEOMETRY_STATE", sheetId, state: "loading" });
    try {
      const geometry = await BackendApiService.fetchPageGeometry(pageId);
      const detections = pageGeometryToDetections(sheetId, geometry);
      dispatchRef.current({ type: "FINISH_SCAN", detections });
      loadedPageIdsRef.current.add(pageId);
      dispatchRef.current({ type: "SET_SHEET_GEOMETRY_STATE", sheetId, state: "ready" });
    } catch (err) {
      console.warn(`[Protake] Geometry fetch failed for page ${pageId} — marking unavailable, not substituting fake data:`, err);
      dispatchRef.current({ type: "SET_SHEET_GEOMETRY_STATE", sheetId, state: "error" });
    } finally {
      inFlightPageIdsRef.current.delete(pageId);
    }
  }

  useEffect(() => {
    if (tradeParam && ["drywall", "flooring", "roofing", "painting", "furniture", "openings"].includes(tradeParam.toLowerCase())) {
      dispatch({ type: "SET_ACTIVE_TRADE", trade: tradeParam.toLowerCase() as any });
    }
  }, [tradeParam, dispatch]);

  useEffect(() => {
    if (!blueprintIdParam) return;

    if (blueprintIdParam === "sample") {
      if (stateFile?.isSample && hydratedBlueprintIdRef.current === "sample") return;
      hydratedBlueprintIdRef.current = "sample";
      // Rehydrate sample data
      dispatch({
        type: "SET_FILE",
        file: { name: "Commercial_Office_Tower_Set.pdf", sizeBytes: 4_213_880, numPages: 3, isSample: true },
      });
      dispatch({ type: "SET_NUM_PAGES", numPages: SAMPLE_SHEETS.length });
      dispatch({ type: "SET_SHEETS", sheets: SAMPLE_SHEETS });
      const sampleDetections = SAMPLE_SHEETS.flatMap((s: any) => generateSampleDetections(s.id));
      dispatch({ type: "FINISH_SCAN", detections: sampleDetections });
      dispatch({ type: "SET_UPLOAD_STAGE", stage: "complete" });
      return;
    }

    const blueprintId = parseInt(blueprintIdParam, 10);
    if (isNaN(blueprintId)) return;

    // BEST PRACTICE 1: If state already has this exact blueprint with its owning project,
    // sheets, and detections primed in memory (e.g. freshly arrived from UploadExperience),
    // skip redundant network rehydration completely for an instant 0ms transition!
    if (
      stateBlueprintId === blueprintId &&
      stateProjectId !== null &&
      stateFile !== null &&
      state.sheets.length > 0 &&
      state.detections.length > 0
    ) {
      hydratedBlueprintIdRef.current = blueprintId;
      return;
    }

    // If already hydrated in this component session, do not repeat
    if (
      stateBlueprintId === blueprintId &&
      stateProjectId !== null &&
      stateFile !== null &&
      hydratedBlueprintIdRef.current === blueprintId
    ) {
      return;
    }

    hydratedBlueprintIdRef.current = blueprintId;
    let active = true;
    setLoading(true);
    setLoadingStage("Resolving project workspace…");
    setLoadingProgress(20);

    async function hydrateState() {
      try {
        // Clear cached page IDs and stale detections from previous blueprints/projects
        loadedPageIdsRef.current.clear();
        inFlightPageIdsRef.current.clear();
        dispatch({ type: "CLEAR_DETECTIONS" });

        // Fetch blueprint status to resolve the true owning project_id
        const blueprintStatus = await BackendApiService.getBlueprintStatus(blueprintId);
        if (!active) return;
        dispatch({ type: "SET_PROJECT_ID", projectId: blueprintStatus.project_id });
        dispatch({ type: "SET_BLUEPRINT_ID", blueprintId });

        setLoadingStage("Loading blueprint sheets & vector pages…");
        setLoadingProgress(45);

        // 1. Fetch blueprint pages
        const pages = await BackendApiService.fetchBlueprintPages(blueprintId);

        if (!active) return;

        if (pages && pages.length > 0) {
          const numPages = pages.length;
          dispatch({ type: "SET_NUM_PAGES", numPages });

          const sheets: Sheet[] = pages.map((page, idx) => ({
            id: `sheet-${idx}`,
            name: page.sheet_name || `Page ${page.page_number}`,
            code: page.sheet_code || `A10${page.page_number}`,
            pageIndex: idx,
            thumbnailUrl: undefined,
            widthPx: page.width_px,
            heightPx: page.height_px,
            pageType: page.page_type ?? undefined,
            isTakeoffEligible: page.is_takeoff_eligible ?? true,
            skipReason: page.skip_reason ?? undefined,
            dbPageId: page.id,
            discipline: page.discipline ?? undefined,
            primaryTitle: page.primary_title ?? undefined,
            classificationConfidence: page.classification_confidence ?? undefined,
            geometryAuthority: page.geometry_authority ?? undefined,
          }));
          dispatch({ type: "SET_SHEETS", sheets });

          // Build the page-lookup refs the priority/background geometry
          // loader (loadPageGeometry, defined above) and the "user switched
          // to an unloaded sheet" effect below both read.
          pageByIdRef.current = new Map(pages.map((p) => [p.id, p]));
          sheetIdForPageRef.current = new Map(sheets.map((s) => [s.dbPageId!, s.id]));

          const firstPageImageUrl = await BackendApiService.fetchPageImageObjectUrl(pages[0].id).catch(() => undefined);
          if (!active) return;
          dispatch({
            type: "SET_FILE",
            file: {
              name: `blueprint_${blueprintId}.png`,
              sizeBytes: 0,
              numPages,
              objectUrl: firstPageImageUrl,
            },
          });

          setLoadingStage("Preparing takeoff workspace…");
          setLoadingProgress(95);
          dispatch({ type: "SET_UPLOAD_STAGE", stage: "complete" });
          setLoading(false);

          // Priority load: load active sheet geometry immediately
          const eligiblePages = pages.filter((p) => p.is_takeoff_eligible !== false);
          const firstPage = eligiblePages[0] ?? pages[0];
          if (firstPage) {
            loadPageGeometry(firstPage.id).catch(() => {});
          }

          // Background load thumbnails progressively
          runWithConcurrency(pages, PAGE_LOAD_CONCURRENCY, async (page, idx) => {
            const url = await BackendApiService.fetchPageThumbnailObjectUrl(page.id).catch(() => undefined);
            if (url) {
              dispatchRef.current({ type: "UPDATE_SHEET_THUMBNAIL", sheetId: `sheet-${idx}`, thumbnailUrl: url });
            }
          }).catch(() => {});

          // Background load remaining page geometries progressively
          const remainingPages = eligiblePages.filter((p) => p.id !== firstPage?.id);
          runWithConcurrency(remainingPages, PAGE_LOAD_CONCURRENCY, (page) => loadPageGeometry(page.id)).catch(() => {});
        }
      } catch (err) {
        console.error("[Protake Workspace] Rehydration failed:", err);
        navigate("/upload");
      } finally {
        if (active) setLoading(false);
      }
    }

    hydrateState();

    return () => {
      active = false;
    };
    // Intentionally narrow: this effect's own dispatches (SET_PROJECT_ID,
    // SET_BLUEPRINT_ID, SET_FILE, SET_SHEETS, FINISH_SCAN) write to exactly
    // the state fields that were previously also listed as dependencies
    // here — stateBlueprintId/stateProjectId/stateFile/sheets.length/
    // detections.length. Because those dispatches happen across real
    // network awaits (not synchronously), React re-renders and re-invokes
    // this effect mid-flight every time one of them changes, restarting
    // hydrateState() from scratch and compounding into overlapping,
    // never-completing fetch storms on any real (non-instant, non-sample)
    // blueprint. The re-entrancy guards above (hydratedBlueprintIdRef, the
    // `active` flag) are what actually need to gate re-running this effect;
    // blueprintIdParam is the only real external trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blueprintIdParam, dispatch, navigate]);

  // Priority load for active sheet when switching sheets & progressive adjacent sheet loading
  useEffect(() => {
    if (!state.activeSheetId || state.sheets.length === 0) return;
    const sheet = state.sheets.find((s) => s.id === state.activeSheetId);
    if (!sheet || !sheet.dbPageId) return;

    const pageId = sheet.dbPageId;
    if (!loadedPageIdsRef.current.has(pageId) && !inFlightPageIdsRef.current.has(pageId)) {
      loadPageGeometry(pageId);
    }

    // Load adjacent sheets progressively
    const currentIndex = state.sheets.findIndex((s) => s.id === state.activeSheetId);
    if (currentIndex !== -1) {
      const adjacentIndices = [currentIndex - 1, currentIndex + 1].filter(
        (i) => i >= 0 && i < state.sheets.length
      );
      for (const idx of adjacentIndices) {
        const adjSheet = state.sheets[idx];
        if (adjSheet?.dbPageId && adjSheet.isTakeoffEligible !== false) {
          if (!loadedPageIdsRef.current.has(adjSheet.dbPageId) && !inFlightPageIdsRef.current.has(adjSheet.dbPageId)) {
            loadPageGeometry(adjSheet.dbPageId).catch(() => {});
          }
        }
      }
    }
  }, [state.activeSheetId, state.sheets]);

  const focusModeRef = useRef(state.focusMode);
  focusModeRef.current = state.focusMode;

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape" || !focusModeRef.current) return;
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
      dispatch({ type: "SET_FOCUS_MODE", enabled: false });
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [dispatch]);

  if (loading) {
    return (
      <div className="h-full w-full flex flex-col items-center justify-center bg-[var(--color-bg)] relative overflow-hidden select-none">
        {/* Subtle background radial glow */}
        <div className="absolute w-[500px] h-[500px] rounded-full bg-blue-600/10 blur-[100px] pointer-events-none" />

        <div className="relative z-10 flex flex-col items-center max-w-sm px-6 text-center">
          {/* Animated Icon Card */}
          <div className="relative w-16 h-16 mb-5 flex items-center justify-center rounded-2xl bg-white/[0.04] border border-white/10 shadow-2xl backdrop-blur-md">
            <div className="absolute inset-0 rounded-2xl bg-gradient-to-tr from-blue-500/20 to-indigo-500/20 animate-pulse" />
            <Compass className="w-8 h-8 text-blue-400 animate-spin" style={{ animationDuration: "12s" }} />
            <div className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-blue-500 animate-ping" />
          </div>

          {/* Title & Stage */}
          <h3 className="text-sm font-semibold text-[var(--color-text-primary)] mb-1 tracking-tight flex items-center gap-1.5">
            <Building2 className="w-4 h-4 text-blue-400" />
            Restoring Takeoff Workspace
          </h3>
          <p className="text-xs text-[var(--color-text-secondary)] font-mono mb-4 min-h-[18px]">
            {loadingStage}
          </p>

          {/* Progress Bar */}
          <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden border border-white/10 p-0.5 mb-2">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 rounded-full transition-all duration-300 ease-out"
              style={{ width: `${loadingProgress}%` }}
            />
          </div>

          <div className="flex items-center justify-between w-full text-[10px] text-[var(--color-text-secondary)] font-mono">
            <span className="flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-amber-400" />
              Blueprint #{blueprintIdParam}
            </span>
            <span>{loadingProgress}%</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-full flex flex-col min-h-0">
      {!state.focusMode && <Toolbar />}
      <div className="flex-1 flex min-h-0">
        {!state.focusMode && <Sidebar />}
        <div className="flex-1 flex flex-col min-h-0 min-w-0">
          <BlueprintWorkspace />
          {!state.focusMode && state.summaryPanelVisible && <SummaryPanel />}
        </div>
        {!state.focusMode && <AIPanel />}
      </div>
    </div>
  );
}
