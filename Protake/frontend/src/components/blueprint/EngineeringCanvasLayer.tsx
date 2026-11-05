import { useMemo, useState } from "react";
import { Group, Line, Text, Tag, Label, Circle } from "react-konva";
import type Konva from "konva";
import { toast } from "sonner";
import { useApp } from "@/state/AppContext";
import { BackendApiService } from "@/api/backendApi";
import { toPixelPoints, centroid } from "@/lib/geometry";
import { formatLength, formatArea } from "@/lib/units";
import { getDetectionColor, getCanonicalWallCategory, TRADE_COLOR } from "@/lib/colors";
import { parseBackendDetectionId } from "@/lib/backendConversion";
import {
  analyzeEngineeringGeometry,
  HIGH_PRECISION,
  STANDARD_PRECISION,
  type EngineeringGeometry
} from "@/lib/engineeringGeometry";
import type { Detection, Point, TradeId } from "@/types";

interface Props {
  detections: Detection[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  interactive?: boolean;
  stageW: number;
  stageH: number;
  isEditingNode?: boolean;
  showPrecisionData?: boolean;
  engineeringMode?: boolean;
  layerOpacity?: number;
}

const DEFAULT_SCALE = 50;

function getDoorWindowCodes(
  detections: Detection[],
  calibration: Record<string, number>
): Record<string, string> {
  const codes: Record<string, string> = {};
  let doorIndex = 1;
  let windowIndex = 1;

  for (const d of detections) {
    if (d.kind !== "door" && d.kind !== "window") continue;
    const prefix = d.kind === "door" ? "D" : "W";
    const index = d.kind === "door" ? doorIndex++ : windowIndex++;
    const scale = calibration[d.sheetId] ?? DEFAULT_SCALE;
    const pts = d.points;
    let widthInches = 36;

    if (pts && pts.length >= 2) {
      const dx = pts[1].x - pts[0].x;
      const dy = pts[1].y - pts[0].y;
      const normLen = Math.sqrt(dx * dx + dy * dy);
      const lenFt = normLen * scale;
      widthInches = Math.round(lenFt * 12);
    }

    codes[d.id] = `${prefix}${index} (${widthInches}")`;
  }

  return codes;
}

function shouldDeemphasizeRoom(
  detection: Detection,
  activeTradeId: TradeId | null,
  showRoomGeometry: boolean
): boolean {
  if (detection.kind !== "room") return false;
  if (!showRoomGeometry) return true;
  if (detection.roomType === "exterior_covered") return false;
  return activeTradeId !== null && detection.trade !== activeTradeId;
}

function isVisibleForActiveTrade(
  detection: Detection,
  activeTradeId: TradeId | null,
  isRcpPage: boolean = false
): boolean {
  if (detection.status === "rejected") return false;
  if (!activeTradeId) return true;
  if (activeTradeId === "drywall") {
    if (isRcpPage) {
      return false; // RCP sheets never render drywall partition wall geometry
    }
    // Drywall markup renders ONLY canonical ArchitecturalWall entities (reconstructed physical walls)
    // Never render raw unclassified CAD vector lines (backend-wall-*) which contain grid/curb noise
    return (
      detection.kind === "wall" &&
      detection.id.startsWith("backend-archwall-")
    );
  }
  if (activeTradeId === "openings") {
    return detection.kind === "door" || detection.kind === "window";
  }
  if (detection.kind === "wall") {
    return (
      activeTradeId === "painting" &&
      detection.id.startsWith("backend-archwall-")
    );
  }

  if (detection.kind === "room") {
    if (detection.roomType === "exterior_covered") return true;
    return detection.trade === activeTradeId;
  }
  return true;
}


function cleanWallId(id: string): string {
  return id
    .replace(/^backend-archwall-/, "AW-")
    .replace(/^backend-wall-/, "W-")
    .replace(/^backend-detection-/, "DET-");
}

function buildEngineeringLabel(
  detection: Detection,
  geometry: EngineeringGeometry | undefined,
  code: string | undefined,
  selected: boolean,
  hovered: boolean
): string {
  if (detection.kind === "wall") {
    const category = detection.wallTypeCode?.replace(/_/g, " ").replace(/\b\w/g, ch => ch.toUpperCase()) || "Wall";
    const tag = detection.wallTag ? `[${detection.wallTag}] ` : "";
    const lenStr = geometry?.length ? ` • ${formatLength(geometry.length.value)}` : "";

    if (detection.status === "approved") {
      return `✓ APPROVED · ${tag}${category}${lenStr}`;
    }
    if (detection.status === "rejected") {
      return `✗ REJECTED · ${tag}${category}`;
    }
    return `${tag}${category}${lenStr}`;
  } else if (detection.kind === "room") {
    const name = detection.name || "Room";
    if (geometry?.area) {
      return `${name} (${formatArea(geometry.area.value)})`;
    }
    return name;
  } else {
    const prefix = code ? `${detection.kind === "door" ? "Door" : "Window"} ${code}` : detection.name;
    return prefix || detection.kind;
  }
}

export default function EngineeringCanvasLayer({
  detections,
  selectedId,
  onSelect,
  interactive,
  stageW,
  stageH,
  isEditingNode = false,
  layerOpacity = 75,
}: Props) {
  const { state, dispatch } = useApp();
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const precision = useMemo(() => {
    const zoomLevel = state.zoom || 1.0;
    return zoomLevel > 2.0 ? HIGH_PRECISION : STANDARD_PRECISION;
  }, [state.zoom]);

  const engineeringGeometries = useMemo(() => {
    const geometries: Record<string, EngineeringGeometry> = {};
    detections.forEach(detection => {
      const scale = state.calibration[detection.sheetId] ?? DEFAULT_SCALE;
      geometries[detection.id] = analyzeEngineeringGeometry(detection, scale, precision);
    });
    return geometries;
  }, [detections, state.calibration, precision]);

  const codes = useMemo(() => getDoorWindowCodes(detections, state.calibration), [detections, state.calibration]);
  const activeTradeId = (state.summaryTab === "drywall" || state.summaryTab === "painting" || state.summaryTab === "flooring" || state.summaryTab === "roofing" || state.summaryTab === "furniture" || state.summaryTab === "openings") ? state.summaryTab : null;

  const handleAnchorDragEnd = async (d: Detection, pointIndex: number, newX: number, newY: number) => {
    const updatedPoints = d.points.map((p, idx) =>
      idx === pointIndex ? {
        x: Math.round(Math.max(0, Math.min(1, newX)) / precision.coordinatePrecision) * precision.coordinatePrecision,
        y: Math.round(Math.max(0, Math.min(1, newY)) / precision.coordinatePrecision) * precision.coordinatePrecision
      } : p
    );

    const parsed = parseBackendDetectionId(d.id);
    if (!parsed) return;

    const { source, backendId } = parsed;
    const scale = state.calibration[d.sheetId] ?? DEFAULT_SCALE;

    try {
      const newGeometry = analyzeEngineeringGeometry(
        { ...d, points: updatedPoints },
        scale,
        precision
      );

      if (source === "room" && newGeometry.area && newGeometry.perimeter) {
        const polygonNorm = updatedPoints.map((p) => [p.x, p.y]);
        await BackendApiService.updateRoom(backendId, {
          polygon_norm: polygonNorm,
          area_sqft: newGeometry.area.value,
          perimeter_ft: newGeometry.perimeter.value,
        });

        dispatch({
          type: "UPDATE_DETECTION",
          id: d.id,
          fields: {
            points: updatedPoints,
            areaSqFt: newGeometry.area.value,
            perimeterFt: newGeometry.perimeter.value,
          },
        });
      } else if (source === "wall" && newGeometry.length) {
        const h = d.perimeterFt && d.areaSqFt ? d.areaSqFt / d.perimeterFt : 9;
        const sides = d.wallType === "interior" ? 2 : 1;
        const areaSqFt = Math.round(newGeometry.length.value * h * sides);

        await BackendApiService.updateWall(backendId, {
          start_norm: updatedPoints[0],
          end_norm: updatedPoints[1],
          length_ft: newGeometry.length.value,
        });

        dispatch({
          type: "UPDATE_DETECTION",
          id: d.id,
          fields: {
            points: updatedPoints,
            perimeterFt: newGeometry.length.value,
            areaSqFt,
          },
        });
      }

      toast.success("Updated geometry coordinates");
    } catch (err) {
      console.error("Failed to save geometry update:", err);
      toast.error("Failed to save updated geometry");
    }
  };

  const activeSheet = state.sheets.find((s) => s.id === state.activeSheetId);
  const isRcp = activeSheet?.pageType === "rcp" || (activeSheet as any)?.page_type === "rcp" || activeSheet?.pageType === "reflected_ceiling_plan";

  const filteredDetections = detections.filter((d) => {
    if (!d.points || d.points.length < 2) return false;

    if (state.focusedDetectionId && d.id !== state.focusedDetectionId) return false;
    if (!isVisibleForActiveTrade(d, activeTradeId, isRcp)) return false;

    if (d.trade && state.hiddenTrades[d.trade.toLowerCase() as TradeId]) {
      if (d.kind === "room" && state.summaryTab === d.trade.toLowerCase()) {
        return false;
      } else if (d.kind !== "room") {
        return false;
      }
    }

    if (d.kind === "wall" && !state.wallCategoryFilter) {
      const wallCode = getCanonicalWallCategory(d.wallTypeCode, d.wallType, d.wallTag, d.status, d.confidence, d.classification);
      if (state.hiddenWallCategories[wallCode]) {
        return false;
      }
    }

    if (d.kind === "wall" && state.hiddenLayers.arch_walls) return false;
    if (d.kind === "room" && state.hiddenLayers.rooms) return false;
    if ((d.kind === "door" || d.kind === "window") && state.hiddenLayers.openings) return false;
    if (d.kind === "column" && state.hiddenLayers.columns) return false;
    if (d.kind === "annotation" && state.hiddenLayers.annotations) return false;

    return d.kind !== "room" || (d.areaSqFt ?? 0) >= 1 || d.id === selectedId;
  });

  const isTakeoffEligible = !activeSheet || activeSheet.isTakeoffEligible !== false;

  if (!isTakeoffEligible) {
    return <Group />;
  }

  return (
    <Group>
      {filteredDetections.map((d) => {
        const geometry = engineeringGeometries[d.id];
        const isWall = d.kind === "wall";
        const code = getCanonicalWallCategory(d.wallTypeCode, d.wallType, d.wallTag, d.status, d.confidence, d.classification);

        if (isWall && state.hiddenWallCategories[code]) {
          return null;
        }

        const pts = toPixelPoints(d.points, stageW, stageH);
        const baseColor = getDetectionColor(d);

        const activeTradeHidden = state.summaryTab && state.hiddenTrades[state.summaryTab as TradeId];
        let tradeColor = baseColor;
        if (d.kind === "room" && d.roomType !== "exterior_covered" && state.summaryTab && !activeTradeHidden) {
          const activeTradeColor = TRADE_COLOR[state.summaryTab];
          if (activeTradeColor) {
            tradeColor = activeTradeColor;
          }
        }

        const isApproved = d.status === "approved";
        const isRejected = d.status === "rejected";

        // Category color (from getDetectionColor / getCanonicalWallCategory) is
        // ALWAYS the stroke/fill color, regardless of approval status. Approval
        // or rejection is layered on top via badges, glow, dash pattern, and
        // line weight below — it must never replace the category color itself
        // (a NEEDS_REVIEW wall must stay gray even once approved).
        const strokeColor = baseColor;

        const selected = d.id === selectedId;
        const hovered = d.id === hoveredId;
        const emphasized = selected || hovered;
        const c = centroid(d.points);

        const isDimmed = isWall && !!state.wallCategoryFilter && state.wallCategoryFilter !== code && !selected;
        const deemphasizeRoom = shouldDeemphasizeRoom(d, activeTradeId, state.showRoomGeometry) && !selected;
        const opacityRatio = (layerOpacity ?? 75) / 100;

        const hasWallFootprint = isWall && d.points.length >= 3;

        return (
          <Group key={d.id}>
            {/* Wall Footprint Polygon (when available) */}
            {isWall && d.wallPolygon && d.wallPolygon.length >= 3 && (
              <Line
                points={toPixelPoints(d.wallPolygon, stageW, stageH)}
                closed={true}
                fill={`${baseColor}${emphasized ? "44" : isApproved ? "30" : "1A"}`}
                stroke="transparent"
                opacity={isDimmed ? 0.15 : isRejected ? 0.45 : opacityRatio}
                listening={false}
              />
            )}

            {/* Main Geometry Line / Clipped Segments / Room Polygon */}
            {isWall && d.clippedSegments && d.clippedSegments.length > 0 ? (
              d.clippedSegments.map((seg, sIdx) => {
                const segPts = toPixelPoints(seg, stageW, stageH);
                return (
                  <Line
                    key={`${d.id}-seg-${sIdx}`}
                    points={segPts}
                    closed={false}
                    stroke={strokeColor}
                    strokeWidth={selected ? 3.5 : isApproved ? 2.5 : hovered ? 2.2 : 1.8}
                    dash={isRejected ? [6, 4] : undefined}
                    shadowColor={selected || isApproved ? strokeColor : undefined}
                    shadowBlur={selected ? 8 : isApproved ? 4 : hovered ? 4 : 0}
                    shadowOpacity={selected ? 0.8 : isApproved ? 0.5 : 0}
                    lineCap="round"
                    lineJoin="round"
                    hitStrokeWidth={20}
                    opacity={isDimmed ? 0.15 : isRejected ? 0.45 : opacityRatio}
                    onClick={(e) => {
                      if (!interactive) return;
                      e.cancelBubble = true;
                      onSelect(d.id);
                    }}
                    onTap={(e) => {
                      if (!interactive) return;
                      e.cancelBubble = true;
                      onSelect(d.id);
                    }}
                    listening={interactive}
                    onMouseEnter={(e: Konva.KonvaEventObject<MouseEvent>) => {
                      if (!interactive) return;
                      setHoveredId(d.id);
                      const stage = e.target.getStage();
                      if (stage) stage.container().style.cursor = "pointer";
                    }}
                    onMouseLeave={(e: Konva.KonvaEventObject<MouseEvent>) => {
                      setHoveredId((cur) => (cur === d.id ? null : cur));
                      const stage = e.target.getStage();
                      if (stage) stage.container().style.cursor = "default";
                    }}
                  />
                );
              })
            ) : (
              <Line
                points={pts}
                closed={d.kind !== "wall" || hasWallFootprint}
                fill={
                  isWall
                    ? hasWallFootprint
                      ? `${baseColor}${emphasized ? "44" : isApproved ? "33" : "20"}`
                      : "transparent"
                    : deemphasizeRoom
                      ? "transparent"
                      : `${tradeColor}${emphasized ? "E6" : isRejected ? "40" : "A6"}`
                }
                stroke={deemphasizeRoom ? "rgba(148,163,184,0.4)" : strokeColor}
                strokeWidth={
                  isWall
                    ? (selected ? 3.5 : isApproved ? 2.5 : hovered ? 2.2 : 1.8)
                    : deemphasizeRoom ? 1 : selected ? 2.5 : 1.5
                }
                dash={isRejected ? [6, 4] : undefined}
                shadowColor={selected || isApproved ? strokeColor : undefined}
                shadowBlur={selected ? 8 : isApproved ? 4 : hovered ? 4 : 0}
                shadowOpacity={selected ? 0.8 : isApproved ? 0.5 : 0}
                lineCap="round"
                lineJoin="round"
                hitStrokeWidth={isWall ? 20 : undefined}
                opacity={isDimmed ? 0.15 : isRejected ? 0.45 : opacityRatio}
                onClick={(e) => {
                  if (!interactive) return;
                  e.cancelBubble = true;
                  onSelect(d.id);
                }}
                onTap={(e) => {
                  if (!interactive) return;
                  e.cancelBubble = true;
                  onSelect(d.id);
                }}
                listening={interactive}
                onMouseEnter={(e: Konva.KonvaEventObject<MouseEvent>) => {
                  if (!interactive) return;
                  setHoveredId(d.id);
                  const stage = e.target.getStage();
                  if (stage) stage.container().style.cursor = "pointer";
                }}
                onMouseLeave={(e: Konva.KonvaEventObject<MouseEvent>) => {
                  setHoveredId((cur) => (cur === d.id ? null : cur));
                  const stage = e.target.getStage();
                  if (stage) stage.container().style.cursor = "default";
                }}
              />
            )}

            {/* Approved / Rejected Visual Badge on Wall Centroid.
                The badge fill stays the real category color (baseColor) —
                approval/rejection is shown only via the ring color and the
                checkmark/x glyph, never by replacing the category color. */}
            {isWall && isApproved && !selected && (
              <Group x={c.x * stageW} y={c.y * stageH} listening={false}>
                <Circle radius={7} fill={baseColor} stroke="#10B981" strokeWidth={2} shadowBlur={4} shadowColor={baseColor} />
                <Text text="✓" fontSize={9} fill="#FFFFFF" fontStyle="bold" x={-3.5} y={-4.5} fontFamily="sans-serif" />
              </Group>
            )}

            {isWall && isRejected && !selected && (
              <Group x={c.x * stageW} y={c.y * stageH} listening={false}>
                <Circle radius={6} fill={baseColor} stroke="#EF4444" strokeWidth={2} />
                <Text text="✗" fontSize={8} fill="#FFFFFF" fontStyle="bold" x={-3} y={-4} fontFamily="sans-serif" />
              </Group>
            )}

            {/* Single-line Crisp Engineering Label ONLY when Selected, Hovered, or deep-zoomed room */}
            {(emphasized || (state.zoom > 3.0 && d.kind === "room")) && (() => {
              const labelText = buildEngineeringLabel(d, geometry, codes[d.id], selected, hovered);
              if (!labelText) return null;

              // Label border/text always reflects the category color; the
              // ✓ APPROVED / ✗ REJECTED text itself (from buildEngineeringLabel)
              // already conveys status without needing a color swap.
              const badgeColor = strokeColor;

              return (
                <Label x={c.x * stageW} y={c.y * stageH - (isWall ? 12 : 8)} listening={false}>
                  <Tag
                    fill="rgba(11,14,20,0.95)"
                    stroke={badgeColor}
                    strokeWidth={1.5}
                    cornerRadius={4}
                    shadowBlur={6}
                    shadowColor="black"
                    shadowOpacity={0.6}
                  />
                  <Text
                    text={labelText}
                    fontSize={selected ? 10.5 : 9}
                    fontStyle={selected ? "bold" : "normal"}
                    fontFamily="JetBrains Mono, monospace"
                    fill={badgeColor}
                    padding={4}
                  />
                </Label>
              );
            })()}

            {/* Anchor points only when selected for vertex adjustments */}
            {selected && d.points.map((pt, idx) => {
              const anchorX = pt.x * stageW;
              const anchorY = pt.y * stageH;
              return (
                <Circle
                  key={`anchor-${d.id}-${idx}`}
                  x={anchorX}
                  y={anchorY}
                  radius={isWall ? 5 : 6.5}
                  fill="#FFFFFF"
                  stroke={strokeColor}
                  strokeWidth={2}
                  shadowColor={strokeColor}
                  shadowBlur={4}
                  draggable={!isWall && !isEditingNode}
                  onDragMove={!isWall ? (e) => {
                    const canvasX = e.target.x();
                    const canvasY = e.target.y();
                    const normX = Math.max(0, Math.min(1, canvasX / stageW));
                    const normY = Math.max(0, Math.min(1, canvasY / stageH));
                    const updatedPoints = d.points.map((p, i) =>
                      i === idx ? { x: normX, y: normY } : p
                    );
                    dispatch({
                      type: "UPDATE_DETECTION",
                      id: d.id,
                      fields: { points: updatedPoints },
                    });
                  } : undefined}
                  onDragEnd={!isWall ? (e) => {
                    const canvasX = e.target.x();
                    const canvasY = e.target.y();
                    const normX = Math.max(0, Math.min(1, canvasX / stageW));
                    const normY = Math.max(0, Math.min(1, canvasY / stageH));
                    handleAnchorDragEnd(d, idx, normX, normY);
                  } : undefined}
                  listening={interactive}
                  onMouseEnter={(e) => {
                    const stage = e.target.getStage();
                    if (stage) stage.container().style.cursor = !isWall ? "move" : "default";
                  }}
                  onMouseLeave={(e) => {
                    const stage = e.target.getStage();
                    if (stage) stage.container().style.cursor = "default";
                  }}
                />
              );
            })}
          </Group>
        );
      })}
    </Group>
  );
}