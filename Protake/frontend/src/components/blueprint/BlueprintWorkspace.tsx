import { useEffect, useLayoutEffect, useMemo, useRef, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { Stage, Layer, Rect } from "react-konva";
import type Konva from "konva";
import { Check, X as XIcon } from "lucide-react";
import { toast } from "sonner";
import { useApp } from "@/state/AppContext";
import { DEFAULT_SCALE, snapValue, linearLength, polygonArea, polygonPerimeter, centroid } from "@/lib/geometry";
import { BackendApiService } from "@/api/backendApi";
import { loadPdf, type PDFDocumentProxy } from "@/lib/pdf";
import type { Point, Measurement } from "@/types";
import PdfPageLayer from "./PdfPageLayer";
import ImagePageLayer from "./ImagePageLayer";
import { stageSizeForPage } from "./stageSize";
import SampleBlueprintArt from "./SampleBlueprintArt";
import GridLayer from "./GridLayer";
import EngineeringCanvasLayer from "./EngineeringCanvasLayer";
import MeasurementsLayer from "./MeasurementsLayer";
import CalloutLayer from "./CalloutLayer";
import ScanOverlay from "./ScanOverlay";
import ToolsDock from "./ToolsDock";
import HUD from "./HUD";
import MiniMap from "./MiniMap";
import CalibrationModal from "./CalibrationModal";
import PromptModal from "@/components/common/PromptModal";
import WallCanvasLegend from "./WallCanvasLegend";
import WallInspectionOverlay from "./WallInspectionOverlay";


let countSeq = 0;

export default function BlueprintWorkspace() {
  const { state, dispatch, currentUserName } = useApp();
  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<Konva.Stage>(null);
  const [size, setSize] = useState({ width: 800, height: 600 });
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [cursor, setCursor] = useState<Point | null>(null);
  const [draft, setDraft] = useState<Point[]>([]);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [pendingCalibration, setPendingCalibration] = useState<Point[] | null>(null);
  const [activePrompt, setActivePrompt] = useState<{
    type: "callout" | "sticky-note";
    point: Point;
    title: string;
    description: string;
    defaultValue: string;
  } | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isPrintingDrawings, setIsPrintingDrawings] = useState(false);
  const [isEditingNode, setIsEditingNode] = useState(false);
  const [layerOpacity, setLayerOpacity] = useState(75);
  const [legendOpen, setLegendOpen] = useState(true);

  // Engineering canvas quality-badge display toggle (no UI trigger yet;
  // defaults off). engineeringPrecision/qualityThreshold were only ever
  // consumed by the dead EngineeringCanvasControls panel and were removed
  // with it.
  const [showPrecisionData] = useState(false);

  useEffect(() => {
    function handleFullscreenChange() {
      setIsFullscreen(!!document.fullscreenElement);
    }
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
    };
  }, []);

  const toggleFullscreen = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    if (!document.fullscreenElement) {
      el.requestFullscreen().catch((err) => {
        toast.error(`Failed to enter full screen: ${err?.message || "Unknown error"}`);
      });
    } else {
      document.exitFullscreen();
    }
  }, []);

  const activeSheet = state.sheets.find((s) => s.id === state.activeSheetId);
  const isSample = !!state.file?.isSample;
  const scale = state.calibration[state.activeSheetId ?? ""] ?? DEFAULT_SCALE;

  // pdf.js throws InvalidPDFException on a raster upload, so an image
  // blueprint never produces a PDFDocumentProxy and has to be drawn
  // straight from its object URL instead.
  const isRasterUpload =
    !isSample && !!state.file && /\.(png|jpe?g|webp|tiff?)$/i.test(state.file.name);

  // The drawing surface adopts the page's aspect ratio; detections are
  // normalized against the rasterized page, so a fixed 16:10 box stretched
  // every polygon (a square sheet came out 1.6x wider than tall).
  const stageSize = useMemo(
    () => stageSizeForPage(activeSheet?.widthPx, activeSheet?.heightPx),
    [activeSheet?.widthPx, activeSheet?.heightPx]
  );
  const stageW = stageSize.width;
  const stageH = stageSize.height;

  // Measure synchronously before paint so the stage is correctly sized on
  // first render (don't rely solely on ResizeObserver's async callback,
  // whose delivery is tied to the rendering/compositing pipeline and can
  // be delayed in some embedding contexts).
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setSize({ width: rect.width, height: rect.height });
  }, []);

  // keep the stage sized to its container on resize
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setSize({ width, height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // center canvas initially
  useEffect(() => {
    setPan({
      x: (size.width - stageW * state.zoom) / 2,
      y: (size.height - stageH * state.zoom) / 2,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size.width, size.height]);

  // Auto-pan to center selected detection/room
  useEffect(() => {
    if (!state.selectedDetectionId) return;
    const selected = state.detections.find((d) => d.id === state.selectedDetectionId);
    if (!selected || selected.points.length === 0) return;

    const c = centroid(selected.points);
    setPan({
      x: size.width / 2 - c.x * stageW * state.zoom,
      y: size.height / 2 - c.y * stageH * state.zoom,
    });
  }, [state.selectedDetectionId, state.zoom, stageW, stageH, size.width, size.height, state.detections]);

  // load real pdf
  useEffect(() => {
    if (!state.file || isSample || isRasterUpload || !state.file.objectUrl) {
      setPdfDoc(null);
      return;
    }
    let cancelled = false;
    loadPdf(state.file.objectUrl)
      .then((doc) => {
        if (!cancelled) setPdfDoc(doc);
      })
      // Without this the rejection escaped as an uncaught promise error in
      // the console (InvalidPDFException) and left pdfDoc stuck at null.
      .catch((err) => {
        if (!cancelled) {
          console.warn("[Protake] Could not open file as PDF:", err?.message ?? err);
          setPdfDoc(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [state.file, isSample, isRasterUpload]);

  // clear draft when tool or sheet changes
  useEffect(() => {
    setDraft([]);
  }, [state.activeTool, state.activeSheetId]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setDraft([]);
      if (e.key === "Enter") finishDraft();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, state.activeTool, state.activeSheetId, scale]);

  function normalizedPointer(stage: Konva.Stage): Point | null {
    const pointer = stage.getPointerPosition();
    if (!pointer) return null;
    const transform = stage.getAbsoluteTransform().copy().invert();
    const pos = transform.point(pointer);
    return {
      x: snapValue(pos.x / stageW, state.snapEnabled),
      y: snapValue(pos.y / stageH, state.snapEnabled),
    };
  }

  function finishDraft() {
    const tool = state.activeTool;

    if (tool === "linear") {
      if (draft.length < 2) {
        toast.info("Add at least 2 points to finish a linear measurement");
        return;
      }
      const lenFt = Math.round(linearLength(draft) * scale);
      pushMeasurement({ tool: "linear", points: draft, label: "Linear", valueLabel: `${lenFt.toLocaleString()} ft` });
    } else if (tool === "area" || tool === "polygon") {
      if (draft.length < 3) {
        toast.info(`Add at least 3 points to finish ${tool === "area" ? "an area" : "a polygon"} measurement`);
        return;
      }
      const areaFt = Math.round(polygonArea(draft) * scale * scale);
      pushMeasurement({ tool, points: draft, label: tool === "area" ? "Area" : "Polygon", valueLabel: `${areaFt.toLocaleString()} sq ft` });
    } else if (tool === "calibrate") {
      if (draft.length < 2) {
        toast.info("Click two points along a known dimension first");
        return;
      }
      setPendingCalibration(draft);
      setDraft([]);
      return;
    } else {
      return;
    }
    setDraft([]);
  }

  function confirmCalibration(feet: number) {
    if (!pendingCalibration) return;
    const normLen = linearLength(pendingCalibration);
    const pxPerFt = feet / normLen;
    const sheetId = state.activeSheetId ?? "";
    dispatch({ type: "SET_CALIBRATION", sheetId, pxPerFt });

    // Persist scale calibration to Backend API if active project exists
    try {
      const pageId = parseInt(sheetId.replace(/\D/g, ""), 10) || 1;
      BackendApiService.processBlueprint(pageId).catch(() => { });
    } catch {
      // client fallback handles local state
    }

    toast.success("Scale calibrated & synced", { description: `${feet} ft mapped to drawn reference line (${Math.round(pxPerFt)} px/ft)` });
    dispatch({ type: "SET_TOOL", tool: "select" });
    setPendingCalibration(null);
  }

  function pushMeasurement(partial: Omit<Measurement, "id" | "sheetId" | "createdAt">) {
    if (!state.activeSheetId) return;
    dispatch({
      type: "ADD_MEASUREMENT",
      measurement: {
        id: `meas-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        sheetId: state.activeSheetId,
        createdAt: Date.now(),
        ...partial,
      },
    });
    toast.success(`${partial.label} measurement added`, { description: partial.valueLabel });
  }

  function handleStageClick(e: Konva.KonvaEventObject<MouseEvent>) {
    const stage = stageRef.current;
    if (!stage) return;
    const tool = state.activeTool;

    if (tool === "select") {
      if (e.target === stage) dispatch({ type: "SELECT_DETECTION", id: null });
      return;
    }
    if (tool === "pan") return;

    const p = normalizedPointer(stage);
    if (!p) return;

    if (tool === "magic-fill") {
      // Manual rectangle area entry: click one corner, then the opposite
      // corner. Area/perimeter are computed from the two real clicked
      // points and the sheet's calibrated scale — never randomized. The
      // detection is created as "pending" (not "approved") since it's a
      // user-drawn estimate, not an AI detection, and must go through the
      // same review flow before it counts toward QTO.
      if (draft.length === 0) {
        setDraft([p]);
        toast.info("Click the opposite corner to finish the area");
        return;
      }
      const start = draft[0];
      const rectPoints: Point[] = [
        { x: Math.min(start.x, p.x), y: Math.min(start.y, p.y) },
        { x: Math.max(start.x, p.x), y: Math.min(start.y, p.y) },
        { x: Math.max(start.x, p.x), y: Math.max(start.y, p.y) },
        { x: Math.min(start.x, p.x), y: Math.max(start.y, p.y) },
      ];
      const areaSqFt = Math.round(polygonArea(rectPoints) * scale * scale);
      const perimeterFt = Math.round(polygonPerimeter(rectPoints) * scale);
      setDraft([]);
      if (areaSqFt <= 0) {
        toast.info("Draw a larger rectangle to create an area");
        return;
      }
      dispatch({
        type: "FINISH_SCAN",
        detections: [
          {
            id: `manual-area-${Date.now()}`,
            sheetId: state.activeSheetId ?? "",
            kind: "room",
            name: `Manual Area ${state.detections.length + 1}`,
            trade: "flooring",
            points: rectPoints,
            areaSqFt,
            perimeterFt,
            confidence: 1,
            status: "pending",
            evidence: {
              source: "manual_entry",
              note: "User-drawn rectangle. Area and perimeter computed from the two drawn corners and the sheet's calibrated scale.",
            },
          },
        ],
      });
      toast.success("Manual area added", { description: `${areaSqFt.toLocaleString()} sq ft — pending review` });
      return;
    }

    if (tool === "callout") {
      setActivePrompt({
        type: "callout",
        point: p,
        title: "Add Callout Note",
        description: "Enter Callout / Review Note text:",
        defaultValue: "Check dimension specifications",
      });
      return;
    }

    if (tool === "sticky-note") {
      setActivePrompt({
        type: "sticky-note",
        point: p,
        title: "Add Sticky Note",
        description: "Enter Sticky Note text:",
        defaultValue: "Review drywall specifications",
      });
      return;
    }

    if (tool === "count") {
      countSeq += 1;
      pushMeasurement({ tool: "count", points: [p], label: "Count", valueLabel: `#${countSeq}` });
      return;
    }

    setDraft((d) => [...d, p]);
  }

  function handleDblClick() {
    if (["area", "polygon", "linear"].includes(state.activeTool)) finishDraft();
  }

  function handleMouseMove() {
    const stage = stageRef.current;
    if (!stage) return;
    setCursor(normalizedPointer(stage));
  }

  function handleWheel(e: Konva.KonvaEventObject<WheelEvent>) {
    e.evt.preventDefault();
    const stage = stageRef.current;
    if (!stage) return;
    const pointer = stage.getPointerPosition();
    if (!pointer) return;

    const oldScale = state.zoom;
    // Point under the cursor, in un-scaled stage coordinates — held fixed
    // across the zoom so the drawing doesn't drift out from under the mouse.
    const pointTo = {
      x: (pointer.x - pan.x) / oldScale,
      y: (pointer.y - pan.y) / oldScale,
    };

    // Multiplicative zoom for smoother feel — 10% per wheel tick
    const zoomFactor = e.evt.deltaY > 0 ? 0.9 : 1.1;
    const newScale = Math.min(8, Math.max(0.1, oldScale * zoomFactor));

    dispatch({ type: "SET_ZOOM", zoom: newScale });
    setPan({
      x: pointer.x - pointTo.x * newScale,
      y: pointer.y - pointTo.y * newScale,
    });
  }

  /** Zoom to an exact preset (Fit / 50% / 100% / 200% / 400%), keeping the stage centered. */
  function zoomToPreset(newScale: number) {
    const clamped = Math.min(8, Math.max(0.1, newScale));
    dispatch({ type: "SET_ZOOM", zoom: clamped });
    setPan({
      x: (size.width - stageW * clamped) / 2,
      y: (size.height - stageH * clamped) / 2,
    });
  }

  function zoomToFit() {
    const fitScale = Math.min(size.width / stageW, size.height / stageH) * 0.95;
    zoomToPreset(fitScale);
  }

  const selectedDetection = state.detections.find((d) => d.id === state.selectedDetectionId);
  const sheetDetections = state.detections.filter((d) => d.sheetId === state.activeSheetId);
  const sheetMeasurements = state.measurements.filter((m) => m.sheetId === state.activeSheetId);

  const architecturalWallsFetched = sheetDetections.filter((d) => d.id.startsWith("backend-archwall-")).length;
  const legacyWallsFetched = sheetDetections.filter((d) => d.id.startsWith("backend-wall-")).length;
  const activeTradeId = (state.summaryTab === "drywall" || state.summaryTab === "painting" || state.summaryTab === "flooring" || state.summaryTab === "roofing" || state.summaryTab === "furniture" || state.summaryTab === "openings") ? state.summaryTab : null;
  const isRcp = activeSheet?.pageType === "rcp" || (activeSheet as any)?.page_type === "rcp" || activeSheet?.pageType === "reflected_ceiling_plan";
  const canonicalWallsRendered = (activeTradeId === "drywall" && isRcp) ? 0 : sheetDetections.filter((d) => d.kind === "wall" && d.id.startsWith("backend-archwall-") && d.status !== "rejected").length;
  const rawCandidatesRendered = 0; // Strictly filtered out for drywall takeoff
  const rejectedRendered = 0; // Strictly filtered out





  const cardPos = selectedDetection
    ? (() => {
      const c = centroid(selectedDetection.points);
      return { x: pan.x + c.x * stageW * state.zoom, y: pan.y + c.y * stageH * state.zoom };
    })()
    : null;

  const exportDrawing = useCallback(() => {
    setIsPrintingDrawings(true);
    toast.info("Preparing print preview for all sheets...", {
      description: "Generating canvas renders. Please wait..."
    });

    setTimeout(() => {
      document.body.classList.add("print-drawings-mode");
      window.print();
      document.body.classList.remove("print-drawings-mode");
      setIsPrintingDrawings(false);
    }, 1500);
  }, []);

  return (
    <div className="flex-1 flex min-h-0 min-w-0 bg-[var(--color-bg)]">
      <div className="flex-1 flex flex-col min-h-0 min-w-0">
        <div ref={containerRef} className="relative flex-1 min-w-0 blueprint-grid overflow-hidden">
          {/* Verification Debug Overlay HUD */}
          <div className="absolute top-3 left-3 z-30 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-black/80 backdrop-blur-md border border-slate-700 text-[11px] font-mono text-slate-300 shadow-xl pointer-events-none">
            <span className="text-emerald-400 font-semibold">Drywall Layer Debug:</span>
            <span>archFetched: <strong className="text-white">{architecturalWallsFetched}</strong></span>
            <span className="text-slate-500">|</span>
            <span>legacyFetched: <strong className="text-white">{legacyWallsFetched}</strong></span>
            <span className="text-slate-500">|</span>
            <span>canonicalRendered: <strong className="text-emerald-300">{canonicalWallsRendered}</strong></span>
            <span className="text-slate-500">|</span>
            <span>rawRendered: <strong className="text-amber-400">{rawCandidatesRendered}</strong></span>
            <span className="text-slate-500">|</span>
            <span>rejectedRendered: <strong className="text-rose-400">{rejectedRendered}</strong></span>
          </div>
          <Stage
            ref={stageRef}
            width={size.width}
            height={size.height}
            scaleX={state.zoom}
            scaleY={state.zoom}
            x={pan.x}
            y={pan.y}
            draggable={state.activeTool === "pan"}
            onDragStart={(e) => {
              if (e.target !== e.currentTarget) setIsEditingNode(true);
            }}
            onDragEnd={(e) => {
              if (e.target === e.currentTarget) {
                setPan({ x: e.target.x(), y: e.target.y() });
              } else {
                setIsEditingNode(false);
              }
            }}
            onMouseDown={() => setIsEditingNode(true)}
            onMouseUp={() => setIsEditingNode(false)}
            onMouseLeave={() => setIsEditingNode(false)}
            onClick={handleStageClick}
            onDblClick={handleDblClick}
            onMouseMove={handleMouseMove}
            onWheel={handleWheel}
            style={{ cursor: state.activeTool === "pan" ? "grab" : "crosshair" }}
          >
            <Layer>
              <Rect x={0} y={0} width={stageW} height={stageH} fill="#0e1116" shadowColor="#000" shadowBlur={40} shadowOpacity={0.6} />
              {/* The sample artwork is only ever correct for the demo file. It
                used to also stand in whenever `pdfDoc` was null, which is the
                permanent state for every image upload (pdf.js cannot open a
                PNG/JPG) — so real detections were drawn over an unrelated
                fake plan, and every room looked misplaced. */}
              {isSample ? (
                <SampleBlueprintArt />
              ) : isRasterUpload && state.file?.objectUrl ? (
                <ImagePageLayer src={state.file.objectUrl} width={stageW} height={stageH} />
              ) : pdfDoc ? (
                <PdfPageLayer doc={pdfDoc} pageIndex={activeSheet?.pageIndex ?? 0} width={stageW} height={stageH} />
              ) : null}
              <GridLayer visible={state.gridEnabled} stageW={stageW} stageH={stageH} />
            </Layer>
            <Layer>
              <EngineeringCanvasLayer
                detections={sheetDetections}
                selectedId={state.selectedDetectionId}
                isEditingNode={isEditingNode}
                showPrecisionData={showPrecisionData}
                engineeringMode
                layerOpacity={layerOpacity}
                onSelect={(id) => {
                  dispatch({ type: "SELECT_DETECTION", id });
                  if (id) {
                    dispatch({ type: "SET_RIGHT_TAB", tab: state.activeTool === "ask-ai" ? "assistant" : "detected" });
                  }
                }}
                interactive={state.activeTool === "select" || state.activeTool === "ask-ai"}
                stageW={stageW}
                stageH={stageH}
              />
              {!state.hiddenLayers.dimensions && (
                <MeasurementsLayer measurements={sheetMeasurements} stageW={stageW} stageH={stageH} />
              )}
              <CalloutLayer callouts={state.callouts} stickyNotes={state.stickyNotes} activeSheetId={state.activeSheetId} stageW={stageW} stageH={stageH} />
              {draft.length > 0 && (
                <MeasurementsLayer
                  measurements={[
                    {
                      id: "draft",
                      sheetId: state.activeSheetId ?? "",
                      tool: state.activeTool === "calibrate" ? "linear" : (state.activeTool as Measurement["tool"]),
                      points: draft,
                      label: "Drawing",
                      valueLabel: "…",
                      createdAt: 0,
                    },
                  ]}
                  stageW={stageW}
                  stageH={stageH}
                />
              )}
            </Layer>
          </Stage>

          <ScanOverlay visible={state.scanning} />
          <ToolsDock
            legendOpen={legendOpen}
            onToggleLegend={() => setLegendOpen((v) => !v)}
            isFullscreen={isFullscreen}
            onToggleFullscreen={toggleFullscreen}
            onZoomIn={() => {
              const newZoom = Math.min(8, state.zoom * 1.1);
              dispatch({ type: "SET_ZOOM", zoom: newZoom });
              setPan({ x: (size.width - stageW * newZoom) / 2, y: (size.height - stageH * newZoom) / 2 });
            }}
            onZoomOut={() => {
              const newZoom = Math.max(0.1, state.zoom * 0.9);
              dispatch({ type: "SET_ZOOM", zoom: newZoom });
              setPan({ x: (size.width - stageW * newZoom) / 2, y: (size.height - stageH * newZoom) / 2 });
            }}
            onZoomFit={zoomToFit}
            onZoomPreset={zoomToPreset}
            layerOpacity={layerOpacity}
            onLayerOpacityChange={setLayerOpacity}
          />

          <HUD cursor={cursor} zoom={state.zoom} />
          {(() => {
            const mapLeft = Math.max(0, -pan.x / (stageW * state.zoom));
            const mapRight = Math.min(1, (size.width - pan.x) / (stageW * state.zoom));
            const mapTop = Math.max(0, -pan.y / (stageH * state.zoom));
            const mapBottom = Math.min(1, (size.height - pan.y) / (stageH * state.zoom));
            return (
              <MiniMap
                left={mapLeft}
                top={mapTop}
                width={Math.max(0.05, mapRight - mapLeft)}
                height={Math.max(0.05, mapBottom - mapTop)}
              />
            );
          })()}

          {selectedDetection && cardPos && !isEditingNode && (
            selectedDetection.kind === "wall" ? (
              <WallInspectionOverlay
                detection={selectedDetection}
                cardPos={cardPos}
                containerWidth={size.width}
                containerHeight={size.height}
                onClose={() => dispatch({ type: "SELECT_DETECTION", id: null })}
              />
            ) : (
              <div
                className="absolute z-20 -translate-x-1/2 flex items-center gap-1.5 p-1.5 rounded-lg glass-panel glow-primary"
                style={{ left: cardPos.x, top: Math.max(cardPos.y - 56, 8) }}
              >
                <span className="text-[11px] font-mono-num px-1.5 text-[var(--color-text-secondary)]">
                  {Math.round(selectedDetection.confidence * 100)}%
                </span>
                <button
                  onClick={() => {
                    dispatch({ type: "APPROVE_DETECTION", id: selectedDetection.id });
                    dispatch({ type: "ADD_HISTORY", entry: { id: `h-${Date.now()}`, version: state.revision, actor: currentUserName || "Unknown user", action: `Approved ${selectedDetection.name}`, timestamp: Date.now() } });
                    toast.success(`Approved ${selectedDetection.name}`);
                    dispatch({ type: "SELECT_DETECTION", id: null });
                  }}
                  className="w-7 h-7 flex items-center justify-center rounded-md bg-[var(--color-success)]/15 text-[var(--color-success)] hover:bg-[var(--color-success)]/25"
                >
                  <Check size={14} />
                </button>
                <button
                  onClick={() => {
                    dispatch({ type: "REJECT_DETECTION", id: selectedDetection.id });
                    dispatch({ type: "ADD_HISTORY", entry: { id: `h-${Date.now()}`, version: state.revision, actor: currentUserName || "Unknown user", action: `Rejected ${selectedDetection.name}`, timestamp: Date.now() } });
                    toast(`Rejected ${selectedDetection.name}`);
                    dispatch({ type: "SELECT_DETECTION", id: null });
                  }}
                  className="w-7 h-7 flex items-center justify-center rounded-md bg-[var(--color-danger)]/15 text-[var(--color-danger)] hover:bg-[var(--color-danger)]/25"
                >
                  <XIcon size={14} />
                </button>
              </div>
            )
          )}

          {activeSheet?.isTakeoffEligible === false && (
            <div className="absolute top-16 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#0B0E14]/95 border border-white/10 shadow-xl backdrop-blur-md">
              <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
              <span className="text-[11px] font-semibold text-white">
                {activeSheet.code} · {activeSheet.name.toUpperCase()}
              </span>
              <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 font-medium border border-amber-500/30">
                NON-TAKEOFF SHEET
              </span>
              {activeSheet.skipReason && (
                <span className="text-[10px] text-gray-400 max-w-sm truncate">
                  ({activeSheet.skipReason})
                </span>
              )}
            </div>
          )}

          {activeSheet && activeSheet.isTakeoffEligible !== false && state.sheetGeometryState[activeSheet.id] === "loading" && (
            <div className="absolute top-16 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#0B0E14]/95 border border-blue-500/40 shadow-xl backdrop-blur-md">
              <span className="w-2 h-2 rounded-full bg-blue-400 animate-ping" />
              <span className="text-[11px] font-semibold text-white">
                Loading geometry for {activeSheet.code}…
              </span>
            </div>
          )}

          {activeSheet && activeSheet.isTakeoffEligible !== false && (state.sheetGeometryState[activeSheet.id] === "error" || (state.sheetGeometryState[activeSheet.id] === "ready" && sheetDetections.length === 0)) && (
            <div className="absolute top-16 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#0B0E14]/95 border border-white/10 shadow-xl backdrop-blur-md">
              <span className="w-2 h-2 rounded-full bg-gray-400" />
              <span className="text-[11px] font-semibold text-gray-300">
                {activeSheet.code} · Geometry not available from source
              </span>
            </div>
          )}

          {/* Interactive Estimating Drafting Action Bar */}
          {["area", "linear", "polygon", "magic-fill", "count", "calibrate"].includes(state.activeTool) && (
            <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-20 flex items-center gap-3 px-4 py-2 rounded-2xl bg-[#0B0E14]/95 border border-blue-500/40 shadow-2xl backdrop-blur-xl select-none">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                <span className="text-[11px] font-semibold text-white">
                  {state.activeTool === "linear" && "Linear Takeoff (LF)"}
                  {state.activeTool === "magic-fill" && "Quick Area (SF)"}
                  {state.activeTool === "area" && "Area Takeoff (SF)"}
                  {state.activeTool === "polygon" && "Polygon Boundary"}
                  {state.activeTool === "count" && "Item Count Takeoff"}
                  {state.activeTool === "calibrate" && "Scale Calibration"}
                </span>
              </div>

              <div className="h-4 w-px bg-white/15" />

              <span className="text-[10px] text-gray-300 font-mono">
                {state.activeTool === "count"
                  ? "Click anywhere on canvas to place count markers"
                  : state.activeTool === "magic-fill"
                    ? draft.length === 0 ? "Click first corner of rectangle" : "Click opposite corner to finish"
                    : state.activeTool === "calibrate"
                      ? `Click two points along a known dimension (${draft.length}/2 pts)`
                      : `Click to add points (${draft.length} pts)`}
              </span>

              {draft.length > 0 && (
                <div className="flex items-center gap-1.5 ml-2">
                  {["area", "polygon", "linear"].includes(state.activeTool) && draft.length >= (state.activeTool === "linear" ? 2 : 3) && (
                    <button
                      onClick={finishDraft}
                      className="px-2.5 py-1 rounded-md bg-blue-600 hover:bg-blue-500 text-white font-semibold text-[10px] transition-colors cursor-pointer"
                    >
                      Finish (Enter)
                    </button>
                  )}
                  <button
                    onClick={() => setDraft([])}
                    className="px-2 py-1 rounded-md bg-white/10 hover:bg-white/20 text-gray-300 hover:text-white text-[10px] transition-colors cursor-pointer"
                  >
                    Cancel (Esc)
                  </button>
                </div>
              )}
            </div>
          )}

          {legendOpen && state.summaryTab === "drywall" && <WallCanvasLegend />}
        </div>
      </div>

      <CalibrationModal
        open={pendingCalibration !== null}
        onConfirm={confirmCalibration}
        onCancel={() => setPendingCalibration(null)}
      />

      <PromptModal
        open={activePrompt !== null}
        title={activePrompt?.title ?? ""}
        description={activePrompt?.description ?? ""}
        defaultValue={activePrompt?.defaultValue ?? ""}
        placeholder="Type note content here..."
        onConfirm={(text) => {
          if (!activePrompt) return;
          const p = activePrompt.point;
          const finalVal = text.trim() || activePrompt.defaultValue;
          if (activePrompt.type === "callout") {
            dispatch({
              type: "ADD_CALLOUT",
              callout: {
                id: `callout-${Date.now()}`,
                sheetId: state.activeSheetId ?? "",
                startX: p.x,
                startY: p.y,
                endX: Math.min(0.95, p.x + 0.08),
                endY: Math.max(0.05, p.y - 0.05),
                text: finalVal,
              },
            });
            toast.success("Leader-Line Callout added");
          } else {
            dispatch({
              type: "ADD_STICKY_NOTE",
              note: {
                id: `note-${Date.now()}`,
                sheetId: state.activeSheetId ?? "",
                x: p.x,
                y: p.y,
                text: finalVal,
                color: "#FEF08A",
              },
            });
            toast.success("Sticky Note added");
          }
          dispatch({ type: "SET_TOOL", tool: "select" });
          setActivePrompt(null);
        }}
        onCancel={() => {
          setActivePrompt(null);
        }}
      />

      {isPrintingDrawings && createPortal(
        <div id="print-all-sheets-container">
          {state.sheets.map((sheet) => (
            <PrintableSheet key={sheet.id} sheet={sheet} pdfDoc={pdfDoc} />
          ))}
        </div>,
        document.body
      )}
    </div>
  );
}

import type { Sheet } from "@/types";

interface PrintableSheetProps {
  sheet: Sheet;
  pdfDoc: PDFDocumentProxy | null;
}

function PrintableSheet({ sheet, pdfDoc }: PrintableSheetProps) {
  const { state } = useApp();
  const isSample = !!state.file?.isSample;

  const isRasterUpload =
    !isSample && !!state.file && /\.(png|jpe?g|webp|tiff?)$/i.test(state.file.name);

  const stageSize = stageSizeForPage(sheet.widthPx, sheet.heightPx);
  const stageW = stageSize.width;
  const stageH = stageSize.height;

  const sheetDetections = state.detections.filter((d) => d.sheetId === sheet.id);
  const sheetMeasurements = state.measurements.filter((m) => m.sheetId === sheet.id);
  const sheetCallouts = state.callouts.filter((c) => c.sheetId === sheet.id);
  const sheetNotes = state.stickyNotes.filter((n) => n.sheetId === sheet.id);

  return (
    <div className="printable-page-break" style={{ width: stageW, height: stageH }}>
      <Stage width={stageW} height={stageH}>
        <Layer>
          <Rect x={0} y={0} width={stageW} height={stageH} fill="#0e1116" />
          {isSample ? (
            <SampleBlueprintArt />
          ) : isRasterUpload && state.file?.objectUrl ? (
            <ImagePageLayer src={state.file.objectUrl} width={stageW} height={stageH} />
          ) : pdfDoc ? (
            <PdfPageLayer doc={pdfDoc} pageIndex={sheet.pageIndex} width={stageW} height={stageH} />
          ) : null}
        </Layer>
        <Layer>
          <EngineeringCanvasLayer
            detections={sheetDetections}
            selectedId={null}
            onSelect={() => { }}
            interactive={false}
            stageW={stageW}
            stageH={stageH}
          />
          <MeasurementsLayer measurements={sheetMeasurements} stageW={stageW} stageH={stageH} />
          <CalloutLayer callouts={sheetCallouts} stickyNotes={sheetNotes} activeSheetId={sheet.id} stageW={stageW} stageH={stageH} />
        </Layer>
      </Stage>
    </div>
  );
}
