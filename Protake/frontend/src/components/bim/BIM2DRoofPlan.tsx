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
  TrendingDown,
  ArrowDown,
} from "lucide-react";

export const ROOFING_PALETTE: Record<
  string,
  {
    hex: number;
    css: string;
    fillRgba: string;
    borderCss: string;
    label: string;
    code: string;
    hatchType: "shingle" | "seam" | "tile" | "membrane" | "shake" | "slate" | "hazard";
  }
> = {
  SHINGLE_ASPHALT: {
    hex: 0x334155,
    css: "#334155",
    fillRgba: "rgba(51, 65, 85, 0.40)",
    borderCss: "#64748b",
    label: "Asphalt Shingle",
    code: "SHINGLE",
    hatchType: "shingle",
  },
  METAL_STANDING_SEAM: {
    hex: 0x0e7490,
    css: "#0e7490",
    fillRgba: "rgba(14, 116, 144, 0.35)",
    borderCss: "#06b6d4",
    label: "Standing Seam Metal",
    code: "METAL",
    hatchType: "seam",
  },
  TILE_CONCRETE_CLAY: {
    hex: 0xc2410c,
    css: "#c2410c",
    fillRgba: "rgba(194, 65, 12, 0.35)",
    borderCss: "#ea580c",
    label: "Clay / Concrete Tile",
    code: "TILE",
    hatchType: "tile",
  },
  MEMBRANE_SINGLE_PLY: {
    hex: 0x475569,
    css: "#475569",
    fillRgba: "rgba(71, 85, 105, 0.35)",
    borderCss: "#94a3b8",
    label: "Single-Ply (TPO/EPDM)",
    code: "MEMBRANE",
    hatchType: "membrane",
  },
  MEMBRANE_TPO: {
    hex: 0x475569,
    css: "#475569",
    fillRgba: "rgba(71, 85, 105, 0.35)",
    borderCss: "#94a3b8",
    label: "TPO Membrane",
    code: "TPO",
    hatchType: "membrane",
  },
  WOOD_SHAKE: {
    hex: 0xb45309,
    css: "#b45309",
    fillRgba: "rgba(180, 83, 9, 0.35)",
    borderCss: "#f59e0b",
    label: "Wood Shake / Shingle",
    code: "SHAKE",
    hatchType: "shake",
  },
  SLATE_NATURAL: {
    hex: 0x1e293b,
    css: "#1e293b",
    fillRgba: "rgba(30, 41, 59, 0.50)",
    borderCss: "#475569",
    label: "Natural Slate",
    code: "SLATE",
    hatchType: "slate",
  },
  UNASSIGNED_ROOF: {
    hex: 0xd97706,
    css: "#d97706",
    fillRgba: "rgba(217, 119, 6, 0.25)",
    borderCss: "#f59e0b",
    label: "Unassigned Finish",
    code: "ROOF",
    hatchType: "hazard",
  },
  REVIEW_REQUIRED: {
    hex: 0xd97706,
    css: "#d97706",
    fillRgba: "rgba(217, 119, 6, 0.25)",
    borderCss: "#f59e0b",
    label: "Review Required",
    code: "REVIEW",
    hatchType: "hazard",
  },
};

export interface BIM2DRoofPlanProps {
  roofs: any[];
  walls?: any[];
  storeys?: any[];
  selectedStorey?: string;
  onSelectStorey?: (storeyName: string) => void;
  selectedRoofGuid: string | null;
  onSelectRoofGuid: (guid: string) => void;
}

export default function BIM2DRoofPlan({
  roofs,
  walls = [],
  storeys = [],
  selectedStorey = "ALL",
  onSelectStorey,
  selectedRoofGuid,
  onSelectRoofGuid,
}: BIM2DRoofPlanProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Pan & Zoom
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [zoom, setZoom] = useState<number>(20);
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  // Display Filters & Overlays
  const [activeTool, setActiveTool] = useState<"select" | "pan">("select");
  const [roofTypeFilter, setRoofTypeFilter] = useState<string>("ALL");
  const [showSlopeArrows, setShowSlopeArrows] = useState(true);
  const [showPitchTags, setShowPitchTags] = useState(true);
  const [showAreaTags, setShowAreaTags] = useState(true);
  const [showWallFootprint, setShowWallFootprint] = useState(true);
  const [showHatches, setShowHatches] = useState(true);
  const [hoveredGuid, setHoveredGuid] = useState<string | null>(null);

  // Filtered Roof Elements
  const displayRoofs = useMemo(() => {
    return (roofs || []).filter((r: any) => {
      const matchStorey =
        selectedStorey === "ALL" ||
        r.storey_name === selectedStorey ||
        r.storey_id === selectedStorey;
      const matchType =
        roofTypeFilter === "ALL" || r.roof_type === roofTypeFilter;
      return matchStorey && matchType;
    });
  }, [roofs, selectedStorey, roofTypeFilter]);

  // Roof Types for Filtering
  const availableTypes = useMemo(() => {
    const set = new Set<string>();
    (roofs || []).forEach((r: any) => {
      if (r.roof_type) set.add(r.roof_type);
    });
    return Array.from(set);
  }, [roofs]);

  // Clean Planar Polygon Extraction (Eliminates serrated / saw-tooth boundary noise)
  const getCleanRoofPolygon = useCallback((roof: any): Array<[number, number]> => {
    const rawVerts = roof.vertices || [];
    if (rawVerts.length >= 3) {
      const pts2d: Array<[number, number]> = [];
      const seen = new Set<string>();

      for (const pt of rawVerts) {
        if (!Array.isArray(pt) || pt.length < 2) continue;
        const x = Number(pt[0]);
        const y = Number(pt[1]);
        if (isNaN(x) || isNaN(y)) continue;
        // Snap to 0.05 ft tolerance to collapse micro-deviations
        const key = `${Math.round(x * 20)},${Math.round(y * 20)}`;
        if (!seen.has(key)) {
          seen.add(key);
          pts2d.push([x, y]);
        }
      }

      if (pts2d.length === 4) {
        const cx = (pts2d[0][0] + pts2d[1][0] + pts2d[2][0] + pts2d[3][0]) / 4;
        const cy = (pts2d[0][1] + pts2d[1][1] + pts2d[2][1] + pts2d[3][1]) / 4;
        pts2d.sort((a, b) => Math.atan2(a[1] - cy, a[0] - cx) - Math.atan2(b[1] - cy, b[0] - cx));
        return pts2d;
      }

      if (pts2d.length > 4) {
        // Compute 2D Convex Hull (Andrew's Monotone Chain) to strip internal tessellation spikes
        const sorted = [...pts2d].sort((a, b) => (a[0] === b[0] ? a[1] - b[1] : a[0] - b[0]));
        const cross = (o: [number, number], a: [number, number], b: [number, number]) =>
          (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);

        const lower: Array<[number, number]> = [];
        for (const p of sorted) {
          while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) {
            lower.pop();
          }
          lower.push(p);
        }

        const upper: Array<[number, number]> = [];
        for (let i = sorted.length - 1; i >= 0; i--) {
          const p = sorted[i];
          while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) {
            upper.pop();
          }
          upper.push(p);
        }

        lower.pop();
        upper.pop();
        const hull = lower.concat(upper);
        if (hull.length >= 3) return hull;
      }

      if (pts2d.length >= 3) return pts2d;
    }

    if (roof.bbox) {
      const minX = Number(roof.bbox.min_x);
      const maxX = Number(roof.bbox.max_x);
      const minY = Number(roof.bbox.min_y);
      const maxY = Number(roof.bbox.max_y);
      if (!isNaN(minX) && !isNaN(maxX) && !isNaN(minY) && !isNaN(maxY)) {
        return [
          [minX, minY],
          [maxX, minY],
          [maxX, maxY],
          [minX, maxY],
        ];
      }
    }

    return [];
  }, []);

  // Auto-Fit Function
  const autoFit = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let minX = Infinity,
      maxX = -Infinity,
      minY = Infinity,
      maxY = -Infinity;

    displayRoofs.forEach((r: any) => {
      const poly = getCleanRoofPolygon(r);
      poly.forEach((v: [number, number]) => {
        minX = Math.min(minX, v[0]);
        maxX = Math.max(maxX, v[0]);
        minY = Math.min(minY, v[1]);
        maxY = Math.max(maxY, v[1]);
      });
    });

    if (minX === Infinity && walls.length > 0) {
      walls.forEach((w: any) => {
        const sx = w.start_point?.[0] || 0;
        const sy = w.start_point?.[1] || 0;
        const ex = w.end_point?.[0] || sx + 10;
        const ey = w.end_point?.[1] || sy;
        minX = Math.min(minX, sx, ex);
        maxX = Math.max(maxX, sx, ex);
        minY = Math.min(minY, sy, ey);
        maxY = Math.max(maxY, sy, ey);
      });
    }

    if (minX === Infinity) return;

    const width = canvas.parentElement?.clientWidth || 800;
    const height = canvas.parentElement?.clientHeight || 600;

    const spanX = Math.max(maxX - minX, 10);
    const spanY = Math.max(maxY - minY, 10);
    const midX = (minX + maxX) / 2;
    const midY = (minY + maxY) / 2;

    const fitZoom = Math.min((width * 0.65) / spanX, (height * 0.60) / spanY, 32);
    const finalZoom = Math.max(8, fitZoom);
    setZoom(finalZoom);
    setPan({ x: -midX * finalZoom, y: midY * finalZoom - 10 });
  }, [displayRoofs, walls, getCleanRoofPolygon]);

  useEffect(() => {
    autoFit();
  }, [autoFit]);

  // Render Engine
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

    // Deep Obsidian Blueprint Background
    ctx.fillStyle = "#080e18";
    ctx.fillRect(0, 0, width, height);

    const originX = width / 2 + pan.x;
    const originY = height / 2 + pan.y;

    // 1. Grid
    ctx.strokeStyle = "#101d2e";
    ctx.lineWidth = 0.5;
    const gridSize = zoom * 5; // 5ft major grid
    const startGridX = ((pan.x % gridSize) + gridSize) % gridSize;
    const startGridY = ((pan.y % gridSize) + gridSize) % gridSize;

    for (let x = startGridX; x < width; x += gridSize) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = startGridY; y < height; y += gridSize) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // 2. Wall Footprint (Ghosted Underlay)
    if (showWallFootprint && walls.length > 0) {
      ctx.strokeStyle = "#1e293b";
      ctx.lineWidth = 1.2;
      walls.forEach((w: any) => {
        const sx = originX + (w.start_point?.[0] || 0) * zoom;
        const sy = originY - (w.start_point?.[1] || 0) * zoom;
        const ex = originX + (w.end_point?.[0] || 0) * zoom;
        const ey = originY - (w.end_point?.[1] || 0) * zoom;

        ctx.beginPath();
        ctx.moveTo(sx, sy);
        ctx.lineTo(ex, ey);
        ctx.stroke();
      });
    }

    // Callout badge data collector for Collision Avoidance pass
    const calloutsToRender: Array<{
      index: number;
      roof: any;
      guid: string;
      isSelected: boolean;
      isHovered: boolean;
      centerScreenX: number;
      centerScreenY: number;
      labelText: string;
      badgeWidth: number;
      badgeHeight: number;
      targetY: number;
      targetX: number;
    }> = [];

    // 3. Render Roof Planes (Geometry & CAD Hatches)
    displayRoofs.forEach((roof: any, index: number) => {
      const poly = getCleanRoofPolygon(roof);
      if (poly.length < 3) return;

      const guid = roof.ifc_guid || roof.id;
      const isSelected = guid === selectedRoofGuid;
      const isHovered = guid === hoveredGuid;
      const matKey = roof.primary_material || roof.material || "UNASSIGNED_ROOF";
      const pal = ROOFING_PALETTE[matKey] || ROOFING_PALETTE.UNASSIGNED_ROOF;

      ctx.save();
      ctx.beginPath();
      const p0x = originX + poly[0][0] * zoom;
      const p0y = originY - poly[0][1] * zoom;
      ctx.moveTo(p0x, p0y);

      let cx = poly[0][0];
      let cy = poly[0][1];

      for (let i = 1; i < poly.length; i++) {
        const px = originX + poly[i][0] * zoom;
        const py = originY - poly[i][1] * zoom;
        ctx.lineTo(px, py);
        cx += poly[i][0];
        cy += poly[i][1];
      }
      ctx.closePath();

      cx /= poly.length;
      cy /= poly.length;
      const centerScreenX = originX + cx * zoom;
      const centerScreenY = originY - cy * zoom;

      // Base Fill
      if (isSelected) {
        ctx.fillStyle = "rgba(245, 158, 11, 0.45)";
      } else if (isHovered) {
        ctx.fillStyle = "rgba(251, 191, 36, 0.28)";
      } else {
        ctx.fillStyle = pal.fillRgba || "rgba(217, 119, 6, 0.20)";
      }
      ctx.fill();

      // Procedural Architectural Hatching (Clip to roof polygon)
      if (showHatches && zoom >= 10) {
        ctx.save();
        ctx.clip();

        // Calculate bounding box in screen coords for hatch filling
        let polyMinX = Infinity, polyMaxX = -Infinity, polyMinY = Infinity, polyMaxY = -Infinity;
        for (const pt of poly) {
          const sx = originX + pt[0] * zoom;
          const sy = originY - pt[1] * zoom;
          polyMinX = Math.min(polyMinX, sx);
          polyMaxX = Math.max(polyMaxX, sx);
          polyMinY = Math.min(polyMinY, sy);
          polyMaxY = Math.max(polyMaxY, sy);
        }

        const hatchType = pal.hatchType || "shingle";
        if (hatchType === "seam") {
          // Standing Seam Metal Ribs (Clean vertical parallel lines)
          ctx.strokeStyle = isSelected ? "rgba(255, 255, 255, 0.35)" : "rgba(6, 182, 212, 0.25)";
          ctx.lineWidth = 1.0;
          const seamSpacing = Math.max(12, zoom * 1.5); // 1.5ft standing seam spacing
          for (let sx = polyMinX - 20; sx <= polyMaxX + 20; sx += seamSpacing) {
            ctx.beginPath();
            ctx.moveTo(sx, polyMinY - 10);
            ctx.lineTo(sx, polyMaxY + 10);
            ctx.stroke();
          }
        } else if (hatchType === "tile") {
          // Spanish / Clay Tile Scallops
          ctx.strokeStyle = isSelected ? "rgba(255, 255, 255, 0.30)" : "rgba(234, 88, 12, 0.25)";
          ctx.lineWidth = 0.9;
          const rowH = Math.max(10, zoom * 1.0);
          const colW = Math.max(14, zoom * 1.4);
          let rowIdx = 0;
          for (let sy = polyMinY; sy <= polyMaxY + rowH; sy += rowH) {
            const xOffset = (rowIdx % 2) * (colW / 2);
            for (let sx = polyMinX - colW; sx <= polyMaxX + colW; sx += colW) {
              ctx.beginPath();
              ctx.arc(sx + xOffset + colW / 2, sy, colW / 2, Math.PI, 0, false);
              ctx.stroke();
            }
            rowIdx++;
          }
        } else if (hatchType === "membrane") {
          // Commercial TPO Grid
          ctx.strokeStyle = "rgba(148, 163, 184, 0.18)";
          ctx.lineWidth = 0.8;
          const gridStep = Math.max(18, zoom * 2.5);
          for (let sx = polyMinX; sx <= polyMaxX; sx += gridStep) {
            ctx.beginPath();
            ctx.moveTo(sx, polyMinY);
            ctx.lineTo(sx, polyMaxY);
            ctx.stroke();
          }
          for (let sy = polyMinY; sy <= polyMaxY; sy += gridStep) {
            ctx.beginPath();
            ctx.moveTo(polyMinX, sy);
            ctx.lineTo(polyMaxX, sy);
            ctx.stroke();
          }
        } else {
          // Asphalt Shingle Coursing Lines with Staggered Tabs
          ctx.strokeStyle = isSelected ? "rgba(255, 255, 255, 0.28)" : "rgba(100, 116, 139, 0.22)";
          ctx.lineWidth = 0.8;
          const shingleRowH = Math.max(8, zoom * 0.7); // ~8" shingle exposure
          const tabSpacing = Math.max(16, zoom * 1.5);
          let rowIdx = 0;
          for (let sy = polyMinY; sy <= polyMaxY + shingleRowH; sy += shingleRowH) {
            // Horizontal coursing line
            ctx.beginPath();
            ctx.moveTo(polyMinX, sy);
            ctx.lineTo(polyMaxX, sy);
            ctx.stroke();

            // Vertical shingle tab keyways
            const xOffset = (rowIdx % 2) * (tabSpacing / 2);
            for (let sx = polyMinX + xOffset; sx <= polyMaxX; sx += tabSpacing) {
              ctx.beginPath();
              ctx.moveTo(sx, sy);
              ctx.lineTo(sx, sy + shingleRowH);
              ctx.stroke();
            }
            rowIdx++;
          }
        }
        ctx.restore();
      }

      // Razor-Sharp Boundary Outline Stroke (Eliminates internal saw-tooth spikes!)
      ctx.strokeStyle = isSelected
        ? "#f59e0b"
        : isHovered
        ? "#fbbf24"
        : pal.borderCss || "#d97706";
      ctx.lineWidth = isSelected ? 2.5 : 1.6;
      ctx.stroke();

      // Prominent Architectural Ridge Line
      const ridgeVerts = roof.ridge_vertices || roof.provenance?.ridge_vertices;
      if (ridgeVerts && ridgeVerts.length >= 2) {
        ctx.strokeStyle = isSelected ? "#ffffff" : "#f59e0b";
        ctx.lineWidth = 2.4;
        ctx.beginPath();
        const rx0 = originX + ridgeVerts[0][0] * zoom;
        const ry0 = originY - ridgeVerts[0][1] * zoom;
        ctx.moveTo(rx0, ry0);
        for (let rIdx = 1; rIdx < ridgeVerts.length; rIdx++) {
          const rx = originX + ridgeVerts[rIdx][0] * zoom;
          const ry = originY - ridgeVerts[rIdx][1] * zoom;
          ctx.lineTo(rx, ry);
        }
        ctx.stroke();
      }

      // Slope Direction Arrow & Fall Indicator
      const slopeDeg = roof.slope_degrees !== undefined && roof.slope_degrees !== null ? Number(roof.slope_degrees) : null;
      const slopeProv = roof.slope_provenance || roof.provenance?.slope_provenance;
      const hasDeterministicSlope = slopeProv === "VERIFIED_EXPLICIT" || slopeProv === "DERIVED_GEOMETRIC";
      
      if (showSlopeArrows && slopeDeg !== null && slopeDeg > 0.1 && hasDeterministicSlope) {
        const arrowLen = Math.min(26, Math.max(16, zoom * 1.2));
        ctx.strokeStyle = isSelected ? "#ffffff" : "#fbbf24";
        ctx.fillStyle = isSelected ? "#ffffff" : "#fbbf24";
        ctx.lineWidth = 1.8;

        ctx.beginPath();
        ctx.moveTo(centerScreenX, centerScreenY - arrowLen / 2);
        ctx.lineTo(centerScreenX, centerScreenY + arrowLen / 2);
        ctx.stroke();

        // Arrowhead
        ctx.beginPath();
        ctx.moveTo(centerScreenX, centerScreenY + arrowLen / 2);
        ctx.lineTo(centerScreenX - 4, centerScreenY + arrowLen / 2 - 6);
        ctx.lineTo(centerScreenX + 4, centerScreenY + arrowLen / 2 - 6);
        ctx.closePath();
        ctx.fill();
      }

      // Prepare callout tag data for the second (collision-avoidance) pass
      if (showPitchTags || showAreaTags) {
        const pitchText = roof.pitch_ratio ? roof.pitch_ratio : slopeDeg !== null ? `${slopeDeg.toFixed(1)}°` : "FLAT";
        const trueSqft = Number(roof.true_surface_area_sqft || roof.plan_area_sqft || 0);
        const roofTypeStr = roof.roof_type || "ROOF";
        const labelText = `R${String(index + 1).padStart(2, "0")} · ${roofTypeStr} | ${trueSqft.toFixed(0)} SF | ${pitchText}`;

        ctx.font = "bold 9px JetBrains Mono, monospace";
        const txtWidth = ctx.measureText(labelText).width;
        const bW = txtWidth + 12;
        const bH = 18;

        calloutsToRender.push({
          index,
          roof,
          guid,
          isSelected,
          isHovered,
          centerScreenX,
          centerScreenY,
          labelText,
          badgeWidth: bW,
          badgeHeight: bH,
          targetX: centerScreenX,
          targetY: centerScreenY + 12,
        });
      }

      ctx.restore();
    });

    // -------------------------------------------------------------------------
    // 3B. Smart Collision-Free Callout Placement Pass
    // -------------------------------------------------------------------------
    if (calloutsToRender.length > 0) {
      // Sort callouts by X position to resolve horizontal cascades
      calloutsToRender.sort((a, b) => a.centerScreenX - b.centerScreenX);

      // Stagger vertical offsets when callouts horizontally collide (distance < badgeWidth + 8)
      for (let i = 0; i < calloutsToRender.length; i++) {
        const current = calloutsToRender[i];
        let collisionCount = 0;

        for (let j = 0; j < i; j++) {
          const prev = calloutsToRender[j];
          const distHoriz = Math.abs(current.targetX - prev.targetX);
          const distVert = Math.abs(current.targetY - prev.targetY);

          if (distHoriz < (current.badgeWidth + prev.badgeWidth) / 2 + 10 && distVert < 22) {
            collisionCount++;
          }
        }

        if (collisionCount > 0) {
          // Stagger upwards or downwards alternatively to break collision clusters
          const offsetDir = collisionCount % 2 === 1 ? -1 : 1;
          const multiplier = Math.ceil(collisionCount / 2);
          current.targetY = current.centerScreenY + offsetDir * (multiplier * 26 + 10);
        }
      }

      // Draw Leader Lines and Badges
      calloutsToRender.forEach((c) => {
        const isDisplaced = Math.abs(c.targetY - (c.centerScreenY + 12)) > 6;

        if (isDisplaced) {
          // Leader Line with anchor dot at roof centroid
          ctx.strokeStyle = c.isSelected ? "#f59e0b" : "rgba(245, 158, 11, 0.45)";
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.arc(c.centerScreenX, c.centerScreenY, 2.5, 0, Math.PI * 2);
          ctx.fillStyle = c.isSelected ? "#f59e0b" : "#d97706";
          ctx.fill();

          ctx.beginPath();
          ctx.moveTo(c.centerScreenX, c.centerScreenY);
          ctx.lineTo(c.targetX, c.targetY);
          ctx.stroke();
        }

        // Callout Pill Badge
        ctx.fillStyle = c.isSelected ? "#78350f" : "rgba(12, 26, 46, 0.92)";
        ctx.strokeStyle = c.isSelected ? "#f59e0b" : "rgba(30, 58, 95, 0.85)";
        ctx.lineWidth = c.isSelected ? 1.5 : 1.0;
        ctx.beginPath();
        ctx.roundRect(
          c.targetX - c.badgeWidth / 2,
          c.targetY - c.badgeHeight / 2,
          c.badgeWidth,
          c.badgeHeight,
          4
        );
        ctx.fill();
        ctx.stroke();

        // Badge Text
        ctx.font = "bold 9px JetBrains Mono, monospace";
        ctx.fillStyle = c.isSelected ? "#fef3c7" : "#fbbf24";
        ctx.textAlign = "center";
        ctx.fillText(c.labelText, c.targetX, c.targetY + 3.2);
        ctx.textAlign = "left";
      });
    }

    // 4. Architectural Scale Bar (Bottom Left)
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

    // 5. North Arrow Indicator (Bottom Right)
    const naX = width - 35;
    const naY = height - 35;
    ctx.strokeStyle = "#f59e0b";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(naX, naY, 13, 0, Math.PI * 2);
    ctx.stroke();

    ctx.fillStyle = "#f59e0b";
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
  }, [
    displayRoofs,
    walls,
    pan,
    zoom,
    selectedRoofGuid,
    hoveredGuid,
    showSlopeArrows,
    showPitchTags,
    showAreaTags,
    showWallFootprint,
    showHatches,
    getCleanRoofPolygon,
  ]);

  // Click Handler for 2D Selection
  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const width = canvas.parentElement?.clientWidth || 800;
    const height = canvas.parentElement?.clientHeight || 600;
    const originX = width / 2 + pan.x;
    const originY = height / 2 + pan.y;

    const worldX = (mouseX - originX) / zoom;
    const worldY = -(mouseY - originY) / zoom;

    // Point in clean boundary polygon test
    for (let r of displayRoofs) {
      const poly = getCleanRoofPolygon(r);
      if (poly.length < 3) continue;

      let inside = false;
      for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const xi = poly[i][0],
          yi = poly[i][1];
        const xj = poly[j][0],
          yj = poly[j][1];

        const intersect =
          yi > worldY !== yj > worldY &&
          worldX < ((xj - xi) * (worldY - yi)) / (yj - yi) + xi;
        if (intersect) inside = !inside;
      }

      if (inside) {
        onSelectRoofGuid(r.ifc_guid || r.id);
        return;
      }
    }
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    dragStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStartRef.current.x,
      y: e.clientY - dragStartRef.current.y,
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 0.88;
    setZoom((prev) => Math.max(3, Math.min(100, prev * factor)));
  };

  return (
    <div ref={containerRef} className="relative h-full w-full bg-[#070d18] select-none overflow-hidden">
      {/* 2D Viewport Header Bar */}
      <div className="absolute top-3 left-3 right-3 z-10 flex items-center justify-between pointer-events-none flex-wrap gap-2">
        {/* Tool Selector */}
        <div className="flex items-center space-x-1 bg-[#0a121e]/90 backdrop-blur-md p-1 rounded-md border border-[#162840] shadow-lg pointer-events-auto">
          <button
            onClick={() => setActiveTool("select")}
            className={`p-1.5 rounded flex items-center gap-1 text-[10px] font-mono font-bold transition-all cursor-pointer ${
              activeTool === "select"
                ? "bg-cyan-600 text-white"
                : "text-gray-400 hover:text-white hover:bg-gray-800"
            }`}
            title="Select Roof Plane"
          >
            <MousePointer size={12} />
            <span>Select</span>
          </button>
          <button
            onClick={() => setActiveTool("pan")}
            className={`p-1.5 rounded flex items-center gap-1 text-[10px] font-mono font-bold transition-all cursor-pointer ${
              activeTool === "pan"
                ? "bg-cyan-600 text-white"
                : "text-gray-400 hover:text-white hover:bg-gray-800"
            }`}
            title="Pan View"
          >
            <Hand size={12} />
            <span>Pan</span>
          </button>
        </div>

        {/* Roof Type Filter Buttons */}
        <div className="flex items-center space-x-1 bg-[#0a121e]/90 backdrop-blur-md p-1 rounded-md border border-[#162840] shadow-lg pointer-events-auto text-[10px] font-mono">
          <button
            onClick={() => setRoofTypeFilter("ALL")}
            className={`px-2 py-0.5 rounded font-bold transition-all cursor-pointer ${
              roofTypeFilter === "ALL"
                ? "bg-cyan-600 text-white"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            ALL ROOFS ({roofs.length})
          </button>
          {availableTypes.map((type) => (
            <button
              key={type}
              onClick={() => setRoofTypeFilter(type)}
              className={`px-2 py-0.5 rounded font-bold transition-all cursor-pointer ${
                roofTypeFilter === type
                  ? "bg-cyan-600 text-white"
                  : "text-gray-400 hover:text-gray-200"
              }`}
            >
              {type}
            </button>
          ))}
        </div>

        {/* Overlay Controls */}
        <div className="flex items-center space-x-1.5 bg-[#0a121e]/90 backdrop-blur-md p-1 rounded-md border border-[#162840] shadow-lg pointer-events-auto text-xs">
          <button
            onClick={() => setShowSlopeArrows(!showSlopeArrows)}
            className={`px-2 py-0.5 rounded text-[10px] font-mono flex items-center gap-1 transition-all cursor-pointer ${
              showSlopeArrows
                ? "bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold"
                : "text-gray-400 hover:text-white"
            }`}
            title="Toggle Slope Fall Arrows"
          >
            <TrendingDown size={11} />
            <span>Slope Arrows</span>
          </button>
          <button
            onClick={() => setShowPitchTags(!showPitchTags)}
            className={`px-2 py-0.5 rounded text-[10px] font-mono flex items-center gap-1 transition-all cursor-pointer ${
              showPitchTags
                ? "bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold"
                : "text-gray-400 hover:text-white"
            }`}
            title="Toggle Pitch Callouts"
          >
            <Layers size={11} />
            <span>Pitch</span>
          </button>
          <button
            onClick={() => setShowAreaTags(!showAreaTags)}
            className={`px-2 py-0.5 rounded text-[10px] font-mono flex items-center gap-1 transition-all cursor-pointer ${
              showAreaTags
                ? "bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold"
                : "text-gray-400 hover:text-white"
            }`}
            title="Toggle Area SF Tags"
          >
            <Box size={11} />
            <span>Area</span>
          </button>
          <button
            onClick={() => setShowHatches(!showHatches)}
            className={`px-2 py-0.5 rounded text-[10px] font-mono flex items-center gap-1 transition-all cursor-pointer ${
              showHatches
                ? "bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold"
                : "text-gray-400 hover:text-white"
            }`}
            title="Toggle Architectural CAD Hatches"
          >
            <Sparkles size={11} />
            <span>Hatches</span>
          </button>
          <button
            onClick={() => setShowWallFootprint(!showWallFootprint)}
            className={`px-2 py-0.5 rounded text-[10px] font-mono flex items-center gap-1 transition-all cursor-pointer ${
              showWallFootprint
                ? "bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold"
                : "text-gray-400 hover:text-white"
            }`}
            title="Toggle Wall Footprint"
          >
            <Eye size={11} />
            <span>Walls</span>
          </button>
          <div className="w-[1px] h-3 bg-gray-700 mx-0.5" />
          <button
            onClick={autoFit}
            className="p-1 rounded hover:bg-gray-800 text-emerald-400 hover:text-white transition-colors cursor-pointer"
            title="Auto-Fit 2D Roof Plan"
          >
            <Maximize2 size={12} />
          </button>
        </div>
      </div>

      {/* Canvas */}
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onClick={handleCanvasClick}
        onWheel={handleWheel}
        className="h-full w-full block cursor-crosshair"
      />

      {/* 2D Bottom Telemetry HUD */}
      <div className="absolute bottom-2.5 left-3 right-3 z-10 flex items-center justify-between text-[9px] font-mono text-gray-400 pointer-events-none">
        <div className="bg-[#0a121e]/90 backdrop-blur-sm px-2 py-0.5 rounded border border-[#162840] flex items-center gap-3">
          <span>ROOF PLAN SCALE: 1/8" = 1'-0"</span>
          <span>ZOOM: {(zoom * 5).toFixed(0)}%</span>
          <span>DISPLAYED PLANES: {displayRoofs.length}</span>
        </div>
        <div className="bg-[#0a121e]/90 backdrop-blur-sm px-2 py-0.5 rounded border border-[#162840] text-amber-400 font-bold">
          ROOFING 2D ↔ 3D SYNC ACTIVE
        </div>
      </div>
    </div>
  );
}
