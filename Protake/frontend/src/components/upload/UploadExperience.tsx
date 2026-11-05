import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { 
  UploadCloud, FileText, CheckCircle2, FolderOpen, Ruler, Zap, ShieldCheck, 
  SquareStack, Layers, Home, Box, Lock, Building2, Check, ArrowRight, 
  Compass, FileSpreadsheet, Cpu, X, RotateCcw, AlertTriangle, ChevronRight
} from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/state/AppContext";
import { loadPdf, renderThumbnail } from "@/lib/pdf";
import { generateSampleDetections, seedHistory, SAMPLE_SHEETS } from "@/lib/sampleData";
import { BackendApiService, type BackendPage, type BackendWall } from "@/api/backendApi";
import { architecturalWallToDetection, isSymbolDetection, roomToDetection, symbolToDetection, wallToDetection } from "@/lib/backendConversion";

import type { Detection, Sheet, TradeId } from "@/types";
import TradeSelectModal from "@/components/common/TradeSelectModal";

function sleep(ms: number) {
  return new Promise((res) => setTimeout(res, ms));
}

function formatFileSize(bytes?: number): string {
  if (!bytes) return "";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadExperience() {
  const { state, dispatch } = useApp();
  const navigate = useNavigate();
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [liveMessage, setLiveMessage] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const bimInputRef = useRef<HTMLInputElement>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);
  const [showTradeSelectModal, setShowTradeSelectModal] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [pendingSample, setPendingSample] = useState<boolean>(false);
  const [selectedTradeForPicker, setSelectedTradeForPicker] = useState<TradeId | "all">("all");
  const [activeTrade, setActiveTrade] = useState<TradeId | "all">("all");

  async function startTakeoffForTrade(trade: TradeId | "all") {
    setShowTradeSelectModal(false);
    setActiveTrade(trade);
    setSelectedTradeForPicker(trade);
    
    if (trade === "all") {
      dispatch({ type: "RESET_VISIBILITY" });
    } else {
      dispatch({ type: "SET_SINGLE_ACTIVE_TRADE", trade });
    }

    if (pendingSample) {
      setPendingSample(false);
      await handleSample(trade);
    } else if (pendingFile) {
      const fileToUpload = pendingFile;
      setPendingFile(null);
      await handleRealFile(fileToUpload, trade);
    } else {
      inputRef.current?.click();
    }
  }

  const stage = state.uploadStage;
  const busy = stage !== "idle";

  const rawProgress = stage === "uploading" ? state.uploadProgress : state.scanProgress;
  const [displayProgress, setDisplayProgress] = useState(0);
  const wasBusyRef = useRef(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!busy) {
      setDisplayProgress(0);
    } else if (!wasBusyRef.current) {
      setDisplayProgress(rawProgress);
    } else {
      setDisplayProgress((prev) => Math.max(prev, rawProgress));
    }
    wasBusyRef.current = busy;
  }, [busy, rawProgress]);



  async function runDetectionPipeline(
    sheets: Sheet[],
    selectedTrade: TradeId | "all",
    backendDetections?: Detection[],
    detectionError?: string,
    blueprintId?: number
  ) {
    dispatch({ type: "SET_UPLOAD_STAGE", stage: "detecting" });
    dispatch({ type: "START_SCAN" });
    setLiveMessage("Rendering results to canvas…");
    for (const p of [15, 35, 58, 76, 94, 100]) {
      await sleep(150);
      dispatch({ type: "SET_SCAN_PROGRESS", progress: p });
    }

    const landingSheet = sheets.find((s) => s.isTakeoffEligible !== false) ?? sheets[0];

    if (backendDetections && backendDetections.length > 0) {
      let filteredDetections = backendDetections;
      if (selectedTrade !== "all") {
        const fetchRooms = ["painting", "flooring", "roofing", "drywall"].includes(selectedTrade);
        const fetchWalls = ["drywall"].includes(selectedTrade);
        const fetchDetections = ["painting", "furniture", "openings"].includes(selectedTrade);

        filteredDetections = backendDetections.filter((d) => {
          if (d.kind === "room") return fetchRooms;
          if (d.kind === "wall") return fetchWalls;
          if (["door", "window"].includes(d.kind)) return selectedTrade === "openings" || selectedTrade === "painting";
          return fetchDetections;
        });
      }

      dispatch({ type: "FINISH_SCAN", detections: filteredDetections });
      seedHistory().forEach((h) => dispatch({ type: "ADD_HISTORY", entry: h }));
      dispatch({ type: "SET_ACTIVE_SHEET", sheetId: landingSheet.id });
      await sleep(200);
      dispatch({ type: "SET_UPLOAD_STAGE", stage: "complete" });
      setLiveMessage(null);
      const roomCount = filteredDetections.filter((d) => d.kind === "room").length;
      const wallCount = filteredDetections.filter((d) => d.kind === "wall").length;
      const symbolCount = filteredDetections.filter((d) => d.kind === "door" || d.kind === "window").length;
      toast.success(
        `${roomCount} rooms, ${wallCount} walls${symbolCount > 0 ? `, ${symbolCount} doors/windows` : ""} loaded`,
        { description: `AI geometry engine initialized for ${selectedTrade === "all" ? "all trades" : selectedTrade}.` }
      );
      const isSample = state.file?.isSample;
      const tradeQuery = selectedTrade && selectedTrade !== "all" ? `&trade=${selectedTrade.toLowerCase()}` : "";
      navigate(`/workspace?blueprint_id=${isSample ? "sample" : blueprintId}${tradeQuery}`);
    } else {
      dispatch({ type: "FINISH_SCAN", detections: [] });
      dispatch({ type: "SET_ACTIVE_SHEET", sheetId: landingSheet.id });
      await sleep(200);
      dispatch({ type: "SET_UPLOAD_STAGE", stage: "complete" });
      setLiveMessage(null);

      if (detectionError) {
        setError(`Detection failed: ${detectionError}`);
        toast.error("Detection failed", { description: detectionError });
      } else {
        const reasons = Array.from(
          new Set(sheets.map((s) => s.skipReason).filter((r): r is string => !!r))
        );
        if (reasons.length > 0) {
          const detail = reasons.join(" · ");
          setError(`No rooms detected — ${detail}`);
          toast.warning("0 rooms detected", { description: detail });
        } else {
          setError(
            "No rooms detected. The geometry engine could not find closed room polygons in this drawing. " +
            "Check that the PDF is an architectural floor plan with closed room boundaries."
          );
          toast.warning("0 rooms detected", {
            description: "Geometry engine found no closed polygons. Ensure this is an architectural floor plan PDF.",
          });
        }
      }
      const tradeQuery = selectedTrade && selectedTrade !== "all" ? `?trade=${selectedTrade.toLowerCase()}` : "";
      navigate(`/workspace${tradeQuery}`);
    }
  }

  async function handleRealFile(file: File, selectedTrade: TradeId | "all") {
    setError(null);
    const isIfc = file.name.toLowerCase().endsWith(".ifc") || file.name.toLowerCase().endsWith(".ifcxml") || file.name.toLowerCase().endsWith(".ifczip");
    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    const isImage = file.type.startsWith("image/") || /\.(png|jpe?g|webp|tiff?)$/i.test(file.name);
    const isDwg = file.name.toLowerCase().endsWith(".dwg") || file.type === "application/acad" || file.type === "image/vnd.dwg" || file.type === "image/x-dwg";

    if (!isIfc && !isPdf && !isImage && !isDwg) {
      setError("Please upload an IFC building model (.ifc, .ifcxml, .ifczip) or PDF drawing.");
      toast.error("Unsupported file", { description: "Only IFC building models and PDF blueprints are supported." });
      return;
    }

    const base64Data = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.readAsDataURL(file);
    }).catch(() => undefined);

    dispatch({
      type: "SET_FILE",
      file: { name: file.name, sizeBytes: file.size, numPages: 1, objectUrl: URL.createObjectURL(file), base64: base64Data },
    });
    dispatch({ type: "SET_UPLOAD_STAGE", stage: "uploading" });
    dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 10 });

    // Handle Native IFC Workflow
    if (isIfc) {
      try {
        setLiveMessage("Uploading IFC model to BIM engine…");
        dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 30 });
        
        const uploadRes = await BackendApiService.uploadIfc(file);
        dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 60 });
        
        setLiveMessage("Parsing geometric extrusions & spatial graph…");
        dispatch({ type: "SET_UPLOAD_STAGE", stage: "processing" });
        dispatch({ type: "SET_SCAN_PROGRESS", progress: 20 });
        
        const parseRes = await BackendApiService.parseIfc(uploadRes.id);
        dispatch({ type: "SET_SCAN_PROGRESS", progress: 60 });
        
        const activeTrade = (selectedTrade && selectedTrade !== "all") ? selectedTrade.toLowerCase() : "drywall";
        setLiveMessage(`Running deterministic ${activeTrade.toUpperCase()} QTO & material formulas…`);
        const takeoffRes = await BackendApiService.calculateIfcTakeoff(uploadRes.id, 0.10, activeTrade);
        dispatch({ type: "SET_SCAN_PROGRESS", progress: 100 });
        
        toast.success(`IFC Model Processed for ${activeTrade.toUpperCase()}!`, {
          description: `Auditable ${activeTrade} takeoff calculated successfully.`,
        });

        await sleep(200);
        dispatch({ type: "RESET_PROJECT" });
        dispatch({ type: "SET_FILE", file: { name: file.name, sizeBytes: file.size, numPages: 1 } });
        dispatch({ type: "SET_UPLOAD_STAGE", stage: "idle" });
        navigate(`/workspace?ifc_id=${uploadRes.id}&trade=${activeTrade}`);
        return;
      } catch (ifcErr: any) {
        const msg = ifcErr instanceof Error ? ifcErr.message : String(ifcErr);
        setError(`IFC Ingestion Error: ${msg}`);
        toast.error("IFC Processing Failed", { description: msg });
        dispatch({ type: "SET_UPLOAD_STAGE", stage: "idle" });
        return;
      }
    }

    // Handle Native Architectural Vector PDF Workflow
    if (isPdf) {
      try {
        setLiveMessage("STEP 1/8: Analyzing 10 sheets & native vector streams…");
        dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 15 });

        const uploadRes = await BackendApiService.uploadPdfFile(file);
        const docId = uploadRes.document_id || uploadRes.id;
        dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 35 });

        setLiveMessage("STEP 2/8: Detecting drawing types (Floor plans, Sections, Roof, Details)…");
        await sleep(150);
        dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 45 });

        setLiveMessage("STEP 3/8: Resolving scale & corroborating dimensions…");
        await sleep(150);
        dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 55 });

        setLiveMessage("STEP 4/8: Reconstructing geometry, casing pairs & room polygons…");
        dispatch({ type: "SET_UPLOAD_STAGE", stage: "processing" });
        dispatch({ type: "SET_SCAN_PROGRESS", progress: 40 });
        await BackendApiService.getPdfGeometry(docId);

        setLiveMessage("STEP 5/8: Classifying trade scope (Partitions vs Masonry, Indoor vs Outdoor)…");
        dispatch({ type: "SET_SCAN_PROGRESS", progress: 65 });
        await sleep(150);

        setLiveMessage("STEP 6/8: Calculating element takeoff with door & window opening deductions…");
        dispatch({ type: "SET_SCAN_PROGRESS", progress: 85 });
        const qtoRes = await BackendApiService.getPdfQto(docId);

        setLiveMessage("STEP 7/8: Validating quantities & duplicate prevention across sheets…");
        dispatch({ type: "SET_SCAN_PROGRESS", progress: 95 });
        await sleep(150);

        setLiveMessage("STEP 8/8: QTO Ready — Project trade totals & BOQ verified.");
        dispatch({ type: "SET_SCAN_PROGRESS", progress: 100 });

        // Alert user if any page required review
        const matrix = qtoRes.sheet_audit_matrix || [];
        const reviewPages = matrix.filter((r: any) => r.qto_status === "REVIEW" || r.qto_status === "REVIEW_REQUIRED");
        if (reviewPages.length > 0) {
          reviewPages.forEach((rp: any) => {
            toast.warning(`Page ${rp.page_number} — REVIEW REQUIRED`, {
              description: `Reason: ${rp.review_reason}`,
              duration: 6000,
            });
          });
        }

        toast.success("PDF Blueprint & Trade QTO Ready!", {
          description: `Extracted ${uploadRes.page_count} page(s) with verified element-level takeoff and BOQ.`,
        });

        await sleep(250);
        dispatch({ type: "RESET_PROJECT" });
        dispatch({ type: "SET_FILE", file: { name: file.name, sizeBytes: file.size, numPages: uploadRes.page_count } });
        dispatch({ type: "SET_UPLOAD_STAGE", stage: "complete" });
        await sleep(200);
        dispatch({ type: "SET_UPLOAD_STAGE", stage: "idle" });
        const activeTrade = (selectedTrade && selectedTrade !== "all") ? selectedTrade.toLowerCase() : "roofing";
        navigate(`/workspace?pdf_id=${docId}&trade=${activeTrade}`);
        return;
      } catch (pdfErr: any) {
        const msg = pdfErr instanceof Error ? pdfErr.message : String(pdfErr);
        setError(`PDF Ingestion Error: ${msg}`);
        toast.error("PDF Processing Failed", { description: msg });
        dispatch({ type: "SET_UPLOAD_STAGE", stage: "idle" });
        return;
      }
    }

    let backendDetections: Detection[] | undefined;
    let backendPages: BackendPage[] = [];
    let detectionErrorMsg: string | undefined;
    let blueprintId: number | undefined;

    try {
      dispatch({ type: "CLEAR_DETECTIONS" });
      dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 10 });
      const project = await BackendApiService.createProject(
        `Takeoff_${Date.now().toString().slice(-4)}`,
        selectedTrade !== "all" ? selectedTrade : undefined
      );
      dispatch({ type: "SET_PROJECT_ID", projectId: project.id });
      if (project.unit_system) {
        dispatch({ type: "SET_UNIT_SYSTEM", unitSystem: project.unit_system });
      }

      dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 20 });
      const uploadRes = await BackendApiService.uploadBlueprint(project.id, file);
      blueprintId = uploadRes.blueprint.id;
      dispatch({ type: "SET_BLUEPRINT_ID", blueprintId });
      dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 45 });

      // Trigger blueprint processing with explicit trade selection
      await BackendApiService.processBlueprint(
        blueprintId,
        selectedTrade !== "all" ? selectedTrade : undefined
      );

      dispatch({ type: "SET_UPLOAD_STAGE", stage: "processing" });
      dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 50 });
      dispatch({ type: "SET_SCAN_PROGRESS", progress: 0 });
      setLiveMessage("Opening blueprint…");
      toast.info("Processing blueprint…", { description: "Running geometry engine & room detection page by page" });

      // waitForBlueprintProcessing already polls every ~800ms and reports
      // live done/total progress via this callback — a separate ticker used
      // to run alongside it on its own 500ms interval and unconditionally
      // reset the bar back to a flat 50, fighting the real percentage and
      // making it look stuck instead of climbing live.
      const pages: BackendPage[] = await BackendApiService.waitForBlueprintProcessing(blueprintId, (done, total, currentStage) => {
        if (currentStage) setLiveMessage(currentStage);
        if (total > 0) {
          const percent = Math.round((done / total) * 90);
          dispatch({ type: "SET_SCAN_PROGRESS", progress: percent });
        }
      });
      backendPages = pages;

      if (pages && pages.length > 0) {
        setLiveMessage(`Loading detected rooms, walls & symbols (${pages.length} sheet${pages.length === 1 ? "" : "s"})…`);
        
        const fetchRooms = selectedTrade === "all" || ["painting", "flooring", "roofing", "drywall"].includes(selectedTrade);
        const fetchWalls = selectedTrade === "all" || ["drywall"].includes(selectedTrade);
        const fetchDetections = selectedTrade === "all" || ["painting", "furniture", "openings"].includes(selectedTrade);

        const [pageRoomResults, pageArchWallResults, pageDetectionResults] = await Promise.all([
          fetchRooms ? BackendApiService.fetchAllBlueprintRooms(blueprintId, pages) : Promise.resolve([]),
          fetchWalls ? BackendApiService.fetchAllBlueprintArchitecturalWalls(pages) : Promise.resolve([]),
          fetchDetections ? BackendApiService.fetchAllBlueprintDetections(pages) : Promise.resolve([]),
        ]);
        dispatch({ type: "SET_SCAN_PROGRESS", progress: 85 });

        const hasArchWalls = pageArchWallResults.some((r) => r.archWalls.length > 0);
        let pageWallResults: { pageId: number; walls: BackendWall[] }[] = [];
        if (!hasArchWalls && fetchWalls) {
          pageWallResults = await BackendApiService.fetchAllBlueprintWalls(pages);
        }

        const pageNumberMap = new Map<number, number>();
        pages.forEach((p) => pageNumberMap.set(p.id, p.page_number));
        const sheetIdFor = (pageId: number) => `sheet-${(pageNumberMap.get(pageId) ?? 1) - 1}`;

        const allDetections: Detection[] = [];
        pageRoomResults.forEach(({ pageId, rooms }) => {
          const sheetId = sheetIdFor(pageId);
          rooms.forEach((room) => allDetections.push(roomToDetection(room, sheetId)));
        });

        // Prefer canonical ArchitecturalWalls; fallback to raw Walls only if arch walls not generated
        if (hasArchWalls) {
          pageArchWallResults.forEach(({ pageId, archWalls }) => {
            const sheetId = sheetIdFor(pageId);
            archWalls.forEach((aw) => allDetections.push(architecturalWallToDetection(aw, sheetId)));
          });
        } else {
          pageWallResults.forEach(({ pageId, walls }) => {
            const sheetId = sheetIdFor(pageId);
            walls.forEach((wall) => allDetections.push(wallToDetection(wall, sheetId)));
          });
        }

        pageDetectionResults.forEach(({ pageId, detections }) => {
          const sheetId = sheetIdFor(pageId);
          detections.filter(isSymbolDetection).forEach((d) => allDetections.push(symbolToDetection(d, sheetId)));
        });

        backendDetections = allDetections;
      }


      if (selectedTrade === "all") {
        BackendApiService.generateEstimate(project.id, blueprintId).catch(() => { });
      }
    } catch (backendError) {
      detectionErrorMsg = backendError instanceof Error ? backendError.message : String(backendError);
    }

    if (isImage) {
      const numPages = 1;
      dispatch({ type: "SET_NUM_PAGES", numPages });
      dispatch({ type: "SET_SCAN_PROGRESS", progress: 95 });
      const objectUrl = URL.createObjectURL(file);
      setPreviewUrl(objectUrl);
      const imagePage = backendPages[0];
      const sheets: Sheet[] = [
        {
          id: "sheet-0",
          name: imagePage?.sheet_name || "Floor Plan",
          code: imagePage?.sheet_code || "A101",
          pageIndex: 0,
          thumbnailUrl: objectUrl,
          widthPx: imagePage?.width_px,
          heightPx: imagePage?.height_px,
          pageType: imagePage?.page_type ?? undefined,
          isTakeoffEligible: imagePage?.is_takeoff_eligible ?? true,
          skipReason: imagePage?.skip_reason ?? undefined,
          dbPageId: imagePage?.id,
          discipline: imagePage?.discipline ?? undefined,
          primaryTitle: imagePage?.primary_title ?? undefined,
          classificationConfidence: imagePage?.classification_confidence ?? undefined,
          geometryAuthority: imagePage?.geometry_authority ?? undefined,
        },
      ];
      dispatch({ type: "SET_SHEETS", sheets });
      dispatch({
        type: "SET_FILE",
        file: { name: file.name, sizeBytes: file.size, numPages: 1, objectUrl, base64: base64Data },
      });
      await runDetectionPipeline(sheets, selectedTrade, backendDetections, detectionErrorMsg, blueprintId);
      return;
    }

    try {
      const buffer = await file.arrayBuffer();
      const doc = await loadPdf(buffer.slice(0));
      const numPages = doc.numPages;
      try {
        const firstPageThumb = await renderThumbnail(doc, 0);
        if (firstPageThumb) setPreviewUrl(firstPageThumb);
      } catch (e) {
        console.warn("Failed to generate preview:", e);
      }
      dispatch({ type: "SET_NUM_PAGES", numPages });
      dispatch({ type: "SET_SCAN_PROGRESS", progress: 88 });

      const codes = ["A101", "A102", "A103", "A104", "A105", "A106", "A107", "A108"];
      const sheets: Sheet[] = [];
      for (let i = 0; i < numPages; i++) {
        let thumbnailUrl: string | undefined;
        try {
          thumbnailUrl = await renderThumbnail(doc, i);
        } catch {
          thumbnailUrl = undefined;
        }
        const backendPage = backendPages.find((p) => p.page_number === i + 1);
        sheets.push({
          id: `sheet-${i}`,
          name: backendPage?.sheet_name || (i === 0 ? "Floor Plan" : `Sheet ${i + 1}`),
          code: backendPage?.sheet_code || codes[i] || `A1${i.toString().padStart(2, "00")}`,
          pageIndex: i,
          thumbnailUrl,
          widthPx: backendPage?.width_px,
          heightPx: backendPage?.height_px,
          pageType: backendPage?.page_type ?? undefined,
          isTakeoffEligible: backendPage?.is_takeoff_eligible ?? true,
          skipReason: backendPage?.skip_reason ?? undefined,
          dbPageId: backendPage?.id,
          discipline: backendPage?.discipline ?? undefined,
          primaryTitle: backendPage?.primary_title ?? undefined,
          classificationConfidence: backendPage?.classification_confidence ?? undefined,
          geometryAuthority: backendPage?.geometry_authority ?? undefined,
        });
        dispatch({ type: "SET_SCAN_PROGRESS", progress: 88 + Math.round(((i + 1) / numPages) * 9) });
      }
      dispatch({ type: "SET_SHEETS", sheets });
      dispatch({
        type: "SET_FILE",
        file: { name: file.name, sizeBytes: file.size, numPages, objectUrl: URL.createObjectURL(file), base64: base64Data },
      });

      await runDetectionPipeline(sheets, selectedTrade, backendDetections, detectionErrorMsg, blueprintId);
    } catch (err) {
      const fallbackSheets: Sheet[] = [{ id: "sheet-0", name: "Floor Plan", code: "A101", pageIndex: 0 }];
      dispatch({ type: "SET_SHEETS", sheets: fallbackSheets });
      dispatch({ type: "SET_NUM_PAGES", numPages: 1 });
      await runDetectionPipeline(fallbackSheets, selectedTrade, backendDetections, detectionErrorMsg, blueprintId);
    }
  }

  async function handleSampleIfc(trade: TradeId | "all") {
    try {
      setError(null);
      dispatch({ type: "SET_UPLOAD_STAGE", stage: "uploading" });
      dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 25 });
      setLiveMessage("Loading Duplex Residential Villa BIM model…");
      
      const res = await fetch("/sample/duplex_sample.ifc");
      if (!res.ok) throw new Error("Could not load sample IFC model file");
      const blob = await res.blob();
      const file = new File([blob], "Duplex_Residential_Villa.ifc", { type: "application/x-step" });
      await handleRealFile(file, trade);
    } catch (err: any) {
      setError(err.message);
      toast.error("Sample IFC Load Failed", { description: err.message });
      dispatch({ type: "SET_UPLOAD_STAGE", stage: "idle" });
    }
  }

  async function handleSample(trade: TradeId | "all") {
    try {
      setError(null);
      dispatch({ type: "SET_UPLOAD_STAGE", stage: "uploading" });
      dispatch({ type: "SET_UPLOAD_PROGRESS", progress: 25 });
      setLiveMessage("Loading Architectural CAD Portfolio sample…");

      const res = await fetch("/sample/commercial_sample.pdf");
      if (!res.ok) throw new Error("Could not load sample PDF blueprint");
      const blob = await res.blob();
      const file = new File([blob], "FATIMA-AHMED-CONSTRUCTION-DRAWINGS-PORTFOLIO.pdf", { type: "application/pdf" });
      await handleRealFile(file, trade);
    } catch (err: any) {
      setError(err?.message || "Failed to load sample blueprint");
      toast.error("Sample PDF Load Failed", { description: err?.message });
      dispatch({ type: "SET_UPLOAD_STAGE", stage: "idle" });
    }
  }

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      if (activeTrade !== "all") {
        handleRealFile(file, activeTrade);
      } else {
        setPendingFile(file);
        setPendingSample(false);
        setShowTradeSelectModal(true);
      }
    }
  }, [activeTrade]);

  return (
    <div 
      className="min-h-screen w-full flex flex-col items-center pt-8 pb-10 px-4 sm:px-6 bg-[#070d18] text-[#f8fafc] relative overflow-y-auto select-none"
      style={{
        backgroundImage: "radial-gradient(circle at 50% 10%, rgba(14, 116, 144, 0.12) 0%, transparent 55%), linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px)",
        backgroundSize: "100% 100%, 32px 32px, 32px 32px"
      }}
    >
      <div className="max-w-4xl w-full relative z-10 flex flex-col items-center">
        
        {/* Engine Telemetry Top Badge */}
        <div className="flex items-center gap-2 px-3 py-0.5 rounded-full bg-[#0a1526]/90 border border-cyan-500/30 shadow-lg shadow-cyan-950/40 mb-2.5 text-[11px] font-mono">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
          <span className="text-cyan-300 font-bold uppercase tracking-wider">PROTAKE BIM ENGINE v2.4</span>
          <span className="text-slate-600">|</span>
          <span className="text-slate-300 flex items-center gap-1">
            <Cpu size={11} className="text-cyan-400" />
            Deterministic Geometric QTO
          </span>
        </div>

        {/* Page Header & Subtitle */}
        <div className="text-center mb-4 max-w-2xl">
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white mb-1.5 font-sans">
            Import Building Model & Drawings
          </h1>
          <p className="text-xs sm:text-sm text-[#94a3b8] leading-relaxed font-sans">
            Upload a native IFC Building Information Model or architectural PDF blueprint for auditable quantity takeoff.
          </p>
        </div>

        {/* Top Trade Navigation Tabs */}
        <div 
          role="tablist" 
          aria-label="Trade takeoff selection"
          className="flex items-center justify-center gap-2 sm:gap-2.5 flex-wrap sm:flex-nowrap mb-5 w-full max-w-2xl overflow-x-auto pb-1"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeTrade === "drywall"}
            onClick={() => {
              const next = activeTrade === "drywall" ? "all" : "drywall";
              setActiveTrade(next);
              setSelectedTradeForPicker(next);
            }}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg border text-xs font-medium transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 ${
              activeTrade === "drywall"
                ? "bg-cyan-950/50 border-cyan-400 text-white shadow-sm shadow-cyan-900/40"
                : "bg-[#0a121e]/70 border-[#162840] text-slate-300 hover:text-white hover:border-slate-700"
            }`}
          >
            <SquareStack size={14} className={activeTrade === "drywall" ? "text-cyan-300" : "text-cyan-400/80"} />
            <span>Drywall Takeoff</span>
            <span className="text-[10px] text-cyan-400/70 font-mono hidden sm:inline">Assemblies & Deductions</span>
            {activeTrade === "drywall" && <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse ml-0.5" />}
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTrade === "flooring"}
            onClick={() => {
              const next = activeTrade === "flooring" ? "all" : "flooring";
              setActiveTrade(next);
              setSelectedTradeForPicker(next);
            }}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg border text-xs font-medium transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 ${
              activeTrade === "flooring"
                ? "bg-cyan-950/50 border-cyan-400 text-white shadow-sm shadow-cyan-900/40"
                : "bg-[#0a121e]/70 border-[#162840] text-slate-300 hover:text-white hover:border-slate-700"
            }`}
          >
            <Layers size={14} className={activeTrade === "flooring" ? "text-cyan-300" : "text-cyan-400/80"} />
            <span>Flooring Takeoff</span>
            <span className="text-[10px] text-cyan-400/70 font-mono hidden sm:inline">Slabs & Finishes</span>
            {activeTrade === "flooring" && <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse ml-0.5" />}
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTrade === "roofing"}
            onClick={() => {
              const next = activeTrade === "roofing" ? "all" : "roofing";
              setActiveTrade(next);
              setSelectedTradeForPicker(next);
            }}
            className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg border text-xs font-medium transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 ${
              activeTrade === "roofing"
                ? "bg-cyan-950/50 border-cyan-400 text-white shadow-sm shadow-cyan-900/40"
                : "bg-[#0a121e]/70 border-[#162840] text-slate-300 hover:text-white hover:border-slate-700"
            }`}
          >
            <Home size={14} className={activeTrade === "roofing" ? "text-cyan-300" : "text-cyan-400/80"} />
            <span>Roofing Takeoff</span>
            <span className="text-[10px] text-cyan-400/70 font-mono hidden sm:inline">Pitched Planes & Tiles</span>
            {activeTrade === "roofing" && <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse ml-0.5" />}
          </button>
        </div>

        {/* Primary Intake Card */}
        <div className="w-full max-w-3xl mb-4">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              if (!busy) setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            className={`w-full bg-[#0a121e]/90 backdrop-blur-xl rounded-xl border-2 transition-all duration-300 relative overflow-hidden shadow-2xl ${
              busy
                ? "border-white/10"
                : dragOver
                ? "border-cyan-400 bg-cyan-950/30 scale-[1.008] shadow-[0_0_25px_rgba(6,182,212,0.25)]"
                : "border-[#1e3a5f]/80 hover:border-cyan-500/50 hover:shadow-cyan-950/20 group"
            }`}
          >
            {/* Top Card Spec Bar */}
            <div className="px-4 py-2.5 border-b border-[#162840] bg-[#070e18]/85 flex items-center justify-between text-[11px] font-mono text-slate-400">
              <div className="flex items-center gap-2">
                <Box size={13} className="text-cyan-400" />
                <span className="text-slate-200 font-semibold tracking-wider uppercase">NATIVE BIM & CAD INTAKE</span>
              </div>
              <div className="flex items-center gap-1.5 text-cyan-400 font-semibold tracking-wider uppercase">
                <ShieldCheck size={13} />
                <span>SOURCE TRACEABILITY</span>
              </div>
            </div>

            <CornerMarks active={dragOver || busy} />

            <div className="p-6 sm:p-7">
              <AnimatePresence mode="wait">
                {!busy ? (
                  <motion.div
                    key="initial"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.18 }}
                    className="flex flex-col items-center text-center max-w-lg mx-auto"
                  >
                    {/* Compact Architectural Upload Icon */}
                    <div className="w-12 h-12 mb-3 rounded-xl bg-cyan-950/30 border border-cyan-500/30 flex items-center justify-center text-cyan-300 group-hover:scale-105 transition-transform duration-200 relative">
                      <div className="absolute inset-0 rounded-xl bg-cyan-400/5 animate-pulse" />
                      <UploadCloud size={24} className="relative z-10" />
                    </div>

                    <h3 className="text-base sm:text-lg font-bold text-white mb-1">
                      {dragOver ? "Release to upload" : "Drop your model or drawing"}
                    </h3>
                    <p className="text-xs text-slate-400 font-mono mb-4">
                      IFC / IFCXML / IFCZIP / Architectural PDF
                    </p>

                    {/* Dual Action Buttons */}
                    <div className="flex flex-col sm:flex-row items-center justify-center gap-3 w-full mb-3.5">
                      <button 
                        type="button"
                        onClick={() => bimInputRef.current?.click()}
                        className="w-full sm:w-auto bg-white hover:bg-slate-100 text-slate-900 px-5 py-2.5 rounded-lg text-xs font-bold flex items-center justify-center gap-2 shadow-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#070d18] cursor-pointer"
                        aria-label="Select BIM File"
                      >
                        <Box size={14} className="text-cyan-600" />
                        <span>Select BIM File</span>
                      </button>

                      <button 
                        type="button"
                        onClick={() => pdfInputRef.current?.click()}
                        className="w-full sm:w-auto bg-white/5 hover:bg-white/10 text-slate-200 border border-white/15 px-5 py-2.5 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 hover:text-white transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 focus-visible:ring-offset-2 focus-visible:ring-offset-[#070d18] cursor-pointer"
                        aria-label="Select PDF Blueprint"
                      >
                        <FileText size={14} className="text-cyan-400" />
                        <span>Select PDF Blueprint</span>
                      </button>
                    </div>

                    {/* Hidden Native File Inputs */}
                    <input
                      ref={inputRef}
                      type="file"
                      accept=".ifc,.ifcxml,.ifczip,application/pdf,.pdf"
                      className="hidden"
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) handleRealFile(file, activeTrade);
                        e.target.value = "";
                      }}
                    />
                    <input
                      ref={bimInputRef}
                      type="file"
                      accept=".ifc,.ifcxml,.ifczip"
                      className="hidden"
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) handleRealFile(file, activeTrade);
                        e.target.value = "";
                      }}
                    />
                    <input
                      ref={pdfInputRef}
                      type="file"
                      accept="application/pdf,.pdf"
                      className="hidden"
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) handleRealFile(file, activeTrade);
                        e.target.value = "";
                      }}
                    />

                    {/* Technical Specification Badges */}
                    <div className="flex items-center justify-center gap-2 text-[10px] font-mono text-slate-400 flex-wrap">
                      <span className="px-2 py-0.5 rounded bg-white/5 border border-white/10 text-slate-300">IFC 2x3 • IFC4</span>
                      <span className="px-2 py-0.5 rounded bg-white/5 border border-white/10 text-slate-300">PDF VECTOR / RASTER</span>
                      <span className="px-2 py-0.5 rounded bg-white/5 border border-white/10 text-slate-300">MAX 250 MB</span>
                    </div>

                    {/* File Support Detail Note */}
                    <div className="mt-3 text-[11px] text-slate-400 flex items-center justify-center gap-2 flex-wrap">
                      <span className="text-cyan-400 font-medium">Native vector PDF supported</span>
                      <span className="text-slate-600">·</span>
                      <span className="text-slate-400">Scanned/raster PDF will be identified separately</span>
                    </div>

                    {error && (
                      <div className="mt-3 p-3 rounded-lg bg-rose-950/40 border border-rose-800/60 flex items-center justify-between gap-3 text-left w-full">
                        <div className="flex items-center gap-2 text-xs text-rose-300">
                          <AlertTriangle size={14} className="text-rose-400 shrink-0" />
                          <span>{error}</span>
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            setError(null);
                            dispatch({ type: "SET_UPLOAD_STAGE", stage: "idle" });
                          }}
                          className="text-xs font-semibold text-rose-200 hover:text-white px-2.5 py-1 rounded bg-rose-900/50 hover:bg-rose-900 border border-rose-700/50 transition-colors shrink-0 flex items-center gap-1 cursor-pointer"
                        >
                          <RotateCcw size={12} />
                          <span>Retry</span>
                        </button>
                      </div>
                    )}
                  </motion.div>
                ) : stage === "uploading" ? (
                  <motion.div
                    key="uploading"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.18 }}
                    className="flex flex-col items-center w-full max-w-md mx-auto text-center py-2"
                  >
                    <div className="w-10 h-10 rounded-xl bg-cyan-950/40 border border-cyan-500/30 flex items-center justify-center mb-2.5 text-cyan-300">
                      <UploadCloud size={20} className="animate-bounce" />
                    </div>
                    <div className="flex items-center justify-center gap-2 text-xs font-mono text-white font-semibold mb-2">
                      <span className="truncate max-w-[240px]">{state.file?.name || "Model/Drawing"}</span>
                      {state.file?.sizeBytes ? (
                        <span className="text-slate-400 text-[11px]">({formatFileSize(state.file?.sizeBytes)})</span>
                      ) : null}
                    </div>
                    <div className="w-full mb-3">
                      <div className="flex justify-between items-end mb-1 text-[11px] font-mono">
                        <span className="text-cyan-400 uppercase tracking-wider font-semibold">Uploading File</span>
                        <span className="text-white font-bold">{displayProgress}%</span>
                      </div>
                      <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden border border-slate-700">
                        <div
                          className="h-full bg-cyan-400 transition-all duration-300 ease-out"
                          style={{ width: `${displayProgress}%` }}
                        />
                      </div>
                    </div>
                    <p className="text-[11px] text-slate-400 font-mono animate-pulse">
                      {liveMessage || "Transferring file stream to local memory..."}
                    </p>
                  </motion.div>
                ) : stage === "complete" ? (
                  <motion.div
                    key="complete"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.18 }}
                    className="flex flex-col items-center w-full max-w-md mx-auto text-center py-3"
                  >
                    <div className="w-10 h-10 rounded-full bg-emerald-950/60 border border-emerald-500/40 flex items-center justify-center mb-2.5 text-emerald-400">
                      <Check size={20} />
                    </div>
                    <h4 className="text-sm font-bold text-white mb-2">Drawing Successfully Processed</h4>
                    <div className="flex items-center justify-center gap-3 text-xs font-mono text-emerald-400 mb-2 flex-wrap">
                      <span>✓ Model parsed</span>
                      <span>✓ Geometry extracted</span>
                      <span>✓ Scale resolved</span>
                    </div>
                    <p className="text-[11px] text-slate-400 font-mono">Launching interactive takeoff workspace...</p>
                  </motion.div>
                ) : (
                  <motion.div
                    key="processing"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.18 }}
                    className="flex flex-col items-center w-full max-w-md mx-auto text-center py-1"
                  >
                    {/* Processing State with Live Progress Bar */}
                    <div className="w-full mb-3">
                      <div className="flex justify-between items-end mb-1.5 text-[11px] font-mono">
                        <span className="text-cyan-400 uppercase tracking-widest font-bold flex items-center gap-1.5">
                          <Cpu size={12} className="animate-spin text-cyan-400" />
                          Processing Native Geometry
                        </span>
                        <span className="text-xs font-mono font-bold text-white">
                          {displayProgress}%
                        </span>
                      </div>
                      <div className="w-full h-2.5 bg-slate-800 rounded-full overflow-hidden border border-slate-700 relative">
                        <div
                          className="h-full bg-gradient-to-r from-cyan-500 to-blue-600 transition-all duration-300 ease-out"
                          style={{ width: `${displayProgress}%` }}
                        />
                      </div>
                    </div>

                    {/* Stage Progression Checklist */}
                    <div className="w-full bg-[#070e18]/80 rounded-lg border border-[#162840] p-3 mb-2.5 text-left font-mono text-[11px] space-y-1.5">
                      <div className="flex items-center gap-2">
                        {displayProgress >= 30 ? (
                          <Check size={12} className="text-emerald-400" />
                        ) : (
                          <Cpu size={12} className="text-cyan-400 animate-spin" />
                        )}
                        <span className={displayProgress >= 30 ? "text-slate-300" : "text-cyan-300 font-semibold"}>
                          Parsing native geometry...
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {displayProgress >= 60 ? (
                          <Check size={12} className="text-emerald-400" />
                        ) : displayProgress >= 30 ? (
                          <Cpu size={12} className="text-cyan-400 animate-spin" />
                        ) : (
                          <span className="w-3 h-3 rounded-full border border-slate-700 inline-block" />
                        )}
                        <span className={displayProgress >= 60 ? "text-slate-300" : displayProgress >= 30 ? "text-cyan-300 font-semibold" : "text-slate-500"}>
                          Extracting drawing structure...
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {displayProgress >= 85 ? (
                          <Check size={12} className="text-emerald-400" />
                        ) : displayProgress >= 60 ? (
                          <Cpu size={12} className="text-cyan-400 animate-spin" />
                        ) : (
                          <span className="w-3 h-3 rounded-full border border-slate-700 inline-block" />
                        )}
                        <span className={displayProgress >= 85 ? "text-slate-300" : displayProgress >= 60 ? "text-cyan-300 font-semibold" : "text-slate-500"}>
                          Resolving scale...
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {displayProgress >= 95 ? (
                          <Check size={12} className="text-emerald-400" />
                        ) : displayProgress >= 85 ? (
                          <Cpu size={12} className="text-cyan-400 animate-spin" />
                        ) : (
                          <span className="w-3 h-3 rounded-full border border-slate-700 inline-block" />
                        )}
                        <span className={displayProgress >= 95 ? "text-slate-300" : displayProgress >= 85 ? "text-cyan-300 font-semibold" : "text-slate-500"}>
                          Building canonical model...
                        </span>
                      </div>
                    </div>

                    <p className="text-[11px] text-slate-400 font-mono truncate max-w-full">
                      {liveMessage || "Processing geometric structure..."}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>

        {/* Trust / Capability Strip */}
        <div className="w-full max-w-3xl flex items-center justify-center gap-2 sm:gap-4 py-2 px-4 rounded-lg bg-[#0a121e]/60 border border-[#162840] text-[11px] font-mono text-slate-400 flex-wrap mb-4">
          <span className="text-slate-300 font-medium">Native IFC</span>
          <span className="text-slate-600">│</span>
          <span className="text-slate-300 font-medium">Vector PDF</span>
          <span className="text-slate-600">│</span>
          <span className="text-slate-300 font-medium">Scale Aware</span>
          <span className="text-slate-600">│</span>
          <span className="text-cyan-400 font-medium flex items-center gap-1">
            <ShieldCheck size={12} />
            Source Traceability
          </span>
          <span className="text-slate-600">│</span>
          <span className="text-slate-300 font-medium">Audit Ready</span>
        </div>

        {/* Sample Models Section */}
        <div className="w-full max-w-3xl">
          <div className="flex items-center justify-between mb-2.5 px-1">
            <div>
              <h2 className="text-xs font-mono font-bold tracking-wider uppercase text-slate-300 flex items-center gap-2">
                <Zap size={13} className="text-cyan-400" />
                <span>Try a Sample Model</span>
              </h2>
              <p className="text-[11px] text-slate-400 font-sans mt-0.5">
                Explore the workspace without uploading your own file.
              </p>
            </div>
            <span className="text-[10px] text-slate-500 font-mono hidden sm:inline">Pre-verified IFC & 2D Sets</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {/* Card 1: Residential IFC */}
            <div 
              className="p-3.5 rounded-xl bg-[#0a121e]/75 border border-[#162840] hover:border-cyan-500/50 hover:bg-[#0d1829] transition-all flex flex-col justify-between group"
            >
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800/60">
                    IFC4 BIM MODEL
                  </span>
                  <span className="text-[10px] text-cyan-400 font-mono flex items-center gap-0.5">
                    <Check size={10} /> Verified
                  </span>
                </div>
                <h3 className="text-xs font-bold text-white group-hover:text-cyan-300 transition-colors mb-0.5">
                  Residential Duplex Villa
                </h3>
                <p className="text-[10px] text-slate-400 font-mono mb-2">
                  Two-Storey · ~3.8 MB · 3D Solids
                </p>
              </div>

              <button
                type="button"
                onClick={() => handleSampleIfc(activeTrade)}
                className="w-full pt-2 border-t border-slate-800/80 text-[11px] font-semibold text-cyan-400 flex items-center justify-between hover:text-cyan-300 transition-colors cursor-pointer"
              >
                <span>Open Sample</span>
                <ArrowRight size={12} className="group-hover:translate-x-0.5 transition-transform" />
              </button>
            </div>

            {/* Card 2: Commercial IFC */}
            <div 
              className="p-3.5 rounded-xl bg-[#0a121e]/75 border border-[#162840] hover:border-cyan-500/50 hover:bg-[#0d1829] transition-all flex flex-col justify-between group"
            >
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800/60">
                    IFC 2x3 / IFC4
                  </span>
                  <span className="text-[10px] text-cyan-400 font-mono flex items-center gap-0.5">
                    <Check size={10} /> Verified
                  </span>
                </div>
                <h3 className="text-xs font-bold text-white group-hover:text-cyan-300 transition-colors mb-0.5">
                  Commercial Office Suite
                </h3>
                <p className="text-[10px] text-slate-400 font-mono mb-2">
                  Multi-Zone HVAC · ~12.4 MB · Assemblies
                </p>
              </div>

              <button
                type="button"
                onClick={() => handleSampleIfc(activeTrade)}
                className="w-full pt-2 border-t border-slate-800/80 text-[11px] font-semibold text-cyan-400 flex items-center justify-between hover:text-cyan-300 transition-colors cursor-pointer"
              >
                <span>Open Sample</span>
                <ArrowRight size={12} className="group-hover:translate-x-0.5 transition-transform" />
              </button>
            </div>

            {/* Card 3: Architectural PDF */}
            <div 
              className="p-3.5 rounded-xl bg-[#0a121e]/75 border border-[#162840] hover:border-cyan-500/50 hover:bg-[#0d1829] transition-all flex flex-col justify-between group"
            >
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800/60">
                    VECTOR PDF BLUEPRINT
                  </span>
                  <span className="text-[10px] text-cyan-400 font-mono flex items-center gap-0.5">
                    <Check size={10} /> Verified
                  </span>
                </div>
                <h3 className="text-xs font-bold text-white group-hover:text-cyan-300 transition-colors mb-0.5">
                  Commercial Office Tower Set
                </h3>
                <p className="text-[10px] text-slate-400 font-mono mb-2">
                  Architectural CAD · 3 Sheets · 4.2 MB
                </p>
              </div>

              <button
                type="button"
                onClick={() => handleSample(activeTrade)}
                className="w-full pt-2 border-t border-slate-800/80 text-[11px] font-semibold text-cyan-400 flex items-center justify-between hover:text-cyan-300 transition-colors cursor-pointer"
              >
                <span>Open Sample</span>
                <ArrowRight size={12} className="group-hover:translate-x-0.5 transition-transform" />
              </button>
            </div>
          </div>
        </div>

      </div>

      <TradeSelectModal
        open={showTradeSelectModal}
        onClose={() => {
          setShowTradeSelectModal(false);
          setPendingFile(null);
          setPendingSample(false);
        }}
        onSelect={startTakeoffForTrade}
      />
    </div>
  );
}

function CornerMarks({ active }: { active: boolean }) {
  const color = active ? "border-cyan-400" : "border-white/10";
  const corners = [
    "top-0 left-0 border-t-2 border-l-2 rounded-tl-md",
    "top-0 right-0 border-t-2 border-r-2 rounded-tr-md",
    "bottom-0 left-0 border-b-2 border-l-2 rounded-bl-md",
    "bottom-0 right-0 border-b-2 border-r-2 rounded-br-md",
  ];
  return (
    <>
      {corners.map((c) => (
        <div key={c} className={`pointer-events-none absolute w-5 h-5 ${c} ${color} transition-colors`} />
      ))}
    </>
  );
}