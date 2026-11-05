import React, { useState } from "react";
import {
  Info,
  Layers,
  Box,
  Square,
  ShieldCheck,
  AlertTriangle,
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  Copy,
  Check,
  DoorOpen,
  Maximize2,
  Ruler,
  Compass,
  FileSpreadsheet,
  Hammer,
  Building2,
} from "lucide-react";
import { formatWallDisplay } from "./BIMModelTree";
import { toast } from "sonner";

export interface BIMInspectorProps {
  selectedGuid: string | null;
  wall?: any;
  lineItem?: any;
  filteredWalls?: any[];
  onSelectGuid?: (guid: string) => void;
  wasteFactor?: number;
  storeyName?: string;
  selectedFlooringElement?: any;
  selectedRoofElement?: any;
  trade?: "drywall" | "flooring" | "roofing";
}

export function ProvenanceBadge({
  status,
  compact = false,
}: {
  status?: string;
  compact?: boolean;
}) {
  const norm = status?.toUpperCase() || "UNKNOWN_UNRESOLVED";

  if (norm === "VERIFIED_EXPLICIT" || norm === "EXPLICIT") {
    return (
      <span
        className={`inline-flex items-center gap-1 font-mono font-bold bg-emerald-950/80 text-emerald-400 border border-emerald-700/60 rounded ${
          compact ? "px-1 py-0.2 text-[8px]" : "px-1.5 py-0.5 text-[9px]"
        }`}
        title="Directly from IFC Property Set / Material Layer"
      >
        <CheckCircle2 size={compact ? 8 : 10} />
        <span>{compact ? "EXPLICIT" : "VERIFIED EXPLICIT"}</span>
      </span>
    );
  }

  if (norm === "DERIVED_GEOMETRIC" || norm === "GEOMETRIC") {
    return (
      <span
        className={`inline-flex items-center gap-1 font-mono font-bold bg-sky-950/80 text-sky-400 border border-sky-700/60 rounded ${
          compact ? "px-1 py-0.2 text-[8px]" : "px-1.5 py-0.5 text-[9px]"
        }`}
        title="Calculated from 3D Solid / Curve Boundary Geometry"
      >
        <Box size={compact ? 8 : 10} />
        <span>{compact ? "GEOMETRIC" : "DERIVED GEOMETRIC"}</span>
      </span>
    );
  }

  if (norm === "CONFIGURED_ASSUMPTION" || norm === "CONFIGURED") {
    return (
      <span
        className={`inline-flex items-center gap-1 font-mono font-bold bg-amber-950/80 text-amber-400 border border-amber-700/60 rounded ${
          compact ? "px-1 py-0.2 text-[8px]" : "px-1.5 py-0.5 text-[9px]"
        }`}
        title="Configured Estimator Assumption / Profile Standard"
      >
        <AlertTriangle size={compact ? 8 : 10} />
        <span>{compact ? "CONFIGURED" : "CONFIGURED ASSUMPTION"}</span>
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1 font-mono font-bold bg-rose-950/80 text-rose-400 border border-rose-700/60 rounded ${
        compact ? "px-1 py-0.2 text-[8px]" : "px-1.5 py-0.5 text-[9px]"
      }`}
      title="Missing from IFC; Estimator Review Required"
    >
      <AlertCircle size={compact ? 8 : 10} />
      <span>{compact ? "UNRESOLVED" : "UNKNOWN UNRESOLVED"}</span>
    </span>
  );
}

export default function BIMInspector({
  selectedGuid,
  wall,
  lineItem,
  filteredWalls = [],
  onSelectGuid,
  wasteFactor = 10,
  storeyName,
  selectedFlooringElement,
  selectedRoofElement,
  trade = "drywall",
}: BIMInspectorProps) {
  const [copied, setCopied] = useState(false);

  // Section Collapse State
  const [sections, setSections] = useState<Record<string, boolean>>({
    identity: true,
    geometry: true,
    assembly: true,
    openings: true,
    scope: true,
    qto: true,
    provenance: false,
    psets: true,
  });

  const toggleSection = (key: string) => {
    setSections((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const activeFlooring = selectedFlooringElement || (wall?.flooring_category ? wall : null);
  const activeRoof = selectedRoofElement || (wall?.roof_type || (wall?.slope_degrees !== undefined && wall?.slope_degrees !== null) ? wall : null);

  // Element Navigation
  const currentIndex = filteredWalls.findIndex((w) => (w.ifc_guid || w.id) === selectedGuid);
  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex >= 0 && currentIndex < filteredWalls.length - 1;

  const handlePrev = () => {
    if (hasPrev && onSelectGuid) {
      onSelectGuid(filteredWalls[currentIndex - 1].ifc_guid || filteredWalls[currentIndex - 1].id);
    }
  };

  const handleNext = () => {
    if (hasNext && onSelectGuid) {
      onSelectGuid(filteredWalls[currentIndex + 1].ifc_guid || filteredWalls[currentIndex + 1].id);
    }
  };

  const handleCopyGuid = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (selectedGuid) {
      navigator.clipboard?.writeText(selectedGuid);
      setCopied(true);
      toast.success("IFC GUID copied to clipboard");
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // If no element selected
  if ((!wall && !activeFlooring && !activeRoof) || !selectedGuid) {
    return (
      <div className="h-full flex flex-col bg-[#0a121e] text-gray-400">
        <div className="p-2.5 border-b border-[#162840] flex items-center justify-between bg-[#080e18]">
          <div className="flex items-center space-x-1.5">
            <Info size={14} className="text-cyan-400" />
            <span className="text-xs font-bold uppercase tracking-wider text-gray-200">
              Inspector
            </span>
          </div>
        </div>
        <div className="flex-1 flex flex-col items-center justify-center p-6 text-center space-y-3 font-mono">
          <div className="w-12 h-12 rounded-xl bg-[#0e1726] border border-[#162840] flex items-center justify-center text-gray-500">
            <Box size={24} />
          </div>
          <div className="space-y-1">
            <h4 className="text-xs font-bold text-gray-300 uppercase tracking-wider">
              No Element Selected
            </h4>
            <p className="text-[11px] text-gray-500 leading-relaxed max-w-[220px]">
              Select an element from the Model Tree, 2D Plan, 3D Viewport, or BOQ Schedule to inspect engineering details.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // =========================================================================
  // ROOFING INSPECTOR VIEW (ESTIMATOR-FIRST CANONICAL QUALITY)
  // =========================================================================
  if (trade === "roofing" || activeRoof) {
    const rf = activeRoof || wall;
    const matName = rf?.material || rf?.material_name || "UNASSIGNED";
    const roofType = (rf?.roof_type || rf?.canonical_roof_type || "UNKNOWN").toUpperCase();
    const sourceType = rf?.ifc_entity_type || rf?.ifc_type || "IfcRoof";
    const trueSqft = Number(rf?.true_surface_area_sqft || rf?.plan_area_sqft || 0);
    const planSqft = Number(rf?.plan_area_sqft || 0);
    const slopeDeg = rf?.slope_degrees !== null && rf?.slope_degrees !== undefined ? Number(rf.slope_degrees) : null;
    const pitchStr = rf?.pitch_ratio || (slopeDeg !== null ? `${(Math.tan(slopeDeg * Math.PI / 180) * 12).toFixed(1)}:12` : "N/A");
    const elig = rf?.qto_eligibility || "ELIGIBLE";
    const isEligible = elig === "ELIGIBLE";
    const isReview = elig === "REVIEW_REQUIRED";
    const reasons = rf?.review_reasons || [];
    const displayMat =
      !matName || matName === "UNASSIGNED" || matName === "DEFAULT ROOF" || matName === "UNKNOWN"
        ? "UNASSIGNED MATERIAL"
        : matName.replace(/_/g, " ");

    return (
      <div className="h-full flex flex-col bg-[#0a121e] text-gray-200 overflow-y-auto">
        {/* Header */}
        <div className="p-2.5 border-b border-[#162840] bg-[#0c1626] flex items-center justify-between flex-shrink-0">
          <div className="flex items-center space-x-2 truncate min-w-0">
            <div className="p-1 rounded bg-amber-950 text-amber-400 border border-amber-800 flex-shrink-0">
              <Building2 size={15} />
            </div>
            <div className="truncate min-w-0">
              <div className="text-xs font-black text-white tracking-wide truncate">
                {rf?.name || "Roof Assembly"}
              </div>
              <div className="text-[10px] font-mono text-amber-300">
                {rf?.storey_name || storeyName || "Roof Level"} • {roofType}
                {filteredWalls.length > 0 && currentIndex >= 0 ? ` (${currentIndex + 1}/${filteredWalls.length})` : ""}
              </div>
            </div>
          </div>
          <div className="flex items-center space-x-1 flex-shrink-0">
            <button
              onClick={handlePrev}
              disabled={!hasPrev}
              className="p-1 rounded text-gray-400 hover:text-white hover:bg-gray-800/60 disabled:opacity-30 cursor-pointer"
              title="Previous Roof Element"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              onClick={handleNext}
              disabled={!hasNext}
              className="p-1 rounded text-gray-400 hover:text-white hover:bg-gray-800/60 disabled:opacity-30 cursor-pointer"
              title="Next Roof Element"
            >
              <ChevronRight size={14} />
            </button>
            <button
              onClick={handleCopyGuid}
              className="p-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 text-[10px] font-mono flex items-center gap-1 border border-gray-700 cursor-pointer ml-1"
              title="Copy IFC GUID"
            >
              {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
              <span>GUID</span>
            </button>
          </div>
        </div>

        {/* Primary Quantity Hero Card */}
        <div className="p-3 border-b border-[#162840] bg-[#070e1a]/80 space-y-3 flex-shrink-0">
          <div className="bg-[#0b1320] border border-amber-800/50 rounded p-3 shadow-inner">
            <div className="text-[10px] font-mono font-bold uppercase text-amber-400 tracking-wider">
              SELECTED PLANE SURFACE AREA (SF)
            </div>
            <div className="flex items-baseline justify-between mt-1">
              <div className="text-2xl font-black font-mono text-white tracking-tight">
                {trueSqft.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}{" "}
                <span className="text-xs text-amber-300 font-normal">SF</span>
              </div>
              <span
                className={`text-[9px] px-2 py-0.5 rounded font-mono font-bold border ${
                  isEligible
                    ? "bg-emerald-950 text-emerald-400 border-emerald-700"
                    : isReview
                    ? "bg-amber-950 text-amber-400 border-amber-700"
                    : "bg-rose-950 text-rose-400 border-rose-700"
                }`}
              >
                {isEligible ? "✓ ELIGIBLE" : isReview ? "⚠ REVIEW REQUIRED" : "— INELIGIBLE"}
              </span>
            </div>
          </div>

          {/* Grid of Key Technical Attributes */}
          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div className="bg-[#0b1320] border border-[#162840] rounded p-2">
              <div className="text-[9px] text-gray-400 uppercase font-bold">ROOF TYPE</div>
              <div className="text-sm font-bold text-white mt-0.5">{roofType}</div>
            </div>
            <div className="bg-[#0b1320] border border-[#162840] rounded p-2">
              <div className="text-[9px] text-gray-400 uppercase font-bold">PRIMARY MATERIAL</div>
              <div className="text-xs font-bold text-amber-300 mt-0.5 truncate" title={displayMat}>
                {displayMat}
              </div>
            </div>
            <div className="bg-[#0b1320] border border-[#162840] rounded p-2">
              <div className="text-[9px] text-gray-400 uppercase font-bold">SLOPE ANGLE</div>
              <div className="text-sm font-bold text-emerald-400 mt-0.5">
                {slopeDeg !== null ? `${slopeDeg.toFixed(1)}°` : "UNKNOWN / N/A"}
              </div>
            </div>
            <div className="bg-[#0b1320] border border-[#162840] rounded p-2">
              <div className="text-[9px] text-gray-400 uppercase font-bold">PITCH RATIO</div>
              <div className="text-sm font-bold text-cyan-400 mt-0.5">{pitchStr}</div>
            </div>
            <div className="bg-[#0b1320] border border-[#162840] rounded p-2">
              <div className="text-[9px] text-gray-400 uppercase font-bold">PLAN FOOTPRINT</div>
              <div className="text-sm font-bold text-gray-200 mt-0.5">
                {planSqft.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} SF
              </div>
            </div>
            <div className="bg-[#0b1320] border border-[#162840] rounded p-2">
              <div className="text-[9px] text-gray-400 uppercase font-bold">SOURCE ENTITY</div>
              <div className="text-xs font-bold text-purple-300 mt-0.5">{sourceType}</div>
            </div>
          </div>
        </div>

        {/* Review Warnings if any */}
        {reasons.length > 0 && (
          <div className="p-3 border-b border-amber-800/40 bg-amber-950/20 space-y-1 flex-shrink-0">
            <div className="text-[10px] uppercase font-bold text-amber-400 flex items-center gap-1">
              <AlertTriangle size={12} />
              <span>REVIEW REASONS</span>
            </div>
            <ul className="text-xs font-mono text-amber-200 list-disc list-inside space-y-0.5">
              {reasons.map((r: string, i: number) => (
                <li key={i}>{r.replace(/_/g, " ")}</li>
              ))}
            </ul>
          </div>
        )}

        {/* IFC PROPERTY SETS VIEWER (ACTUAL IFC EVIDENCE ONLY) */}
        {(() => {
          const psets = rf?.source_psets || {};
          const psetEntries = Object.entries(psets);
          if (psetEntries.length === 0) return null;

          return (
            <div className="p-3 border-b border-[#162840] space-y-1.5 text-xs font-mono flex-shrink-0">
              <div className="text-[10px] uppercase font-bold text-gray-400 tracking-wider">
                IFC PROPERTY SETS ({psetEntries.length})
              </div>
              <div className="bg-[#0b1320] border border-[#162840] rounded p-2.5 max-h-48 overflow-y-auto space-y-2">
                {psetEntries.map(([psetName, psetVal]) => (
                  <div key={psetName} className="space-y-1">
                    <div className="text-[10px] font-bold text-amber-300 border-b border-gray-800 pb-0.5">
                      {psetName}
                    </div>
                    {typeof psetVal === "object" && psetVal !== null ? (
                      Object.entries(psetVal as Record<string, any>).map(([k, v]) => (
                        <div key={k} className="flex justify-between text-[10px] pl-1">
                          <span className="text-gray-400">{k}:</span>
                          <span className="text-gray-200 truncate max-w-[140px]">{String(v)}</span>
                        </div>
                      ))
                    ) : (
                      <div className="text-[10px] text-gray-300 pl-1">{String(psetVal)}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          );
        })()}

        {/* Provenance Card */}
        <div className="p-3 border-b border-[#162840] space-y-2 text-xs font-mono flex-shrink-0">
          <div className="text-[10px] uppercase font-bold text-gray-400 tracking-wider">
            DATA PROVENANCE
          </div>
          <div className="space-y-1.5 bg-[#0b1320] border border-[#162840] rounded p-2.5">
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Surface Area:</span>
              <ProvenanceBadge status={rf?.area_provenance || "DERIVED_GEOMETRIC"} compact />
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Slope / Pitch:</span>
              <ProvenanceBadge status={rf?.slope_provenance || "UNKNOWN_UNRESOLVED"} compact />
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Material:</span>
              <ProvenanceBadge status={rf?.material_provenance || "UNKNOWN_UNRESOLVED"} compact />
            </div>
            <div className="pt-1.5 border-t border-gray-800 flex justify-between items-center text-[10px]">
              <span className="text-gray-500">IFC GUID:</span>
              <span className="text-cyan-400 font-bold">{selectedGuid}</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // =========================================================================
  // FLOORING INSPECTOR VIEW (ESTIMATOR-FIRST COMMERCIAL QUALITY)
  // =========================================================================
  if (activeFlooring || trade === "flooring") {
    const f = activeFlooring || wall;
    const gross = Number(f.gross_area_sqft || 0);
    const voidDed = Number(f.void_deductions_sqft || 0);
    const net = Number(f.net_area_sqft || Math.max(0, gross - voidDed));
    const perim = Number(f.perimeter_ft || 0);
    const elig = f.qto_eligibility || "ELIGIBLE";
    const prov = f.provenance_status || "DERIVED_GEOMETRIC";
    const reasons = f.eligibility_reasons || [];
    const psets = f.source_psets || {};

    const isExcluded = elig.startsWith("INELIGIBLE") || elig === "BLOCKED";
    const isSuperseded = elig === "SUPERSEDED_BY_PHYSICAL_ELEMENT";
    const isEligible = elig === "ELIGIBLE";

    // Clean display title
    let displayTitle = f.finish_material_name || f.source_name || "Flooring Element";
    if (displayTitle.includes(":")) {
      const parts = displayTitle.split(":");
      displayTitle = parts[parts.length - 1].replace(/^nbl_/, "").replace(/_/g, " ");
    } else {
      displayTitle = displayTitle.replace(/^nbl_/, "").replace(/_/g, " ");
    }

    const materialCategory = (f.flooring_category || "UNASSIGNED_FINISH").replace(/_/g, " ");
    const finishMaterial = f.finish_material_name || materialCategory;

    return (
      <div className="h-full flex flex-col bg-[#0a121e] text-gray-200 overflow-hidden font-sans">
        {/* 1. Header & Navigation */}
        <div className="p-2.5 border-b border-[#162840] bg-[#080e18] flex items-center justify-between flex-shrink-0">
          <div className="flex items-center space-x-2">
            <Info size={14} className="text-cyan-400" />
            <span className="text-xs font-bold uppercase tracking-wider text-white">
              Flooring Inspector
            </span>
            {filteredWalls.length > 0 && currentIndex >= 0 && (
              <span className="text-[10px] font-mono text-gray-400 border-l border-gray-700 pl-2">
                {currentIndex + 1} / {filteredWalls.length}
              </span>
            )}
          </div>
          <div className="flex items-center space-x-1">
            <button
              onClick={handlePrev}
              disabled={!hasPrev}
              className="p-1 rounded text-gray-400 hover:text-white hover:bg-gray-800/60 disabled:opacity-30 cursor-pointer"
            >
              <ChevronLeft size={14} />
            </button>
            <button
              onClick={handleNext}
              disabled={!hasNext}
              className="p-1 rounded text-gray-400 hover:text-white hover:bg-gray-800/60 disabled:opacity-30 cursor-pointer"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>

        {/* 2. Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-3 space-y-3 font-mono text-xs">
          {/* Main Element Header Card */}
          <div className="p-3.5 rounded-lg bg-[#060b14] border border-[#162840] space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[9px] font-extrabold text-cyan-400 uppercase tracking-wider font-sans">
                FLOORING ELEMENT
              </span>
              <span className="text-[10px] font-bold text-amber-300 uppercase px-1.5 py-0.5 rounded bg-[#0a121e] border border-amber-800/50">
                {f.storey_name || storeyName || "LEVEL 01"}
              </span>
            </div>
            <div className="text-sm font-black text-white font-sans truncate leading-snug">
              {displayTitle}
            </div>
          </div>

          {/* Alert State Card: Excluded Elements */}
          {isExcluded && (
            <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-800/80 text-rose-300 space-y-1.5">
              <div className="flex items-center gap-1.5 font-bold text-xs text-rose-400 font-sans uppercase tracking-wider">
                <AlertTriangle size={14} />
                <span>EXCLUDED FROM TAKEOFF</span>
              </div>
              <div className="text-[11px] text-gray-300 font-sans leading-relaxed">
                <span className="font-semibold text-rose-300">Reason: </span>
                {reasons.length > 0
                  ? reasons.join(". ")
                  : "Roof / structural element is outside interior flooring scope."}
              </div>
            </div>
          )}

          {/* Alert State Card: Superseded Elements */}
          {isSuperseded && (
            <div className="p-3 rounded-lg bg-purple-950/40 border border-purple-800/80 text-purple-200 space-y-1.5">
              <div className="flex items-center gap-1.5 font-bold text-xs text-purple-300 font-sans uppercase tracking-wider">
                <AlertCircle size={14} />
                <span>SUPERSEDED BY PHYSICAL FLOORING</span>
              </div>
              <div className="text-[11px] text-gray-300 font-sans">
                <span className="font-semibold text-purple-300">Source: </span>
                Physical Flooring GUID{" "}
                <span className="font-mono font-bold text-white">
                  {f.superseded_by_guid || "VERIFIED EXPLICIT"}
                </span>
              </div>
              <p className="text-[10px] text-gray-400 italic font-sans leading-tight">
                Spatial quantity is preserved for architectural audit, but is not counted towards total flooring QTO.
              </p>
            </div>
          )}

          {/* Section 1: Finish & Material Information */}
          <div className="p-3 rounded-lg bg-[#060b14] border border-[#162840] space-y-2.5">
            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider font-sans">
              Finish Specification
            </div>
            <div className="space-y-2 text-[11px] divide-y divide-[#162840]/60">
              <div className="flex justify-between items-center">
                <span className="text-gray-400">Finish:</span>
                <span className="text-amber-300 font-bold">{materialCategory}</span>
              </div>
              <div className="flex justify-between items-center pt-2">
                <span className="text-gray-400">Material:</span>
                <span className="text-white font-bold">{finishMaterial}</span>
              </div>
              {f.thickness_in != null && (
                <div className="flex justify-between items-center pt-2">
                  <span className="text-gray-400">Thickness:</span>
                  <span className="text-gray-200 font-bold">{f.thickness_in.toFixed(3)}"</span>
                </div>
              )}
            </div>
          </div>

          {/* Section 2: Quantities / Net Floor Area */}
          <div className="p-3 rounded-lg bg-[#060b14] border border-[#162840] space-y-2.5">
            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider font-sans">
              Surface Takeoff Quantities
            </div>

            {/* Hero Net Area Card */}
            <div className={`p-3 rounded-md border flex items-center justify-between ${
              isEligible
                ? "bg-cyan-950/40 border-cyan-700/70"
                : "bg-gray-900/60 border-gray-800"
            }`}>
              <div>
                <div className="text-[9px] font-bold uppercase text-cyan-400 tracking-wider font-sans">
                  {isExcluded ? "NET TAKEOFF CONTRIBUTION" : "NET FLOOR AREA"}
                </div>
                <div className={`text-lg font-black font-mono leading-tight ${
                  isEligible ? "text-cyan-300" : "text-gray-400"
                }`}>
                  {isEligible ? `${net.toFixed(2)} SF` : "0.00 SF"}
                  {isExcluded && <span className="text-[10px] text-rose-400 font-sans ml-1.5 font-bold tracking-normal">(EXCLUDED)</span>}
                </div>
              </div>
              <span
                className={`text-[9px] font-bold px-2 py-0.5 rounded font-mono ${
                  isEligible
                    ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                    : isSuperseded
                    ? "bg-purple-950 text-purple-400 border border-purple-800"
                    : "bg-rose-950 text-rose-400 border border-rose-800"
                }`}
              >
                {isEligible ? "✓ INCLUDED" : isSuperseded ? "↗ SUPERSEDED" : "— EXCLUDED"}
              </span>
            </div>

            {/* Explicit Arithmetic Scope Reconciliation Card for Excluded Slabs */}
            {isExcluded && (
              <div className="p-2.5 rounded-md bg-amber-950/20 border border-amber-800/50 text-[10px] space-y-1.5 font-sans">
                <div className="font-bold text-amber-400 flex items-center gap-1.5">
                  <AlertTriangle size={12} />
                  <span>Scope Reconciliation Breakdown</span>
                </div>
                <div className="space-y-1 text-gray-300 font-mono">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Physical Slab Gross:</span>
                    <span>+{gross.toFixed(2)} SF</span>
                  </div>
                  <div className="flex justify-between text-rose-400">
                    <span>Non-Finish Scope Deduction:</span>
                    <span>-{gross.toFixed(2)} SF</span>
                  </div>
                  <div className="flex justify-between pt-1 border-t border-amber-800/40 font-bold text-amber-300">
                    <span>Net Finish Takeoff:</span>
                    <span>0.00 SF</span>
                  </div>
                </div>
                <div className="text-[9.5px] text-gray-400 font-sans italic pt-0.5 leading-snug">
                  * Excluded from active interior finish takeoff per trade classification (structural deck / roof slab).
                  Project grand total only aggregates active, interior finish-eligible zones.
                </div>
              </div>
            )}

            <div className="space-y-1.5 text-[11px] divide-y divide-[#162840]/60 pt-1">
              <div className="flex justify-between items-center">
                <span className="text-gray-400">Physical Slab Area:</span>
                <span className="text-gray-200 font-mono">{gross.toFixed(2)} SF</span>
              </div>
              <div className="flex justify-between items-center pt-1.5">
                <span className="text-gray-400">Void Deductions:</span>
                <span className="text-rose-400 font-mono">
                  {voidDed > 0 ? `-${voidDed.toFixed(2)} SF` : "0.00 SF"}
                </span>
              </div>
              {isExcluded && (
                <div className="flex justify-between items-center pt-1.5">
                  <span className="text-gray-400">Trade Scope Status:</span>
                  <span className="text-rose-400 font-bold font-mono">100% Deducted (Non-Finish)</span>
                </div>
              )}
              {perim > 0 && (
                <div className="flex justify-between items-center pt-1.5">
                  <span className="text-gray-400">Perimeter:</span>
                  <span className="text-gray-200 font-mono">{perim.toFixed(2)} LF</span>
                </div>
              )}
            </div>
          </div>

          {/* Section 3: Collapsible Source & Audit Provenance */}
          <div className="border border-[#162840] rounded-lg overflow-hidden bg-[#060b14]">
            <button
              onClick={() => toggleSection("provenance")}
              className="w-full p-2.5 bg-[#0a121e] flex items-center justify-between text-left font-bold text-gray-300 hover:bg-[#0e1726] transition-colors"
            >
              <span className="flex items-center gap-1.5 text-[11px]">
                <ShieldCheck size={13} className="text-cyan-400" />
                <span>Source & Provenance Audit</span>
              </span>
              {sections.provenance ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>
            {sections.provenance && (
              <div className="p-3 space-y-2 text-[11px] divide-y divide-[#162840]/60">
                <div className="flex justify-between items-center">
                  <span className="text-gray-400">Source Entity:</span>
                  <span className="text-cyan-300 font-bold">{f.source_entity_type || "IfcSlab"}</span>
                </div>
                <div className="flex justify-between items-center pt-1.5">
                  <span className="text-gray-400">Evidence Type:</span>
                  <span className="text-sky-300">{f.evidence_type || "PHYSICAL_SLAB"}</span>
                </div>
                <div className="flex justify-between items-center pt-1.5">
                  <span className="text-gray-400">Provenance:</span>
                  <ProvenanceBadge status={prov} compact />
                </div>
                <div className="pt-1.5 space-y-1">
                  <div className="flex items-center justify-between text-[10px] text-gray-400">
                    <span>IFC GUID:</span>
                    <button
                      onClick={handleCopyGuid}
                      className="flex items-center gap-1 text-cyan-400 hover:text-cyan-300 cursor-pointer"
                    >
                      {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
                      <span>{copied ? "Copied" : "Copy"}</span>
                    </button>
                  </div>
                  <div className="p-1.5 rounded bg-[#0a121e] border border-[#162840] text-gray-300 text-[10px] truncate font-mono select-all">
                    {selectedGuid}
                  </div>
                </div>
                {f.source_name && (
                  <div className="pt-1.5 space-y-1">
                    <span className="text-[10px] text-gray-400">Raw Source Name:</span>
                    <div className="p-1.5 rounded bg-[#0a121e] border border-[#162840] text-gray-400 text-[10px] truncate font-mono">
                      {f.source_name}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Section 4: Property Sets */}
          {Object.keys(psets).length > 0 && (
            <div className="border border-[#162840] rounded-lg overflow-hidden bg-[#060b14]">
              <button
                onClick={() => toggleSection("psets")}
                className="w-full p-2.5 bg-[#0a121e] flex items-center justify-between text-left font-bold text-gray-300 hover:bg-[#0e1726] transition-colors"
              >
                <span className="flex items-center gap-1.5 text-[11px]">
                  <Box size={13} className="text-purple-400" />
                  <span>IFC Property Sets ({Object.keys(psets).length})</span>
                </span>
                {sections.psets ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              </button>
              {sections.psets && (
                <div className="p-2.5 space-y-2 text-[10px]">
                  {Object.entries(psets).map(([psetName, props]: [string, any]) => (
                    <div key={psetName} className="p-2 rounded bg-[#0a121e] border border-[#162840] space-y-1">
                      <div className="font-bold text-cyan-400 truncate">{psetName}</div>
                      <div className="space-y-0.5 text-gray-300">
                        {typeof props === "object" && props !== null ? (
                          Object.entries(props).map(([k, v]: [string, any]) => (
                            <div key={k} className="flex justify-between">
                              <span className="text-gray-500">{k}:</span>
                              <span className="text-gray-200 font-bold truncate max-w-[140px]" title={String(v)}>
                                {String(v)}
                              </span>
                            </div>
                          ))
                        ) : (
                          <span>{String(props)}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  const wallMeta = formatWallDisplay(wall);

  // Derive Geometry Numbers directly from backend canonical & line item single source of truth
  const lengthFt = Number(lineItem?.provenance?.length_ft ?? wall.length_ft ?? 0);
  const heightFt = Number(
    lineItem?.provenance?.finish_height_ft ??
      wall.drywall_finish_height_ft ??
      wall.physical_height_ft ??
      10
  );
  const thicknessIn = Number(wall.nominal_thickness_in ?? 0);
  const grossFaceArea = lengthFt * heightFt;

  const sideALayers = wall.drywall_side_a_scope ? (wall.assembly?.side_a_layers ?? 1) : 0;
  const sideBLayers = wall.drywall_side_b_scope ? (wall.assembly?.side_b_layers ?? 1) : 0;
  const totalActiveLayers = sideALayers + sideBLayers;
  const grossBoardArea = grossFaceArea * totalActiveLayers;

  // Openings Breakdown
  const openings = wall.openings || [];
  const validOpenings = openings.filter((op: any) => (op.area_sqft || 0) > 0);
  const totalSingleOpeningDeduction = Number(
    lineItem?.provenance?.openings_deduction_sqft ??
      validOpenings.reduce((sum: number, op: any) => sum + (op.area_sqft || 0), 0)
  );
  const totalOpeningBoardDeduction = totalSingleOpeningDeduction * totalActiveLayers;
  const netBoardArea = Number(
    lineItem?.provenance?.net_drywall_sqft ??
      Math.max(0, grossBoardArea - totalOpeningBoardDeduction)
  );
  const estSheets4x8 = Math.ceil((netBoardArea * (1 + wasteFactor / 100)) / 32);
  const estStuds =
    lineItem?.provenance?.studs_count ??
    (lengthFt > 0
      ? Math.ceil(lengthFt / ((wall.assembly?.stud_spacing_in || 16) / 12)) + 1
      : 0);

  // Review Gating State
  const isReviewRequired =
    wall.qto_eligibility === "REVIEW_REQUIRED" ||
    wall.qto_eligibility === "BLOCKED" ||
    wall.qto_eligibility?.startsWith("INELIGIBLE") ||
    wallMeta.status === "UNKNOWN_UNRESOLVED";

  return (
    <div className="h-full flex flex-col bg-[#0a121e] text-gray-200 overflow-hidden font-sans">
      {/* ===================================================================== */}
      {/* 1. INSPECTOR HEADER & ELEMENT NAVIGATION                              */}
      {/* ===================================================================== */}
      <div className="p-2.5 border-b border-[#162840] bg-[#080e18] flex items-center justify-between flex-shrink-0">
        <div className="flex items-center space-x-2">
          <Info size={14} className="text-cyan-400" />
          <span className="text-xs font-bold uppercase tracking-wider text-white">
            Inspector
          </span>
          {filteredWalls.length > 0 && currentIndex >= 0 && (
            <span className="text-[10px] font-mono text-gray-400 border-l border-gray-700 pl-2">
              {currentIndex + 1} / {filteredWalls.length}
            </span>
          )}
        </div>

        {/* Navigation Arrows */}
        <div className="flex items-center space-x-1">
          <button
            onClick={handlePrev}
            disabled={!hasPrev}
            title="Previous element in filtered set"
            className="p-1 rounded text-gray-400 hover:text-white hover:bg-gray-800/60 disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer"
          >
            <ChevronLeft size={14} />
          </button>
          <button
            onClick={handleNext}
            disabled={!hasNext}
            title="Next element in filtered set"
            className="p-1 rounded text-gray-400 hover:text-white hover:bg-gray-800/60 disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      </div>

      {/* ===================================================================== */}
      {/* 2. REVIEW / GATING ALERT BANNER (IF APPLICABLE)                        */}
      {/* ===================================================================== */}
      {isReviewRequired && (
        <div className="bg-amber-950/50 border-b border-amber-800/80 p-2.5 flex items-start space-x-2 flex-shrink-0">
          <AlertTriangle size={15} className="text-amber-400 mt-0.5 flex-shrink-0" />
          <div className="space-y-0.5 font-mono text-[10px]">
            <div className="font-bold text-amber-300 uppercase tracking-wider">
              {wall.qto_eligibility || "REVIEW REQUIRED"}
            </div>
            <p className="text-amber-200/80 leading-tight">
              {wall.eligibility_reasons?.join("; ") ||
                "Drywall assembly or classification requires estimator verification. Backend provenance maintained without fabricated defaults."}
            </p>
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* 3. SCROLLABLE INSPECTION SECTIONS                                     */}
      {/* ===================================================================== */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 font-mono text-xs">
        {/* =================================================================== */}
        {/* SECTION A: IDENTITY                                                 */}
        {/* =================================================================== */}
        <div className="border border-[#162840] rounded bg-[#060b14]/60 overflow-hidden">
          <button
            onClick={() => toggleSection("identity")}
            className="w-full p-2 bg-[#0e1726] border-b border-[#162840] flex items-center justify-between font-bold text-gray-300 text-[11px] cursor-pointer hover:text-white"
          >
            <div className="flex items-center space-x-1.5">
              <Square size={12} className="text-cyan-400" />
              <span className="uppercase tracking-wider">Identity</span>
            </div>
            {sections.identity ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>

          {sections.identity && (
            <div className="p-2.5 space-y-2">
              {/* Primary Label Tile */}
              <div className="p-2 rounded bg-[#0a121e] border border-[#162840] space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-[9px] text-gray-400 uppercase tracking-wider font-semibold">
                    Canonical Classification
                  </span>
                  <span
                    className={`text-[8px] px-1 py-0.2 rounded font-bold ${
                      wallMeta.status === "UNKNOWN_UNRESOLVED"
                        ? "bg-amber-950 text-amber-400 border border-amber-800"
                        : "bg-emerald-950 text-emerald-400 border border-emerald-800"
                    }`}
                  >
                    {wallMeta.status === "UNKNOWN_UNRESOLVED" ? "UNKNOWN" : "CANONICAL"}
                  </span>
                </div>
                <div className="text-xs font-bold text-white tracking-wide">
                  {wallMeta.primaryLabel}
                </div>
              </div>

              {/* Source Audit Metadata */}
              <div className="space-y-1.5 text-[11px] pt-0.5">
                <div className="flex justify-between">
                  <span className="text-gray-400">IFC Class:</span>
                  <span className="text-gray-300 font-bold">{wall.ifc_class || "IfcWallStandardCase"}</span>
                </div>

                <div className="flex justify-between items-baseline gap-2">
                  <span className="text-gray-400 flex-shrink-0">Source Name:</span>
                  <span
                    className="text-gray-300 text-right truncate font-mono text-[10px]"
                    title={wall.name}
                  >
                    {wall.name || "NOT AVAILABLE FROM IFC"}
                  </span>
                </div>

                <div className="flex justify-between items-center gap-2">
                  <span className="text-gray-400 flex-shrink-0">IFC GUID:</span>
                  <div className="flex items-center space-x-1 min-w-0">
                    <span
                      className="text-cyan-300 font-bold font-mono text-[10px] truncate"
                      title={wall.ifc_guid}
                    >
                      {wall.ifc_guid}
                    </span>
                    <button
                      onClick={handleCopyGuid}
                      className="p-0.5 text-gray-500 hover:text-cyan-300 cursor-pointer"
                      title="Copy GUID"
                    >
                      {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
                    </button>
                  </div>
                </div>

                <div className="flex justify-between">
                  <span className="text-gray-400">Storey:</span>
                  <span className="text-gray-300">
                    {wall.storey_name || storeyName || "NOT AVAILABLE FROM IFC"}
                  </span>
                </div>

                <div className="flex justify-between">
                  <span className="text-gray-400">Object Type:</span>
                  <span className="text-gray-400 text-[10px] truncate max-w-[170px]" title={wall.object_type}>
                    {wall.object_type || "Standard Wall"}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* =================================================================== */}
        {/* SECTION B: ANALYTICAL GEOMETRY                                      */}
        {/* =================================================================== */}
        <div className="border border-[#162840] rounded bg-[#060b14]/60 overflow-hidden">
          <button
            onClick={() => toggleSection("geometry")}
            className="w-full p-2 bg-[#0e1726] border-b border-[#162840] flex items-center justify-between font-bold text-gray-300 text-[11px] cursor-pointer hover:text-white"
          >
            <div className="flex items-center space-x-1.5">
              <Ruler size={12} className="text-sky-400" />
              <span className="uppercase tracking-wider">Analytical Geometry</span>
            </div>
            {sections.geometry ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>

          {sections.geometry && (
            <div className="p-2.5 space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-[10px] text-gray-400 uppercase font-semibold">
                  Geometry Dimensions
                </span>
                <ProvenanceBadge status={wall.length_provenance || "DERIVED_GEOMETRIC"} compact />
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div className="bg-[#0a121e] p-2 rounded border border-[#162840] text-center">
                  <span className="text-[8px] text-gray-400 uppercase block font-semibold">Length</span>
                  <span className="text-xs font-bold text-white">{lengthFt.toFixed(3)} ft</span>
                </div>
                <div className="bg-[#0a121e] p-2 rounded border border-[#162840] text-center">
                  <span className="text-[8px] text-gray-400 uppercase block font-semibold">Finish Ht</span>
                  <span className="text-xs font-bold text-white">{heightFt.toFixed(2)} ft</span>
                </div>
                <div className="bg-[#0a121e] p-2 rounded border border-[#162840] text-center">
                  <span className="text-[8px] text-gray-400 uppercase block font-semibold">Thickness</span>
                  <span className="text-xs font-bold text-white">{thicknessIn.toFixed(2)} in</span>
                </div>
              </div>

              {/* Spatial Coordinates */}
              <div className="space-y-1 text-[10px] pt-1 text-gray-400">
                <div className="flex justify-between">
                  <span>Start Point:</span>
                  <span className="text-gray-300 font-mono">
                    ({wall.start_point?.map((v: number) => v.toFixed(2)).join(", ") ?? "0.0, 0.0, 0.0"})
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>End Point:</span>
                  <span className="text-gray-300 font-mono">
                    ({wall.end_point?.map((v: number) => v.toFixed(2)).join(", ") ?? "0.0, 0.0, 0.0"})
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Bottom Elevation:</span>
                  <span className="text-gray-300 font-mono">
                    {Number(wall.start_point?.[2] ?? wall.elevation_ft ?? 0).toFixed(2)} ft
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Top Elevation:</span>
                  <span className="text-gray-300 font-mono">
                    {(Number(wall.start_point?.[2] ?? wall.elevation_ft ?? 0) + heightFt).toFixed(2)} ft
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* =================================================================== */}
        {/* SECTION C: WALL ASSEMBLY & FRAMING                                 */}
        {/* =================================================================== */}
        <div className="border border-[#162840] rounded bg-[#060b14]/60 overflow-hidden">
          <button
            onClick={() => toggleSection("assembly")}
            className="w-full p-2 bg-[#0e1726] border-b border-[#162840] flex items-center justify-between font-bold text-gray-300 text-[11px] cursor-pointer hover:text-white"
          >
            <div className="flex items-center space-x-1.5">
              <Hammer size={12} className="text-amber-400" />
              <span className="uppercase tracking-wider">Wall Assembly & Framing</span>
            </div>
            {sections.assembly ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>

          {sections.assembly && (
            <div className="p-2.5 space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-[10px] text-gray-400 uppercase font-semibold">Assembly Definition</span>
                <ProvenanceBadge
                  status={wall.assembly?.assembly_provenance || "CONFIGURED_ASSUMPTION"}
                  compact
                />
              </div>

              <div className="space-y-1.5 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-gray-400">Board Type:</span>
                  <span className="text-amber-300 font-bold">
                    {wall.assembly?.board_type || '5/8" Type X Gypsum'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Board Thickness:</span>
                  <span className="text-gray-300">
                    {wall.assembly?.board_thickness_in ? `${wall.assembly.board_thickness_in}"` : '5/8" (0.625")'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Stud Framing:</span>
                  <span className="text-gray-300 font-bold">
                    {wall.assembly?.stud_size || '3-5/8"'} Light Gauge Steel
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Stud Spacing:</span>
                  <span className="text-gray-300">
                    {wall.assembly?.stud_spacing_in || 16}" O.C.
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Layers (Side A / B):</span>
                  <span className="text-gray-300">
                    Side A: {wall.assembly?.side_a_layers ?? 1}L · Side B: {wall.assembly?.side_b_layers ?? 1}L
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* =================================================================== */}
        {/* SECTION D: HOSTED OPENINGS & VOIDS                                 */}
        {/* =================================================================== */}
        <div className="border border-[#162840] rounded bg-[#060b14]/60 overflow-hidden">
          <button
            onClick={() => toggleSection("openings")}
            className="w-full p-2 bg-[#0e1726] border-b border-[#162840] flex items-center justify-between font-bold text-gray-300 text-[11px] cursor-pointer hover:text-white"
          >
            <div className="flex items-center space-x-1.5">
              <DoorOpen size={12} className="text-emerald-400" />
              <span className="uppercase tracking-wider">
                Hosted Openings ({validOpenings.length})
              </span>
            </div>
            {sections.openings ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>

          {sections.openings && (
            <div className="p-2.5 space-y-2">
              {validOpenings.length > 0 ? (
                <div className="space-y-1.5">
                  {validOpenings.map((op: any, idx: number) => {
                    const opSingleArea = Number(op.area_sqft || 0);
                    const opSideADed = wall.drywall_side_a_scope ? opSingleArea * sideALayers : 0;
                    const opSideBDed = wall.drywall_side_b_scope ? opSingleArea * sideBLayers : 0;
                    const opTotalDed = opSideADed + opSideBDed;

                    return (
                      <div
                        key={op.ifc_guid || idx}
                        className="p-2 rounded bg-[#0a121e] border border-[#162840] text-[10px] space-y-1"
                      >
                        <div className="flex justify-between items-center font-bold">
                          <span className="text-cyan-300">
                            {op.opening_type || "OPENING"}: {op.name || "Hosted Opening"}
                          </span>
                          <span className="text-rose-400">-{opTotalDed.toFixed(1)} SF</span>
                        </div>
                        <div className="text-gray-400 flex justify-between">
                          <span>Dimensions:</span>
                          <span className="font-mono">
                            {Number(op.width_ft || 0).toFixed(2)}' W × {Number(op.height_ft || 0).toFixed(2)}' H
                          </span>
                        </div>
                        <div className="text-gray-400 flex justify-between">
                          <span>Deductions:</span>
                          <span className="font-mono text-gray-300">
                            A: -{opSideADed.toFixed(1)} SF · B: -{opSideBDed.toFixed(1)} SF
                          </span>
                        </div>
                        <div className="text-gray-400 flex justify-between">
                          <span>Placement:</span>
                          {op.position_along_wall_ft != null ? (
                            <span className="font-mono text-emerald-400">
                              {Number(op.position_along_wall_ft).toFixed(2)}' (Sill: {Number(op.sill_height_ft || 0).toFixed(2)}')
                            </span>
                          ) : (
                            <span className="font-mono text-amber-400 font-semibold">
                              UNRESOLVED / REVIEW / BLOCKED
                            </span>
                          )}
                        </div>
                        <div className="text-gray-500 flex justify-between text-[9px] pt-0.5 border-t border-gray-800/60">
                          <span>GUID:</span>
                          <span className="font-mono truncate max-w-[140px]">{op.ifc_guid || op.id || "N/A"}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-[10px] text-gray-500 italic py-1">
                  No hosted openings or architectural voids in this element.
                </p>
              )}
            </div>
          )}
        </div>

        {/* =================================================================== */}
        {/* SECTION E: DRYWALL SCOPE & ELIGIBILITY                             */}
        {/* =================================================================== */}
        <div className="border border-[#162840] rounded bg-[#060b14]/60 overflow-hidden">
          <button
            onClick={() => toggleSection("scope")}
            className="w-full p-2 bg-[#0e1726] border-b border-[#162840] flex items-center justify-between font-bold text-gray-300 text-[11px] cursor-pointer hover:text-white"
          >
            <div className="flex items-center space-x-1.5">
              <Layers size={12} className="text-emerald-400" />
              <span className="uppercase tracking-wider">Drywall Scope</span>
            </div>
            {sections.scope ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>

          {sections.scope && (
            <div className="p-2.5 space-y-2">
              <div className="space-y-1 text-[11px]">
                <div className="flex justify-between items-center">
                  <span className="text-gray-400">Side A (Interior):</span>
                  <span
                    className={`font-bold ${
                      wall.drywall_side_a_scope ? "text-emerald-400" : "text-gray-500"
                    }`}
                  >
                    {wall.drywall_side_a_scope ? `IN SCOPE (${sideALayers} Layer)` : "EXCLUDED"}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-gray-400">Side B (Opposite):</span>
                  <span
                    className={`font-bold ${
                      wall.drywall_side_b_scope ? "text-emerald-400" : "text-gray-500"
                    }`}
                  >
                    {wall.drywall_side_b_scope ? `IN SCOPE (${sideBLayers} Layer)` : "EXCLUDED"}
                  </span>
                </div>
                <div className="flex justify-between items-center border-t border-gray-800 pt-1">
                  <span className="text-gray-400 font-semibold">Total Active Faces:</span>
                  <span className="text-cyan-300 font-extrabold">{totalActiveLayers} Layer(s)</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-gray-400">Eligibility Status:</span>
                  <span
                    className={`px-1.5 py-0.2 rounded text-[9px] font-bold ${
                      wall.qto_eligibility === "ELIGIBLE"
                        ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                        : "bg-amber-950 text-amber-400 border border-amber-800"
                    }`}
                  >
                    {wall.qto_eligibility || "ELIGIBLE"}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* =================================================================== */}
        {/* SECTION F: QTO DERIVATION & ARITHMETIC                              */}
        {/* =================================================================== */}
        <div className="border border-[#162840] rounded bg-[#060b14]/60 overflow-hidden">
          <button
            onClick={() => toggleSection("qto")}
            className="w-full p-2 bg-[#0e1726] border-b border-[#162840] flex items-center justify-between font-bold text-gray-300 text-[11px] cursor-pointer hover:text-white"
          >
            <div className="flex items-center space-x-1.5">
              <FileSpreadsheet size={12} className="text-cyan-400" />
              <span className="uppercase tracking-wider">QTO Derivation</span>
            </div>
            {sections.qto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>

          {sections.qto && (
            <div className="p-2.5 space-y-2">
              <div className="p-2.5 rounded bg-[#0a121e] border border-cyan-800/40 space-y-1.5 text-[11px]">
                {/* Gross Wall Face */}
                <div className="flex justify-between items-baseline">
                  <span className="text-gray-400">Gross Wall Face:</span>
                  <span className="text-gray-200">
                    {lengthFt.toFixed(2)}' × {heightFt.toFixed(2)}' ={" "}
                    <strong className="text-white">{grossFaceArea.toFixed(1)} SF</strong>
                  </span>
                </div>

                {/* Gross Board Area */}
                <div className="flex justify-between items-baseline">
                  <span className="text-gray-400">Gross Board Area:</span>
                  <span className="text-white font-semibold">
                    {grossFaceArea.toFixed(1)} SF × {totalActiveLayers}L ={" "}
                    <strong className="text-cyan-200">{grossBoardArea.toFixed(1)} SF</strong>
                  </span>
                </div>

                {/* Opening Deductions */}
                <div className="flex justify-between items-baseline text-rose-400">
                  <span>Opening Deduction:</span>
                  <span>
                    -{totalOpeningBoardDeduction.toFixed(1)} SF{" "}
                    {totalActiveLayers > 1 && totalSingleOpeningDeduction > 0
                      ? `(${totalSingleOpeningDeduction.toFixed(1)} × ${totalActiveLayers}L)`
                      : ""}
                  </span>
                </div>

                {/* Net Board Area */}
                <div className="border-t border-gray-800 pt-1.5 flex justify-between font-bold text-cyan-300">
                  <span>Net Board Area Eq:</span>
                  <span className="text-sm font-extrabold text-cyan-300">
                    {netBoardArea.toFixed(1)} SF
                  </span>
                </div>

                {/* 4x8 Sheets */}
                <div className="flex justify-between items-center text-amber-300 font-semibold text-[10px] bg-amber-950/30 p-1.5 rounded border border-amber-900/40">
                  <span>Est. 4×8 Sheets ({wasteFactor}% waste):</span>
                  <span className="font-bold text-xs">{estSheets4x8} Sheets</span>
                </div>

                {/* Estimated Studs */}
                <div className="flex justify-between items-center text-emerald-300 font-semibold text-[10px] bg-emerald-950/30 p-1.5 rounded border border-emerald-900/40">
                  <span>Est. Steel Studs (16" o.c.):</span>
                  <span className="font-bold text-xs">{estStuds} Studs</span>
                </div>

                {/* Provenance Formula */}
                {lineItem?.provenance?.formula && (
                  <div className="text-[9px] text-gray-400 font-mono pt-1 border-t border-gray-800/60 leading-relaxed break-words">
                    <span className="text-gray-500 block font-bold uppercase tracking-wider text-[8px] mb-0.5">
                      Backend Audit Formula:
                    </span>
                    {lineItem.provenance.formula}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* =================================================================== */}
        {/* SECTION G: AUDIT PROVENANCE SUMMARY                                 */}
        {/* =================================================================== */}
        <div className="border border-[#162840] rounded bg-[#060b14]/60 overflow-hidden">
          <button
            onClick={() => toggleSection("provenance")}
            className="w-full p-2 bg-[#0e1726] border-b border-[#162840] flex items-center justify-between font-bold text-gray-300 text-[11px] cursor-pointer hover:text-white"
          >
            <div className="flex items-center space-x-1.5">
              <ShieldCheck size={12} className="text-emerald-400" />
              <span className="uppercase tracking-wider">Provenance Summary</span>
            </div>
            {sections.provenance ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>

          {sections.provenance && (
            <div className="p-2.5 space-y-1.5 text-[10px]">
              <div className="flex justify-between items-center">
                <span className="text-gray-400">Length & Alignment:</span>
                <ProvenanceBadge status={wall.length_provenance || "DERIVED_GEOMETRIC"} compact />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-400">Finish Height:</span>
                <ProvenanceBadge status={wall.height_provenance || "CONFIGURED_ASSUMPTION"} compact />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-400">Assembly / Layers:</span>
                <ProvenanceBadge status={wall.assembly?.assembly_provenance || "CONFIGURED_ASSUMPTION"} compact />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-400">Openings Deductions:</span>
                <ProvenanceBadge status={validOpenings.length > 0 ? "VERIFIED_EXPLICIT" : "DERIVED_GEOMETRIC"} compact />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
