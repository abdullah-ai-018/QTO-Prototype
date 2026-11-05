import React, { useState, useMemo } from "react";
import {
  AlertTriangle,
  AlertCircle,
  Info,
  ShieldCheck,
  CheckCircle2,
  Filter,
  Search,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Box,
  Copy,
  Check,
  ExternalLink,
  Layers,
  Square,
  Crosshair,
} from "lucide-react";
import { formatWallDisplay } from "./BIMModelTree";
import { ProvenanceBadge } from "./BIMInspector";
import { toast } from "sonner";

export interface ReviewItem {
  guid: string;
  ifc_class: string;
  canonical_classification: string;
  source_name: string;
  storey: string;
  trade: string;
  issue_category:
    | "MISSING_GEOMETRY"
    | "INVALID_GEOMETRY"
    | "ZERO_LENGTH"
    | "MISSING_HEIGHT"
    | "MISSING_WALL_ASSEMBLY"
    | "MISSING_MATERIAL_LAYERS"
    | "AMBIGUOUS_DRYWALL_SCOPE"
    | "OPENING_RECONCILIATION_CONFLICT"
    | "MISSING_REQUIRED_PSET"
    | "UNSUPPORTED_GEOMETRY"
    | "CONFIGURED_ASSUMPTION"
    | "OTHER_UNRESOLVED";
  severity: "CRITICAL" | "WARNING" | "INFO";
  status:
    | "BLOCKED"
    | "REVIEW_REQUIRED"
    | "UNKNOWN_UNRESOLVED"
    | "CONFIGURED_ASSUMPTION"
    | "DERIVED"
    | "VERIFIED";
  provenance: string;
  affected_quantity?: string | null;
  reason: string;
  source_field?: string;
  blocks_qto: boolean;
}

export interface BIMReviewQueueProps {
  walls: any[];
  spaces: any[];
  lineItemByGuid: Record<string, any>;
  selectedWallGuid: string | null;
  onSelectGuid: (guid: string) => void;
  onNavigateToTakeoff?: (guid: string) => void;
}

export type ReviewSeverityFilter = "ALL" | "CRITICAL" | "WARNING" | "INFO";
export type ReviewStatusFilter = "ALL" | "BLOCKED" | "REVIEW_REQUIRED" | "CONFIGURED_ASSUMPTION";

export default function BIMReviewQueue({
  walls,
  spaces,
  lineItemByGuid,
  selectedWallGuid,
  onSelectGuid,
  onNavigateToTakeoff,
}: BIMReviewQueueProps) {
  const [severityFilter, setSeverityFilter] = useState<ReviewSeverityFilter>("ALL");
  const [statusFilter, setStatusFilter] = useState<ReviewStatusFilter>("ALL");
  const [selectedStorey, setSelectedStorey] = useState<string>("ALL");
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [copiedGuid, setCopiedGuid] = useState<string | null>(null);

  const handleCopy = (guid: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard?.writeText(guid);
    setCopiedGuid(guid);
    toast.success(`Copied GUID: ${guid}`);
    setTimeout(() => setCopiedGuid(null), 1500);
  };

  // 1. Extract Review Items from Canonical Model & QTO Provenance
  const allReviewItems = useMemo<ReviewItem[]>(() => {
    const items: ReviewItem[] = [];

    // Evaluate Walls
    walls.forEach((w: any) => {
      const line = lineItemByGuid[w.ifc_guid];
      const wallMeta = formatWallDisplay(w);

      // A. Critical Blocked Geometry
      if (
        w.qto_eligibility === "INELIGIBLE_INVALID_GEOMETRY" ||
        (w.length_ft != null && w.length_ft <= 0)
      ) {
        items.push({
          guid: w.ifc_guid,
          ifc_class: w.ifc_class || "IfcWallStandardCase",
          canonical_classification: wallMeta.primaryLabel,
          source_name: w.name || "Unnamed Wall",
          storey: w.storey_name || "Unknown Storey",
          trade: "drywall",
          issue_category: "INVALID_GEOMETRY",
          severity: "CRITICAL",
          status: "BLOCKED",
          provenance: w.length_provenance || "UNKNOWN_UNRESOLVED",
          affected_quantity: "0.0 SF (Takeoff Blocked)",
          reason:
            w.eligibility_reasons?.join("; ") ||
            "Zero or corrupted analytical geometry dimensions extracted from IFC axis/solid.",
          blocks_qto: true,
        });
      }

      // B. Review Required (Unknown Classification or ambiguous scope)
      else if (
        w.qto_eligibility === "REVIEW_REQUIRED" ||
        wallMeta.status === "UNKNOWN_UNRESOLVED"
      ) {
        items.push({
          guid: w.ifc_guid,
          ifc_class: w.ifc_class || "IfcWallStandardCase",
          canonical_classification: wallMeta.primaryLabel,
          source_name: w.name || "Unnamed Wall",
          storey: w.storey_name || "Unknown Storey",
          trade: "drywall",
          issue_category:
            w.wall_classification === "UNKNOWN"
              ? "OTHER_UNRESOLVED"
              : "AMBIGUOUS_DRYWALL_SCOPE",
          severity: "WARNING",
          status: "REVIEW_REQUIRED",
          provenance: "UNKNOWN_UNRESOLVED",
          affected_quantity: line?.provenance?.net_drywall_sqft
            ? `${Number(line.provenance.net_drywall_sqft).toFixed(1)} SF`
            : "Requires Estimator Confirmation",
          reason:
            w.eligibility_reasons?.join("; ") ||
            "Ambiguous wall classification or unconfirmed assembly scope.",
          blocks_qto: false,
        });
      }

      // C. Configured Assumptions (Stud spacing, default layers)
      else if (
        w.assembly?.assembly_provenance === "CONFIGURED_ASSUMPTION" ||
        w.height_provenance === "CONFIGURED_ASSUMPTION"
      ) {
        items.push({
          guid: w.ifc_guid,
          ifc_class: w.ifc_class || "IfcWallStandardCase",
          canonical_classification: wallMeta.primaryLabel,
          source_name: w.name || "Unnamed Wall",
          storey: w.storey_name || "Unknown Storey",
          trade: "drywall",
          issue_category: "CONFIGURED_ASSUMPTION",
          severity: "INFO",
          status: "CONFIGURED_ASSUMPTION",
          provenance: "CONFIGURED_ASSUMPTION",
          affected_quantity: line?.provenance?.net_drywall_sqft
            ? `${Number(line.provenance.net_drywall_sqft).toFixed(1)} SF`
            : null,
          reason:
            "Standard drywall partition assembly applied from project estimator profile (5/8\" Type X, 3-5/8\" stud @ 16\" o.c.).",
          blocks_qto: false,
        });
      }

      // D. Ineligible Non-Drywall
      else if (w.qto_eligibility === "INELIGIBLE_NON_DRYWALL") {
        items.push({
          guid: w.ifc_guid,
          ifc_class: w.ifc_class || "IfcWallStandardCase",
          canonical_classification: wallMeta.primaryLabel,
          source_name: w.name || "Unnamed Wall",
          storey: w.storey_name || "Unknown Storey",
          trade: "drywall",
          issue_category: "AMBIGUOUS_DRYWALL_SCOPE",
          severity: "INFO",
          status: "BLOCKED",
          provenance: "DERIVED_GEOMETRIC",
          affected_quantity: "Excluded from Drywall Scope",
          reason: `${w.wall_classification?.replace(/_/g, " ") || "Non-drywall element"} — excluded from drywall bill of quantities.`,
          blocks_qto: true,
        });
      }
    });

    // Evaluate Spaces with Missing Properties
    spaces.forEach((sp: any) => {
      if (sp.provenance_status === "UNKNOWN_UNRESOLVED" || (sp.net_floor_area_sqft || 0) <= 0) {
        items.push({
          guid: sp.ifc_guid,
          ifc_class: "IfcSpace",
          canonical_classification: "Space / Room",
          source_name: sp.name || "Unnamed Space",
          storey: sp.storey_name || sp.storey_id || "Unknown Storey",
          trade: "architectural",
          issue_category: "MISSING_REQUIRED_PSET",
          severity: "WARNING",
          status: "UNKNOWN_UNRESOLVED",
          provenance: "UNKNOWN_UNRESOLVED",
          affected_quantity: "Missing Floor Area",
          reason: "Space boundary polygon or base area property missing from IFC.",
          blocks_qto: false,
        });
      }
    });

    return items;
  }, [walls, spaces, lineItemByGuid]);

  // 2. Dynamic KPI Counts
  const counts = useMemo(() => {
    let critical = 0;
    let warning = 0;
    let info = 0;
    let blocked = 0;
    let reviewRequired = 0;
    let assumptions = 0;

    allReviewItems.forEach((item) => {
      if (item.severity === "CRITICAL") critical++;
      else if (item.severity === "WARNING") warning++;
      else if (item.severity === "INFO") info++;

      if (item.status === "BLOCKED") blocked++;
      else if (item.status === "REVIEW_REQUIRED" || item.status === "UNKNOWN_UNRESOLVED") reviewRequired++;
      else if (item.status === "CONFIGURED_ASSUMPTION") assumptions++;
    });

    return {
      total: allReviewItems.length,
      critical,
      warning,
      info,
      blocked,
      reviewRequired,
      assumptions,
    };
  }, [allReviewItems]);

  // 3. Unique Filter Options
  const uniqueStoreys = useMemo(() => {
    const set = new Set<string>();
    allReviewItems.forEach((i) => i.storey && set.add(i.storey));
    return Array.from(set);
  }, [allReviewItems]);

  const uniqueCategories = useMemo(() => {
    const set = new Set<string>();
    allReviewItems.forEach((i) => i.issue_category && set.add(i.issue_category));
    return Array.from(set);
  }, [allReviewItems]);

  // 4. Filtered Items
  const filteredItems = useMemo(() => {
    return allReviewItems.filter((item) => {
      // Severity Filter
      if (severityFilter !== "ALL" && item.severity !== severityFilter) return false;

      // Status Filter
      if (statusFilter !== "ALL" && item.status !== statusFilter) return false;

      // Storey Filter
      if (selectedStorey !== "ALL" && item.storey !== selectedStorey) return false;

      // Category Filter
      if (selectedCategory !== "ALL" && item.issue_category !== selectedCategory) return false;

      // Search Query
      if (searchQuery.trim() !== "") {
        const q = searchQuery.toLowerCase();
        const match =
          item.guid.toLowerCase().includes(q) ||
          item.source_name.toLowerCase().includes(q) ||
          item.canonical_classification.toLowerCase().includes(q) ||
          item.reason.toLowerCase().includes(q) ||
          item.storey.toLowerCase().includes(q);
        if (!match) return false;
      }

      return true;
    });
  }, [allReviewItems, severityFilter, statusFilter, selectedStorey, selectedCategory, searchQuery]);

  return (
    <div className="h-full flex flex-col bg-[#060b14] text-gray-200 overflow-hidden font-sans p-6 space-y-4">
      {/* ===================================================================== */}
      {/* 1. HEADER & KPI METRIC TILES                                          */}
      {/* ===================================================================== */}
      <div className="flex items-center justify-between flex-shrink-0 flex-wrap gap-3">
        <div>
          <h2 className="text-base font-black text-white flex items-center gap-2">
            <AlertTriangle size={18} className="text-amber-400" />
            <span>IFC Model Review Queue</span>
            <span className="text-xs font-mono bg-[#162840] text-cyan-300 px-2 py-0.5 rounded font-bold">
              {counts.total} Items
            </span>
          </h2>
          <p className="text-xs text-gray-400">
            Unresolved, gated, or assumed conditions from IFC canonical ingestion. Click any item to spotlight in 3D/2D geometry.
          </p>
        </div>

        {/* Dynamic Metric Tiles */}
        <div className="flex items-center space-x-2 text-xs font-mono">
          <div className="bg-[#0a121e] px-3 py-1.5 rounded-lg border border-rose-800/60 flex items-center space-x-2">
            <AlertCircle size={14} className="text-rose-400" />
            <div>
              <span className="text-[9px] text-gray-400 uppercase font-semibold block">Blocked QTO</span>
              <span className="text-xs font-bold text-rose-300">{counts.blocked}</span>
            </div>
          </div>

          <div className="bg-[#0a121e] px-3 py-1.5 rounded-lg border border-amber-800/60 flex items-center space-x-2">
            <AlertTriangle size={14} className="text-amber-400" />
            <div>
              <span className="text-[9px] text-gray-400 uppercase font-semibold block">Review Required</span>
              <span className="text-xs font-bold text-amber-300">{counts.reviewRequired}</span>
            </div>
          </div>

          <div className="bg-[#0a121e] px-3 py-1.5 rounded-lg border border-sky-800/60 flex items-center space-x-2">
            <Info size={14} className="text-sky-400" />
            <div>
              <span className="text-[9px] text-gray-400 uppercase font-semibold block">Assumptions</span>
              <span className="text-xs font-bold text-sky-300">{counts.assumptions}</span>
            </div>
          </div>
        </div>
      </div>

      {/* ===================================================================== */}
      {/* 2. FILTER & SEARCH CONTROL BAR                                        */}
      {/* ===================================================================== */}
      <div className="p-2.5 bg-[#0a121e] border border-[#162840] rounded-lg flex items-center justify-between flex-shrink-0 flex-wrap gap-2 text-xs font-mono">
        {/* Severity Filter Pills */}
        <div className="flex items-center space-x-1">
          {(["ALL", "CRITICAL", "WARNING", "INFO"] as ReviewSeverityFilter[]).map((sev) => (
            <button
              key={sev}
              onClick={() => setSeverityFilter(sev)}
              className={`px-2.5 py-1 rounded text-[10px] font-bold transition-all cursor-pointer ${
                severityFilter === sev
                  ? "bg-cyan-600 text-white font-extrabold shadow-sm"
                  : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60"
              }`}
            >
              {sev === "ALL" ? "ALL SEVERITIES" : sev}
            </button>
          ))}
        </div>

        {/* Dropdowns & Search */}
        <div className="flex items-center space-x-2">
          {/* Storey Filter */}
          <select
            value={selectedStorey}
            onChange={(e) => setSelectedStorey(e.target.value)}
            className="bg-[#060b14] text-xs text-gray-300 px-2 py-1 rounded border border-[#162840] outline-none cursor-pointer"
          >
            <option value="ALL">All Storeys</option>
            {uniqueStoreys.map((st) => (
              <option key={st} value={st}>
                {st}
              </option>
            ))}
          </select>

          {/* Issue Category Filter */}
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="bg-[#060b14] text-xs text-gray-300 px-2 py-1 rounded border border-[#162840] outline-none cursor-pointer"
          >
            <option value="ALL">All Issue Categories</option>
            {uniqueCategories.map((cat) => (
              <option key={cat} value={cat}>
                {cat.replace(/_/g, " ")}
              </option>
            ))}
          </select>

          {/* Search Box */}
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-2 text-gray-500" />
            <input
              type="text"
              placeholder="Search GUID, name, reason…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-[#060b14] text-xs text-gray-200 pl-7 pr-2.5 py-1 rounded border border-[#162840] outline-none placeholder:text-gray-600 w-52"
            />
          </div>
        </div>
      </div>

      {/* ===================================================================== */}
      {/* 3. DENSE REVIEW QUEUE TABLE                                           */}
      {/* ===================================================================== */}
      <div className="flex-1 border border-[#162840] rounded-lg overflow-hidden bg-[#0a121e] flex flex-col">
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-[#0e1726] sticky top-0 border-b border-[#162840] text-gray-400 text-[10px] z-10">
              <tr>
                <th className="p-3 text-center">Severity</th>
                <th className="p-3">Gating Status</th>
                <th className="p-3">IFC GUID</th>
                <th className="p-3">Classification / Element</th>
                <th className="p-3">Storey</th>
                <th className="p-3">Issue Category</th>
                <th className="p-3">Reason / Description</th>
                <th className="p-3">Affected Quantity</th>
                <th className="p-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#162840]/60 font-mono text-[11px]">
              {filteredItems.length > 0 ? (
                filteredItems.map((item) => {
                  const isSelected = item.guid === selectedWallGuid;

                  return (
                    <tr
                      key={item.guid}
                      onClick={() => onSelectGuid(item.guid)}
                      className={`hover:bg-[#162840]/50 transition-colors cursor-pointer ${
                        isSelected
                          ? "bg-cyan-950/70 text-cyan-200 font-bold border-l-2 border-cyan-400"
                          : "text-gray-300"
                      }`}
                    >
                      {/* Severity Chip */}
                      <td className="p-3 text-center">
                        <span
                          className={`px-1.5 py-0.2 rounded text-[9px] font-bold ${
                            item.severity === "CRITICAL"
                              ? "bg-rose-950 text-rose-400 border border-rose-800"
                              : item.severity === "WARNING"
                              ? "bg-amber-950 text-amber-400 border border-amber-800"
                              : "bg-sky-950 text-sky-400 border border-sky-800"
                          }`}
                        >
                          {item.severity}
                        </span>
                      </td>

                      {/* Status */}
                      <td className="p-3">
                        <span
                          className={`px-1.5 py-0.2 rounded text-[9px] font-bold ${
                            item.status === "BLOCKED"
                              ? "bg-rose-950/80 text-rose-400 border border-rose-700"
                              : item.status === "REVIEW_REQUIRED" ||
                                item.status === "UNKNOWN_UNRESOLVED"
                              ? "bg-amber-950/80 text-amber-400 border border-amber-700"
                              : "bg-sky-950/80 text-sky-400 border border-sky-700"
                          }`}
                        >
                          {item.status}
                        </span>
                      </td>

                      {/* IFC GUID with Copy Button */}
                      <td className="p-3 text-cyan-400 font-bold">
                        <div className="flex items-center space-x-1">
                          <span className="truncate max-w-[100px]" title={item.guid}>
                            {item.guid}
                          </span>
                          <button
                            onClick={(e) => handleCopy(item.guid, e)}
                            className="p-0.5 text-gray-500 hover:text-cyan-300 cursor-pointer"
                            title="Copy GUID"
                          >
                            {copiedGuid === item.guid ? (
                              <Check size={10} className="text-emerald-400" />
                            ) : (
                              <Copy size={10} />
                            )}
                          </button>
                        </div>
                      </td>

                      {/* Canonical Classification & Source Name */}
                      <td className="p-3 max-w-[170px]">
                        <div className="font-semibold text-white truncate">
                          {item.canonical_classification}
                        </div>
                        <div className="text-[9px] text-gray-400 truncate" title={item.source_name}>
                          {item.source_name}
                        </div>
                      </td>

                      {/* Storey */}
                      <td className="p-3 text-gray-400">{item.storey}</td>

                      {/* Issue Category */}
                      <td className="p-3">
                        <span className="text-[10px] text-amber-300 font-semibold">
                          {item.issue_category.replace(/_/g, " ")}
                        </span>
                      </td>

                      {/* Description Reason */}
                      <td className="p-3 text-gray-300 max-w-sm leading-relaxed break-words">
                        {item.reason}
                      </td>

                      {/* Affected Quantity */}
                      <td className="p-3 text-gray-300 font-bold">
                        {item.affected_quantity || "—"}
                      </td>

                      {/* Action Spotlight Button */}
                      <td className="p-3 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectGuid(item.guid);
                            onNavigateToTakeoff?.(item.guid);
                          }}
                          className="px-2.5 py-1 rounded bg-[#0284c7] hover:bg-cyan-500 text-white text-[10px] font-bold cursor-pointer inline-flex items-center gap-1"
                        >
                          <Crosshair size={10} />
                          <span>Spotlight</span>
                        </button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={9} className="p-8 text-center text-gray-500 font-sans space-y-1">
                    <CheckCircle2 size={24} className="mx-auto mb-2 text-emerald-400 opacity-60" />
                    <p className="font-semibold text-gray-300">
                      No review items match the active filters
                    </p>
                    <p className="text-xs text-gray-500">
                      All elements meet the selected criteria.
                    </p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
