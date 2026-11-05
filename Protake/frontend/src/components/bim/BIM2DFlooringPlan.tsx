import React, { useRef, useEffect, useState, useMemo, useCallback } from "react";
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  Layers,
  Compass,
  Filter,
  CheckCircle2,
  AlertTriangle,
  Box,
  Eye,
  Crosshair,
  RotateCcw,
  Sparkles,
  MousePointer,
  Hand,
  Ruler,
  Download,
  X,
} from "lucide-react";

/** Formats a distance in decimal feet to architectural feet & inches (e.g. 14'-6") */
export function formatDimensionFt(distFt: number): string {
  if (isNaN(distFt) || distFt <= 0) return `0'-0"`;
  const feet = Math.floor(distFt);
  const inches = Math.round((distFt - feet) * 12);
  if (inches >= 12) {
    return `${feet + 1}'-0"`;
  }
  return `${feet}'-${inches}"`;
}

export const FLOORING_PALETTE: Record<
  string,
  {
    hex: number;
    css: string;
    fillRgba: string;
    borderCss: string;
    label: string;
    code: string;
    hatchType: "grid" | "plank" | "offset_plank" | "stipple" | "concrete" | "hazard";
  }
> = {
  TILE_CERAMIC_PORCELAIN: {
    hex: 0x0d9488,
    css: "#0d9488",
    fillRgba: "rgba(13, 148, 136, 0.22)",
    borderCss: "#2dd4bf",
    label: "Ceramic / Porcelain Tile",
    code: "TILE",
    hatchType: "grid",
  },
  HARDWOOD_FLOORING: {
    hex: 0xb45309,
    css: "#b45309",
    fillRgba: "rgba(180, 83, 9, 0.22)",
    borderCss: "#f59e0b",
    label: "Hardwood Flooring",
    code: "HARDWOOD",
    hatchType: "plank",
  },
  LAMINATE_FLOORING: {
    hex: 0xd97706,
    css: "#d97706",
    fillRgba: "rgba(217, 119, 6, 0.22)",
    borderCss: "#fbbf24",
    label: "Laminate Flooring",
    code: "LVP",
    hatchType: "offset_plank",
  },
  CARPET_TILE: {
    hex: 0x475569,
    css: "#475569",
    fillRgba: "rgba(71, 85, 105, 0.25)",
    borderCss: "#94a3b8",
    label: "Carpet Tile",
    code: "CARPET",
    hatchType: "stipple",
  },
  CARPET_BROADLOOM: {
    hex: 0x475569,
    css: "#475569",
    fillRgba: "rgba(71, 85, 105, 0.25)",
    borderCss: "#94a3b8",
    label: "Carpet Broadloom",
    code: "CARPET",
    hatchType: "stipple",
  },
  RESILIENT_VINYL_LVT: {
    hex: 0x059669,
    css: "#059669",
    fillRgba: "rgba(5, 150, 105, 0.22)",
    borderCss: "#34d399",
    label: "Resilient Vinyl / LVT",
    code: "RESILIENT",
    hatchType: "offset_plank",
  },
  CONCRETE_POLISHED_SEALED: {
    hex: 0x64748b,
    css: "#64748b",
    fillRgba: "rgba(100, 116, 139, 0.20)",
    borderCss: "#cbd5e1",
    label: "Polished Concrete",
    code: "CONCRETE",
    hatchType: "concrete",
  },
  UNASSIGNED_FINISH: {
    hex: 0xd97706,
    css: "#d97706",
    fillRgba: "rgba(217, 119, 6, 0.20)",
    borderCss: "#f59e0b",
    label: "Unassigned Finish",
    code: "REVIEW",
    hatchType: "hazard",
  },
  REVIEW_REQUIRED: {
    hex: 0xd97706,
    css: "#d97706",
    fillRgba: "rgba(217, 119, 6, 0.20)",
    borderCss: "#f59e0b",
    label: "Review Required",
    code: "REVIEW",
    hatchType: "hazard",
  },
};

/** Extracts concise, human-readable Room ID without debug prefixes or raw long strings */
export function getCleanRoomTag(elem: any, fallbackIndex: number): string {
  const name = String(elem.source_name || elem.name || "").trim();

  // Pattern 1: Exact room codes like 20WC.01, 20BOH.07, 101, RM-102, BED-1, OFF-204
  const codeMatch = name.match(/\b([0-9]{1,2}[A-Z]{2,4}\.[0-9]{1,3}|RM[-_ ]?[0-9]{1,4}|[A-Z]{2,4}[-_][0-9]{1,3}|[0-9]{3,4})\b/i);
  if (codeMatch) return codeMatch[1].toUpperCase();

  // Pattern 2: Clean room descriptions (e.g. "Space: Corridor 101" -> "CORRIDOR 101")
  if (name.includes(":")) {
    const parts = name.split(":");
    const lastPart = parts[parts.length - 1].trim();
    if (lastPart && !lastPart.startsWith("51") && lastPart.length < 20) {
      return lastPart.replace(/^nbl_/i, "").toUpperCase();
    }
  }

  // Pattern 3: Clean material abbreviation or short ID
  if (name.toLowerCase().startsWith("floor:")) {
    const sub = name.substring(6).trim();
    const clean = sub.replace(/^nbl_/i, "").replace(/_.*$/, "");
    if (clean && clean.length <= 12) return clean.toUpperCase();
  }

  const catCode = FLOORING_PALETTE[elem.flooring_category]?.code || "FLR";
  return `${catCode}-${String(fallbackIndex + 1).padStart(2, "0")}`;
}

export interface BIM2DFlooringPlanProps {
  flooringElements: any[];
  walls?: any[];
  storeys?: any[];
  selectedStorey?: string;
  onSelectStorey?: (storeyName: string) => void;
  selectedFlooringGuid: string | null;
  onSelectFlooringGuid: (guid: string) => void;
}

interface PlacedBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export default function BIM2DFlooringPlan({
  flooringElements,
  walls = [],
  storeys = [],
  selectedStorey = "ALL",
  onSelectStorey,
  selectedFlooringGuid,
  onSelectFlooringGuid,
}: BIM2DFlooringPlanProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [zoom, setZoom] = useState<number>(24);
  const [isDragging, setIsDragging] = useState(false);
  const dragStart = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  const [hoveredGuid, setHoveredGuid] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState<"select" | "pan" | "measure">("select");
  const [showDimensions, setShowDimensions] = useState(true);
  const [showWallsBackdrop, setShowWallsBackdrop] = useState(true);
  const [showRoomTags, setShowRoomTags] = useState(true);
  const [showHatches, setShowHatches] = useState(true);
  const [showGrid, setShowGrid] = useState(true);
  const [showLegend, setShowLegend] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<string>("ALL");

  // Interactive CAD Tape Measurement State
  const [measureStart, setMeasureStart] = useState<{ x: number; y: number } | null>(null);
  const [measureEnd, setMeasureEnd] = useState<{ x: number; y: number } | null>(null);
  const [liveCursorWorld, setLiveCursorWorld] = useState<{ x: number; y: number } | null>(null);

  // Determine active isolated storey: prioritize storey with highest eligible flooring SF
  const activeStorey = useMemo(() => {
    if (selectedStorey && selectedStorey !== "ALL") return selectedStorey;
    const storeyStats: Record<string, { count: number; sf: number }> = {};
    flooringElements.forEach((f) => {
      const sName = f.storey_name || "Level 01";
      if (!storeyStats[sName]) storeyStats[sName] = { count: 0, sf: 0 };
      if (f.qto_eligibility === "ELIGIBLE") {
        storeyStats[sName].count += 1;
        storeyStats[sName].sf += (f.net_area_sqft || f.gross_area_sqft || 0);
      }
    });
    let bestStorey = "";
    let maxSf = -1;
    for (const [st, stats] of Object.entries(storeyStats)) {
      if (stats.sf > maxSf) {
        maxSf = stats.sf;
        bestStorey = st;
      }
    }
    if (bestStorey && maxSf > 0) return bestStorey;

    // Fallback: storey with most elements
    const firstWithFlooring = storeys.find((st) =>
      flooringElements.some((f) => f.storey_name === st.name || f.storey_id === st.id)
    );
    return firstWithFlooring?.name || (storeys[0]?.name ?? "ALL");
  }, [selectedStorey, storeys, flooringElements]);

  // Filter elements by active storey and category
  const filteredElements = useMemo(() => {
    return flooringElements.filter((elem: any) => {
      const matchStorey =
        activeStorey === "ALL" ||
        elem.storey_name === activeStorey ||
        elem.storey_id === activeStorey;
      const matchCat =
        categoryFilter === "ALL" || elem.flooring_category === categoryFilter;
      return matchStorey && matchCat;
    });
  }, [flooringElements, activeStorey, categoryFilter]);

  // Filter walls for backdrop
  const filteredWalls = useMemo(() => {
    if (!showWallsBackdrop) return [];
    return walls.filter((w: any) => {
      return (
        activeStorey === "ALL" ||
        w.storey_name === activeStorey ||
        w.storey_id === activeStorey
      );
    });
  }, [walls, activeStorey, showWallsBackdrop]);

  // Compute storey total SF
  const storeyTotalSF = useMemo(() => {
    return filteredElements
      .filter((e: any) => e.qto_eligibility === "ELIGIBLE")
      .reduce((sum: number, e: any) => sum + (e.net_area_sqft || e.gross_area_sqft || 0), 0);
  }, [filteredElements]);

  // Auto-fit to active storey flooring and walls on initial load or storey change
  const handleFitToStorey = useCallback(() => {
    if (filteredElements.length === 0 && filteredWalls.length === 0) return;
    let minX = Infinity,
      maxX = -Infinity,
      minY = Infinity,
      maxY = -Infinity;

    filteredElements.forEach((elem) => {
      let pts = elem.vertices || [];
      if (pts.length < 3 && elem.bbox) {
        pts = [
          [elem.bbox.min_x, elem.bbox.min_y],
          [elem.bbox.max_x, elem.bbox.min_y],
          [elem.bbox.max_x, elem.bbox.max_y],
          [elem.bbox.min_x, elem.bbox.max_y],
        ];
      }
      pts.forEach((pt: any) => {
        if (pt[0] < minX) minX = pt[0];
        if (pt[0] > maxX) maxX = pt[0];
        if (pt[1] < minY) minY = pt[1];
        if (pt[1] > maxY) maxY = pt[1];
      });
    });

    filteredWalls.forEach((w: any) => {
      if (w.start_point) {
        if (w.start_point[0] < minX) minX = w.start_point[0];
        if (w.start_point[0] > maxX) maxX = w.start_point[0];
        if (w.start_point[1] < minY) minY = w.start_point[1];
        if (w.start_point[1] > maxY) maxY = w.start_point[1];
      }
      if (w.end_point) {
        if (w.end_point[0] < minX) minX = w.end_point[0];
        if (w.end_point[0] > maxX) maxX = w.end_point[0];
        if (w.end_point[1] < minY) minY = w.end_point[1];
        if (w.end_point[1] > maxY) maxY = w.end_point[1];
      }
    });

    if (minX !== Infinity && maxX !== -Infinity && containerRef.current) {
      const w = containerRef.current.clientWidth || 800;
      const h = containerRef.current.clientHeight || 600;
      const spanX = Math.max(10, maxX - minX);
      const spanY = Math.max(10, maxY - minY);
      const targetZoom = Math.min((w * 0.75) / spanX, (h * 0.75) / spanY, 50);
      const midX = (minX + maxX) / 2;
      const midY = (minY + maxY) / 2;

      setZoom(Math.max(8, Math.min(targetZoom, 60)));
      setPan({ x: -midX * targetZoom, y: midY * targetZoom });
    }
  }, [filteredElements, filteredWalls]);

  useEffect(() => {
    handleFitToStorey();
  }, [activeStorey, handleFitToStorey]);

  // Center smoothly when an element is selected
  useEffect(() => {
    if (selectedFlooringGuid) {
      const selected = flooringElements.find(
        (e: any) => (e.ifc_guid || e.id) === selectedFlooringGuid
      );
      if (selected?.vertices && selected.vertices.length > 0) {
        let sumX = 0,
          sumY = 0;
        selected.vertices.forEach((pt: any) => {
          sumX += pt[0] || 0;
          sumY += pt[1] || 0;
        });
        const avgX = sumX / selected.vertices.length;
        const avgY = sumY / selected.vertices.length;
        setPan({ x: -avgX * zoom, y: avgY * zoom });
      }
    }
  }, [selectedFlooringGuid]);

  // Draw Architectural Hatch Patterns
  const drawHatchPattern = (
    ctx: CanvasRenderingContext2D,
    hatchType: string,
    minX: number,
    minY: number,
    maxX: number,
    maxY: number,
    color: string
  ) => {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 0.8;

    if (hatchType === "grid") {
      // Tile grid hatch
      const spacing = 10;
      for (let x = minX - 10; x <= maxX + 10; x += spacing) {
        ctx.beginPath();
        ctx.moveTo(x, minY);
        ctx.lineTo(x, maxY);
        ctx.stroke();
      }
      for (let y = minY - 10; y <= maxY + 10; y += spacing) {
        ctx.beginPath();
        ctx.moveTo(minX, y);
        ctx.lineTo(maxX, y);
        ctx.stroke();
      }
    } else if (hatchType === "plank" || hatchType === "offset_plank") {
      // Wood / LVP horizontal planks
      const spacing = 12;
      for (let y = minY - 10; y <= maxY + 10; y += spacing) {
        ctx.beginPath();
        ctx.moveTo(minX, y);
        ctx.lineTo(maxX, y);
        ctx.stroke();
      }
      // Staggered vertical ticks
      const colSpacing = 32;
      let rowIdx = 0;
      for (let y = minY - 10; y <= maxY + 10; y += spacing) {
        const offset = (rowIdx % 2) * (colSpacing / 2);
        for (let x = minX - 10 + offset; x <= maxX + 10; x += colSpacing) {
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineTo(x, y + spacing);
          ctx.stroke();
        }
        rowIdx++;
      }
    } else if (hatchType === "hazard") {
      // 45 degree hazard caution stripes
      const spacing = 14;
      const diagLen = (maxX - minX) + (maxY - minY) + 40;
      for (let d = -diagLen; d <= diagLen; d += spacing) {
        ctx.beginPath();
        ctx.moveTo(minX + d, minY);
        ctx.lineTo(minX + d + (maxY - minY), maxY);
        ctx.stroke();
      }
    } else if (hatchType === "stipple" || hatchType === "concrete") {
      // Fine dot stipple
      ctx.fillStyle = color;
      const dotSpacing = hatchType === "concrete" ? 14 : 10;
      for (let x = minX; x <= maxX; x += dotSpacing) {
        for (let y = minY; y <= maxY; y += dotSpacing) {
          ctx.beginPath();
          ctx.arc(x + ((y % 2) * 4), y, 1.0, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
    ctx.restore();
  };

  // Helper: check if two boxes overlap
  const boxesOverlap = (b1: PlacedBox, b2: PlacedBox, padding = 4) => {
    return !(
      b1.x + b1.w + padding < b2.x ||
      b1.x > b2.x + b2.w + padding ||
      b1.y + b1.h + padding < b2.y ||
      b1.y > b2.y + b2.h + padding
    );
  };

  // Main Canvas Rendering Loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.parentElement?.clientWidth || 800;
    const height = canvas.parentElement?.clientHeight || 600;
    const dpr = Math.min(window.devicePixelRatio || 2, 2);
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    // Dark architectural CAD canvas background
    ctx.fillStyle = "#050b14";
    ctx.fillRect(0, 0, width, height);

    const originX = width / 2 + pan.x;
    const originY = height / 2 + pan.y;

    // 1. Precision Coordinate Grid with Major/Minor Blueprint Hierarchy
    if (showGrid) {
      const minorGrid = zoom * 2; // 2-ft minor grid
      const majorGrid = zoom * 10; // 10-ft major grid
      const startMinorX = ((pan.x % minorGrid) + minorGrid) % minorGrid;
      const startMinorY = ((pan.y % minorGrid) + minorGrid) % minorGrid;
      const startMajorX = ((pan.x % majorGrid) + majorGrid) % majorGrid;
      const startMajorY = ((pan.y % majorGrid) + majorGrid) % majorGrid;

      // Minor grid lines
      ctx.strokeStyle = "rgba(14, 28, 46, 0.4)";
      ctx.lineWidth = 0.5;
      for (let x = startMinorX; x < width; x += minorGrid) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = startMinorY; y < height; y += minorGrid) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // Major grid lines
      ctx.strokeStyle = "rgba(22, 45, 74, 0.65)";
      ctx.lineWidth = 0.8;
      for (let x = startMajorX; x < width; x += majorGrid) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = startMajorY; y < height; y += majorGrid) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // Precision '+' crosshair ticks at major intersections
      ctx.strokeStyle = "rgba(56, 189, 248, 0.35)";
      ctx.lineWidth = 1;
      const tick = 3;
      for (let x = startMajorX; x < width; x += majorGrid) {
        for (let y = startMajorY; y < height; y += majorGrid) {
          ctx.beginPath();
          ctx.moveTo(x - tick, y);
          ctx.lineTo(x + tick, y);
          ctx.moveTo(x, y - tick);
          ctx.lineTo(x, y + tick);
          ctx.stroke();
        }
      }
    }

    // 2. High-Contrast Architectural Walls Context (Double-line CAD drafting)
    if (showWallsBackdrop && filteredWalls.length > 0) {
      filteredWalls.forEach((w: any) => {
        const sx = originX + (w.start_point?.[0] || 0) * zoom;
        const sy = originY - (w.start_point?.[1] || 0) * zoom;
        const ex =
          originX +
          (w.end_point?.[0] || (w.start_point?.[0] || 0) + (w.length_ft || 10)) * zoom;
        const ey = originY - (w.end_point?.[1] || (w.start_point?.[1] || 0)) * zoom;

        const thickPx = Math.max(2.5, ((w.thickness_in || 6.0) / 12.0) * zoom);

        // Core fill
        ctx.beginPath();
        ctx.moveTo(sx, sy);
        ctx.lineTo(ex, ey);
        ctx.strokeStyle = w.is_external ? "#1e293b" : "#131d2e";
        ctx.lineWidth = thickPx;
        ctx.lineCap = "square";
        ctx.stroke();

        // Architectural double boundary strokes
        const dx = ex - sx;
        const dy = ey - sy;
        const len = Math.hypot(dx, dy);
        if (len > 0) {
          const nx = (-dy / len) * (thickPx / 2);
          const ny = (dx / len) * (thickPx / 2);
          ctx.strokeStyle = w.is_external ? "#475569" : "#2d3c52";
          ctx.lineWidth = 0.8;
          ctx.beginPath();
          ctx.moveTo(sx + nx, sy + ny);
          ctx.lineTo(ex + nx, ey + ny);
          ctx.moveTo(sx - nx, sy - ny);
          ctx.lineTo(ex - nx, ey - ny);
          ctx.stroke();
        }
      });
    }

    // Array to store placed label boxes to prevent collisions
    const placedLabelBoxes: PlacedBox[] = [];

    // 3. Render Flooring Surface Polygons & Hatches
    filteredElements.forEach((elem: any, elemIdx: number) => {
      const guid = elem.ifc_guid || elem.id;
      const isSelected = guid === selectedFlooringGuid;
      const isHovered = guid === hoveredGuid;
      const category = elem.flooring_category || "UNASSIGNED_FINISH";
      const palette = FLOORING_PALETTE[category] || FLOORING_PALETTE.UNASSIGNED_FINISH;
      const isSpatial = elem.evidence_type === "SPATIAL_SPACE_FINISH";
      const isStructuralSlab = elem.source_entity_type === "IFC_SLAB" && elem.qto_eligibility !== "ELIGIBLE";

      // Robust vertex extraction: vertices if available, or bbox fallback
      let verts: number[][] = [];
      if (elem.vertices && elem.vertices.length >= 3) {
        verts = elem.vertices;
      } else if (elem.bbox) {
        verts = [
          [elem.bbox.min_x, elem.bbox.min_y],
          [elem.bbox.max_x, elem.bbox.min_y],
          [elem.bbox.max_x, elem.bbox.max_y],
          [elem.bbox.min_x, elem.bbox.max_y],
        ];
      }

      if (verts.length >= 3) {
        let minPxX = Infinity,
          maxPxX = -Infinity,
          minPxY = Infinity,
          maxPxY = -Infinity;
        let sumX = 0,
          sumY = 0;

        ctx.beginPath();
        verts.forEach((pt: any, idx: number) => {
          const px = originX + pt[0] * zoom;
          const py = originY - pt[1] * zoom;
          if (idx === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);

          if (px < minPxX) minPxX = px;
          if (px > maxPxX) maxPxX = px;
          if (py < minPxY) minPxY = py;
          if (py > maxPxY) maxPxY = py;
          sumX += px;
          sumY += py;
        });
        ctx.closePath();

        const centroidX = sumX / verts.length;
        const centroidY = sumY / verts.length;
        const polyWidth = maxPxX - minPxX;
        const polyHeight = maxPxY - minPxY;

        // Base fill: structural slabs get subtle background fill, finish zones get vibrant palette
        if (isStructuralSlab) {
          ctx.fillStyle = isSelected
            ? "rgba(0, 240, 255, 0.15)"
            : "rgba(15, 23, 42, 0.35)";
          ctx.fill();
        } else {
          ctx.fillStyle = isSelected
            ? "rgba(0, 240, 255, 0.28)"
            : isHovered
            ? "rgba(56, 189, 248, 0.22)"
            : palette.fillRgba;
          ctx.fill();
        }

        // Architectural CAD Hatches
        if (showHatches && zoom > 14) {
          ctx.save();
          ctx.clip();
          drawHatchPattern(
            ctx,
            palette.hatchType,
            minPxX,
            minPxY,
            maxPxX,
            maxPxY,
            isSelected ? "rgba(0, 240, 255, 0.45)" : isHovered ? "rgba(56, 189, 248, 0.35)" : palette.borderCss + "33"
          );
          ctx.restore();
        }

        // Perimeter CAD Line Hierarchy
        ctx.save();
        if (isSpatial) {
          ctx.setLineDash([5, 3]); // Dashed line for spatial finish evidence
        }
        ctx.strokeStyle = isSelected ? "#00f0ff" : isHovered ? "#38bdf8" : palette.borderCss;
        ctx.lineWidth = isSelected ? 2.8 : isHovered ? 2.0 : 1.4;
        ctx.stroke();
        ctx.restore();

        // 4. Intelligent Label Placement & Anti-Collision Engine
        if (showRoomTags && zoom > 12) {
          const cleanRoomTag = getCleanRoomTag(elem, elemIdx);
          const materialTag = palette.code;
          const netArea = Number(elem.net_area_sqft || elem.gross_area_sqft || 0);
          const areaTag = `${netArea.toFixed(0)} SF`;

          ctx.font = "bold 9px Inter, sans-serif";
          const tw1 = ctx.measureText(cleanRoomTag).width;
          ctx.font = "8px JetBrains Mono, monospace";
          const tw2 = ctx.measureText(materialTag).width;
          ctx.font = "bold 8.5px JetBrains Mono, monospace";
          const tw3 = ctx.measureText(areaTag).width;

          const boxW = Math.max(tw1, tw2, tw3, 44) + 12;
          const boxH = 34;

          // Check if tag fits inside polygon centroid without collision
          const fitsInside =
            polyWidth >= boxW + 8 &&
            polyHeight >= boxH + 8;

          let targetBox: PlacedBox = {
            x: centroidX - boxW / 2,
            y: centroidY - boxH / 2,
            w: boxW,
            h: boxH,
          };

          let useLeader = !fitsInside;
          let hasOverlap = placedLabelBoxes.some((b) => boxesOverlap(b, targetBox));

          // If overlapping or doesn't fit, find nearest clear offset slot with CAD leader line
          if (useLeader || hasOverlap) {
            useLeader = true;
            const offsets = [
              { dx: boxW * 0.9, dy: -boxH * 0.9 },
              { dx: -boxW * 0.9, dy: -boxH * 0.9 },
              { dx: boxW * 0.9, dy: boxH * 0.9 },
              { dx: -boxW * 0.9, dy: boxH * 0.9 },
              { dx: 0, dy: -boxH * 1.3 },
              { dx: 0, dy: boxH * 1.3 },
              { dx: boxW * 1.4, dy: 0 },
              { dx: -boxW * 1.4, dy: 0 },
            ];

            let bestSlot: PlacedBox | null = null;
            for (const off of offsets) {
              const candidateBox: PlacedBox = {
                x: centroidX + off.dx - boxW / 2,
                y: centroidY + off.dy - boxH / 2,
                w: boxW,
                h: boxH,
              };
              if (!placedLabelBoxes.some((b) => boxesOverlap(b, candidateBox))) {
                bestSlot = candidateBox;
                break;
              }
            }

            if (bestSlot) {
              targetBox = bestSlot;
            } else {
              // Stagger downwards if dense
              targetBox.y += (elemIdx % 4) * (boxH + 6);
            }
          }

          // Register placed box
          placedLabelBoxes.push(targetBox);

          const tagCenterX = targetBox.x + boxW / 2;
          const tagCenterY = targetBox.y + boxH / 2;

          // Draw CAD Leader Line if tag is outside polygon
          if (useLeader) {
            ctx.strokeStyle = isSelected ? "#00f0ff" : "#475569";
            ctx.lineWidth = 1.0;
            ctx.beginPath();
            ctx.moveTo(centroidX, centroidY);
            // Leader line to box anchor
            const anchorX = tagCenterX < centroidX ? targetBox.x + boxW : targetBox.x;
            const anchorY = tagCenterY;
            ctx.lineTo(anchorX, anchorY);
            ctx.stroke();

            // Centroid terminal dot
            ctx.fillStyle = isSelected ? "#00f0ff" : "#64748b";
            ctx.beginPath();
            ctx.arc(centroidX, centroidY, 2.5, 0, Math.PI * 2);
            ctx.fill();
          }

          // Render High-Contrast 3-Line Tag Box
          ctx.save();
          if (isSelected) {
            ctx.shadowColor = "rgba(0, 240, 255, 0.45)";
            ctx.shadowBlur = 8;
          }
          ctx.fillStyle = isSelected ? "#04192bfa" : "#081322f2";
          ctx.strokeStyle = isSelected ? "#00f0ff" : isHovered ? "#38bdf8" : "#1e3a5f";
          ctx.lineWidth = isSelected ? 1.6 : 1.0;
          ctx.beginPath();
          ctx.roundRect(targetBox.x, targetBox.y, boxW, boxH, 3);
          ctx.fill();
          ctx.stroke();
          ctx.shadowBlur = 0;

          // Material color indicator accent bar on left edge
          ctx.fillStyle = palette.borderCss;
          ctx.beginPath();
          ctx.roundRect(targetBox.x, targetBox.y, 3.5, boxH, [3, 0, 0, 3]);
          ctx.fill();

          // 3-Line Text Hierarchy
          ctx.textAlign = "center";
          // Line 1: Room ID
          ctx.fillStyle = isSelected ? "#00f0ff" : "#f1f5f9";
          ctx.font = "bold 9px Inter, sans-serif";
          ctx.fillText(cleanRoomTag, tagCenterX, tagCenterY - 6);

          // Line 2: Material Code
          ctx.fillStyle = isSelected ? "#7dd3fc" : "#94a3b8";
          ctx.font = "8px JetBrains Mono, monospace";
          ctx.fillText(materialTag, tagCenterX, tagCenterY + 4);

          // Line 3: Net Area SF
          ctx.fillStyle = isSelected ? "#38bdf8" : "#38bdf8";
          ctx.font = "bold 8px JetBrains Mono, monospace";
          ctx.fillText(areaTag, tagCenterX, tagCenterY + 13);
          ctx.textAlign = "left";
          ctx.restore();
        }

        // Perimeter Linear Dimensions on Selected Element
        if (isSelected && showDimensions && verts.length >= 3) {
          for (let i = 0; i < verts.length; i++) {
            const p1 = verts[i];
            const p2 = verts[(i + 1) % verts.length];
            const segLenFt = Math.hypot(p2[0] - p1[0], p2[1] - p1[1]);
            if (segLenFt < 1.8) continue; // skip micro chamfers

            const x1 = originX + p1[0] * zoom;
            const y1 = originY - p1[1] * zoom;
            const x2 = originX + p2[0] * zoom;
            const y2 = originY - p2[1] * zoom;

            const dx = x2 - x1;
            const dy = y2 - y1;
            const len = Math.hypot(dx, dy);
            if (len <= 0) continue;
            const nx = -dy / len;
            const ny = dx / len;

            const midX = (x1 + x2) / 2;
            const midY = (y1 + y2) / 2;
            const toCentroidX = centroidX - midX;
            const toCentroidY = centroidY - midY;
            const dot = nx * toCentroidX + ny * toCentroidY;
            const sign = dot > 0 ? -1 : 1;

            const dimOffset = 18 * sign;
            const ox1 = x1 + nx * dimOffset;
            const oy1 = y1 + ny * dimOffset;
            const ox2 = x2 + nx * dimOffset;
            const oy2 = y2 + ny * dimOffset;

            ctx.save();
            ctx.strokeStyle = "rgba(0, 240, 255, 0.4)";
            ctx.lineWidth = 0.75;
            ctx.setLineDash([2, 2]);
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(ox1 + nx * 3 * sign, oy1 + ny * 3 * sign);
            ctx.moveTo(x2, y2);
            ctx.lineTo(ox2 + nx * 3 * sign, oy2 + ny * 3 * sign);
            ctx.stroke();

            ctx.setLineDash([]);
            ctx.strokeStyle = "#00f0ff";
            ctx.lineWidth = 1.1;
            ctx.beginPath();
            ctx.moveTo(ox1, oy1);
            ctx.lineTo(ox2, oy2);
            ctx.stroke();

            const tickLen = 4.5;
            const segAngle = Math.atan2(dy, dx);
            const tickAngle = segAngle + Math.PI / 4;
            [
              { x: ox1, y: oy1 },
              { x: ox2, y: oy2 },
            ].forEach((pt) => {
              ctx.beginPath();
              ctx.moveTo(pt.x - Math.cos(tickAngle) * tickLen, pt.y - Math.sin(tickAngle) * tickLen);
              ctx.lineTo(pt.x + Math.cos(tickAngle) * tickLen, pt.y + Math.sin(tickAngle) * tickLen);
              ctx.stroke();
            });

            const dimText = formatDimensionFt(segLenFt);
            ctx.font = "bold 8.5px JetBrains Mono, monospace";
            const textW = ctx.measureText(dimText).width;
            const tMidX = (ox1 + ox2) / 2;
            const tMidY = (oy1 + oy2) / 2;

            ctx.fillStyle = "#04192bfa";
            ctx.strokeStyle = "rgba(0, 240, 255, 0.8)";
            ctx.lineWidth = 0.8;
            ctx.beginPath();
            ctx.roundRect(tMidX - textW / 2 - 4, tMidY - 7, textW + 8, 14, 2);
            ctx.fill();
            ctx.stroke();

            ctx.fillStyle = "#00f0ff";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText(dimText, tMidX, tMidY);
            ctx.restore();
          }
        }
      }
    });

    // 5. Architectural Scale Bar (Bottom Left)
    const scaleFt = 10;
    const scalePx = scaleFt * zoom;
    const barX = 20;
    const barY = height - 25;

    ctx.strokeStyle = "#64748b";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(barX, barY);
    ctx.lineTo(barX + scalePx, barY);
    ctx.moveTo(barX, barY - 4);
    ctx.lineTo(barX, barY + 4);
    ctx.moveTo(barX + scalePx, barY - 4);
    ctx.lineTo(barX + scalePx, barY + 4);
    ctx.stroke();

    ctx.fillStyle = "#94a3b8";
    ctx.font = "bold 9px JetBrains Mono, monospace";
    ctx.fillText(`0`, barX - 2, barY - 7);
    ctx.fillText(`${scaleFt}'-0" SCALE`, barX + scalePx - 28, barY - 7);

    // 6. North Arrow Indicator (Bottom Right)
    const naX = width - 35;
    const naY = height - 35;
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(naX, naY, 13, 0, Math.PI * 2);
    ctx.stroke();

    ctx.fillStyle = "#38bdf8";
    ctx.beginPath();
    ctx.moveTo(naX, naY - 10);
    ctx.lineTo(naX - 4, naY + 3);
    ctx.lineTo(naX, naY);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.moveTo(naX, naY - 10);
    ctx.lineTo(naX + 4, naY + 3);
    ctx.lineTo(naX, naY);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 8px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("N", naX, naY - 13);
    ctx.textAlign = "left";

    // 7. Architectural CAD Title Block (Bottom Left)
    const tbX = 20;
    const tbY = height - 76;
    ctx.fillStyle = "rgba(10, 18, 30, 0.88)";
    ctx.strokeStyle = "#162840";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(tbX, tbY, 260, 42, 4);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#38bdf8";
    ctx.font = "bold 9px Inter, sans-serif";
    ctx.fillText("PROTAKEOFF · CANONICAL FLOORING PLAN", tbX + 10, tbY + 14);
    ctx.fillStyle = "#94a3b8";
    ctx.font = "8px JetBrains Mono, monospace";
    ctx.fillText(`LEVEL: ${activeStorey.toUpperCase()} | SCALE: 1/8" = 1'-0"`, tbX + 10, tbY + 26);
    ctx.fillStyle = "#38bdf8";
    ctx.font = "bold 8.5px JetBrains Mono, monospace";
    ctx.fillText(`TOTAL TAKEOFF: ${storeyTotalSF.toLocaleString()} SF (${filteredElements.filter((e: any) => e.qto_eligibility === "ELIGIBLE").length} FINISH ZONES)`, tbX + 10, tbY + 36);

    // 8. Architectural Interactive Measurement Tape
    if (measureStart && (measureEnd || liveCursorWorld)) {
      const p1 = measureStart;
      const p2 = measureEnd || liveCursorWorld!;
      const sx = originX + p1.x * zoom;
      const sy = originY - p1.y * zoom;
      const ex = originX + p2.x * zoom;
      const ey = originY - p2.y * zoom;
      const distFt = Math.hypot(p2.x - p1.x, p2.y - p1.y);

      ctx.save();
      ctx.shadowColor = "#f59e0b";
      ctx.shadowBlur = 6;
      ctx.strokeStyle = "#fbbf24";
      ctx.lineWidth = 1.8;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(sx, sy);
      ctx.lineTo(ex, ey);
      ctx.stroke();

      ctx.shadowBlur = 0;
      ctx.setLineDash([]);

      // Start & End points
      [
        { x: sx, y: sy },
        { x: ex, y: ey },
      ].forEach((pt) => {
        ctx.strokeStyle = "#fbbf24";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = "#f59e0b";
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 2, 0, Math.PI * 2);
        ctx.fill();
      });

      // Measurement Callout Badge
      const midX = (sx + ex) / 2;
      const midY = (sy + ey) / 2;
      const textFt = formatDimensionFt(distFt);
      const textDetail = `${textFt} (${distFt.toFixed(2)} LF)`;
      ctx.font = "bold 9.5px JetBrains Mono, monospace";
      const badgeW = ctx.measureText(textDetail).width + 16;
      const badgeH = 20;

      ctx.fillStyle = "#0c1524fa";
      ctx.strokeStyle = "#f59e0b";
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.roundRect(midX - badgeW / 2, midY - badgeH / 2, badgeW, badgeH, 3);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = "#fbbf24";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(textDetail, midX, midY);
      ctx.restore();
    }

  }, [
    filteredElements,
    filteredWalls,
    selectedFlooringGuid,
    hoveredGuid,
    pan,
    zoom,
    showGrid,
    showWallsBackdrop,
    showRoomTags,
    showHatches,
    showDimensions,
    measureStart,
    measureEnd,
    liveCursorWorld,
    activeStorey,
    storeyTotalSF,
  ]);

  // Point in polygon test for click & hover (with robust bbox fallback)
  const findElementAtPoint = useCallback(
    (worldX: number, worldY: number) => {
      for (const elem of filteredElements) {
        let verts = elem.vertices || [];
        if (verts.length < 3 && elem.bbox) {
          verts = [
            [elem.bbox.min_x, elem.bbox.min_y],
            [elem.bbox.max_x, elem.bbox.min_y],
            [elem.bbox.max_x, elem.bbox.max_y],
            [elem.bbox.min_x, elem.bbox.max_y],
          ];
        }
        if (verts.length < 3) continue;

        let inside = false;
        for (let i = 0, j = verts.length - 1; i < verts.length; j = i++) {
          const xi = verts[i][0],
            yi = verts[i][1];
          const xj = verts[j][0],
            yj = verts[j][1];

          const intersect =
            yi > worldY !== yj > worldY &&
            worldX < ((xj - xi) * (worldY - yi)) / (yj - yi) + xi;
          if (intersect) inside = !inside;
        }

        if (inside) return elem;
      }
      return null;
    },
    [filteredElements]
  );

  const handlePointerDown = (e: React.MouseEvent) => {
    if (activeTool === "measure") {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;
      const originX = canvas.clientWidth / 2 + pan.x;
      const originY = canvas.clientHeight / 2 + pan.y;
      const worldX = (px - originX) / zoom;
      const worldY = (originY - py) / zoom;

      if (!measureStart || measureEnd) {
        setMeasureStart({ x: worldX, y: worldY });
        setMeasureEnd(null);
      } else {
        setMeasureEnd({ x: worldX, y: worldY });
      }
      return;
    }

    setIsDragging(true);
    dragStart.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  };

  const handlePointerMove = (e: React.MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;

    const originX = canvas.clientWidth / 2 + pan.x;
    const originY = canvas.clientHeight / 2 + pan.y;

    const worldX = (px - originX) / zoom;
    const worldY = (originY - py) / zoom;

    if (activeTool === "measure") {
      setLiveCursorWorld({ x: worldX, y: worldY });
      if (containerRef.current) containerRef.current.style.cursor = "crosshair";
      return;
    }

    if (isDragging) {
      setPan({
        x: e.clientX - dragStart.current.x,
        y: e.clientY - dragStart.current.y,
      });
      return;
    }

    const hit = findElementAtPoint(worldX, worldY);
    if (hit) {
      setHoveredGuid(hit.ifc_guid || hit.id);
      if (containerRef.current) containerRef.current.style.cursor = "pointer";
    } else {
      setHoveredGuid(null);
      if (containerRef.current) containerRef.current.style.cursor = activeTool === "pan" ? "grab" : "default";
    }
  };

  const handlePointerUp = (e: React.MouseEvent) => {
    if (activeTool === "measure") return;

    if (isDragging) {
      const movedX = Math.abs(e.clientX - (dragStart.current.x + pan.x));
      const movedY = Math.abs(e.clientY - (dragStart.current.y + pan.y));
      setIsDragging(false);
      if (movedX > 4 || movedY > 4) return; // was a pan drag
    }

    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;

    const originX = canvas.clientWidth / 2 + pan.x;
    const originY = canvas.clientHeight / 2 + pan.y;

    const worldX = (px - originX) / zoom;
    const worldY = (originY - py) / zoom;

    const hit = findElementAtPoint(worldX, worldY);
    if (hit) {
      onSelectFlooringGuid(hit.ifc_guid || hit.id);
    }
  };

  const handleExportPNG = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const link = document.createElement("a");
    link.download = `ProTakeoff_2D_${activeStorey.replace(/\s+/g, "_")}_Flooring.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
    setZoom((prev) => Math.max(5, Math.min(100, prev * zoomFactor)));
  };

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full bg-[#050b14] overflow-hidden select-none"
    >
      {/* 2D Canvas */}
      <canvas
        ref={canvasRef}
        onMouseDown={handlePointerDown}
        onMouseMove={handlePointerMove}
        onMouseUp={handlePointerUp}
        onWheel={handleWheel}
        className="w-full h-full block"
      />

      {/* Floating Top Controls Bar (CAD Tool Modes, Storey & Category Isolations) */}
      <div className="absolute top-3 left-3 flex items-center space-x-2 bg-[#0a121e]/90 backdrop-blur-md px-3 py-1.5 rounded-lg border border-[#162840] shadow-lg text-xs z-10 flex-wrap gap-y-1">
        {/* CAD Tool Mode Selector */}
        <div className="flex items-center space-x-1 bg-[#060b14] p-0.5 rounded border border-[#162840]">
          <button
            onClick={() => {
              setActiveTool("select");
              setMeasureStart(null);
              setMeasureEnd(null);
            }}
            className={`px-2 py-1 rounded flex items-center gap-1 text-[10px] font-mono font-bold transition-all cursor-pointer ${
              activeTool === "select"
                ? "bg-cyan-600 text-white shadow-sm"
                : "text-gray-400 hover:text-white"
            }`}
            title="Select & Inspect Element (V)"
          >
            <MousePointer size={12} />
            <span>SELECT</span>
          </button>
          <button
            onClick={() => {
              setActiveTool("pan");
              setMeasureStart(null);
              setMeasureEnd(null);
            }}
            className={`px-2 py-1 rounded flex items-center gap-1 text-[10px] font-mono font-bold transition-all cursor-pointer ${
              activeTool === "pan"
                ? "bg-cyan-600 text-white shadow-sm"
                : "text-gray-400 hover:text-white"
            }`}
            title="Pan Viewport (H)"
          >
            <Hand size={12} />
            <span>PAN</span>
          </button>
          <button
            onClick={() => setActiveTool("measure")}
            className={`px-2 py-1 rounded flex items-center gap-1 text-[10px] font-mono font-bold transition-all cursor-pointer ${
              activeTool === "measure"
                ? "bg-amber-600 text-white shadow-sm"
                : "text-gray-400 hover:text-white"
            }`}
            title="Measure Distance Tape (M)"
          >
            <Ruler size={12} />
            <span>MEASURE</span>
          </button>
        </div>

        <span className="text-gray-600">|</span>

        <span className="font-bold text-gray-300 font-mono flex items-center gap-1.5">
          <Layers size={13} className="text-amber-400" />
          <span>STOREY:</span>
        </span>
        <select
          value={activeStorey}
          onChange={(e) => onSelectStorey?.(e.target.value)}
          className="bg-[#060b14] text-xs font-mono text-cyan-300 px-2 py-0.5 rounded border border-[#162840] outline-none cursor-pointer"
        >
          <option value="ALL">All Storeys ({storeys.length})</option>
          {storeys.map((st: any) => (
            <option key={st.id} value={st.name}>
              {st.name}
            </option>
          ))}
        </select>

        <span className="text-gray-600">|</span>

        <span className="font-bold text-gray-300 font-mono flex items-center gap-1.5">
          <Filter size={13} className="text-cyan-400" />
          <span>FINISH:</span>
        </span>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="bg-[#060b14] text-xs font-mono text-gray-200 px-2 py-0.5 rounded border border-[#162840] outline-none cursor-pointer"
        >
          <option value="ALL">All Materials</option>
          {Object.entries(FLOORING_PALETTE).map(([key, item]) => (
            <option key={key} value={key}>
              {item.label}
            </option>
          ))}
        </select>

        <span className="text-gray-600">|</span>

        {/* Storey Summary Readout */}
        <div className="flex items-center space-x-2 text-[10px] font-mono">
          <span className="text-gray-400">FINISH ZONES:</span>
          <span className="text-white font-bold">{filteredElements.length}</span>
          <span className="text-gray-400 ml-1">NET SF:</span>
          <span className="text-cyan-300 font-bold">{storeyTotalSF.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} SF</span>
        </div>
      </div>

      {/* Measurement Active Mode Banner */}
      {activeTool === "measure" && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-amber-950/90 backdrop-blur-md px-3.5 py-1.5 rounded-md border border-amber-600/80 shadow-lg text-[10px] font-mono text-amber-200 z-20 flex items-center gap-2 animate-fadeIn">
          <Ruler size={13} className="text-amber-400 animate-pulse" />
          <span>
            {measureStart
              ? measureEnd
                ? "Distance locked. Click anywhere to measure new segment."
                : "Move cursor & click 2nd point to lock measurement."
              : "Click starting point on drawing to measure."}
          </span>
          {(measureStart || measureEnd) && (
            <button
              onClick={() => {
                setMeasureStart(null);
                setMeasureEnd(null);
              }}
              className="text-amber-400 hover:text-white underline ml-1 cursor-pointer font-bold"
            >
              Reset
            </button>
          )}
        </div>
      )}

      {/* Floating Hover Inspector HUD */}
      {(() => {
        if (!hoveredGuid || isDragging) return null;
        const hoveredElem = filteredElements.find((e: any) => (e.ifc_guid || e.id) === hoveredGuid);
        if (!hoveredElem) return null;
        const cat = hoveredElem.flooring_category || "UNASSIGNED_FINISH";
        const pal = FLOORING_PALETTE[cat] || FLOORING_PALETTE.UNASSIGNED_FINISH;
        const isEligible = hoveredElem.qto_eligibility === "ELIGIBLE";
        return (
          <div className="absolute top-14 left-3 bg-[#0a121e]/95 backdrop-blur-md px-3 py-2 rounded-lg border border-cyan-500/40 shadow-2xl z-20 pointer-events-none flex flex-col gap-1 min-w-[210px] animate-fadeIn">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[11px] font-bold text-white font-sans flex items-center gap-1.5 truncate max-w-[140px]">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: pal.borderCss }} />
                {hoveredElem.source_name || hoveredElem.name || "Flooring Finish"}
              </span>
              <span
                className={`text-[8.5px] font-mono px-1.5 py-0.5 rounded font-bold border ${
                  isEligible
                    ? "bg-emerald-950 text-emerald-300 border-emerald-800"
                    : "bg-rose-950 text-rose-300 border-rose-800"
                }`}
              >
                {isEligible ? "INCLUDED" : "EXCLUDED"}
              </span>
            </div>
            <div className="text-[10px] font-mono text-gray-300">
              Spec: <span className="text-amber-300 font-semibold">{pal.label}</span>
            </div>
            <div className="flex items-center justify-between text-[10px] font-mono border-t border-[#162840] pt-1 mt-0.5">
              <span className="text-gray-400">Net Area:</span>
              <span className="font-bold text-cyan-300">
                {isEligible
                  ? `${(hoveredElem.net_area_sqft || hoveredElem.gross_area_sqft || 0).toLocaleString()} SF`
                  : "0.0 SF (Excluded)"}
              </span>
            </div>
          </div>
        );
      })()}

      {/* Floating Right Overlay Controls */}
      <div className="absolute top-3 right-3 flex items-center space-x-1 bg-[#0a121e]/90 backdrop-blur-md p-1 rounded-lg border border-[#162840] shadow-lg z-10">
        <button
          onClick={() => setShowDimensions(!showDimensions)}
          className={`px-2 py-1 rounded text-[11px] font-bold font-mono transition-all cursor-pointer ${
            showDimensions
              ? "bg-cyan-950 text-cyan-300 border border-cyan-700"
              : "text-gray-400 hover:text-gray-200"
          }`}
          title="Toggle Room Boundary Linear Dimensions"
        >
          Dims
        </button>
        <button
          onClick={() => setShowHatches(!showHatches)}
          className={`px-2 py-1 rounded text-[11px] font-bold font-mono transition-all cursor-pointer ${
            showHatches
              ? "bg-cyan-950 text-cyan-300 border border-cyan-700"
              : "text-gray-400 hover:text-gray-200"
          }`}
          title="Toggle Material CAD Hatches"
        >
          Hatch
        </button>
        <button
          onClick={() => setShowRoomTags(!showRoomTags)}
          className={`px-2 py-1 rounded text-[11px] font-bold font-mono transition-all cursor-pointer ${
            showRoomTags
              ? "bg-cyan-950 text-cyan-300 border border-cyan-700"
              : "text-gray-400 hover:text-gray-200"
          }`}
          title="Toggle 3-Line Takeoff Room Tags"
        >
          Tags
        </button>
        <button
          onClick={() => setShowWallsBackdrop(!showWallsBackdrop)}
          className={`px-2 py-1 rounded text-[11px] font-bold font-mono transition-all cursor-pointer ${
            showWallsBackdrop
              ? "bg-cyan-950 text-cyan-300 border border-cyan-700"
              : "text-gray-400 hover:text-gray-200"
          }`}
          title="Toggle Walls Backdrop"
        >
          Walls
        </button>
        <button
          onClick={() => setShowGrid(!showGrid)}
          className={`px-2 py-1 rounded text-[11px] font-bold font-mono transition-all cursor-pointer ${
            showGrid
              ? "bg-cyan-950 text-cyan-300 border border-cyan-700"
              : "text-gray-400 hover:text-gray-200"
          }`}
          title="Toggle Grid"
        >
          Grid
        </button>
        <button
          onClick={() => setShowLegend(!showLegend)}
          className={`px-2 py-1 rounded text-[11px] font-bold font-mono transition-all cursor-pointer ${
            showLegend
              ? "bg-cyan-950 text-cyan-300 border border-cyan-700"
              : "text-gray-400 hover:text-gray-200"
          }`}
          title="Toggle Material CAD Legend"
        >
          Legend
        </button>
        <span className="text-gray-700">|</span>
        <button
          onClick={handleExportPNG}
          className="p-1 rounded text-cyan-400 hover:text-white hover:bg-gray-800 cursor-pointer"
          title="Export High-Resolution Plan (PNG)"
        >
          <Download size={13} />
        </button>
        <button
          onClick={handleFitToStorey}
          className="p-1 rounded text-gray-300 hover:text-cyan-300 hover:bg-gray-800 cursor-pointer"
          title="Fit Storey to Viewport"
        >
          <Maximize2 size={13} />
        </button>
        <button
          onClick={() => setZoom((z) => Math.min(100, z * 1.25))}
          className="p-1 rounded text-gray-300 hover:text-white hover:bg-gray-800 cursor-pointer"
          title="Zoom In"
        >
          <ZoomIn size={13} />
        </button>
        <button
          onClick={() => setZoom((z) => Math.max(5, z * 0.8))}
          className="p-1 rounded text-gray-300 hover:text-white hover:bg-gray-800 cursor-pointer"
          title="Zoom Out"
        >
          <ZoomOut size={13} />
        </button>
        <button
          onClick={() => {
            setPan({ x: 0, y: 0 });
            setZoom(24);
          }}
          className="p-1 rounded text-gray-300 hover:text-white hover:bg-gray-800 cursor-pointer"
          title="Reset View"
        >
          <RotateCcw size={13} />
        </button>
      </div>

      {/* Floating Material CAD Legend (Docked cleanly above title block with close button) */}
      {showLegend && (
        <div className="absolute bottom-24 left-3 bg-[#0a121e]/95 backdrop-blur-md px-3.5 py-2.5 rounded-lg border border-[#162840] shadow-2xl text-[10px] font-mono z-20 max-w-xs animate-fadeIn">
          <div className="font-bold text-gray-300 mb-2 flex items-center justify-between border-b border-[#162840] pb-1">
            <span className="flex items-center gap-1 text-cyan-400">
              <Sparkles size={11} />
              <span>FLOORING SPECIFICATION LEGEND</span>
            </span>
            <button
              onClick={() => setShowLegend(false)}
              className="text-gray-400 hover:text-white p-0.5 rounded cursor-pointer"
              title="Close Legend"
            >
              <X size={12} />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
            {Object.entries(FLOORING_PALETTE).map(([key, pal]) => (
              <div key={key} className="flex items-center space-x-1.5">
                <div
                  className="w-3 h-3 rounded-sm border flex-shrink-0"
                  style={{ backgroundColor: pal.fillRgba, borderColor: pal.borderCss }}
                />
                <span className="text-gray-300 truncate" title={pal.label}>
                  {pal.code} · {pal.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
