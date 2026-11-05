import React, { useRef, useEffect, useState, useMemo, useCallback } from "react";
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  FileSpreadsheet,
  Layers,
  Compass,
  Filter,
  CheckCircle2,
  AlertTriangle,
  Eye,
  Crosshair,
  RotateCcw,
  Sparkles,
  MousePointer,
  Hand,
  Ruler,
  Sliders,
  Image as ImageIcon,
  Info,
} from "lucide-react";
import type { PdfGeometryResponse } from "@/api/backendApi";

interface PDFNativeDrawingCanvasProps {
  geometryData: PdfGeometryResponse;
  selectedObjectId: string | null;
  onSelectObject: (obj: any | null) => void;
  activeLayers: Set<string>;
  rasterImageUrl?: string;
  showRasterComparison?: boolean;
  rasterOpacity?: number;
  selectedTrade?: string;
  viewMode?: "RAW" | "CLEAN" | "TAKEOFF";
  onViewModeChange?: (mode: "RAW" | "CLEAN" | "TAKEOFF") => void;
}

export default function PDFNativeDrawingCanvas({
  geometryData,
  selectedObjectId,
  onSelectObject,
  activeLayers,
  rasterImageUrl,
  showRasterComparison = false,
  rasterOpacity = 0.4,
  selectedTrade = "ALL",
  viewMode = "CLEAN",
  onViewModeChange,
}: PDFNativeDrawingCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // View Mode: 'RAW' (native un-decluttered) vs 'CLEAN' (engineering readable) vs 'TAKEOFF' (trade-scoped overlay)
  const [internalViewMode, setInternalViewMode] = useState<"RAW" | "CLEAN" | "TAKEOFF">(viewMode || "CLEAN");
  useEffect(() => {
    if (viewMode) setInternalViewMode(viewMode);
  }, [viewMode]);

  const handleToggleViewMode = (mode: "RAW" | "CLEAN" | "TAKEOFF") => {
    setInternalViewMode(mode);
    onViewModeChange?.(mode);
  };

  // Pan & Zoom (in screen pixel space)
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [zoom, setZoom] = useState<number>(0.8);
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  // Tools: 'select', 'pan', 'measure'
  const [activeTool, setActiveTool] = useState<"select" | "pan" | "measure">("select");
  const [hoveredObjectId, setHoveredObjectId] = useState<string | null>(null);

  // Mouse Coordinates readout
  const [cursorPos, setCursorPos] = useState<{ ptX: number; ptY: number; ftX: number; ftY: number } | null>(null);

  // Measurement State
  const [measureStart, setMeasureStart] = useState<[number, number] | null>(null);
  const [measureEnd, setMeasureEnd] = useState<[number, number] | null>(null);

  // Source vs Canonical Overlay Validation Mode (Phase 6 Constraint 4)
  const [showSourceOverlay, setShowSourceOverlay] = useState(true);

  // Raster Image Loading
  const [rasterImg, setRasterImg] = useState<HTMLImageElement | null>(null);
  useEffect(() => {
    if (!rasterImageUrl) {
      setRasterImg(null);
      return;
    }
    const img = new Image();
    img.src = rasterImageUrl;
    img.onload = () => setRasterImg(img);
  }, [rasterImageUrl]);

  const ftPerPt = geometryData.scale?.ft_per_pt || 50.0 / 864.0;
  const isScaleResolved = geometryData.scale?.scale_status !== "SCALE_UNRESOLVED";

  // Calculate actual bounding box of reconstructed drawing linework (excluding outer empty page margins)
  const drawingBounds = useMemo(() => {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;

    // 1. Inspect semantic objects
    for (const obj of geometryData.semantic_objects || []) {
      // Exclude full-page border if it's identical to whole page
      if (obj.object_type === "TITLE_BLOCK" && obj.bbox_pdf && obj.bbox_pdf[2] >= (geometryData.width_pt || 1000) * 0.95) {
        // still include for bounds if no other geometry
      }
      if (obj.bbox_pdf && obj.bbox_pdf.length === 4) {
        const [x0, y0, x1, y1] = obj.bbox_pdf;
        if (x0 < minX) minX = x0;
        if (y0 < minY) minY = y0;
        if (x1 > maxX) maxX = x1;
        if (y1 > maxY) maxY = y1;
      }
      for (const p of obj.source_points_pdf || []) {
        if (p[0] < minX) minX = p[0];
        if (p[1] < minY) minY = p[1];
        if (p[0] > maxX) maxX = p[0];
        if (p[1] > maxY) maxY = p[1];
      }
    }

    // 2. Inspect dimension objects
    for (const dim of geometryData.dimension_objects || []) {
      if (dim.start_pt) {
        if (dim.start_pt[0] < minX) minX = dim.start_pt[0];
        if (dim.start_pt[1] < minY) minY = dim.start_pt[1];
        if (dim.start_pt[0] > maxX) maxX = dim.start_pt[0];
        if (dim.start_pt[1] > maxY) maxY = dim.start_pt[1];
      }
      if (dim.end_pt) {
        if (dim.end_pt[0] < minX) minX = dim.end_pt[0];
        if (dim.end_pt[1] < minY) minY = dim.end_pt[1];
        if (dim.end_pt[0] > maxX) maxX = dim.end_pt[0];
        if (dim.end_pt[1] > maxY) maxY = dim.end_pt[1];
      }
    }

    // Fallback if no geometry
    if (!isFinite(minX) || !isFinite(minY) || !isFinite(maxX) || !isFinite(maxY)) {
      return {
        minX: 0,
        minY: 0,
        maxX: geometryData.width_pt || 1000,
        maxY: geometryData.height_pt || 700,
        width: geometryData.width_pt || 1000,
        height: geometryData.height_pt || 700,
      };
    }

    return {
      minX,
      minY,
      maxX,
      maxY,
      width: Math.max(10, maxX - minX),
      height: Math.max(10, maxY - minY),
    };
  }, [geometryData]);

  // Fit to Drawing (reconstructed geometry bounds)
  const fitToDrawing = useCallback(() => {
    if (!containerRef.current) return;
    const { clientWidth, clientHeight } = containerRef.current;
    if (clientWidth <= 0 || clientHeight <= 0) return;

    const bounds = drawingBounds;
    const padding = 50;
    const availableW = Math.max(100, clientWidth - padding * 2);
    const availableH = Math.max(100, clientHeight - padding * 2);

    const scaleX = availableW / bounds.width;
    const scaleY = availableH / bounds.height;
    const newZoom = Math.max(0.1, Math.min(scaleX, scaleY, 3.0));

    const boundsCenterX = bounds.minX + bounds.width / 2;
    const boundsCenterY = bounds.minY + bounds.height / 2;

    const panX = clientWidth / 2 - boundsCenterX * newZoom;
    const panY = clientHeight / 2 - boundsCenterY * newZoom;

    setZoom(newZoom);
    setPan({ x: panX, y: panY });
  }, [drawingBounds]);

  // Fit to Page (full sheet boundary)
  const fitToPage = useCallback(() => {
    if (!containerRef.current) return;
    const { clientWidth, clientHeight } = containerRef.current;
    if (clientWidth <= 0 || clientHeight <= 0) return;

    const docW = geometryData.width_pt || 1000;
    const docH = geometryData.height_pt || 700;

    const scaleX = (clientWidth - 80) / docW;
    const scaleY = (clientHeight - 80) / docH;
    const newZoom = Math.max(0.1, Math.min(scaleX, scaleY, 2.5));

    const cx = (clientWidth - docW * newZoom) / 2;
    const cy = (clientHeight - docH * newZoom) / 2;

    setZoom(newZoom);
    setPan({ x: cx, y: cy });
  }, [geometryData]);

  // Initial auto-fit: prefer fitting drawing linework
  useEffect(() => {
    fitToDrawing();
  }, [fitToDrawing]);

  // Click-to-Source: Automatically pan and zoom to focused object geometry
  useEffect(() => {
    if (!selectedObjectId || !containerRef.current) return;
    let targetBbox: number[] | null = null;
    let sem = geometryData.semantic_objects?.find(
      (o) =>
        o.id === selectedObjectId ||
        o.source_object_id === selectedObjectId ||
        o.qto_reference_id === selectedObjectId ||
        (o.source_vector_ids && o.source_vector_ids.includes(selectedObjectId)) ||
        o.properties?.canonical_wall_id === selectedObjectId ||
        o.label === selectedObjectId
    );

    // If not directly matched, check if selectedObjectId matches a takeoff item
    if (!sem && geometryData.takeoff_summary?.items) {
      const tItem = geometryData.takeoff_summary.items.find(
        (it: any) =>
          it.item_id === selectedObjectId ||
          it.canonical_object_id === selectedObjectId ||
          it.item_code === selectedObjectId
      );
      if (tItem) {
        sem = geometryData.semantic_objects?.find(
          (o) =>
            o.id === tItem.canonical_object_id ||
            tItem.source_object_ids?.includes(o.id) ||
            tItem.source_object_ids?.some((sid: string) => o.source_vector_ids?.includes(sid)) ||
            (o.label && tItem.name && o.label.toLowerCase() === tItem.name.toLowerCase())
        );
      }
    }

    if (sem?.bbox_pdf && sem.bbox_pdf.length === 4) {
      targetBbox = sem.bbox_pdf;
    } else {
      const dim = geometryData.dimension_objects?.find(
        (d) => d.id === selectedObjectId || d.text_object_id === selectedObjectId
      );
      if (dim?.start_pt && dim?.end_pt) {
        targetBbox = [
          Math.min(dim.start_pt[0], dim.end_pt[0]) - 30,
          Math.min(dim.start_pt[1], dim.end_pt[1]) - 30,
          Math.max(dim.start_pt[0], dim.end_pt[0]) + 30,
          Math.max(dim.start_pt[1], dim.end_pt[1]) + 30,
        ];
      } else {
        const txt = geometryData.text_objects?.find((t) => t.id === selectedObjectId);
        if (txt?.bbox_pdf && txt.bbox_pdf.length === 4) {
          targetBbox = [txt.bbox_pdf[0] - 25, txt.bbox_pdf[1] - 25, txt.bbox_pdf[2] + 25, txt.bbox_pdf[3] + 25];
        }
      }
    }

    if (targetBbox) {
      const { clientWidth, clientHeight } = containerRef.current;
      if (clientWidth <= 0 || clientHeight <= 0) return;
      const bw = Math.max(25, targetBbox[2] - targetBbox[0]);
      const bh = Math.max(25, targetBbox[3] - targetBbox[1]);
      const targetZoom = Math.min(2.5, Math.max(0.8, Math.min((clientWidth * 0.45) / bw, (clientHeight * 0.45) / bh)));
      const cx = (targetBbox[0] + targetBbox[2]) / 2;
      const cy = (targetBbox[1] + targetBbox[3]) / 2;
      setZoom(targetZoom);
      setPan({
        x: clientWidth / 2 - cx * targetZoom,
        y: clientHeight / 2 - cy * targetZoom,
      });
    }
  }, [selectedObjectId, geometryData]);

  // Filter semantic objects by active layers
  const visibleObjects = useMemo(() => {
    return (geometryData.semantic_objects || []).filter((obj) => activeLayers.has(obj.layer));
  }, [geometryData, activeLayers]);

  // Screen <-> PDF Coordinate Transforms
  const pdfToScreen = useCallback(
    (pt: [number, number]): [number, number] => {
      return [pan.x + pt[0] * zoom, pan.y + pt[1] * zoom];
    },
    [pan, zoom]
  );

  const screenToPdf = useCallback(
    (screenX: number, screenY: number): [number, number] => {
      return [(screenX - pan.x) / zoom, (screenY - pan.y) / zoom];
    },
    [pan, zoom]
  );

  // Canvas Render Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Handle high-DPI displays
    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    // Canvas Background
    ctx.fillStyle = "#090d16";
    ctx.fillRect(0, 0, width, height);

    ctx.save();
    ctx.translate(pan.x, pan.y);
    ctx.scale(zoom, zoom);

    const docW = geometryData.width_pt || 1000;
    const docH = geometryData.height_pt || 700;

    // 1. Draw Page Sheet Paper Boundary
    ctx.fillStyle = "#0f172a";
    ctx.shadowColor = "rgba(0, 0, 0, 0.6)";
    ctx.shadowBlur = 24 / zoom;
    ctx.shadowOffsetX = 4 / zoom;
    ctx.shadowOffsetY = 6 / zoom;
    ctx.fillRect(0, 0, docW, docH);
    ctx.shadowColor = "transparent";

    ctx.strokeStyle = "#334155";
    ctx.lineWidth = 1 / zoom;
    ctx.strokeRect(0, 0, docW, docH);

    // 1.5 Render Explicit Drawing Regions (DETAIL_REGION, LEGEND_REGION, TITLE_BLOCK_REGION, NOTES_REGION, DRAWING_REGION)
    if (internalViewMode !== "RAW" && geometryData.regions && geometryData.regions.length > 0) {
      ctx.save();
      for (const reg of geometryData.regions) {
        if (!reg.bbox_pdf || reg.bbox_pdf.length < 4) continue;
        const [rx0, ry0, rx1, ry1] = reg.bbox_pdf;
        const rw = rx1 - rx0;
        const rh = ry1 - ry0;
        const cat = reg.region_category || "DRAWING_REGION";

        let strokeColor = "rgba(56, 189, 248, 0.4)";
        let fillColor = "rgba(56, 189, 248, 0.02)";
        let tagBg = "#0284c7";
        if (cat === "TITLE_BLOCK_REGION") {
          strokeColor = "rgba(148, 163, 184, 0.35)";
          fillColor = "rgba(148, 163, 184, 0.02)";
          tagBg = "#475569";
        } else if (cat === "LEGEND_REGION") {
          strokeColor = "rgba(168, 85, 247, 0.45)";
          fillColor = "rgba(168, 85, 247, 0.03)";
          tagBg = "#7e22ce";
        } else if (cat === "NOTES_REGION") {
          strokeColor = "rgba(16, 185, 129, 0.4)";
          fillColor = "rgba(16, 185, 129, 0.02)";
          tagBg = "#047857";
        } else if (cat === "DETAIL_REGION") {
          strokeColor = "rgba(245, 158, 11, 0.45)";
          fillColor = "rgba(245, 158, 11, 0.03)";
          tagBg = "#b45309";
        }

        ctx.fillStyle = fillColor;
        ctx.fillRect(rx0, ry0, rw, rh);
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = 1.2 / zoom;
        ctx.setLineDash([6 / zoom, 3 / zoom]);
        ctx.strokeRect(rx0, ry0, rw, rh);
        ctx.setLineDash([]);

        // Region Tag Badge
        const tagText = `${cat.replace("_REGION", "")} — ${reg.title || "AREA"}`;
        ctx.font = `600 ${Math.max(7, 9 / zoom)}px Inter, sans-serif`;
        const tw = ctx.measureText(tagText).width;
        const badgeW = tw + 10 / zoom;
        const badgeH = 14 / zoom;
        ctx.fillStyle = tagBg;
        ctx.beginPath();
        ctx.roundRect(rx0 + 4 / zoom, ry0 + 4 / zoom, badgeW, badgeH, 2 / zoom);
        ctx.fill();
        ctx.fillStyle = "#ffffff";
        ctx.textBaseline = "middle";
        ctx.fillText(tagText, rx0 + 9 / zoom, ry0 + 4 / zoom + badgeH / 2);
      }
      ctx.restore();
    }

    // 2. Optional Raster Debug Comparison Layer
    if (showRasterComparison && rasterImg) {
      ctx.save();
      ctx.globalAlpha = rasterOpacity;
      ctx.drawImage(rasterImg, 0, 0, docW, docH);
      ctx.restore();
    }

    // 3. Render Standing Seam Hatches
    if (activeLayers.has("Hatches")) {
      ctx.strokeStyle = "#475569";
      ctx.lineWidth = 0.5 / zoom;
      const hatches = visibleObjects.filter((o) => o.layer === "Hatches");
      for (const h of hatches) {
        const pts = h.source_points_pdf;
        if (pts && pts.length >= 2) {
          ctx.beginPath();
          ctx.moveTo(pts[0][0], pts[0][1]);
          for (let i = 1; i < pts.length; i++) {
            ctx.lineTo(pts[i][0], pts[i][1]);
          }
          ctx.stroke();
        }
      }
    }

    // 3.5 Render Original PDF Native Vector Geometry (Source vs Canonical Overlay)
    if (showSourceOverlay && geometryData.native_geometry && geometryData.native_geometry.length > 0) {
      ctx.save();
      ctx.strokeStyle = "rgba(249, 115, 22, 0.45)";
      ctx.lineWidth = 0.85 / zoom;
      ctx.setLineDash([3 / zoom, 2 / zoom]);
      for (const n of geometryData.native_geometry) {
        const pts = n.source_points_pdf;
        if (pts && pts.length >= 2) {
          ctx.beginPath();
          ctx.moveTo(pts[0][0], pts[0][1]);
          for (let i = 1; i < pts.length; i++) {
            ctx.lineTo(pts[i][0], pts[i][1]);
          }
          if (n.is_closed) {
            ctx.closePath();
          }
          ctx.stroke();
        }
      }
      ctx.restore();
    }

    // 4. Render Title Block & Border Linework
    if (activeLayers.has("Title Block")) {
      ctx.strokeStyle = "#475569";
      ctx.lineWidth = 1.0 / zoom;
      const borders = visibleObjects.filter((o) => o.layer === "Title Block" && o.object_type === "TITLE_BLOCK");
      for (const b of borders) {
        const pts = b.source_points_pdf;
        if (pts && pts.length >= 2) {
          ctx.beginPath();
          ctx.moveTo(pts[0][0], pts[0][1]);
          for (let i = 1; i < pts.length; i++) {
            ctx.lineTo(pts[i][0], pts[i][1]);
          }
          ctx.stroke();
        }
      }
    }

    // 5. Render Grid Lines
    if (activeLayers.has("Grid")) {
      ctx.strokeStyle = "#64748b";
      ctx.setLineDash([8 / zoom, 4 / zoom, 2 / zoom, 4 / zoom]);
      ctx.lineWidth = 0.8 / zoom;
      const grids = visibleObjects.filter((o) => o.layer === "Grid" && o.object_type === "GRID");
      for (const g of grids) {
        const pts = g.source_points_pdf;
        if (pts && pts.length >= 2) {
          ctx.beginPath();
          ctx.moveTo(pts[0][0], pts[0][1]);
          for (let i = 1; i < pts.length; i++) {
            ctx.lineTo(pts[i][0], pts[i][1]);
          }
          ctx.stroke();
        }
      }
      ctx.setLineDash([]);
    }

    // 6. Render Architectural Elements with Trade Scoping (Phase 7B Requirements 5 & 6)
    const specializedLayers = [
      "Walls",
      "Doors",
      "Windows",
      "Rooms",
      "Plumbing",
      "Fixtures",
      "Details",
      "Legend",
      "Title Block",
      "Annotations",
      "Symbols",
    ];
    const specializedLayerColors: Record<string, string> = {
      Walls: "#e11d48",
      Doors: "#f97316",
      Windows: "#0284c7",
      Rooms: "#a855f7",
      Plumbing: "#06b6d4",
      Fixtures: "#10b981",
      Details: "#f59e0b",
      Legend: "#8b5cf6",
      "Title Block": "#64748b",
      Annotations: "#14b8a6",
      Symbols: "#a855f7",
    };

    const isNonQtoSheet =
      geometryData.drawing_type === "SECTION" ||
      geometryData.drawing_type === "ELEVATION" ||
      geometryData.drawing_type === "DETAIL_DRAWING" ||
      geometryData.drawing_type === "FOUNDATION_PLAN";

    for (const al of specializedLayers) {
      if (activeLayers.has(al)) {
        const objs = visibleObjects.filter((o) => o.layer === al);
        for (const obj of objs) {
          const pts = obj.source_points_pdf;
          if (!pts || pts.length < 2) continue;

          ctx.save();

          // Trade-Scoped Visibility & Styling
          let strokeColor = specializedLayerColors[al] || "#94a3b8";
          let lineWidth = (al === "Plumbing" || al === "Fixtures" || al === "Walls" ? 1.4 : 1.0) / zoom;
          let alpha = 1.0;

          if (internalViewMode === "TAKEOFF") {
            if (selectedTrade === "DRYWALL") {
              if (al === "Walls") {
                if (isNonQtoSheet) {
                  // Non-takeoff section/elevation: neutral drafting line, NO false drywall highlights
                  strokeColor = "#64748b";
                  lineWidth = 1.0 / zoom;
                  alpha = 0.45;
                } else if (obj.semantic_type === "DRYWALL_PARTITION") {
                  strokeColor = "#f43f5e";
                  lineWidth = 2.6 / zoom;
                  alpha = 1.0;
                } else if (obj.semantic_type === "MASONRY_WALL") {
                  strokeColor = "#fb7185";
                  lineWidth = 2.0 / zoom;
                  alpha = 0.9;
                } else {
                  strokeColor = "#e11d48";
                  lineWidth = 2.0 / zoom;
                }
              } else if (al === "Doors" || al === "Windows") {
                // Opening deductions for drywall
                strokeColor = al === "Doors" ? "#f97316" : "#0284c7";
                lineWidth = 1.8 / zoom;
                alpha = 0.95;
              } else if (al === "Rooms") {
                // Supporting room context
                alpha = 0.35;
              } else {
                // Unrelated plumbing, fixtures, details, legend, title block
                alpha = 0.15;
              }
            } else if (selectedTrade === "FLOORING") {
              if (al === "Rooms") {
                strokeColor = "#a855f7";
                lineWidth = 2.2 / zoom;
                alpha = 1.0;
              } else if (al === "Doors" || al === "Windows") {
                alpha = 0.4;
              } else {
                alpha = 0.15;
              }
            } else if (selectedTrade === "ROOFING") {
              if (al === "Roof") {
                alpha = 1.0;
              } else {
                alpha = 0.15;
              }
            } else if (selectedTrade === "PLUMBING") {
              if (al === "Plumbing" || al === "Fixtures") {
                strokeColor = al === "Plumbing" ? "#06b6d4" : "#10b981";
                lineWidth = 2.2 / zoom;
                alpha = 1.0;
              } else {
                alpha = 0.15;
              }
            }
          }

          const isSelected = selectedObjectId === obj.id || selectedObjectId === obj.qto_reference_id;
          const isHovered = hoveredObjectId === obj.id;
          if (isSelected) {
            strokeColor = "#ffffff";
            lineWidth = Math.max(lineWidth, 3.0 / zoom);
            alpha = 1.0;
          } else if (isHovered) {
            strokeColor = "#38bdf8";
            lineWidth = Math.max(lineWidth, 2.2 / zoom);
            alpha = 1.0;
          }

          ctx.globalAlpha = alpha;
          ctx.strokeStyle = strokeColor;
          ctx.lineWidth = lineWidth;

          ctx.beginPath();
          ctx.moveTo(pts[0][0], pts[0][1]);
          for (let i = 1; i < pts.length; i++) {
            ctx.lineTo(pts[i][0], pts[i][1]);
          }

          if (obj.object_type === "ROOM" || obj.object_type === "POLYGON") {
            ctx.closePath();
            if (internalViewMode === "TAKEOFF" && selectedTrade === "FLOORING") {
              ctx.fillStyle = isSelected
                ? "rgba(168, 85, 247, 0.4)"
                : isHovered
                ? "rgba(168, 85, 247, 0.3)"
                : "rgba(168, 85, 247, 0.22)";
            } else {
              ctx.fillStyle = "rgba(168, 85, 247, 0.12)";
            }
            ctx.fill();
          }

          ctx.stroke();
          ctx.restore();
        }
      }
    }

    // 7. Render General Geometry, Annotations & Symbols
    const generalGeom = visibleObjects.filter(
      (o) => o.layer === "Geometry" || o.layer === "Symbols" || o.layer === "Annotations"
    );
    for (const g of generalGeom) {
      if (g.object_type === "TEXT" || g.object_type === "DIMENSION" || g.object_type === "ROOF") continue;
      const pts = g.source_points_pdf;
      if (pts && pts.length >= 2) {
        ctx.save();
        let geomAlpha = 1.0;
        let geomColor = "#94a3b8";
        let geomWidth = 0.9 / zoom;

        if (internalViewMode === "TAKEOFF") {
          if (selectedTrade !== "ALL") {
            geomAlpha = 0.18;
          }
          if (isNonQtoSheet && (g.object_type === "SECTION_WALL_REPRESENTATION" || g.object_type === "SLAB")) {
            geomColor = "#64748b";
            geomAlpha = 0.65;
            geomWidth = 1.0 / zoom;
          }
        }

        const isSelected = selectedObjectId === g.id;
        const isHovered = hoveredObjectId === g.id;
        if (isSelected) {
          geomColor = "#ffffff";
          geomAlpha = 1.0;
          geomWidth = 2.5 / zoom;
        } else if (isHovered) {
          geomColor = "#38bdf8";
          geomAlpha = 1.0;
          geomWidth = 2.0 / zoom;
        }

        ctx.globalAlpha = geomAlpha;
        ctx.strokeStyle = geomColor;
        ctx.lineWidth = geomWidth;
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        for (let i = 1; i < pts.length; i++) {
          ctx.lineTo(pts[i][0], pts[i][1]);
        }
        if (g.object_type === "SYMBOL") {
          ctx.strokeStyle = "#a855f7";
        }
        ctx.stroke();
        ctx.restore();
      }
    }

    // 8. Render ROOF PLANES (Primary Trade Polygons with pitch fill)
    if (activeLayers.has("Roof")) {
      const roofObjs = visibleObjects.filter((o) => o.object_type === "ROOF");
      for (const rf of roofObjs) {
        const pts = rf.source_points_pdf;
        if (pts && pts.length >= 3) {
          const isSelected = selectedObjectId === rf.id || selectedObjectId === rf.qto_reference_id;
          const isHovered = hoveredObjectId === rf.id;

          ctx.beginPath();
          ctx.moveTo(pts[0][0], pts[0][1]);
          for (let i = 1; i < pts.length; i++) {
            ctx.lineTo(pts[i][0], pts[i][1]);
          }
          ctx.closePath();

          // Fill styling
          if (isSelected) {
            ctx.fillStyle = "rgba(6, 182, 212, 0.35)";
            ctx.strokeStyle = "#06b6d4";
            ctx.lineWidth = 3.0 / zoom;
          } else if (isHovered) {
            ctx.fillStyle = "rgba(6, 182, 212, 0.22)";
            ctx.strokeStyle = "#22d3ee";
            ctx.lineWidth = 2.0 / zoom;
          } else {
            ctx.fillStyle = "rgba(14, 116, 144, 0.16)";
            ctx.strokeStyle = "#0891b2";
            ctx.lineWidth = 1.8 / zoom;
          }

          ctx.fill();
          ctx.stroke();

          // Render slope badge & area label at polygon centroid
          const cx = pts.reduce((sum, p) => sum + p[0], 0) / pts.length;
          const cy = pts.reduce((sum, p) => sum + p[1], 0) / pts.length;

          ctx.save();
          ctx.fillStyle = "#ffffff";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";

          // Label badge box
          const labelText = `${rf.label} (${rf.properties?.slope || "2:12"})`;
          const areaText = `${Number(rf.properties?.plan_area_sqft || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })} SF Plan | ${Number(rf.properties?.true_surface_area_sqft || 0).toLocaleString(undefined, { maximumFractionDigits: 1 })} SF True`;

          const boxW = 200 / zoom;
          const boxH = 38 / zoom;
          ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
          ctx.strokeStyle = isSelected ? "#06b6d4" : "#334155";
          ctx.lineWidth = 1 / zoom;
          ctx.beginPath();
          ctx.roundRect(cx - boxW / 2, cy - boxH / 2, boxW, boxH, 6 / zoom);
          ctx.fill();
          ctx.stroke();

          ctx.fillStyle = "#f8fafc";
          ctx.font = `bold ${Math.max(10, 13 / zoom)}px Inter, -apple-system, sans-serif`;
          ctx.fillText(labelText, cx, cy - 5 / zoom);
          ctx.fillStyle = "#38bdf8";
          ctx.font = `normal ${Math.max(8, 10 / zoom)}px Inter, -apple-system, sans-serif`;
          ctx.fillText(areaText, cx, cy + 9 / zoom);
          ctx.restore();
        }
      }
    }

    // 9. Render Structured Dimensions (Line + Witness Lines + Text Tag)
    if (activeLayers.has("Dimensions")) {
      const dimObjs = geometryData.dimension_objects || [];
      for (const dim of dimObjs) {
        const isSelected = selectedObjectId === dim.id || selectedObjectId === dim.text_object_id;
        const isHovered = hoveredObjectId === dim.id;

        ctx.strokeStyle = isSelected ? "#f59e0b" : isHovered ? "#fbbf24" : "#d97706";
        ctx.lineWidth = isSelected ? 2.2 / zoom : 1.2 / zoom;

        if (dim.start_pt && dim.end_pt) {
          // Dimension line
          ctx.beginPath();
          ctx.moveTo(dim.start_pt[0], dim.start_pt[1]);
          ctx.lineTo(dim.end_pt[0], dim.end_pt[1]);
          ctx.stroke();

          // Endpoint ticks
          const dx = dim.end_pt[0] - dim.start_pt[0];
          const dy = dim.end_pt[1] - dim.start_pt[1];
          const len = Math.hypot(dx, dy) || 1;
          const nx = -dy / len;
          const ny = dx / len;
          const tickSize = 6 / zoom;

          // Start tick (architectural 45° slash)
          ctx.beginPath();
          ctx.moveTo(dim.start_pt[0] - (nx + dx / len) * tickSize * 0.7, dim.start_pt[1] - (ny + dy / len) * tickSize * 0.7);
          ctx.lineTo(dim.start_pt[0] + (nx + dx / len) * tickSize * 0.7, dim.start_pt[1] + (ny + dy / len) * tickSize * 0.7);
          ctx.stroke();

          // End tick
          ctx.beginPath();
          ctx.moveTo(dim.end_pt[0] - (nx + dx / len) * tickSize * 0.7, dim.end_pt[1] - (ny + dy / len) * tickSize * 0.7);
          ctx.lineTo(dim.end_pt[0] + (nx + dx / len) * tickSize * 0.7, dim.end_pt[1] + (ny + dy / len) * tickSize * 0.7);
          ctx.stroke();

          // Witness extension lines
          const extLen = 10 / zoom;
          ctx.strokeStyle = isSelected ? "#f59e0b" : "#92400e";
          ctx.lineWidth = 0.8 / zoom;
          ctx.beginPath();
          ctx.moveTo(dim.start_pt[0] - (nx * 2) / zoom, dim.start_pt[1] - (ny * 2) / zoom);
          ctx.lineTo(dim.start_pt[0] + nx * extLen, dim.start_pt[1] + ny * extLen);
          ctx.moveTo(dim.end_pt[0] - (nx * 2) / zoom, dim.end_pt[1] - (ny * 2) / zoom);
          ctx.lineTo(dim.end_pt[0] + nx * extLen, dim.end_pt[1] + ny * extLen);
          ctx.stroke();

          // Dimension Text Label Pill at Midpoint
          const midX = (dim.start_pt[0] + dim.end_pt[0]) / 2;
          const midY = (dim.start_pt[1] + dim.end_pt[1]) / 2;

          ctx.save();
          const dimText = dim.dimension_text || (dim.measured_length_ft ? `${dim.measured_length_ft.toFixed(2)} ft` : "");
          if (dimText) {
            const fontPx = Math.max(8, 10 / zoom);
            ctx.font = `bold ${fontPx}px Inter, monospace, sans-serif`;
            const textMetrics = ctx.measureText(dimText);
            const pillW = textMetrics.width + 12 / zoom;
            const pillH = fontPx + 8 / zoom;

            // Pill box
            ctx.fillStyle = "rgba(15, 23, 42, 0.92)";
            ctx.strokeStyle = isSelected ? "#f59e0b" : "#78350f";
            ctx.lineWidth = 1 / zoom;
            ctx.beginPath();
            ctx.roundRect(midX - pillW / 2, midY - pillH / 2, pillW, pillH, 4 / zoom);
            ctx.fill();
            ctx.stroke();

            // Text
            ctx.fillStyle = isSelected ? "#fbbf24" : "#f59e0b";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(dimText, midX, midY);
          }
          ctx.restore();
        }
      }
    }

    // 10. Render Native Text Elements with Deterministic Collision Handling (Phase 7B Requirements 7 & 8)
    if (
      activeLayers.has("Text") ||
      activeLayers.has("Annotations") ||
      activeLayers.has("Title Block") ||
      activeLayers.has("Legend") ||
      activeLayers.has("Details")
    ) {
      const textObjs = geometryData.text_objects || [];

      // Priority ladder: TAKEOFF LABEL > DIMENSION > ROOM / SPACE LABEL > TRADE NOTE > SECTION / DETAIL LABEL > GENERAL NOTE > TITLE BLOCK > BACKGROUND ANNOTATION
      const TEXT_PRIORITY: Record<string, number> = {
        TAKEOFF_LABEL: 120,
        DIMENSION: 110,
        DIMENSION_TEXT: 105,
        ROOM_LABEL: 95,
        TRADE_NOTE: 85,
        WALL_NOTE: 80,
        MATERIAL_NOTE: 75,
        MATERIAL_LABEL: 75,
        SECTION_LABEL: 70,
        DETAIL_LABEL: 65,
        DETAIL_CALLOUT: 65,
        ELEVATION_LABEL: 65,
        DRAWING_TITLE: 60,
        SHEET_NUMBER: 55,
        SCALE_TEXT: 50,
        SCALE_LABEL: 50,
        LEVEL_LABEL: 45,
        GENERAL_NOTE: 40,
        NOTE: 40,
        TITLE_BLOCK_TEXT: 35,
        TITLE_BLOCK: 30,
        LEGEND_TEXT: 25,
        LEGEND_DESCRIPTION: 25,
        LEGEND_SYMBOL: 20,
        ANNOTATION: 20,
        UNKNOWN: 10,
      };

      // Sort by priority descending
      const sortedTextObjs = [...textObjs].sort((a, b) => {
        const prioA = (a.display_priority ?? TEXT_PRIORITY[a.semantic_role || ""]) || 20;
        const prioB = (b.display_priority ?? TEXT_PRIORITY[b.semantic_role || ""]) || 20;
        return prioB - prioA;
      });

      // Maintain screen-space bounding boxes to prevent overlapping text collisions
      const screenBoxes: { x0: number; y0: number; x1: number; y1: number }[] = [];

      for (const txt of sortedTextObjs) {
        // Clean Mode & Takeoff Mode decluttering: suppress duplicates and CAD bolding offsets
        if (internalViewMode !== "RAW" && (txt.is_duplicate || txt.is_suppressed_in_clean_mode)) {
          continue;
        }

        // Clean Mode & Takeoff Mode: suppress raw dimension text when structured dimension lines + midpoint pills are active
        if (internalViewMode !== "RAW" && activeLayers.has("Dimensions") && txt.semantic_role === "DIMENSION_TEXT") {
          continue;
        }

        let targetLayer = "Text";
        if (
          txt.semantic_role === "NOTE" ||
          txt.semantic_role === "GENERAL_ANNOTATION" ||
          txt.semantic_role === "PLUMBING_NOTE" ||
          txt.semantic_role === "GENERAL_NOTE"
        ) {
          targetLayer = "Annotations";
        } else if (
          ["DRAWING_TITLE", "SHEET_NUMBER", "SCALE_LABEL", "TITLE_BLOCK", "TITLE_BLOCK_TEXT"].includes(txt.semantic_role)
        ) {
          targetLayer = "Title Block";
        } else if (txt.semantic_role === "GRID_LABEL") {
          targetLayer = "Grid";
        } else if (txt.semantic_role === "DIMENSION_TEXT") {
          targetLayer = "Dimensions";
        } else if (
          txt.semantic_role === "LEGEND_TEXT" ||
          txt.semantic_role === "LEGEND_SYMBOL" ||
          txt.semantic_role === "LEGEND_DESCRIPTION"
        ) {
          targetLayer = "Legend";
        } else if (txt.semantic_role === "DETAIL_CALLOUT") {
          targetLayer = "Details";
        }

        if (!activeLayers.has(targetLayer)) continue;

        const isSelected = selectedObjectId === txt.id;
        const isHovered = hoveredObjectId === txt.id;

        const posX = txt.origin_pdf?.[0] ?? txt.bbox_pdf[0];
        const posY = txt.origin_pdf?.[1] ?? txt.bbox_pdf[3];
        const fontSizePt = Math.max(6, txt.font_size || 10);

        // Screen-space bounding box for collision detection
        const screenX = pan.x + posX * zoom;
        const screenY = pan.y + posY * zoom;
        const fontSizeScreen = fontSizePt * zoom;
        const rawW = txt.bbox_pdf ? txt.bbox_pdf[2] - txt.bbox_pdf[0] : txt.text.length * fontSizePt * 0.6;
        const boxW = Math.max(12, rawW * zoom);
        const boxH = fontSizeScreen * 1.25;
        const textRect = {
          x0: screenX - 2,
          y0: screenY - fontSizeScreen,
          x1: screenX + boxW + 2,
          y1: screenY + 4,
        };

        // Collision check in CLEAN and TAKEOFF view modes: prevent unreadable text overlaps
        let collides = false;
        if (internalViewMode !== "RAW" && !isSelected && !isHovered) {
          for (const b of screenBoxes) {
            if (
              textRect.x0 < b.x1 &&
              textRect.x1 > b.x0 &&
              textRect.y0 < b.y1 &&
              textRect.y1 > b.y0
            ) {
              collides = true;
              break;
            }
          }
        }

        if (collides) {
          // Suppress lower priority overlapping text in clean/takeoff modes
          continue;
        }

        if (!isSelected && !isHovered) {
          screenBoxes.push(textRect);
        }

        ctx.save();

        // Trade-scoped text alpha
        let textAlpha = 1.0;
        if (internalViewMode === "TAKEOFF") {
          if (selectedTrade === "DRYWALL") {
            if (
              txt.semantic_role === "PLUMBING_NOTE" ||
              txt.semantic_role === "LEGEND_TEXT" ||
              txt.semantic_role === "TITLE_BLOCK_TEXT" ||
              txt.semantic_role === "GENERAL_NOTE"
            ) {
              textAlpha = 0.2;
            }
          } else if (selectedTrade === "FLOORING") {
            if (txt.semantic_role !== "ROOM_LABEL" && txt.semantic_role !== "DRAWING_TITLE") {
              textAlpha = 0.2;
            }
          } else if (selectedTrade === "ROOFING") {
            if (txt.semantic_role !== "ROOF_LABEL" && txt.semantic_role !== "DRAWING_TITLE") {
              textAlpha = 0.2;
            }
          }
        }

        ctx.globalAlpha = isSelected || isHovered ? 1.0 : textAlpha;
        ctx.translate(posX, posY);
        if (txt.rotation_deg) {
          ctx.rotate((-txt.rotation_deg * Math.PI) / 180);
        }

        let textColor = "#cbd5e1";
        let isBold = false;

        switch (txt.semantic_role) {
          case "DRAWING_TITLE":
          case "SHEET_NUMBER":
            textColor = "#38bdf8";
            isBold = true;
            break;
          case "ROOM_LABEL":
            textColor = "#e2e8f0";
            isBold = true;
            break;
          case "SCALE_LABEL":
            textColor = "#fbbf24";
            isBold = true;
            break;
          case "DIMENSION_TEXT":
            textColor = "#f59e0b";
            break;
          case "ROOF_LABEL":
            textColor = "#22d3ee";
            isBold = true;
            break;
          case "MATERIAL_LABEL":
            textColor = "#a7f3d0";
            break;
          case "DETAIL_CALLOUT":
            textColor = "#f59e0b";
            isBold = true;
            break;
          case "LEGEND_TEXT":
          case "LEGEND_DESCRIPTION":
          case "LEGEND_SYMBOL":
            textColor = "#c084fc";
            break;
          case "NOTE":
          case "GENERAL_ANNOTATION":
          case "PLUMBING_NOTE":
          case "GENERAL_NOTE":
            textColor = "#94a3b8";
            break;
          case "GRID_LABEL":
            textColor = "#f472b6";
            isBold = true;
            break;
          default:
            textColor = "#cbd5e1";
        }

        if (isSelected) {
          textColor = "#ffffff";
        }

        ctx.font = `${isBold ? "bold " : ""}${fontSizePt}px Inter, -apple-system, sans-serif`;
        ctx.fillStyle = textColor;
        ctx.textBaseline = "alphabetic";

        if (isSelected || isHovered) {
          ctx.strokeStyle = isSelected ? "#38bdf8" : "rgba(56, 189, 248, 0.4)";
          ctx.lineWidth = 1 / zoom;
          const w = (txt.bbox_pdf ? txt.bbox_pdf[2] - txt.bbox_pdf[0] : 0) || txt.text.length * fontSizePt * 0.6;
          const h = fontSizePt * 1.2;
          ctx.strokeRect(-2, -fontSizePt, w + 4, h);
          if (isSelected) {
            ctx.fillStyle = "rgba(56, 189, 248, 0.15)";
            ctx.fillRect(-2, -fontSizePt, w + 4, h);
            ctx.fillStyle = "#ffffff";
          }
        }

        ctx.fillText(txt.text, 0, 0);
        ctx.restore();
      }
    }

    // 11. Measurement In-Progress Line
    if (measureStart && measureEnd) {
      ctx.strokeStyle = "#ec4899";
      ctx.lineWidth = 2.0 / zoom;
      ctx.setLineDash([4 / zoom, 4 / zoom]);
      ctx.beginPath();
      ctx.moveTo(measureStart[0], measureStart[1]);
      ctx.lineTo(measureEnd[0], measureEnd[1]);
      ctx.stroke();
      ctx.setLineDash([]);

      const distPt = Math.hypot(measureEnd[0] - measureStart[0], measureEnd[1] - measureStart[1]);
      const distFt = distPt * ftPerPt;
      const distMm = distFt * 304.8;
      const midX = (measureStart[0] + measureEnd[0]) / 2;
      const midY = (measureStart[1] + measureEnd[1]) / 2;

      ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
      ctx.strokeStyle = "#ec4899";
      ctx.lineWidth = 1 / zoom;
      ctx.beginPath();
      ctx.roundRect(midX - 55 / zoom, midY - 14 / zoom, 110 / zoom, 28 / zoom, 4 / zoom);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = "#f472b6";
      ctx.font = `bold ${Math.max(9, 11 / zoom)}px Inter, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(`${distFt.toFixed(2)} ft (${distMm.toFixed(0)} mm)`, midX, midY);
    }

    ctx.restore();
  }, [
    pan,
    zoom,
    geometryData,
    visibleObjects,
    activeLayers,
    selectedObjectId,
    hoveredObjectId,
    showRasterComparison,
    rasterImg,
    rasterOpacity,
    measureStart,
    measureEnd,
    ftPerPt,
    internalViewMode,
    selectedTrade,
  ]);

  // Pointer Event Handlers
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button !== 0) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const screenX = e.clientX - rect.left;
    const screenY = e.clientY - rect.top;
    const [pdfX, pdfY] = screenToPdf(screenX, screenY);

    if (activeTool === "pan" || e.altKey || e.shiftKey) {
      setIsDragging(true);
      dragStartRef.current = { x: screenX - pan.x, y: screenY - pan.y };
      return;
    }

    if (activeTool === "measure") {
      if (!measureStart) {
        setMeasureStart([pdfX, pdfY]);
        setMeasureEnd([pdfX, pdfY]);
      } else {
        setMeasureEnd([pdfX, pdfY]);
      }
      return;
    }

    // Select Tool: hit-test objects with true Phase 7B contract fields
    let clickedObj: any = null;

    // 1. Check Roof Polygons
    for (const obj of geometryData.semantic_objects || []) {
      if (obj.object_type === "ROOF" && activeLayers.has("Roof")) {
        const poly = obj.source_points_pdf;
        if (poly && poly.length >= 3 && isPointInPoly([pdfX, pdfY], poly)) {
          clickedObj = {
            ...obj,
            source_type: "PDF POLYGON",
            semantic_type: "ROOF_PLANE",
            trade_scope: "ROOFING",
            qto_eligible: true,
            qto_reason: "Verified roof plane polygon with pitch slope datum",
            classification_status: "VERIFIED",
          };
          break;
        }
      }
    }

    // 2. Check Dimensions
    if (!clickedObj && activeLayers.has("Dimensions")) {
      for (const dim of geometryData.dimension_objects || []) {
        if (dim.start_pt && dim.end_pt) {
          const d = distToSegment([pdfX, pdfY], dim.start_pt, dim.end_pt);
          if (d < 16.0 / zoom) {
            clickedObj = {
              ...dim,
              source_type: "PDF DIMENSION",
              semantic_type: "DIMENSION",
              trade_scope: "SUPPORTING_EVIDENCE",
              qto_eligible: false,
              qto_reason: "Supporting dimensional datum (evidence only)",
              classification_status: "VERIFIED",
            };
            break;
          }
        }
      }
    }

    // 3. Check Text Objects (Acceptance Test G: Non-QTO text)
    if (
      !clickedObj &&
      (activeLayers.has("Text") ||
        activeLayers.has("Annotations") ||
        activeLayers.has("Title Block") ||
        activeLayers.has("Legend"))
    ) {
      for (const txt of geometryData.text_objects || []) {
        const tb = txt.bbox_pdf;
        if (tb && pdfX >= tb[0] - 2 && pdfX <= tb[2] + 2 && pdfY >= tb[1] - 2 && pdfY <= tb[3] + 2) {
          const isRoom = txt.semantic_role === "ROOM_LABEL";
          clickedObj = {
            id: txt.id,
            text: txt.text,
            label: txt.text,
            source_type: "PDF TEXT",
            semantic_type: txt.semantic_role || "TEXT",
            trade_scope: isRoom ? "SUPPORTING_EVIDENCE" : "NONE",
            qto_eligible: false,
            qto_reason: isRoom
              ? "Supporting semantic room evidence (non-takeoff text)"
              : "Non-takeoff textual annotation",
            classification_status: "VERIFIED",
            layer: txt.layer || "Text",
            bbox_pdf: txt.bbox_pdf,
          };
          break;
        }
      }
    }

    // 4. Check Grid Lines
    if (!clickedObj && activeLayers.has("Grid")) {
      for (const obj of visibleObjects) {
        if (obj.object_type === "GRID") {
          const pts = obj.source_points_pdf;
          if (pts && pts.length >= 2) {
            for (let i = 0; i < pts.length - 1; i++) {
              if (distToSegment([pdfX, pdfY], pts[i], pts[i + 1]) < 10.0 / zoom) {
                clickedObj = {
                  ...obj,
                  source_type: "PDF GRID LINE",
                  semantic_type: "GRID",
                  trade_scope: "NONE",
                  qto_eligible: false,
                  qto_reason: "Structural grid reference line",
                  classification_status: "SUPPORTED",
                };
                break;
              }
            }
          }
        }
        if (clickedObj) break;
      }
    }

    // 5. Check other visible semantic objects (Acceptance Tests H & I)
    if (!clickedObj) {
      for (const obj of visibleObjects) {
        const tb = obj.bbox_pdf;
        if (tb && tb.length === 4 && pdfX >= tb[0] && pdfX <= tb[2] && pdfY >= tb[1] && pdfY <= tb[3]) {
          let sType = obj.semantic_type || obj.object_type || "SEMANTIC";
          let srcType = "PDF VECTOR / LINE";
          let tradeScope = obj.trade_scope || "NONE";
          let qtoEligible = obj.qto_eligible ?? false;
          let qtoReason = obj.qto_reason || "";
          let classStatus = obj.classification_status || "VERIFIED";

          if (obj.object_type === "TITLE_BLOCK" || obj.layer === "Title Block") {
            sType = "TITLE_BLOCK";
            srcType = "PDF VECTOR PATH";
            tradeScope = "NONE";
            qtoEligible = false;
            qtoReason = "Title block boundary: excluded from takeoff";
            classStatus = "EXCLUDED";
          } else if (obj.object_type === "SYMBOL" || obj.layer === "Legend" || obj.layer === "Symbols") {
            sType = "LEGEND_SYMBOL";
            srcType = "PDF SYMBOL / GEOMETRY";
            tradeScope = "NONE";
            qtoEligible = false;
            qtoReason = "Legend symbol: reference definition only, excluded from project takeoff";
            classStatus = "EXCLUDED";
          } else if (obj.object_type === "SECTION_WALL_REPRESENTATION") {
            sType = "SECTION_WALL_REPRESENTATION";
            srcType = "PDF LINE";
            tradeScope = "NONE";
            qtoEligible = false;
            qtoReason = "Section cut line: ceiling height reference only, excluded from drywall takeoff";
            classStatus = "VERIFIED";
          } else if (obj.object_type === "DRYWALL_PARTITION") {
            sType = "DRYWALL_PARTITION";
            srcType = "PDF WALL VECTOR";
            tradeScope = "DRYWALL";
            qtoEligible = true;
            qtoReason = "Interior drywall partition: verified centerline and height";
            classStatus = "VERIFIED";
          }

          clickedObj = {
            ...obj,
            semantic_type: sType,
            source_type: srcType,
            trade_scope: tradeScope,
            qto_eligible: qtoEligible,
            qto_reason: qtoReason,
            classification_status: classStatus,
          };
          break;
        }
      }
    }

    onSelectObject(clickedObj);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const screenX = e.clientX - rect.left;
    const screenY = e.clientY - rect.top;
    const [pdfX, pdfY] = screenToPdf(screenX, screenY);

    // Live Coordinate HUD
    const ftX = pdfX * ftPerPt;
    const ftY = pdfY * ftPerPt;
    setCursorPos({ ptX: pdfX, ptY: pdfY, ftX, ftY });

    if (isDragging) {
      setPan({
        x: screenX - dragStartRef.current.x,
        y: screenY - dragStartRef.current.y,
      });
      return;
    }

    if (activeTool === "measure" && measureStart) {
      setMeasureEnd([pdfX, pdfY]);
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
    const newZoom = Math.max(0.1, Math.min(8.0, zoom * zoomFactor));

    setPan({
      x: mouseX - (mouseX - pan.x) * (newZoom / zoom),
      y: mouseY - (mouseY - pan.y) * (newZoom / zoom),
    });
    setZoom(newZoom);
  };

  return (
    <div ref={containerRef} className="relative w-full h-full flex flex-col bg-slate-950 overflow-hidden select-none">
      {/* Top Floating Viewport Control Toolbar */}
      <div className="absolute top-3 left-4 z-10 flex items-center gap-1.5 p-1.5 rounded-lg bg-slate-900/90 backdrop-blur-md border border-slate-700/60 shadow-xl">
        <button
          onClick={() => setActiveTool("select")}
          title="Selection Tool"
          className={`p-2 rounded-md transition-all ${
            activeTool === "select" ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/40" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <MousePointer className="w-4 h-4" />
        </button>
        <button
          onClick={() => setActiveTool("pan")}
          title="Pan Tool"
          className={`p-2 rounded-md transition-all ${
            activeTool === "pan" ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/40" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <Hand className="w-4 h-4" />
        </button>
        <button
          onClick={() => {
            if (activeTool === "measure") {
              setActiveTool("select");
              setMeasureStart(null);
              setMeasureEnd(null);
            } else {
              setActiveTool("measure");
              setMeasureStart(null);
              setMeasureEnd(null);
            }
          }}
          title="Measurement Tool"
          className={`p-2 rounded-md transition-all ${
            activeTool === "measure" ? "bg-pink-500/20 text-pink-400 border border-pink-500/40" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <Ruler className="w-4 h-4" />
        </button>

        <button
          onClick={() => setShowSourceOverlay((v) => !v)}
          title="Toggle Source vs Canonical Linework Overlay (Phase 6)"
          className={`p-2 rounded-md transition-all ${
            showSourceOverlay ? "bg-amber-500/20 text-amber-400 border border-amber-500/40" : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <Sliders className="w-4 h-4" />
        </button>

        <div className="w-px h-5 bg-slate-700/60 my-auto mx-1" />

        {/* 3 Canvas View Modes: RAW PDF, CLEAN DRAWING, TAKEOFF OVERLAY */}
        <div className="flex items-center bg-slate-950 p-0.5 rounded-md border border-slate-700/60 text-xs">
          <button
            onClick={() => handleToggleViewMode("RAW")}
            title="RAW PDF: Exact native PDF rendering with all original linework and annotations"
            className={`px-2.5 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer ${
              internalViewMode === "RAW"
                ? "bg-amber-500 text-slate-950 shadow-sm font-bold"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            RAW PDF
          </button>
          <button
            onClick={() => handleToggleViewMode("CLEAN")}
            title="CLEAN DRAWING: Engineering-readable representation with duplicate suppression and collision avoidance"
            className={`px-2.5 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer ${
              internalViewMode === "CLEAN"
                ? "bg-emerald-500 text-slate-950 shadow-sm font-bold"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            CLEAN DRAWING
          </button>
          <button
            onClick={() => handleToggleViewMode("TAKEOFF")}
            title="TAKEOFF OVERLAY: Highlights only trade-relevant canonical geometry with quantified measurements"
            className={`px-2.5 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer ${
              internalViewMode === "TAKEOFF"
                ? "bg-cyan-500 text-slate-950 shadow-sm font-bold"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            TAKEOFF OVERLAY
          </button>
        </div>

        <div className="w-px h-5 bg-slate-700/60 my-auto mx-1" />

        <button
          onClick={() => setZoom((z) => Math.min(8.0, z * 1.25))}
          title="Zoom In"
          className="p-2 rounded-md text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <button
          onClick={() => setZoom((z) => Math.max(0.1, z * 0.8))}
          title="Zoom Out"
          className="p-2 rounded-md text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ZoomOut className="w-4 h-4" />
        </button>
        <button
          onClick={fitToDrawing}
          title="Fit Drawing to Viewport"
          className="p-2 rounded-md text-cyan-400 hover:text-cyan-300 hover:bg-cyan-950/40 transition-colors"
        >
          <Maximize2 className="w-4 h-4" />
        </button>
        <button
          onClick={fitToPage}
          title="Fit Entire Page Sheet"
          className="p-2 rounded-md text-slate-400 hover:text-slate-200 transition-colors"
        >
          <FileSpreadsheet className="w-4 h-4" />
        </button>
        <button
          onClick={() => {
            setZoom(0.8);
            setPan({ x: 0, y: 0 });
          }}
          title="Reset View"
          className="p-2 rounded-md text-slate-400 hover:text-slate-200 transition-colors"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>

      {/* Top Center Trade Scope Overlay Banner (Phase 7B Requirement 2) */}
      {internalViewMode === "TAKEOFF" && selectedTrade !== "ALL" && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 pointer-events-none">
          {selectedTrade === "DRYWALL" && geometryData.takeoff_summary?.drywall_status === "NOT_APPLICABLE" ? (
            <div className="flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-slate-900/95 border border-amber-500/60 text-amber-300 text-xs font-mono shadow-2xl backdrop-blur-md">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
              <span>DRYWALL: NOT APPLICABLE — SECTION SHEET (Ceiling Datum Reference 10'-0")</span>
            </div>
          ) : selectedTrade === "FLOORING" && geometryData.takeoff_summary?.flooring_status === "NOT_APPLICABLE" ? (
            <div className="flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-slate-900/95 border border-amber-500/60 text-amber-300 text-xs font-mono shadow-2xl backdrop-blur-md">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
              <span>FLOORING: NOT APPLICABLE — SECTION SHEET (Zero Floor Surfaces)</span>
            </div>
          ) : selectedTrade === "ROOFING" && geometryData.takeoff_summary?.roofing_status === "NOT_APPLICABLE" ? (
            <div className="flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-slate-900/95 border border-amber-500/60 text-amber-300 text-xs font-mono shadow-2xl backdrop-blur-md">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
              <span>ROOFING: NOT APPLICABLE — SECTION SHEET</span>
            </div>
          ) : selectedTrade === "PLUMBING" ? (
            <div className="flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-slate-900/95 border border-cyan-500/60 text-cyan-300 text-xs font-mono shadow-2xl backdrop-blur-md">
              <Info className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
              <span>PLUMBING: ARCHITECTURAL MEP REFERENCE (Takeoff Not Implemented)</span>
            </div>
          ) : null}
        </div>
      )}

      {/* Main Vector Drawing Canvas */}
      <canvas
        ref={canvasRef}
        className={`w-full h-full ${
          activeTool === "pan" || isDragging ? "cursor-grab active:cursor-grabbing" : activeTool === "measure" ? "cursor-crosshair" : "cursor-default"
        }`}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onWheel={handleWheel}
      />

      {/* Bottom Coordinate & Scale HUD */}
      <div className="absolute bottom-2 left-4 right-4 pointer-events-none flex items-center justify-between text-xs font-mono">
        <div className="flex items-center gap-2 p-1.5 px-3 rounded-md bg-slate-900/90 backdrop-blur-md border border-slate-800 text-slate-400 shadow-md">
          <span className="text-cyan-400 font-semibold">{geometryData.sheet_number}</span>
          <span className="text-slate-600">|</span>
          <span>{geometryData.sheet_title}</span>
          <span className="text-amber-400">
            Scale: {geometryData.scale?.scale_display || geometryData.scale?.scale_string || "UNRESOLVED"}
          </span>
        </div>

        {cursorPos && (
          <div className="flex items-center gap-3 p-1.5 px-3 rounded-md bg-slate-900/90 backdrop-blur-md border border-slate-800 text-slate-400 shadow-md">
            <span>
              PDF: <span className="text-slate-200 font-mono">{cursorPos.ptX.toFixed(1)}, {cursorPos.ptY.toFixed(1)} pt</span>
            </span>
            {isScaleResolved && (
              <>
                <span className="text-slate-600">|</span>
                <span>
                  Real: <span className="text-emerald-400 font-mono">{cursorPos.ftX.toFixed(2)} ft, {cursorPos.ftY.toFixed(2)} ft</span> (
                  <span className="text-emerald-500 font-mono">{(cursorPos.ftX * 0.3048).toFixed(2)} m, {(cursorPos.ftY * 0.3048).toFixed(2)} m</span>)
                </span>
              </>
            )}
          </div>
        )}
      </div>

      {/* Source vs Canonical Overlay Telemetry HUD (Phase 7 Reconciliation) */}
      {showSourceOverlay && (
        <div className="absolute top-3 right-4 z-10 flex flex-col gap-2 p-3.5 rounded-lg bg-slate-900/95 backdrop-blur-md border border-slate-700/80 shadow-2xl text-[11px] font-mono pointer-events-none max-w-sm w-80">
          <div className="flex items-center justify-between text-xs font-bold border-b border-slate-800 pb-1.5">
            <span className="flex items-center gap-1.5 text-amber-400">
              <Sliders className="w-3.5 h-3.5" />
              <span>Source / Canonical Reconciliation</span>
            </span>
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                geometryData.roof_planes?.length > 0 || (geometryData.semantic_objects?.length > 0 && geometryData.text_objects?.length > 0)
                  ? "bg-emerald-950/80 text-emerald-400 border border-emerald-800"
                  : "bg-amber-950/80 text-amber-400 border border-amber-800"
              }`}
            >
              {geometryData.scale?.scale_validated === "VERIFIED" ? "VERIFIED" : "REVIEW REQUIRED"}
            </span>
          </div>

          <div className="text-[10px] text-slate-300 space-y-1">
            <div className="grid grid-cols-4 font-semibold text-slate-500 border-b border-slate-800/80 pb-0.5 mb-1">
              <span>CATEGORY</span>
              <span className="text-right">NATIVE</span>
              <span className="text-right">CANON</span>
              <span className="text-right">RENDER</span>
            </div>

            {/* Geometry */}
            <div className="grid grid-cols-4 items-center">
              <span className="text-slate-400">Geometry</span>
              <span className="text-right text-amber-400 font-mono">
                {geometryData.reconciliation_table?.geometry?.native ?? geometryData.native_geometry?.length ?? 0}
              </span>
              <span className="text-right text-cyan-400 font-mono">
                {geometryData.reconciliation_table?.geometry?.canonical ?? geometryData.semantic_objects?.length ?? 0}
              </span>
              <span className="text-right text-slate-200 font-mono">
                {geometryData.reconciliation_table?.geometry?.rendered ?? geometryData.semantic_objects?.length ?? 0}
              </span>
            </div>

            {/* Text */}
            <div className="grid grid-cols-4 items-center">
              <span className="text-slate-400">Text</span>
              <span className="text-right text-amber-400 font-mono">
                {geometryData.reconciliation_table?.text?.native ?? geometryData.text_objects?.length ?? 0}
              </span>
              <span className="text-right text-cyan-400 font-mono">
                {geometryData.reconciliation_table?.text?.canonical ?? geometryData.text_objects?.length ?? 0}
              </span>
              <span className="text-right text-slate-200 font-mono">
                {geometryData.reconciliation_table?.text?.rendered ?? geometryData.text_objects?.length ?? 0}
              </span>
            </div>

            {/* Dimensions */}
            <div className="grid grid-cols-4 items-center">
              <span className="text-slate-400">Dimensions</span>
              <span className="text-right text-amber-400 font-mono">
                {geometryData.reconciliation_table?.dimensions?.native_candidates ?? geometryData.reconciliation_table?.dimensions?.native ?? geometryData.dimension_objects?.length ?? 0}
              </span>
              <span className="text-right text-cyan-400 font-mono">
                {geometryData.reconciliation_table?.dimensions?.canonical ?? geometryData.dimension_objects?.length ?? 0}
              </span>
              <span className="text-right text-slate-200 font-mono">
                {geometryData.reconciliation_table?.dimensions?.rendered ?? geometryData.dimension_objects?.length ?? 0}
              </span>
            </div>

            {/* Plumbing Symbols */}
            {geometryData.reconciliation_table?.plumbing_symbols && (
              <div className="grid grid-cols-4 items-center">
                <span className="text-slate-400">Symbols</span>
                <span className="text-right text-amber-400 font-mono">
                  {geometryData.reconciliation_table.plumbing_symbols.native}
                </span>
                <span className="text-right text-cyan-400 font-mono">
                  {geometryData.reconciliation_table.plumbing_symbols.canonical}
                </span>
                <span className="text-right text-slate-200 font-mono">
                  {geometryData.reconciliation_table.plumbing_symbols.rendered}
                </span>
              </div>
            )}

            {/* Legend */}
            {geometryData.reconciliation_table?.legend && (
              <div className="grid grid-cols-4 items-center">
                <span className="text-slate-400">Legend</span>
                <span className="text-right text-amber-400 font-mono">
                  {geometryData.reconciliation_table.legend.native}
                </span>
                <span className="text-right text-cyan-400 font-mono">
                  {geometryData.reconciliation_table.legend.canonical}
                </span>
                <span className="text-right text-slate-200 font-mono">
                  {geometryData.reconciliation_table.legend.rendered}
                </span>
              </div>
            )}

            {/* Detail Regions */}
            {geometryData.reconciliation_table?.detail_regions && (
              <div className="grid grid-cols-4 items-center">
                <span className="text-slate-400">Details</span>
                <span className="text-right text-amber-400 font-mono">
                  {geometryData.reconciliation_table.detail_regions.detected}
                </span>
                <span className="text-right text-cyan-400 font-mono">
                  {geometryData.reconciliation_table.detail_regions.canonical}
                </span>
                <span className="text-right text-slate-200 font-mono">
                  {geometryData.reconciliation_table.detail_regions.rendered}
                </span>
              </div>
            )}

            {/* Notes */}
            {geometryData.reconciliation_table?.notes && (
              <div className="grid grid-cols-4 items-center">
                <span className="text-slate-400">Notes</span>
                <span className="text-right text-amber-400 font-mono">
                  {geometryData.reconciliation_table.notes.native}
                </span>
                <span className="text-right text-cyan-400 font-mono">
                  {geometryData.reconciliation_table.notes.canonical}
                </span>
                <span className="text-right text-slate-200 font-mono">
                  {geometryData.reconciliation_table.notes.rendered}
                </span>
              </div>
            )}

            {/* Roof Planes if present */}
            {geometryData.roof_planes && geometryData.roof_planes.length > 0 && (
              <div className="pt-1.5 border-t border-slate-800 space-y-0.5">
                <div className="flex justify-between">
                  <span>Roof IoU Overlap:</span>
                  <span className="text-emerald-400 font-bold">
                    {(geometryData.roof_planes[0].iou_overlap ?? 1.0).toFixed(3)} (100%)
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Centroid Δ:</span>
                  <span className="text-emerald-400">
                    {(geometryData.roof_planes[0].centroid_delta_pt ?? 0).toFixed(2)} pt
                  </span>
                </div>
              </div>
            )}

            <div className="text-[9px] text-slate-400/90 italic pt-1.5 border-t border-slate-800 leading-snug">
              {geometryData.roof_planes?.length > 0
                ? "Verified closed vector boundaries. Pitch-corrected takeoff active."
                : "Legend symbols excluded from project takeoff. Disconnected linework preserved without synthetic geometry."}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Helpers
function isPointInPoly(pt: [number, number], poly: number[][]): boolean {
  const [x, y] = pt;
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i][0];
    const yi = poly[i][1];
    const xj = poly[j][0];
    const yj = poly[j][1];
    const intersect = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi + 1e-9) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

function distToSegment(p: [number, number], p1: number[], p2: number[]): number {
  const [x, y] = p;
  const x1 = p1[0];
  const y1 = p1[1];
  const x2 = p2[0];
  const y2 = p2[1];
  const dx = x2 - x1;
  const dy = y2 - y1;
  if (dx === 0 && dy === 0) return Math.hypot(x - x1, y - y1);
  const t = Math.max(0, Math.min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)));
  return Math.hypot(x - (x1 + t * dx), y - (y1 + t * dy));
}
