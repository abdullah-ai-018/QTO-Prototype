import React, { useState, useMemo, useCallback } from "react";
import {
  Building2,
  Layers,
  Box,
  Square,
  Search,
  ChevronDown,
  ChevronRight,
  Eye,
  EyeOff,
  Crosshair,
  Filter,
  RotateCcw,
  Maximize2,
  Minimize2,
  FolderTree,
} from "lucide-react";
import { CATEGORY_COLORS } from "./BIM3DCanvasViewer";
import { FLOORING_PALETTE } from "./BIM2DFlooringPlan";

export interface WallDisplayLabel {
  primaryLabel: string;
  secondaryLabel: string;
  categoryGroup:
    | "Interior Partition"
    | "Exterior Wall"
    | "Foundation / Perimeter"
    | "Structural Concrete"
    | "Curtain Wall"
    | "Other / Review Required";
  status: "CONFIRMED" | "UNKNOWN_UNRESOLVED";
}

export function formatWallDisplay(wall?: {
  name?: string;
  wall_classification?: string;
  ifc_guid?: string;
}): WallDisplayLabel {
  const rawName = wall?.name || "Wall";
  const rawClass = wall?.wall_classification;

  if (!rawClass || rawClass === "UNKNOWN" || rawClass === "UNKNOWN_UNRESOLVED") {
    return {
      primaryLabel: rawName,
      secondaryLabel: rawName,
      categoryGroup: "Other / Review Required",
      status: "UNKNOWN_UNRESOLVED",
    };
  }

  const upper = rawClass.toUpperCase();
  switch (upper) {
    case "INTERIOR_PARTITION":
      return {
        primaryLabel: "Interior Partition",
        secondaryLabel: rawName,
        categoryGroup: "Interior Partition",
        status: "CONFIRMED",
      };
    case "DEMISING_WALL":
    case "DEMISING":
      return {
        primaryLabel: "Demising Wall (2-Hr)",
        secondaryLabel: rawName,
        categoryGroup: "Interior Partition",
        status: "CONFIRMED",
      };
    case "SHAFT_WALL":
    case "SHAFT":
      return {
        primaryLabel: "Shaft Wall",
        secondaryLabel: rawName,
        categoryGroup: "Interior Partition",
        status: "CONFIRMED",
      };
    case "EXTERIOR_WALL":
    case "EXTERIOR_PERIMETER":
      return {
        primaryLabel: "Exterior Wall",
        secondaryLabel: rawName,
        categoryGroup: "Exterior Wall",
        status: "CONFIRMED",
      };
    case "MASONRY":
    case "CMU":
      return {
        primaryLabel: "Masonry / CMU Wall",
        secondaryLabel: rawName,
        categoryGroup: "Exterior Wall",
        status: "CONFIRMED",
      };
    case "FOUNDATION":
    case "FOUNDATION_PERIMETER":
      return {
        primaryLabel: "Foundation / Perimeter",
        secondaryLabel: rawName,
        categoryGroup: "Foundation / Perimeter",
        status: "CONFIRMED",
      };
    case "STRUCTURAL_CONCRETE":
    case "STRUCTURAL_BEARING":
      return {
        primaryLabel: "Structural Concrete",
        secondaryLabel: rawName,
        categoryGroup: "Structural Concrete",
        status: "CONFIRMED",
      };
    case "CURTAIN_WALL":
    case "STOREFRONT":
      return {
        primaryLabel: "Curtain Wall",
        secondaryLabel: rawName,
        categoryGroup: "Curtain Wall",
        status: "CONFIRMED",
      };
    default:
      return {
        primaryLabel: rawClass.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        secondaryLabel: rawName,
        categoryGroup: "Other / Review Required",
        status: "CONFIRMED",
      };
  }
}

export const CANONICAL_TREE_CATEGORIES = [
  "Interior Partition",
  "Exterior Wall",
  "Foundation / Perimeter",
  "Structural Concrete",
  "Curtain Wall",
  "Other / Review Required",
] as const;

export interface BIMModelTreeProps {
  projectName?: string;
  buildingName?: string;
  storeys: Array<{ id: string; name: string; elevation_ft?: number }>;
  walls?: Array<{
    ifc_guid: string;
    name: string;
    storey_name?: string;
    storey_id?: string;
    wall_classification?: string;
    length_ft?: number;
    drywall_finish_height_ft?: number;
    qto_eligibility?: string;
    assembly?: any;
  }>;
  spaces?: Array<{
    ifc_guid: string;
    name: string;
    storey_id?: string;
    net_floor_area_sqft?: number;
    provenance_status?: string;
  }>;
  slabs?: Array<{
    ifc_guid: string;
    name: string;
    storey_id?: string;
    area_sqft?: number;
  }>;
  roofs?: Array<{
    ifc_guid: string;
    name: string;
    storey_id?: string;
    storey_name?: string;
    area_sqft?: number;
    roof_type?: string;
    primary_material?: string;
    slope_degrees?: number;
    pitch?: string;
    true_surface_area_sqft?: number;
    plan_area_sqft?: number;
    qto_eligibility?: string;
    [key: string]: any;
  }>;
  flooringElements?: Array<{
    id?: string;
    ifc_guid: string;
    source_entity_type?: string;
    evidence_type?: string;
    source_name?: string;
    storey_id?: string;
    storey_name?: string;
    flooring_category?: string;
    finish_material_name?: string;
    thickness_in?: number;
    gross_area_sqft?: number;
    void_deductions_sqft?: number;
    net_area_sqft?: number;
    perimeter_ft?: number;
    qto_eligibility?: string;
    provenance_status?: string;
    eligibility_reasons?: string[];
    source_psets?: Record<string, any>;
  }>;
  trade?: "drywall" | "flooring" | "roofing";
  selectedWallGuid: string | null;
  onSelectGuid: (guid: string) => void;
  hiddenGuids: Set<string>;
  onToggleVisibility: (guid: string, e?: React.MouseEvent) => void;
  isolatedGuid: string | null;
  onIsolateGuid: (guid: string, e?: React.MouseEvent) => void;
  onShowAll?: () => void;
  searchQuery?: string;
  onSearchChange?: (query: string) => void;
  selectedStoreyFilter?: string;
  onStoreyFilterChange?: (storey: string) => void;
  selectedClassificationFilter?: string;
  onClassificationFilterChange?: (classification: string) => void;
}

export default function BIMModelTree({
  projectName = "BIM Project Model",
  buildingName = "Building 01",
  storeys = [],
  walls = [],
  spaces = [],
  slabs = [],
  roofs = [],
  flooringElements = [],
  trade = "drywall",
  selectedWallGuid,
  onSelectGuid,
  hiddenGuids,
  onToggleVisibility,
  isolatedGuid,
  onIsolateGuid,
  onShowAll,
  searchQuery = "",
  onSearchChange,
  selectedStoreyFilter = "ALL",
  onStoreyFilterChange,
  selectedClassificationFilter = "ALL",
  onClassificationFilterChange,
}: BIMModelTreeProps) {
  const isFlooring = trade === "flooring";
  const isRoofing = trade === "roofing";

  // Local Tree Expansion State
  const [projectExpanded, setProjectExpanded] = useState<boolean>(true);
  const [buildingExpanded, setBuildingExpanded] = useState<boolean>(true);
  const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({});

  // Distinct Flooring Categories for quick filter dropdown
  const distinctFlooringCategories = useMemo(() => {
    const cats = new Set<string>();
    flooringElements.forEach((f) => {
      if (f.flooring_category) cats.add(f.flooring_category);
    });
    return Array.from(cats);
  }, [flooringElements]);

  // Distinct Roofing Types for quick filter dropdown
  const distinctRoofTypes = useMemo(() => {
    const types = new Set<string>();
    roofs.forEach((r) => {
      if (r.roof_type) types.add(r.roof_type);
    });
    return Array.from(types);
  }, [roofs]);

  // Toggle individual subtree node
  const toggleNode = useCallback((nodeId: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setExpandedNodes((prev) => ({
      ...prev,
      [nodeId]: prev[nodeId] === undefined ? false : !prev[nodeId],
    }));
  }, []);

  // Expand All / Collapse All Controls
  const handleExpandAll = useCallback(() => {
    setProjectExpanded(true);
    setBuildingExpanded(true);
    const next: Record<string, boolean> = {};
    storeys.forEach((st) => {
      next[`storey-${st.id}`] = true;
      next[`${st.id}-walls`] = true;
      next[`${st.id}-spaces`] = true;
      next[`${st.id}-slabs`] = true;
      next[`${st.id}-roofs`] = true;
      next[`${st.id}-flooring`] = true;
      CANONICAL_TREE_CATEGORIES.forEach((cat) => {
        next[`${st.id}-cat-${cat}`] = true;
      });
      distinctFlooringCategories.forEach((cat) => {
        next[`${st.id}-flrcat-${cat}`] = true;
      });
    });
    setExpandedNodes(next);
  }, [storeys, distinctFlooringCategories]);

  const handleCollapseAll = useCallback(() => {
    setProjectExpanded(false);
    setBuildingExpanded(false);
    setExpandedNodes({});
  }, []);

  // Filter Elements based on active search and filter state
  const queryLower = searchQuery.trim().toLowerCase();

  const filteredWalls = useMemo(() => {
    if (isFlooring || isRoofing) return [];
    return walls.filter((w) => {
      // Storey Filter
      if (
        selectedStoreyFilter !== "ALL" &&
        w.storey_name !== selectedStoreyFilter &&
        w.storey_id !== selectedStoreyFilter
      ) {
        return false;
      }

      // Classification Filter
      if (
        selectedClassificationFilter !== "ALL" &&
        w.wall_classification !== selectedClassificationFilter
      ) {
        return false;
      }

      // Search Filter
      if (!queryLower) return true;

      const meta = formatWallDisplay(w);
      return (
        w.ifc_guid?.toLowerCase().includes(queryLower) ||
        w.name?.toLowerCase().includes(queryLower) ||
        meta.primaryLabel.toLowerCase().includes(queryLower) ||
        meta.categoryGroup.toLowerCase().includes(queryLower) ||
        w.storey_name?.toLowerCase().includes(queryLower)
      );
    });
  }, [walls, selectedStoreyFilter, selectedClassificationFilter, queryLower, isFlooring, isRoofing]);

  const filteredSpaces = useMemo(() => {
    if (isFlooring || isRoofing) return [];
    return spaces.filter((sp) => {
      if (
        selectedStoreyFilter !== "ALL" &&
        sp.storey_id !== selectedStoreyFilter
      ) {
        return false;
      }

      if (!queryLower) return true;

      return (
        sp.ifc_guid?.toLowerCase().includes(queryLower) ||
        sp.name?.toLowerCase().includes(queryLower) ||
        sp.storey_id?.toLowerCase().includes(queryLower)
      );
    });
  }, [spaces, selectedStoreyFilter, queryLower, isFlooring, isRoofing]);

  const filteredFlooring = useMemo(() => {
    if (!isFlooring) return [];
    return flooringElements.filter((f) => {
      // Storey Filter
      if (
        selectedStoreyFilter !== "ALL" &&
        f.storey_name !== selectedStoreyFilter &&
        f.storey_id !== selectedStoreyFilter
      ) {
        return false;
      }

      // Category / Type Filter
      if (
        selectedClassificationFilter !== "ALL" &&
        f.flooring_category !== selectedClassificationFilter
      ) {
        return false;
      }

      // Search Filter
      if (!queryLower) return true;

      return (
        f.ifc_guid?.toLowerCase().includes(queryLower) ||
        f.source_name?.toLowerCase().includes(queryLower) ||
        f.finish_material_name?.toLowerCase().includes(queryLower) ||
        f.flooring_category?.toLowerCase().includes(queryLower) ||
        f.storey_name?.toLowerCase().includes(queryLower)
      );
    });
  }, [flooringElements, selectedStoreyFilter, selectedClassificationFilter, queryLower, isFlooring]);

  const filteredRoofs = useMemo(() => {
    if (!isRoofing) return [];
    return roofs.filter((r) => {
      // Storey Filter
      if (
        selectedStoreyFilter !== "ALL" &&
        r.storey_name !== selectedStoreyFilter &&
        r.storey_id !== selectedStoreyFilter
      ) {
        return false;
      }

      // Type Filter
      if (
        selectedClassificationFilter !== "ALL" &&
        r.roof_type !== selectedClassificationFilter
      ) {
        return false;
      }

      // Search Filter
      if (!queryLower) return true;

      return (
        r.ifc_guid?.toLowerCase().includes(queryLower) ||
        r.name?.toLowerCase().includes(queryLower) ||
        r.roof_type?.toLowerCase().includes(queryLower) ||
        r.primary_material?.toLowerCase().includes(queryLower) ||
        r.storey_name?.toLowerCase().includes(queryLower)
      );
    });
  }, [roofs, selectedStoreyFilter, selectedClassificationFilter, queryLower, isRoofing]);

  // Overall Totals for Top-Level Badges
  const totalModelElements = isRoofing
    ? roofs.length
    : isFlooring
    ? flooringElements.length
    : walls.length + spaces.length + slabs.length + roofs.length;

  const filteredTotalCount = isRoofing
    ? filteredRoofs.length
    : isFlooring
    ? filteredFlooring.length
    : filteredWalls.length + filteredSpaces.length;

  return (
    <div className="h-full flex flex-col bg-[#0a121e] text-gray-200 select-none overflow-hidden font-mono">
      {/* 1. Header Toolbar */}
      <div className="p-2.5 border-b border-[#162840] flex items-center justify-between bg-[#080e18] flex-shrink-0">
        <div className="flex items-center space-x-1.5">
          <FolderTree size={14} className="text-cyan-400" />
          <span className="text-xs font-bold uppercase tracking-wider text-gray-100 font-sans">
            {isRoofing ? "Roofing Model Tree" : isFlooring ? "Flooring Model Tree" : "Model Tree"}
          </span>
        </div>

        <div className="flex items-center space-x-1">
          <button
            onClick={handleExpandAll}
            className="p-1 rounded hover:bg-gray-800 text-gray-400 hover:text-cyan-300 transition-colors"
            title="Expand All Nodes"
          >
            <Maximize2 size={11} />
          </button>
          <button
            onClick={handleCollapseAll}
            className="p-1 rounded hover:bg-gray-800 text-gray-400 hover:text-cyan-300 transition-colors"
            title="Collapse All Nodes"
          >
            <Minimize2 size={11} />
          </button>
          {onShowAll && (
            <button
              onClick={onShowAll}
              className="p-1 rounded hover:bg-gray-800 text-gray-400 hover:text-emerald-400 transition-colors"
              title="Reset View: Show All Elements"
            >
              <RotateCcw size={11} />
            </button>
          )}
          <span className="text-[10px] bg-[#060b14] border border-[#162840] px-1.5 py-0.5 rounded text-cyan-300 font-bold ml-1">
            {filteredTotalCount} / {totalModelElements}
          </span>
        </div>
      </div>

      {/* 2. Search & Filter Bar */}
      <div className="p-2 border-b border-[#162840] bg-[#060b14] space-y-1.5 flex-shrink-0">
        <div className="flex items-center px-2 py-1 rounded bg-[#0a121e] border border-[#162840] text-xs">
          <Search size={12} className="text-gray-400 mr-1.5 flex-shrink-0" />
          <input
            type="text"
            placeholder={
              isRoofing
                ? "Search Roof, Type, Material, GUID…"
                : isFlooring
                ? "Search Floor Finish, GUID, Category…"
                : "Search GUID, Source Name, Class…"
            }
            value={searchQuery}
            onChange={(e) => onSearchChange?.(e.target.value)}
            className="bg-transparent w-full outline-none text-xs text-gray-200 placeholder-gray-500 font-mono"
          />
          {searchQuery && (
            <button
              onClick={() => onSearchChange?.("")}
              className="text-[10px] text-gray-400 hover:text-white ml-1 px-1 rounded hover:bg-gray-800"
            >
              ×
            </button>
          )}
        </div>

        {/* Storey & Classification Quick Filter Strip */}
        <div className="flex items-center gap-1 text-[10px]">
          {onStoreyFilterChange && (
            <select
              value={selectedStoreyFilter}
              onChange={(e) => onStoreyFilterChange(e.target.value)}
              className="flex-1 bg-[#0a121e] border border-[#162840] rounded px-1.5 py-0.5 text-gray-300 outline-none cursor-pointer truncate"
            >
              <option value="ALL">All Levels ({storeys.length})</option>
              {storeys.map((st) => (
                <option key={st.id} value={st.name}>
                  {st.name}
                </option>
              ))}
            </select>
          )}

          {onClassificationFilterChange && (
            <select
              value={selectedClassificationFilter}
              onChange={(e) => onClassificationFilterChange(e.target.value)}
              className="flex-1 bg-[#0a121e] border border-[#162840] rounded px-1.5 py-0.5 text-gray-300 outline-none cursor-pointer truncate"
            >
              <option value="ALL">All {isFlooring ? "Categories" : "Types"}</option>
              {isFlooring ? (
                distinctFlooringCategories.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat.replace(/_/g, " ")}
                  </option>
                ))
              ) : (
                <>
                  <option value="INTERIOR_PARTITION">Interior Partition</option>
                  <option value="DEMISING_WALL">Demising Wall (2-Hr)</option>
                  <option value="SHAFT_WALL">Shaft Wall</option>
                  <option value="EXTERIOR_WALL">Exterior Wall</option>
                  <option value="STRUCTURAL_CONCRETE">Structural Concrete</option>
                  <option value="CURTAIN_WALL">Curtain Wall</option>
                  <option value="MASONRY">Masonry / CMU</option>
                  <option value="UNKNOWN">Other / Review</option>
                </>
              )}
            </select>
          )}
        </div>
      </div>

      {/* 3. Hierarchical BIM Tree Body */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1 text-xs">
        {/* LEVEL 1: PROJECT NODE */}
        <div className="border border-[#162840]/60 rounded bg-[#060b14]/50 overflow-hidden">
          <div
            onClick={() => setProjectExpanded((p) => !p)}
            className="flex items-center justify-between px-2 py-1.5 bg-[#0a1424] hover:bg-[#0f1d32] cursor-pointer text-cyan-200 font-bold border-b border-[#162840]/40"
          >
            <div className="flex items-center space-x-1.5 truncate">
              {projectExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              <span className="text-[11px] truncate">{projectName}</span>
            </div>
            <span className="text-[9px] bg-cyan-950 text-cyan-300 px-1 rounded border border-cyan-800 flex-shrink-0">
              {totalModelElements} elems
            </span>
          </div>

          {projectExpanded && (
            <div className="p-1 pl-2 space-y-1">
              {/* LEVEL 2: BUILDING NODE */}
              <div className="border border-[#162840]/40 rounded bg-[#060b14]/40 overflow-hidden">
                <div
                  onClick={() => setBuildingExpanded((p) => !p)}
                  className="flex items-center justify-between px-2 py-1 bg-[#0c182a] hover:bg-[#11223b] cursor-pointer text-gray-200 font-semibold"
                >
                  <div className="flex items-center space-x-1.5 truncate">
                    {buildingExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                    <Building2 size={12} className="text-cyan-400" />
                    <span className="text-[11px] truncate">{buildingName}</span>
                  </div>
                  <span className="text-[9px] text-gray-400 flex-shrink-0">
                    {storeys.length} Storeys · {filteredTotalCount} items
                  </span>
                </div>

                {buildingExpanded && (
                  <div className="p-1 pl-2 space-y-1">
                    {/* LEVEL 3: STOREY NODES */}
                    {storeys.map((st) => {
                      const stKey = `storey-${st.id}`;
                      const isStExpanded = expandedNodes[stKey] !== false;

                      if (selectedStoreyFilter !== "ALL" && st.name !== selectedStoreyFilter) {
                        return null;
                      }

                      // FLOORING TREE RENDERING (ESTIMATOR-FIRST HIERARCHY)
                      if (isFlooring) {
                        const stFloors = filteredFlooring.filter(
                          (f) => f.storey_name === st.name || f.storey_id === st.id
                        );
                        const stFlooringArea = stFloors
                          .filter((f) => f.qto_eligibility === "ELIGIBLE")
                          .reduce((sum, f) => sum + (Number(f.net_area_sqft) || 0), 0);

                        return (
                          <div
                            key={st.id}
                            className="border border-[#162840]/60 rounded bg-[#070e1a]/80 overflow-hidden mb-1"
                          >
                            {/* Storey Header */}
                            <div
                              onClick={(e) => toggleNode(stKey, e)}
                              className="flex items-center justify-between px-2.5 py-1.5 bg-[#0e1726] hover:bg-[#132034] cursor-pointer text-gray-200 font-bold border-b border-[#162840]/30 transition-colors"
                            >
                              <div className="flex items-center space-x-1.5 truncate">
                                {isStExpanded ? <ChevronDown size={12} className="text-cyan-400" /> : <ChevronRight size={12} className="text-gray-400" />}
                                <Layers size={13} className="text-amber-400 flex-shrink-0" />
                                <span className="text-[11px] font-sans tracking-wide text-white uppercase truncate">
                                  {st.name}
                                </span>
                              </div>
                              <div className="flex items-center space-x-2 text-[10px] font-mono">
                                <span className="text-cyan-300 font-extrabold">
                                  {stFlooringArea > 0 ? `${stFlooringArea.toLocaleString(undefined, { maximumFractionDigits: 0 })} SF` : "—"}
                                </span>
                                <span className="text-gray-400 text-[9px] bg-[#060b14] px-1.5 py-0.2 rounded border border-[#162840]">
                                  {stFloors.length}
                                </span>
                              </div>
                            </div>

                            {isStExpanded && (
                              <div className="p-1 pl-2 space-y-1">
                                {stFloors.length === 0 ? (
                                  <div className="text-[10px] text-gray-500 italic p-1.5">
                                    No flooring elements on this level
                                  </div>
                                ) : (
                                  (() => {
                                    // Group by flooring category
                                    const floorsByCat: Record<string, any[]> = {};
                                    stFloors.forEach((f) => {
                                      const cat = f.flooring_category || "UNASSIGNED_FINISH";
                                      if (!floorsByCat[cat]) floorsByCat[cat] = [];
                                      floorsByCat[cat].push(f);
                                    });

                                    return Object.entries(floorsByCat).map(([catKey, catItems], catIdx) => {
                                      const catSubTreeKey = `${st.id}-flrcat-${catKey}`;
                                      const catExpanded = expandedNodes[catSubTreeKey] !== false;
                                      const catArea = catItems
                                        .filter((f) => f.qto_eligibility === "ELIGIBLE")
                                        .reduce((sum, f) => sum + (Number(f.net_area_sqft) || 0), 0);
                                      const pal = FLOORING_PALETTE[catKey] || {
                                        css: "#f59e0b",
                                        label: catKey.replace(/_/g, " "),
                                      };

                                      return (
                                        <div key={catKey} className="border border-[#162840]/30 rounded bg-[#060b14]/60 overflow-hidden space-y-0.5">
                                          {/* Category Header */}
                                          <div
                                            onClick={(e) => toggleNode(catSubTreeKey, e)}
                                            className="flex items-center justify-between px-2 py-1 bg-[#09111e] hover:bg-[#0f1d32] cursor-pointer text-gray-200 text-[10px] font-semibold transition-colors"
                                          >
                                            <div className="flex items-center space-x-1.5 truncate">
                                              {catExpanded ? <ChevronDown size={11} className="text-cyan-400" /> : <ChevronRight size={11} className="text-gray-400" />}
                                              <span
                                                className="w-2.5 h-2.5 rounded-sm flex-shrink-0 shadow-sm"
                                                style={{ backgroundColor: pal.css }}
                                              />
                                              <span className="font-bold text-gray-100 uppercase tracking-tight truncate max-w-[140px] font-sans">
                                                {pal.label || catKey.replace(/_/g, " ")}
                                              </span>
                                            </div>
                                            <div className="flex items-center space-x-1.5 text-[9px] font-mono">
                                              <span className="text-amber-300 font-bold">
                                                {catArea > 0 ? `${catArea.toFixed(0)} SF` : "—"}
                                              </span>
                                              <span className="text-gray-400">({catItems.length})</span>
                                            </div>
                                          </div>

                                          {/* Flooring Items */}
                                          {catExpanded && (
                                            <div className="p-1 pl-2 space-y-1 border-t border-[#162840]/30">
                                              {catItems.map((f, itemIdx) => {
                                                const guid = f.ifc_guid || f.id;
                                                const isSelected = guid === selectedWallGuid;
                                                const isHidden = hiddenGuids.has(f.ifc_guid);
                                                const isIsolated = isolatedGuid === f.ifc_guid;
                                                const netArea = Number(f.net_area_sqft || f.gross_area_sqft || 0);
                                                const elig = f.qto_eligibility || "ELIGIBLE";
                                                const isEligible = elig === "ELIGIBLE";
                                                const isSuperseded = elig === "SUPERSEDED_BY_PHYSICAL_ELEMENT";
                                                const isExcluded = elig.startsWith("INELIGIBLE") || elig === "BLOCKED";
                                                const isReview = elig === "REVIEW_REQUIRED";

                                                // Clean estimator-first display name
                                                let displayTitle = f.finish_material_name || f.source_name || `Floor ${String(itemIdx + 1).padStart(3, "0")}`;
                                                if (displayTitle.includes(":")) {
                                                  const parts = displayTitle.split(":");
                                                  displayTitle = parts[parts.length - 1].replace(/^nbl_/, "").replace(/_/g, " ");
                                                } else {
                                                  displayTitle = displayTitle.replace(/^nbl_/, "").replace(/_/g, " ");
                                                }

                                                const materialSubtitle = f.finish_material_name || f.flooring_category?.replace(/_/g, " ") || "Flooring Surface";

                                                return (
                                                  <div
                                                    key={guid}
                                                    onClick={() => onSelectGuid(guid)}
                                                    className={`flex items-center justify-between px-2 py-1.5 rounded text-xs transition-all cursor-pointer border ${
                                                      isSelected
                                                        ? "bg-cyan-950/80 text-white border-cyan-500 shadow-md font-bold ring-1 ring-cyan-400/40"
                                                        : "border-[#162840]/30 hover:border-cyan-800/60 hover:bg-[#0f1d32]/60 text-gray-300 bg-[#070e1a]/60"
                                                    }`}
                                                    title={`${displayTitle}\nMaterial: ${materialSubtitle}\nIFC GUID: ${f.ifc_guid}\nStatus: ${elig}`}
                                                  >
                                                    <div className="flex items-center space-x-2 truncate min-w-0 flex-1">
                                                      <span
                                                        className="w-2 h-2 rounded-full flex-shrink-0"
                                                        style={{ backgroundColor: pal.css }}
                                                      />
                                                      <div className="truncate min-w-0 flex-1">
                                                        <div className="flex items-center space-x-1.5">
                                                          <span className="truncate text-[11px] font-bold text-white block leading-tight font-sans">
                                                            {displayTitle}
                                                          </span>
                                                          {/* Compact status badge */}
                                                          <span
                                                            className={`text-[8px] px-1 py-0.2 rounded font-mono font-extrabold flex-shrink-0 ${
                                                              isEligible
                                                                ? "bg-emerald-950/90 text-emerald-400 border border-emerald-700/60"
                                                                : isSuperseded
                                                                ? "bg-purple-950/90 text-purple-300 border border-purple-700/60"
                                                                : isExcluded
                                                                ? "bg-rose-950/90 text-rose-400 border border-rose-700/60"
                                                                : "bg-amber-950/90 text-amber-400 border border-amber-700/60"
                                                            }`}
                                                          >
                                                            {isEligible
                                                              ? "✓ INCLUDED"
                                                              : isSuperseded
                                                              ? "↗ SUPERSEDED"
                                                              : isExcluded
                                                              ? "— EXCLUDED"
                                                              : "⚠ REVIEW"}
                                                          </span>
                                                        </div>
                                                        <span className="truncate text-[9px] text-gray-400 block leading-tight mt-0.5 font-mono">
                                                          {materialSubtitle}
                                                        </span>
                                                      </div>
                                                    </div>

                                                    <div className="flex items-center space-x-2 ml-2 flex-shrink-0">
                                                      <span className={`text-[10px] font-mono font-bold ${
                                                        isEligible ? "text-cyan-300" : "text-gray-500 line-through"
                                                      }`}>
                                                        {isEligible ? `${netArea.toFixed(1)} SF` : "—"}
                                                      </span>
                                                      <button
                                                        onClick={(e) => onIsolateGuid(f.ifc_guid, e)}
                                                        className={`p-0.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white transition-colors cursor-pointer ${
                                                          isIsolated ? "text-cyan-400" : ""
                                                        }`}
                                                        title="Isolate Element in 3D/2D"
                                                      >
                                                        <Crosshair size={11} />
                                                      </button>
                                                      <button
                                                        onClick={(e) => onToggleVisibility(f.ifc_guid, e)}
                                                        className={`p-0.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white transition-colors cursor-pointer ${
                                                          isHidden ? "text-rose-400" : ""
                                                        }`}
                                                        title="Toggle Visibility in 3D/2D"
                                                      >
                                                        {isHidden ? <EyeOff size={11} /> : <Eye size={11} />}
                                                      </button>
                                                    </div>
                                                  </div>
                                                );
                                              })}
                                            </div>
                                          )}
                                        </div>
                                      );
                                    });
                                  })()
                                )}
                              </div>
                            )}
                          </div>
                        );
                      }

                      // ROOFING TREE RENDERING (PHASE 4 CANONICAL)
                      if (trade === "roofing") {
                        const stRoofs = (roofs || []).filter(
                          (r: any) => r.storey_name === st.name || r.storey_id === st.id || (!r.storey_id && !r.storey_name)
                        );
                        if (stRoofs.length === 0) return null;

                        return (
                          <div
                            key={st.id}
                            className="border border-rose-950/40 rounded bg-[#0a0f18]/80 overflow-hidden shadow-sm"
                          >
                            {/* Storey Header */}
                            <div
                              onClick={(e) => toggleNode(stKey, e)}
                              className="flex items-center justify-between px-2 py-1.5 bg-[#120b14] hover:bg-[#1a0f1d] cursor-pointer text-gray-300 font-semibold border-b border-rose-950/40"
                            >
                              <div className="flex items-center space-x-1.5 truncate">
                                {isStExpanded ? <ChevronDown size={12} className="text-rose-400" /> : <ChevronRight size={12} className="text-gray-400" />}
                                <Building2 size={12} className="text-rose-400 flex-shrink-0" />
                                <span className="text-[11px] truncate text-white font-bold">{st.name}</span>
                              </div>
                              <span className="text-[9px] font-mono text-rose-300/80 bg-rose-950/80 px-1.5 py-0.5 rounded border border-rose-800/40">
                                {stRoofs.length} Roof{stRoofs.length > 1 ? "s" : ""}
                              </span>
                            </div>

                            {isStExpanded && (
                              <div className="p-1 space-y-1">
                                {stRoofs.map((rf: any, idx: number) => {
                                  const guid = rf.ifc_guid || rf.id;
                                  const isSelected = guid === selectedWallGuid;
                                  const isHidden = hiddenGuids.has(guid);
                                  const isIsolated = isolatedGuid === guid;
                                  const trueSqft = Number(rf.true_surface_area_sqft || rf.plan_area_sqft || 0);
                                  const isEligible = rf.qto_eligibility === "ELIGIBLE";
                                  const isReview = rf.qto_eligibility === "REVIEW_REQUIRED";

                                  return (
                                    <div
                                      key={guid}
                                      onClick={() => onSelectGuid(guid)}
                                      className={`flex items-center justify-between px-2 py-1.5 rounded text-xs transition-all cursor-pointer border ${
                                        isSelected
                                          ? "bg-rose-950/90 text-white border-rose-500 shadow-md font-bold ring-1 ring-rose-400/40"
                                          : "border-[#162840]/30 hover:border-rose-800/60 hover:bg-[#180d18]/60 text-gray-300 bg-[#070e1a]/60"
                                      }`}
                                    >
                                      <div className="flex items-center space-x-2 truncate min-w-0 flex-1">
                                        <span className="w-2 h-2 rounded-full flex-shrink-0 bg-rose-500" />
                                        <div className="truncate min-w-0 flex-1">
                                          <div className="flex items-center space-x-1.5">
                                            <span className="truncate text-[11px] font-bold text-white block leading-tight">
                                              {rf.name || `Roof ${idx + 1}`}
                                            </span>
                                            <span className="text-[8px] px-1 py-0.2 rounded font-mono font-extrabold bg-rose-950 text-rose-300 border border-rose-800/60">
                                              {rf.roof_type || "ROOF"}
                                            </span>
                                            {rf.pitch_ratio && (
                                              <span className="text-[8px] px-1 py-0.2 rounded font-mono font-bold bg-cyan-950 text-cyan-300 border border-cyan-800/60">
                                                {rf.pitch_ratio}
                                              </span>
                                            )}
                                          </div>
                                          <span className="truncate text-[9px] text-gray-400 block leading-tight mt-0.5 font-mono">
                                            {rf.primary_material || "UNASSIGNED"} • {rf.source_type || "IfcRoof"}
                                          </span>
                                        </div>
                                      </div>

                                      <div className="flex items-center space-x-2 ml-2 flex-shrink-0">
                                        <span className="text-[10px] font-mono font-bold text-rose-300">
                                          {trueSqft.toFixed(1)} SF
                                        </span>
                                        <button
                                          onClick={(e) => onIsolateGuid(guid, e)}
                                          className={`p-0.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white transition-colors cursor-pointer ${
                                            isIsolated ? "text-cyan-400" : ""
                                          }`}
                                          title="Isolate Element in 3D/2D"
                                        >
                                          <Crosshair size={11} />
                                        </button>
                                        <button
                                          onClick={(e) => onToggleVisibility(guid, e)}
                                          className={`p-0.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white transition-colors cursor-pointer ${
                                            isHidden ? "text-rose-400" : ""
                                          }`}
                                          title="Toggle Visibility in 3D/2D"
                                        >
                                          {isHidden ? <EyeOff size={11} /> : <Eye size={11} />}
                                        </button>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        );
                      }

                      // DRYWALL TREE RENDERING (FROZEN PHASE 2)
                      const stWalls = filteredWalls.filter(
                        (w) => w.storey_name === st.name || w.storey_id === st.id
                      );
                      const stSpaces = filteredSpaces.filter(
                        (sp) => sp.storey_id === st.name || sp.storey_id === st.id
                      );
                      const stRoofs = (roofs || []).filter(
                        (r: any) => r.storey_name === st.name || r.storey_id === st.id
                      );
                      const stTotalCount = stWalls.length + stSpaces.length + stRoofs.length;

                      return (
                        <div
                          key={st.id}
                          className="border border-[#162840]/40 rounded bg-[#070e1a]/60 overflow-hidden"
                        >
                          {/* Storey Header */}
                          <div
                            onClick={(e) => toggleNode(stKey, e)}
                            className="flex items-center justify-between px-2 py-1 bg-[#0e1726] hover:bg-[#132034] cursor-pointer text-gray-300 font-semibold"
                          >
                            <div className="flex items-center space-x-1.5 truncate">
                              {isStExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                              <Layers size={12} className="text-cyan-400 flex-shrink-0" />
                              <span className="text-[11px] truncate">{st.name}</span>
                            </div>
                            <span className="text-[9px] text-gray-400 flex-shrink-0">
                              {stTotalCount} items
                            </span>
                          </div>

                          {isStExpanded && (
                            <div className="p-1 pl-2 space-y-1 border-t border-[#162840]/40">
                              {/* LEVEL 4A: WALLS CATEGORY */}
                              {stWalls.length > 0 && (
                                <div className="space-y-0.5">
                                  {/* Walls Category Header */}
                                  <div
                                    onClick={(e) => toggleNode(`${st.id}-walls`, e)}
                                    className="flex items-center justify-between px-1.5 py-0.5 rounded bg-[#091220] hover:bg-gray-800/40 cursor-pointer text-gray-300 text-[11px]"
                                  >
                                    <div className="flex items-center space-x-1">
                                      {expandedNodes[`${st.id}-walls`] !== false ? (
                                        <ChevronDown size={11} />
                                      ) : (
                                        <ChevronRight size={11} />
                                      )}
                                      <Box size={11} className="text-cyan-400" />
                                      <span className="font-semibold text-gray-200">
                                        Walls ({stWalls.length})
                                      </span>
                                    </div>
                                  </div>

                                  {/* LEVEL 5: WALLS GROUPED BY CANONICAL CLASSIFICATION */}
                                  {expandedNodes[`${st.id}-walls`] !== false && (
                                    <div className="pl-2 space-y-1 pt-0.5">
                                      {(() => {
                                        const wallsByCat: Record<string, any[]> = {};
                                        CANONICAL_TREE_CATEGORIES.forEach((cat) => {
                                          wallsByCat[cat] = [];
                                        });

                                        stWalls.forEach((w) => {
                                          const meta = formatWallDisplay(w);
                                          const grp = meta.categoryGroup;
                                          if (!wallsByCat[grp]) wallsByCat[grp] = [];
                                          wallsByCat[grp].push(w);
                                        });

                                        return CANONICAL_TREE_CATEGORIES.map((catName) => {
                                          const groupWalls = wallsByCat[catName] || [];
                                          if (groupWalls.length === 0) return null;

                                          const subTreeKey = `${st.id}-cat-${catName}`;
                                          const catExpanded = expandedNodes[subTreeKey] !== false;

                                          return (
                                            <div key={catName} className="space-y-0.5">
                                              {/* Canonical Group Header */}
                                              <div
                                                onClick={(e) => toggleNode(subTreeKey, e)}
                                                className="flex items-center justify-between px-1.5 py-0.5 rounded hover:bg-gray-800/40 cursor-pointer text-gray-400 text-[10px]"
                                              >
                                                <div className="flex items-center space-x-1">
                                                  {catExpanded ? (
                                                    <ChevronDown size={10} />
                                                  ) : (
                                                    <ChevronRight size={10} />
                                                  )}
                                                  <span className="font-semibold text-gray-300">
                                                    {catName}
                                                  </span>
                                                </div>
                                                <span className="text-[9px] font-mono text-gray-500">
                                                  {groupWalls.length}
                                                </span>
                                              </div>

                                              {/* LEVEL 6: INDIVIDUAL WALL ELEMENTS */}
                                              {catExpanded && (
                                                <div className="pl-3 space-y-0.5">
                                                  {groupWalls.map((w) => {
                                                    const isSelected = w.ifc_guid === selectedWallGuid;
                                                    const isHidden = hiddenGuids.has(w.ifc_guid);
                                                    const isIsolated = isolatedGuid === w.ifc_guid;
                                                    const meta = formatWallDisplay(w);

                                                    return (
                                                      <div
                                                        key={w.ifc_guid}
                                                        onClick={() => onSelectGuid(w.ifc_guid)}
                                                        className={`flex items-center justify-between px-2 py-1 rounded text-xs transition-colors cursor-pointer border ${
                                                          isSelected
                                                            ? "bg-cyan-950/80 text-cyan-200 border-cyan-500 shadow-sm font-bold"
                                                            : "border-transparent hover:bg-gray-800/60 text-gray-300"
                                                        }`}
                                                      >
                                                        {/* Primary / Secondary Metadata */}
                                                        <div className="flex items-center space-x-1.5 truncate min-w-0 flex-1">
                                                          <span
                                                            className="w-2 h-2 rounded-full flex-shrink-0"
                                                            style={{
                                                              backgroundColor:
                                                                CATEGORY_COLORS[w.wall_classification]?.css ||
                                                                "#38bdf8",
                                                            }}
                                                          />
                                                          <div className="truncate min-w-0 flex-1">
                                                            {/* Primary: Canonical Classification */}
                                                            <div className="flex items-center space-x-1">
                                                              <span className="truncate text-[11px] font-semibold text-white block leading-tight">
                                                                {meta.primaryLabel}
                                                              </span>
                                                              {meta.status === "UNKNOWN_UNRESOLVED" && (
                                                                <span className="text-[7px] px-1 rounded bg-amber-950 text-amber-400 border border-amber-800 font-bold">
                                                                  REVIEW
                                                                </span>
                                                              )}
                                                            </div>
                                                            {/* Secondary: Raw IFC Source Name */}
                                                            <span
                                                              className="truncate text-[9px] font-mono text-gray-400 block leading-tight"
                                                              title={w.name}
                                                            >
                                                              {w.name}
                                                            </span>
                                                            {/* Stable Identifier: IFC GUID */}
                                                            <span className="truncate text-[8px] font-mono text-cyan-500/80 block leading-tight">
                                                              {w.ifc_guid}
                                                            </span>
                                                          </div>
                                                        </div>

                                                        {/* Actions: Isolate / Hide */}
                                                        <div className="flex items-center space-x-1 ml-2 flex-shrink-0">
                                                          <button
                                                            onClick={(e) => onIsolateGuid(w.ifc_guid, e)}
                                                            className={`p-0.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white ${
                                                              isIsolated ? "text-cyan-400" : ""
                                                            }`}
                                                            title="Isolate Element in 3D/2D"
                                                          >
                                                            <Crosshair size={11} />
                                                          </button>
                                                          <button
                                                            onClick={(e) => onToggleVisibility(w.ifc_guid, e)}
                                                            className={`p-0.5 rounded hover:bg-gray-700 text-gray-400 hover:text-white ${
                                                              isHidden ? "text-rose-400" : ""
                                                            }`}
                                                            title="Toggle Visibility in 3D/2D"
                                                          >
                                                            {isHidden ? <EyeOff size={11} /> : <Eye size={11} />}
                                                          </button>
                                                        </div>
                                                      </div>
                                                    );
                                                  })}
                                                </div>
                                              )}
                                            </div>
                                          );
                                        });
                                      })()}
                                    </div>
                                  )}
                                </div>
                              )}

                              {/* LEVEL 4B: SPACES CATEGORY */}
                              {stSpaces.length > 0 && (
                                <div className="space-y-0.5">
                                  <div
                                    onClick={(e) => toggleNode(`${st.id}-spaces`, e)}
                                    className="flex items-center justify-between px-1.5 py-0.5 rounded bg-[#091220] hover:bg-gray-800/40 cursor-pointer text-gray-300 text-[11px]"
                                  >
                                    <div className="flex items-center space-x-1">
                                      {expandedNodes[`${st.id}-spaces`] === true ? (
                                        <ChevronDown size={11} />
                                      ) : (
                                        <ChevronRight size={11} />
                                      )}
                                      <Square size={11} className="text-emerald-400" />
                                      <span className="font-semibold text-gray-200">
                                        Spaces ({stSpaces.length})
                                      </span>
                                    </div>
                                  </div>

                                  {expandedNodes[`${st.id}-spaces`] === true && (
                                    <div className="pl-3 space-y-0.5 pt-0.5">
                                      {stSpaces.map((sp) => {
                                        const isSelected = sp.ifc_guid === selectedWallGuid;
                                        return (
                                          <div
                                            key={sp.ifc_guid}
                                            onClick={() => onSelectGuid(sp.ifc_guid)}
                                            className={`flex items-center justify-between px-2 py-1 rounded text-xs transition-colors cursor-pointer border ${
                                              isSelected
                                                ? "bg-emerald-950/80 text-emerald-200 border-emerald-500 font-bold"
                                                : "border-transparent hover:bg-gray-800/60 text-gray-300"
                                            }`}
                                          >
                                            <div className="truncate min-w-0 flex-1">
                                              <span className="truncate text-[11px] font-semibold text-white block">
                                                {sp.name}
                                              </span>
                                              <span className="truncate text-[8px] font-mono text-cyan-500/80 block">
                                                {sp.ifc_guid}
                                              </span>
                                            </div>
                                            <span className="text-[10px] font-mono text-emerald-400 flex-shrink-0 ml-2">
                                              {Number(sp.net_floor_area_sqft || 0).toFixed(0)} SF
                                            </span>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  )}
                                </div>
                              )}

                              {/* LEVEL 4C: ROOFS CATEGORY */}
                              {stRoofs.length > 0 && (
                                <div className="space-y-0.5">
                                  <div
                                    onClick={(e) => toggleNode(`${st.id}-roofs`, e)}
                                    className="flex items-center justify-between px-1.5 py-0.5 rounded bg-[#180d18] hover:bg-rose-950/40 cursor-pointer text-rose-300 text-[11px]"
                                  >
                                    <div className="flex items-center space-x-1">
                                      {expandedNodes[`${st.id}-roofs`] !== false ? (
                                        <ChevronDown size={11} />
                                      ) : (
                                        <ChevronRight size={11} />
                                      )}
                                      <Building2 size={11} className="text-rose-400" />
                                      <span className="font-semibold text-rose-200">
                                        Roofs ({stRoofs.length})
                                      </span>
                                    </div>
                                  </div>

                                  {expandedNodes[`${st.id}-roofs`] !== false && (
                                    <div className="pl-3 space-y-0.5 pt-0.5">
                                      {stRoofs.map((rf: any) => {
                                        const isSelected = rf.ifc_guid === selectedWallGuid || rf.id === selectedWallGuid;
                                        return (
                                          <div
                                            key={rf.ifc_guid || rf.id}
                                            onClick={() => onSelectGuid(rf.ifc_guid || rf.id)}
                                            className={`flex items-center justify-between px-2 py-1 rounded text-xs transition-colors cursor-pointer border ${
                                              isSelected
                                                ? "bg-rose-950/80 text-rose-200 border-rose-500 font-bold"
                                                : "border-transparent hover:bg-gray-800/60 text-gray-300"
                                            }`}
                                          >
                                            <div className="truncate min-w-0 flex-1">
                                              <div className="flex items-center space-x-1">
                                                <span className="truncate text-[11px] font-semibold text-white block">
                                                  {rf.name || "Roof Assembly"}
                                                </span>
                                                <span className="text-[8px] px-1 rounded bg-rose-950 text-rose-400 border border-rose-800 font-mono">
                                                  {rf.roof_type || "ROOF"}
                                                </span>
                                              </div>
                                              <span className="truncate text-[8px] font-mono text-cyan-500/80 block">
                                                {rf.ifc_guid}
                                              </span>
                                            </div>
                                            <span className="text-[10px] font-mono text-rose-400 flex-shrink-0 ml-2">
                                              {Number(rf.true_surface_area_sqft || rf.plan_area_sqft || 0).toFixed(0)} SF
                                            </span>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

