import React, { useMemo } from "react";
import { AlertCircle, Compass } from "lucide-react";
import type { Detection, Point } from "@/types";
import { CanonicalWallCategory } from "@/lib/colors";
import { calculateWall3DGeometry, WallGeometry3DParams } from "@/lib/wallGeometry3D";

export interface Wall3DGeometryPreviewProps {
  detection?: Detection | null;
  lengthFt?: number | null;
  heightFt?: number | null;
  thicknessIn?: number | null;
  thicknessFt?: number | null;
  points?: Point[] | null;
  categoryCode?: CanonicalWallCategory | null;
  categoryColor?: string | null;
  categoryLabel?: string | null;
  wallTag?: string | null;
  compact?: boolean;
  className?: string;
  width?: number;
  height?: number;
}

export const Wall3DGeometryPreview: React.FC<Wall3DGeometryPreviewProps> = ({
  detection: d,
  lengthFt: propLengthFt,
  heightFt: propHeightFt,
  thicknessIn: propThicknessIn,
  thicknessFt: propThicknessFt,
  points: propPoints,
  categoryCode: propCategoryCode,
  categoryColor: propCategoryColor,
  compact = false,
  className = "",
  width = 300,
  height = 175,
}) => {
  // Extract parameters prioritizing explicit props, then detection fields
  const params: WallGeometry3DParams = useMemo(() => {
    const length = propLengthFt ?? d?.perimeterFt ?? null;
    const heightVal = propHeightFt ?? d?.heightFt ?? (d?.areaSqFt && d?.perimeterFt ? d.areaSqFt / d.perimeterFt : 9.0);
    const thicknessInch =
      propThicknessIn ??
      (d?.thicknessIn ? d.thicknessIn : d?.thicknessFt ? d.thicknessFt * 12 : 4.875);
    const thicknessF = propThicknessFt ?? (thicknessInch ? thicknessInch / 12 : 0.40625);

    const points = propPoints ?? d?.points ?? null;

    return {
      lengthFt: length,
      heightFt: heightVal,
      thicknessIn: thicknessInch,
      thicknessFt: thicknessF,
      points,
      categoryCode: propCategoryCode,
      wallType: d?.wallType,
      wallTypeCode: d?.wallTypeCode,
      wallTag: d?.wallTag,
      status: d?.status,
      confidence: d?.confidence,
      classification: (d as any)?.classification,
    };
  }, [
    d,
    propLengthFt,
    propHeightFt,
    propThicknessIn,
    propThicknessFt,
    propPoints,
    propCategoryCode,
  ]);

  const geo = useMemo(() => {
    const w = compact ? 56 : width;
    const h = compact ? 44 : height;
    return calculateWall3DGeometry(params, w, h);
  }, [params, compact, width, height]);

  // Color resolution
  const catColor = propCategoryColor || geo.categoryColor;

  // Render Compact Mini Icon (e.g. Header badge)
  if (compact) {
    if (!geo.valid) {
      return (
        <div
          className={`w-14 h-12 rounded-lg bg-black/40 border border-white/10 flex items-center justify-center text-gray-500 ${className}`}
          title="Geometry unavailable"
        >
          <AlertCircle size={16} />
        </div>
      );
    }

    return (
      <div
        className={`w-14 h-12 rounded-lg bg-black/40 border border-white/10 flex items-center justify-center relative overflow-hidden shrink-0 shadow-inner ${className}`}
        title={`${geo.categoryLabel} (${geo.lengthFt.toFixed(1)}' × ${geo.heightFt.toFixed(1)}' × ${geo.thicknessIn.toFixed(1)}")`}
      >
        <svg
          width="48"
          height="38"
          viewBox={`0 0 ${geo.viewBox.width} ${geo.viewBox.height}`}
          fill="none"
        >
          {/* Top Face */}
          <polygon
            points={geo.topFacePoints}
            fill={catColor}
            fillOpacity={0.65}
            stroke={catColor}
            strokeWidth="0.8"
          />
          {/* Front Face */}
          <polygon
            points={geo.frontFacePoints}
            fill={catColor}
            fillOpacity={0.9}
            stroke={catColor}
            strokeWidth="0.8"
          />
          {/* Side Face */}
          <polygon
            points={geo.sideFacePoints}
            fill="#0F172A"
            fillOpacity={0.7}
            stroke={catColor}
            strokeWidth="0.8"
          />
          {/* Outer stroke */}
          <polygon
            points={geo.outlinePoints}
            fill="none"
            stroke={catColor}
            strokeWidth="1.2"
          />
        </svg>
      </div>
    );
  }

  // Missing or Invalid Geometry State (Requirement 8: Do NOT create fake geometry)
  if (!geo.valid) {
    return (
      <div
        className={`rounded-lg bg-black/40 border border-white/10 p-4 flex flex-col items-center justify-center text-center space-y-2 font-mono ${className}`}
      >
        <AlertCircle size={20} className="text-amber-400/80" />
        <span className="text-[10px] text-amber-200/90 font-medium">
          {geo.errorMessage || "Geometry preview unavailable — source dimension missing"}
        </span>
        <span className="text-[9px] text-gray-500 font-sans">
          Wall length, height, or thickness was not provided in source data.
        </span>
      </div>
    );
  }

  // Full Engineering 3D Wall Preview
  return (
    <div
      className={`rounded-lg bg-[#080B10] border border-white/10 p-3 space-y-2 shadow-inner overflow-hidden flex flex-col ${className}`}
      data-testid="wall-3d-geometry-preview"
    >
      {/* Top Header Information & Dimension Summary */}
      <div className="flex items-center justify-between text-[9px] font-mono text-gray-400 border-b border-white/5 pb-1.5 gap-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ backgroundColor: catColor, boxShadow: `0 0 6px ${catColor}80` }}
          />
          <span className="font-semibold truncate" style={{ color: catColor }}>
            {geo.categoryLabel}
          </span>
          <span className="text-gray-600">•</span>
          <span className="flex items-center gap-1 text-gray-300">
            <Compass size={10} className="text-cyan-400" />
            {geo.orientationLabel}
          </span>
        </div>

        <div className="text-[9px] font-bold text-white shrink-0 bg-white/5 px-2 py-0.5 rounded border border-white/5">
          L {geo.lengthFt.toFixed(2)} ft • H {geo.heightFt.toFixed(2)} ft • T {geo.thicknessIn.toFixed(2)} in
        </div>
      </div>

      {/* SVG 3D Isometric Viewport */}
      <div className="relative w-full flex items-center justify-center py-1 overflow-hidden bg-black/30 rounded border border-white/5">
        <svg
          viewBox={`0 0 ${geo.viewBox.width} ${geo.viewBox.height}`}
          className="w-full h-auto max-h-[190px] select-none"
          style={{ overflow: "visible" }}
        >
          <defs>
            {/* Shading gradients */}
            <linearGradient id={`frontGrad-${catColor}`} x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor={catColor} stopOpacity="0.95" />
              <stop offset="100%" stopColor={catColor} stopOpacity="0.7" />
            </linearGradient>
            <linearGradient id={`topGrad-${catColor}`} x1="0%" y1="100%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.35" />
              <stop offset="100%" stopColor={catColor} stopOpacity="0.65" />
            </linearGradient>
          </defs>

          {/* Reference Ground / Shadow Grid */}
          <line
            x1="20"
            y1={geo.vertices.frontBottomLeft.y + 24}
            x2={geo.viewBox.width - 20}
            y2={geo.vertices.frontBottomLeft.y + 24}
            stroke="rgba(255,255,255,0.06)"
            strokeDasharray="3 3"
          />

          {/* 3D CUBIC FACES */}
          {/* Top Face */}
          <polygon
            points={geo.topFacePoints}
            fill={`url(#topGrad-${catColor})`}
            stroke={catColor}
            strokeWidth="1.2"
            strokeLinejoin="round"
          />

          {/* Front Face */}
          <polygon
            points={geo.frontFacePoints}
            fill={`url(#frontGrad-${catColor})`}
            stroke={catColor}
            strokeWidth="1.5"
            strokeLinejoin="round"
          />

          {/* Side / Depth Face */}
          <polygon
            points={geo.sideFacePoints}
            fill="#090D16"
            fillOpacity={0.8}
            stroke={catColor}
            strokeWidth="1.2"
            strokeLinejoin="round"
          />

          {/* Solid Wireframe Edge Accents */}
          <line
            x1={geo.vertices.frontTopRight.x}
            y1={geo.vertices.frontTopRight.y}
            x2={geo.vertices.frontBottomRight.x}
            y2={geo.vertices.frontBottomRight.y}
            stroke={catColor}
            strokeWidth="1.5"
          />

          {/* ─── ENGINEERING DIMENSION LINES ─── */}

          {/* 1. Length Dimension (Bottom Front) */}
          <g className="font-mono text-[9px]">
            {/* Extension lines / Ticks */}
            <line
              x1={geo.lengthDim.tickStart1.x}
              y1={geo.lengthDim.tickStart1.y}
              x2={geo.lengthDim.tickStart2.x}
              y2={geo.lengthDim.tickStart2.y}
              stroke="#34D399"
              strokeWidth="1"
            />
            <line
              x1={geo.lengthDim.tickEnd1.x}
              y1={geo.lengthDim.tickEnd1.y}
              x2={geo.lengthDim.tickEnd2.x}
              y2={geo.lengthDim.tickEnd2.y}
              stroke="#34D399"
              strokeWidth="1"
            />
            {/* Dimension Line */}
            <line
              x1={geo.lengthDim.start.x}
              y1={geo.lengthDim.start.y}
              x2={geo.lengthDim.end.x}
              y2={geo.lengthDim.end.y}
              stroke="#34D399"
              strokeWidth="1"
            />
            {/* Label */}
            <text
              x={geo.lengthDim.textPos.x}
              y={geo.lengthDim.textPos.y}
              fill="#34D399"
              fontSize="9"
              fontWeight="bold"
              textAnchor="middle"
              className="drop-shadow"
            >
              {geo.lengthDim.label}
            </text>
          </g>

          {/* 2. Height Dimension (Vertical Left) */}
          <g className="font-mono text-[9px]">
            <line
              x1={geo.heightDim.tickStart1.x}
              y1={geo.heightDim.tickStart1.y}
              x2={geo.heightDim.tickStart2.x}
              y2={geo.heightDim.tickStart2.y}
              stroke="#38BDF8"
              strokeWidth="1"
            />
            <line
              x1={geo.heightDim.tickEnd1.x}
              y1={geo.heightDim.tickEnd1.y}
              x2={geo.heightDim.tickEnd2.x}
              y2={geo.heightDim.tickEnd2.y}
              stroke="#38BDF8"
              strokeWidth="1"
            />
            <line
              x1={geo.heightDim.start.x}
              y1={geo.heightDim.start.y}
              x2={geo.heightDim.end.x}
              y2={geo.heightDim.end.y}
              stroke="#38BDF8"
              strokeWidth="1"
            />
            <text
              x={geo.heightDim.textPos.x}
              y={geo.heightDim.textPos.y}
              fill="#38BDF8"
              fontSize="9"
              fontWeight="bold"
              textAnchor="end"
              className="drop-shadow"
            >
              {geo.heightDim.label}
            </text>
          </g>

          {/* 3. Thickness Dimension (Top Depth) */}
          <g className="font-mono text-[8.5px]">
            <line
              x1={geo.thicknessDim.tickStart1.x}
              y1={geo.thicknessDim.tickStart1.y}
              x2={geo.thicknessDim.tickStart2.x}
              y2={geo.thicknessDim.tickStart2.y}
              stroke="#FBBF24"
              strokeWidth="1"
            />
            <line
              x1={geo.thicknessDim.tickEnd1.x}
              y1={geo.thicknessDim.tickEnd1.y}
              x2={geo.thicknessDim.tickEnd2.x}
              y2={geo.thicknessDim.tickEnd2.y}
              stroke="#FBBF24"
              strokeWidth="1"
            />
            <line
              x1={geo.thicknessDim.start.x}
              y1={geo.thicknessDim.start.y}
              x2={geo.thicknessDim.end.x}
              y2={geo.thicknessDim.end.y}
              stroke="#FBBF24"
              strokeWidth="1"
            />
            <text
              x={geo.thicknessDim.textPos.x}
              y={geo.thicknessDim.textPos.y}
              fill="#FBBF24"
              fontSize="8.5"
              fontWeight="bold"
              textAnchor="end"
              className="drop-shadow"
            >
              {geo.thicknessDim.label}
            </text>
          </g>
        </svg>
      </div>

      {/* Visual Scale Notice Disclaimer (Requirement 4) */}
      {geo.isVisualScaleApplied && (
        <div className="text-[9px] text-gray-500 italic text-center font-sans tracking-tight">
          {geo.visualScaleNotice}
        </div>
      )}
    </div>
  );
};

export default Wall3DGeometryPreview;
