import React, { useState, useMemo } from "react";
import {
  Table,
  Filter,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  FileSpreadsheet,
  AlertTriangle,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  Layers,
  Box,
} from "lucide-react";
import { formatWallDisplay } from "./BIMModelTree";
import { ProvenanceBadge } from "./BIMInspector";
import { toast } from "sonner";

export interface BIMBOQScheduleProps {
  walls: any[];
  lineItemByGuid: Record<string, any>;
  takeoff: any;
  selectedWallGuid: string | null;
  onSelectGuid: (guid: string) => void;
  wasteFactor: number;
  onWasteFactorChange: (waste: number) => void;
  onExportExcel?: () => void;
  exporting?: boolean;
  trade?: "drywall" | "flooring" | "roofing";
  flooringElements?: any[];
  roofs?: any[];
}

export type BOQFilterType =
  | "ALL"
  | "ELIGIBLE"
  | "REVIEW_REQUIRED"
  | "BLOCKED"
  | "SUPERSEDED"
  | "SINGLE_FACE"
  | "DOUBLE_FACE"
  | "VERIFIED"
  | "DERIVED"
  | "ASSUMED";

export type BOQSortField =
  | "ifc_guid"
  | "storey"
  | "classification"
  | "length_ft"
  | "height_ft"
  | "face_area"
  | "net_board_sqft"
  | "sheets_4x8"
  | "material"
  | "gross_sqft"
  | "net_sqft"
  | "status";

export default function BIMBOQSchedule({
  walls,
  lineItemByGuid,
  takeoff,
  selectedWallGuid,
  onSelectGuid,
  wasteFactor,
  onWasteFactorChange,
  onExportExcel,
  exporting = false,
  trade = "drywall",
  flooringElements = [],
  roofs = [],
}: BIMBOQScheduleProps) {
  const [filter, setFilter] = useState<BOQFilterType>("ALL");
  const [sortField, setSortField] = useState<BOQSortField>("storey");
  const [sortAsc, setSortAsc] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [copiedGuid, setCopiedGuid] = useState<string | null>(null);

  // Additional local filters for Flooring / Roofing BOQ
  const [selectedStoreyFilter, setSelectedStoreyFilter] = useState<string>("ALL");
  const [selectedMaterialFilter, setSelectedMaterialFilter] = useState<string>("ALL");

  const handleCopy = (guid: string, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard?.writeText(guid);
    setCopiedGuid(guid);
    toast.success(`Copied GUID: ${guid}`);
    setTimeout(() => setCopiedGuid(null), 1500);
  };

  const handleSort = (field: BOQSortField) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
    }
  };

  // Distinct storeys and materials for quick filters
  const distinctStoreys = useMemo(() => {
    const s = new Set<string>();
    if (trade === "roofing") {
      roofs.forEach((r) => {
        if (r.storey_name) s.add(r.storey_name);
      });
    } else {
      flooringElements.forEach((f) => {
        if (f.storey_name) s.add(f.storey_name);
      });
    }
    return Array.from(s);
  }, [flooringElements, roofs, trade]);

  const distinctMaterials = useMemo(() => {
    const m = new Set<string>();
    if (trade === "roofing") {
      roofs.forEach((r) => {
        if (r.primary_material) m.add(r.primary_material);
      });
    } else {
      flooringElements.forEach((f) => {
        if (f.flooring_category) m.add(f.flooring_category);
      });
    }
    return Array.from(m);
  }, [flooringElements, roofs, trade]);

  // 1. Filter Displayed BOQ Items
  const displayedItems = useMemo(() => {
    if (trade === "roofing") {
      const items = roofs.length > 0 ? roofs : (takeoff?.line_items || []);
      return items.filter((rf: any) => {
        let matchFilter = true;
        const elig = rf.qto_eligibility || rf.status || "ELIGIBLE";
        const prov = rf.slope_provenance || rf.area_provenance || rf.provenance?.geometry_provenance || "DERIVED_GEOMETRIC";

        if (filter === "ELIGIBLE") matchFilter = elig === "ELIGIBLE";
        else if (filter === "REVIEW_REQUIRED") matchFilter = elig === "REVIEW_REQUIRED";
        else if (filter === "BLOCKED") matchFilter = elig.startsWith("INELIGIBLE") || elig === "BLOCKED";
        else if (filter === "VERIFIED") matchFilter = prov === "VERIFIED_EXPLICIT";
        else if (filter === "DERIVED") matchFilter = prov === "DERIVED_GEOMETRIC";

        // Storey Filter
        if (selectedStoreyFilter !== "ALL" && rf.storey_name !== selectedStoreyFilter) {
          return false;
        }

        // Material Filter
        if (selectedMaterialFilter !== "ALL" && rf.primary_material !== selectedMaterialFilter) {
          return false;
        }

        const matchSearch =
          searchQuery === "" ||
          (rf.name || rf.description || "")?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (rf.ifc_guid || rf.source_guid || rf.id || "")?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (rf.primary_material || "")?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (rf.roof_type || "")?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (rf.storey_name || "")?.toLowerCase().includes(searchQuery.toLowerCase());

        return matchFilter && matchSearch;
      });
    }

    if (trade === "flooring") {
      const items = flooringElements.length > 0 ? flooringElements : (takeoff?.line_items || []);
      return items.filter((f: any) => {
        let matchFilter = true;
        const elig = f.qto_eligibility || f.status || "ELIGIBLE";
        const prov = f.provenance_status || f.provenance?.status || "DERIVED_GEOMETRIC";

        if (filter === "ELIGIBLE") matchFilter = elig === "ELIGIBLE";
        else if (filter === "REVIEW_REQUIRED") matchFilter = elig === "REVIEW_REQUIRED";
        else if (filter === "SUPERSEDED") matchFilter = elig === "SUPERSEDED_BY_PHYSICAL_ELEMENT";
        else if (filter === "BLOCKED") matchFilter = elig.startsWith("INELIGIBLE") || elig === "BLOCKED";
        else if (filter === "VERIFIED") matchFilter = prov === "VERIFIED_EXPLICIT";
        else if (filter === "DERIVED") matchFilter = prov === "DERIVED_GEOMETRIC";

        // Storey Filter
        if (selectedStoreyFilter !== "ALL" && f.storey_name !== selectedStoreyFilter) {
          return false;
        }

        // Material Filter
        if (selectedMaterialFilter !== "ALL" && f.flooring_category !== selectedMaterialFilter) {
          return false;
        }

        const matchSearch =
          searchQuery === "" ||
          (f.source_name || f.description || "")?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (f.ifc_guid || f.source_guid || "")?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (f.finish_material_name || f.trade_category || "")?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (f.storey_name || "")?.toLowerCase().includes(searchQuery.toLowerCase());

        return matchFilter && matchSearch;
      });
    }

    return walls.filter((w: any) => {
      // Scope/Status Filter
      let matchFilter = true;
      if (filter === "ELIGIBLE") matchFilter = w.qto_eligibility === "ELIGIBLE";
      else if (filter === "REVIEW_REQUIRED") matchFilter = w.qto_eligibility === "REVIEW_REQUIRED";
      else if (filter === "BLOCKED") matchFilter = w.qto_eligibility?.startsWith("INELIGIBLE");
      else if (filter === "SINGLE_FACE") matchFilter = w.drywall_side_a_scope && !w.drywall_side_b_scope;
      else if (filter === "DOUBLE_FACE") matchFilter = w.drywall_side_a_scope && w.drywall_side_b_scope;
      else if (filter === "VERIFIED") {
        matchFilter =
          w.assembly?.assembly_provenance === "VERIFIED_EXPLICIT" ||
          w.length_provenance === "VERIFIED_EXPLICIT";
      } else if (filter === "DERIVED") {
        matchFilter = w.length_provenance === "DERIVED_GEOMETRIC";
      } else if (filter === "ASSUMED") {
        matchFilter = w.assembly?.assembly_provenance === "CONFIGURED_ASSUMPTION";
      }

      // Search Filter
      const matchSearch =
        searchQuery === "" ||
        w.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        w.ifc_guid?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        w.wall_classification?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        w.storey_name?.toLowerCase().includes(searchQuery.toLowerCase());

      return matchFilter && matchSearch;
    });
  }, [walls, flooringElements, roofs, takeoff, trade, filter, searchQuery, selectedStoreyFilter, selectedMaterialFilter]);

  // 2. Sort Displayed Items
  const sortedItems = useMemo(() => {
    const list = [...displayedItems];
    list.sort((a: any, b: any) => {
      if (trade === "roofing") {
        const guidA = a.ifc_guid || a.source_guid || a.id || "";
        const guidB = b.ifc_guid || b.source_guid || b.id || "";
        let valA: any = "";
        let valB: any = "";

        switch (sortField) {
          case "ifc_guid":
            valA = guidA;
            valB = guidB;
            break;
          case "storey":
            valA = a.storey_name || "";
            valB = b.storey_name || "";
            break;
          case "material":
          case "classification":
            valA = a.primary_material || "";
            valB = b.primary_material || "";
            break;
          case "gross_sqft":
            valA = Number(a.plan_area_sqft || 0);
            valB = Number(b.plan_area_sqft || 0);
            break;
          case "net_sqft":
          case "net_board_sqft":
            valA = Number(a.true_surface_area_sqft || a.quantity || 0);
            valB = Number(b.true_surface_area_sqft || b.quantity || 0);
            break;
          case "status":
            valA = a.qto_eligibility || a.status || "";
            valB = b.qto_eligibility || b.status || "";
            break;
          default:
            valA = a.storey_name || "";
            valB = b.storey_name || "";
            break;
        }

        if (typeof valA === "string") {
          return sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }
        return sortAsc ? valA - valB : valB - valA;
      }

      if (trade === "flooring") {
        const guidA = a.ifc_guid || a.source_guid || a.id || "";
        const guidB = b.ifc_guid || b.source_guid || b.id || "";
        let valA: any = "";
        let valB: any = "";

        switch (sortField) {
          case "ifc_guid":
            valA = guidA;
            valB = guidB;
            break;
          case "storey":
            valA = a.storey_name || "";
            valB = b.storey_name || "";
            break;
          case "material":
          case "classification":
            valA = a.finish_material_name || a.flooring_category || "";
            valB = b.finish_material_name || b.flooring_category || "";
            break;
          case "gross_sqft":
            valA = Number(a.gross_area_sqft || 0);
            valB = Number(b.gross_area_sqft || 0);
            break;
          case "net_sqft":
          case "net_board_sqft":
            valA = Number(a.net_area_sqft || a.quantity || 0);
            valB = Number(b.net_area_sqft || b.quantity || 0);
            break;
          case "status":
            valA = a.qto_eligibility || a.status || "";
            valB = b.qto_eligibility || b.status || "";
            break;
          default:
            valA = a.storey_name || "";
            valB = b.storey_name || "";
            break;
        }

        if (typeof valA === "string") {
          return sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }
        return sortAsc ? valA - valB : valB - valA;
      }

      const lineA = lineItemByGuid[a.ifc_guid];
      const lineB = lineItemByGuid[b.ifc_guid];

      let valA: any = "";
      let valB: any = "";

      switch (sortField) {
        case "ifc_guid":
          valA = a.ifc_guid;
          valB = b.ifc_guid;
          break;
        case "storey":
          valA = a.storey_name || "";
          valB = b.storey_name || "";
          break;
        case "classification":
          valA = formatWallDisplay(a).primaryLabel;
          valB = formatWallDisplay(b).primaryLabel;
          break;
        case "length_ft":
          valA = Number(lineA?.provenance?.length_ft ?? a.length_ft ?? 0);
          valB = Number(lineB?.provenance?.length_ft ?? b.length_ft ?? 0);
          break;
        case "height_ft":
          valA = Number(lineA?.provenance?.finish_height_ft ?? a.drywall_finish_height_ft ?? 10);
          valB = Number(lineB?.provenance?.finish_height_ft ?? b.drywall_finish_height_ft ?? 10);
          break;
        case "face_area": {
          const lA = Number(lineA?.provenance?.length_ft ?? a.length_ft ?? 0);
          const hA = Number(lineA?.provenance?.finish_height_ft ?? a.drywall_finish_height_ft ?? 10);
          const lB = Number(lineB?.provenance?.length_ft ?? b.length_ft ?? 0);
          const hB = Number(lineB?.provenance?.finish_height_ft ?? b.drywall_finish_height_ft ?? 10);
          valA = lA * hA;
          valB = lB * hB;
          break;
        }
        case "net_board_sqft":
          valA = Number(lineA?.provenance?.net_drywall_sqft ?? 0);
          valB = Number(lineB?.provenance?.net_drywall_sqft ?? 0);
          break;
        case "sheets_4x8": {
          const netA = Number(lineA?.provenance?.net_drywall_sqft ?? 0);
          const netB = Number(lineB?.provenance?.net_drywall_sqft ?? 0);
          valA = Math.ceil((netA * (1 + wasteFactor / 100)) / 32);
          valB = Math.ceil((netB * (1 + wasteFactor / 100)) / 32);
          break;
        }
        case "status":
          valA = a.qto_eligibility || "";
          valB = b.qto_eligibility || "";
          break;
        default:
          valA = a.storey_name || "";
          valB = b.storey_name || "";
          break;
      }

      if (typeof valA === "string") {
        return sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }
      return sortAsc ? valA - valB : valB - valA;
    });
    return list;
  }, [displayedItems, trade, sortField, sortAsc, lineItemByGuid, wasteFactor]);

  // 3. Totals and Material Breakdown
  const totals = useMemo(() => {
    if (trade === "roofing") {
      let sumTrueSqft = 0;
      let sumPlanSqft = 0;
      let countEligible = 0;
      let countReview = 0;
      let countExcluded = 0;

      const matMap: Record<string, number> = {};

      sortedItems.forEach((r: any) => {
        const elig = r.qto_eligibility || r.status || "ELIGIBLE";
        const trueSqft = Number(r.true_surface_area_sqft || r.quantity || r.plan_area_sqft || 0);
        const planSqft = Number(
          r.plan_area_sqft ||
            (r.true_surface_area_sqft ? r.true_surface_area_sqft / (r.pitch_multiplier || 1.0) : 0)
        );

        if (elig === "ELIGIBLE") {
          sumTrueSqft += trueSqft;
          sumPlanSqft += planSqft;
          countEligible++;

          const mat = r.primary_material || "UNASSIGNED";
          matMap[mat] = (matMap[mat] || 0) + trueSqft;
        } else if (elig.startsWith("INELIGIBLE") || elig === "BLOCKED") {
          countExcluded++;
        } else {
          countReview++;
        }
      });

      const materialBreakdown = Object.entries(matMap)
        .map(([category, sqft]) => ({
          category,
          sqft,
          percentage: sumTrueSqft > 0 ? (sqft / sumTrueSqft) * 100 : 0,
        }))
        .sort((a, b) => b.sqft - a.sqft);

      return {
        totalTrueSqft: sumTrueSqft,
        totalPlanSqft: sumPlanSqft,
        countEligible,
        countReview,
        countExcluded,
        materialBreakdown,
        totalItems: sortedItems.length,
      };
    }

    if (trade === "flooring") {
      let sumGrossSqft = 0;
      let sumVoidDeductions = 0;
      let sumNetSqft = 0;
      let countEligible = 0;
      let countReview = 0;
      let countSuperseded = 0;
      let countExcluded = 0;

      const matMap: Record<string, number> = {};

      sortedItems.forEach((f: any) => {
        const elig = f.qto_eligibility || f.status || "ELIGIBLE";
        const gross = Number(f.gross_area_sqft || f.quantity || 0);
        const voidDed = Number(f.void_deductions_sqft || 0);
        const net = Number(f.net_area_sqft || f.quantity || Math.max(0, gross - voidDed));

        if (elig === "ELIGIBLE") {
          sumGrossSqft += gross;
          sumVoidDeductions += voidDed;
          sumNetSqft += net;
          countEligible++;

          const cat = f.flooring_category || "OTHER";
          matMap[cat] = (matMap[cat] || 0) + net;
        } else if (elig === "SUPERSEDED_BY_PHYSICAL_ELEMENT") {
          countSuperseded++;
        } else if (elig.startsWith("INELIGIBLE") || elig === "BLOCKED") {
          countExcluded++;
        } else {
          countReview++;
        }
      });

      const materialBreakdown = Object.entries(matMap)
        .map(([category, sqft]) => ({
          category,
          sqft,
          percentage: sumNetSqft > 0 ? (sqft / sumNetSqft) * 100 : 0,
        }))
        .sort((a, b) => b.sqft - a.sqft);

      return {
        totalGrossSqft: sumGrossSqft,
        totalVoidDeductions: sumVoidDeductions,
        totalNetSqft: sumNetSqft,
        countEligible,
        countReview,
        countSuperseded,
        countExcluded,
        materialBreakdown,
        totalItems: sortedItems.length,
      };
    }

    let sumFaceArea = 0;
    let sumGrossBoard = 0;
    let sumDeductions = 0;
    let sumNetBoard = 0;
    let sumSheets = 0;
    let sumLengthFt = 0;
    let countEligible = 0;
    let countReview = 0;

    sortedItems.forEach((w: any) => {
      const line = lineItemByGuid[w.ifc_guid];
      const l = Number(line?.provenance?.length_ft ?? w.length_ft ?? 0);
      const h = Number(line?.provenance?.finish_height_ft ?? w.drywall_finish_height_ft ?? 10);
      const face = l * h;
      const sideA = w.drywall_side_a_scope ? (w.assembly?.side_a_layers ?? 1) : 0;
      const sideB = w.drywall_side_b_scope ? (w.assembly?.side_b_layers ?? 1) : 0;
      const layers = sideA + sideB;
      const gross = face * layers;
      const opSingle = Number(
        line?.provenance?.openings_deduction_sqft ??
          w.openings?.reduce((sum: number, op: any) => sum + (op.area_sqft || 0), 0) ??
          0
      );
      const ded = opSingle * layers;
      const net = Number(line?.provenance?.net_drywall_sqft ?? Math.max(0, gross - ded));
      const sheets = Math.ceil((net * (1 + wasteFactor / 100)) / 32);

      sumLengthFt += l;
      sumFaceArea += face;
      sumGrossBoard += gross;
      sumDeductions += ded;
      sumNetBoard += net;
      sumSheets += sheets;

      if (w.qto_eligibility === "ELIGIBLE") countEligible++;
      else countReview++;
    });

    return {
      totalLengthFt: sumLengthFt,
      totalFaceAreaSqft: sumFaceArea,
      totalGrossBoardSqft: sumGrossBoard,
      totalDeductionsSqft: sumDeductions,
      totalNetBoardSqft: sumNetBoard,
      totalSheets4x8: sumSheets,
      countEligible,
      countReview,
      materialBreakdown: [],
      totalItems: sortedItems.length,
    };
  }, [sortedItems, trade, lineItemByGuid, wasteFactor]);

  const renderSortHeader = (label: string, field: BOQSortField, align: "left" | "right" | "center" = "left") => {
    const isActive = sortField === field;
    return (
      <th
        onClick={() => handleSort(field)}
        className={`p-2.5 cursor-pointer select-none hover:text-white transition-colors uppercase tracking-wider font-sans text-[9px] font-bold ${
          align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left"
        }`}
      >
        <div
          className={`inline-flex items-center gap-1 ${
            align === "right" ? "justify-end" : align === "center" ? "justify-center" : "justify-start"
          }`}
        >
          <span>{label}</span>
          {isActive ? (
            sortAsc ? (
              <ArrowUp size={10} className="text-cyan-400" />
            ) : (
              <ArrowDown size={10} className="text-cyan-400" />
            )
          ) : (
            <ArrowUpDown size={9} className="text-gray-600 opacity-60" />
          )}
        </div>
      </th>
    );
  };

  return (
    <section className="h-full flex flex-col bg-[#0a121e] text-gray-200 border-t border-[#162840] overflow-hidden font-mono">
      {/* ===================================================================== */}
      {/* 1. SCHEDULE TOOLBAR & SCOPE FILTERS                                   */}
      {/* ===================================================================== */}
      <div className="p-2 border-b border-[#162840] bg-[#080e18] flex items-center justify-between flex-shrink-0 flex-wrap gap-2">
        {/* Left: Trade & Scope Filter Pills */}
        <div className="flex items-center space-x-3 flex-wrap gap-y-1">
          <div className="flex items-center space-x-1.5">
            <Table size={13} className="text-cyan-400" />
            <span className="text-xs font-bold uppercase tracking-wider text-white font-sans">
              {trade === "roofing"
                ? "Roofing Surface QTO Schedule"
                : trade === "flooring"
                ? "Flooring Surface BOQ"
                : "Drywall BOQ Schedule"}
            </span>
            <span className="text-[10px] bg-cyan-950/80 text-cyan-300 px-1.5 py-0.2 rounded border border-cyan-800 font-bold">
              {sortedItems.length}
            </span>
          </div>

          <div className="flex items-center space-x-1">
            {(trade === "roofing"
              ? [
                  { key: "ALL", label: "ALL" },
                  { key: "ELIGIBLE", label: "INCLUDED" },
                  { key: "REVIEW_REQUIRED", label: "REVIEW" },
                  { key: "BLOCKED", label: "EXCLUDED" },
                ]
              : trade === "flooring"
              ? [
                  { key: "ALL", label: "ALL" },
                  { key: "ELIGIBLE", label: "INCLUDED" },
                  { key: "REVIEW_REQUIRED", label: "REVIEW" },
                  { key: "SUPERSEDED", label: "SUPERSEDED" },
                  { key: "BLOCKED", label: "EXCLUDED" },
                ]
              : [
                  { key: "ALL", label: "ALL" },
                  { key: "ELIGIBLE", label: "ELIGIBLE" },
                  { key: "REVIEW_REQUIRED", label: "REVIEW" },
                  { key: "BLOCKED", label: "BLOCKED" },
                  { key: "SINGLE_FACE", label: "1-FACE" },
                  { key: "DOUBLE_FACE", label: "2-FACE" },
                ]
            ).map((flt) => (
              <button
                key={flt.key}
                onClick={() => setFilter(flt.key as BOQFilterType)}
                className={`px-2 py-0.5 rounded text-[10px] font-bold transition-all cursor-pointer font-sans ${
                  filter === flt.key
                    ? "bg-cyan-600 text-white font-black shadow-sm"
                    : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/60 bg-[#060b14] border border-[#162840]"
                }`}
              >
                {flt.label}
              </button>
            ))}
          </div>

          {/* Additional Flooring / Roofing Dropdown Filters */}
          {(trade === "flooring" || trade === "roofing") && (
            <div className="flex items-center space-x-1.5 text-[10px]">
              {/* Storey Filter */}
              <select
                value={selectedStoreyFilter}
                onChange={(e) => setSelectedStoreyFilter(e.target.value)}
                className="bg-[#060b14] border border-[#162840] rounded px-2 py-0.5 text-gray-300 outline-none cursor-pointer"
              >
                <option value="ALL">All Levels</option>
                {distinctStoreys.map((st) => (
                  <option key={st} value={st}>
                    {st}
                  </option>
                ))}
              </select>

              {/* Material Filter */}
              <select
                value={selectedMaterialFilter}
                onChange={(e) => setSelectedMaterialFilter(e.target.value)}
                className="bg-[#060b14] border border-[#162840] rounded px-2 py-0.5 text-gray-300 outline-none cursor-pointer"
              >
                <option value="ALL">All Materials</option>
                {distinctMaterials.map((mat) => (
                  <option key={mat} value={mat}>
                    {mat.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Right: Quick Search & Export */}
        <div className="flex items-center space-x-2 text-xs">
          {/* Search Box */}
          <input
            type="text"
            placeholder={
              trade === "roofing"
                ? "Search roof / assembly / GUID…"
                : trade === "flooring"
                ? "Search floor / room / GUID…"
                : "Search element / room / GUID…"
            }
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-[#060b14] border border-[#162840] px-2 py-0.5 rounded text-xs text-gray-200 placeholder-gray-500 outline-none w-48 font-mono"
          />

          {/* Export BOQ Button */}
          {onExportExcel && (
            <button
              onClick={onExportExcel}
              disabled={exporting}
              className="flex items-center space-x-1 px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-bold transition-all disabled:opacity-50 cursor-pointer shadow-sm"
              title="Export schedule to Excel (.xlsx)"
            >
              <FileSpreadsheet size={12} />
              <span>{exporting ? "Exporting…" : "Export"}</span>
            </button>
          )}
        </div>
      </div>

      {/* ===================================================================== */}
      {/* 2. DENSE SCHEDULE TABLE                                               */}
      {/* ===================================================================== */}
      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-[#0e1726] sticky top-0 border-b border-[#162840] text-gray-400 z-10">
            {trade === "roofing" ? (
              <tr>
                {renderSortHeader("Element / Assembly", "ifc_guid")}
                {renderSortHeader("Storey", "storey")}
                <th className="p-2.5 text-left uppercase tracking-wider font-sans text-[9px] font-bold">Roof Type</th>
                {renderSortHeader("Primary Material", "material")}
                {renderSortHeader("Plan Area (SF)", "gross_sqft", "right")}
                {renderSortHeader("True Surface (SF)", "net_sqft", "right")}
                <th className="p-2.5 text-right uppercase tracking-wider font-sans text-[9px] font-bold">Slope (°)</th>
                <th className="p-2.5 text-center uppercase tracking-wider font-sans text-[9px] font-bold">Pitch</th>
                <th className="p-2.5 text-center uppercase tracking-wider font-sans text-[9px] font-bold">Unit</th>
                {renderSortHeader("Status", "status", "center")}
                <th className="p-2.5 text-center uppercase tracking-wider font-sans text-[9px] font-bold">Provenance</th>
              </tr>
            ) : trade === "flooring" ? (
              <tr>
                {renderSortHeader("Element", "ifc_guid")}
                {renderSortHeader("Storey", "storey")}
                <th className="p-2.5 text-left uppercase tracking-wider font-sans text-[9px] font-bold">Room / Space</th>
                {renderSortHeader("Finish Material", "material")}
                <th className="p-2.5 text-left uppercase tracking-wider font-sans text-[9px] font-bold">Category</th>
                {renderSortHeader("Gross (SF)", "gross_sqft", "right")}
                <th className="p-2.5 text-right uppercase tracking-wider font-sans text-[9px] font-bold">Void Ded.</th>
                {renderSortHeader("Net Area", "net_sqft", "right")}
                <th className="p-2.5 text-center uppercase tracking-wider font-sans text-[9px] font-bold">Unit</th>
                {renderSortHeader("Status", "status", "center")}
              </tr>
            ) : (
              <tr>
                {renderSortHeader("IFC GUID", "ifc_guid")}
                {renderSortHeader("Storey", "storey")}
                {renderSortHeader("Wall Classification", "classification")}
                {renderSortHeader("Length (ft)", "length_ft", "right")}
                {renderSortHeader("Finish Ht", "height_ft", "right")}
                <th className="p-2 text-center">Faces</th>
                {renderSortHeader("Face Area", "face_area", "right")}
                <th className="p-2 text-right">Gross Board</th>
                <th className="p-2 text-right">Deductions</th>
                {renderSortHeader("Net Board Eq.", "net_board_sqft", "right")}
                {renderSortHeader("4×8 Sheets", "sheets_4x8", "right")}
                {renderSortHeader("Status", "status", "center")}
                <th className="p-2 text-center">Provenance</th>
              </tr>
            )}
          </thead>

          <tbody className="divide-y divide-[#162840]/40 text-[11px]">
            {sortedItems.length > 0 ? (
              sortedItems.map((item: any, itemIdx: number) => {
                const guid = item.ifc_guid || item.source_guid || item.id;
                const isSelected = guid === selectedWallGuid;

                if (trade === "roofing") {
                  const trueSqft = Number(item.true_surface_area_sqft || item.quantity || item.plan_area_sqft || 0);
                  const planSqft = Number(item.plan_area_sqft || (item.true_surface_area_sqft ? item.true_surface_area_sqft / (item.pitch_multiplier || 1.0) : 0));
                  const slopeDeg = item.slope_degrees !== null && item.slope_degrees !== undefined ? Number(item.slope_degrees) : (item.provenance?.slope_degrees ?? null);
                  const pitchStr = item.pitch_ratio || item.provenance?.pitch_ratio || (slopeDeg !== null ? `${(Math.tan(slopeDeg * Math.PI / 180) * 12).toFixed(1)}:12` : "N/A");
                  const elig = item.qto_eligibility || item.status || "ELIGIBLE";
                  const isIncluded = elig === "ELIGIBLE";
                  const isReview = elig === "REVIEW_REQUIRED";
                  const matName = item.primary_material || item.provenance?.primary_material || "UNASSIGNED";
                  const roofType = item.roof_type || item.provenance?.roof_type || "ROOF";
                  const provStatus = item.area_provenance || item.provenance?.geometry_provenance || "DERIVED_GEOMETRIC";

                  return (
                    <tr
                      key={guid}
                      onClick={() => onSelectGuid(guid)}
                      className={`hover:bg-[#162840]/50 transition-colors cursor-pointer ${
                        isSelected
                          ? "bg-rose-950/70 text-rose-200 font-bold border-l-2 border-rose-400"
                          : isReview
                          ? "text-amber-300 bg-amber-950/10"
                          : "text-gray-300"
                      }`}
                    >
                      {/* Element Name */}
                      <td className="p-2.5 font-semibold text-white">
                        <div className="flex items-center space-x-1.5">
                          <span className="truncate max-w-[160px] font-sans" title={`IFC GUID: ${guid}`}>
                            {item.name || item.description || `Roof ${String(itemIdx + 1).padStart(2, "0")}`}
                          </span>
                          <button
                            onClick={(e) => handleCopy(guid, e)}
                            className="p-0.5 text-gray-500 hover:text-rose-300 cursor-pointer"
                            title={`Copy IFC GUID: ${guid}`}
                          >
                            {copiedGuid === guid ? <Check size={10} className="text-emerald-400" /> : <Copy size={10} />}
                          </button>
                        </div>
                      </td>

                      {/* Storey */}
                      <td className="p-2.5 text-gray-300 truncate max-w-[90px]">{item.storey_name || "Roof Level"}</td>

                      {/* Roof Type */}
                      <td className="p-2.5 text-rose-300 font-bold text-[10px] uppercase truncate max-w-[90px]">
                        {roofType}
                      </td>

                      {/* Primary Material */}
                      <td className="p-2.5 text-gray-200 font-semibold truncate max-w-[120px]" title={matName}>
                        {matName}
                      </td>

                      {/* Plan Area SF */}
                      <td className="p-2.5 text-right text-gray-400 font-mono">
                        {planSqft.toFixed(1)}
                      </td>

                      {/* True Surface Area SF */}
                      <td className="p-2.5 text-right font-mono">
                        <span className="text-rose-300 font-bold text-xs">{trueSqft.toFixed(1)}</span>
                      </td>

                      {/* Slope */}
                      <td className="p-2.5 text-right font-mono text-emerald-400">
                        {slopeDeg !== null ? `${slopeDeg.toFixed(1)}°` : "—"}
                      </td>

                      {/* Pitch */}
                      <td className="p-2.5 text-center font-mono text-cyan-300 text-[10px]">
                        {pitchStr}
                      </td>

                      {/* Unit */}
                      <td className="p-2.5 text-center text-gray-400 text-[10px] font-sans">SF</td>

                      {/* Status Badge */}
                      <td className="p-2.5 text-center">
                        <span
                          className={`px-2 py-0.5 rounded text-[9px] font-bold font-sans ${
                            isIncluded
                              ? "bg-emerald-950/90 text-emerald-400 border border-emerald-700/60"
                              : isReview
                              ? "bg-amber-950/90 text-amber-400 border border-amber-700/60"
                              : "bg-rose-950/90 text-rose-400 border border-rose-700/60"
                          }`}
                        >
                          {isIncluded ? "✓ ELIGIBLE" : isReview ? "⚠ REVIEW" : "— BLOCKED"}
                        </span>
                      </td>

                      {/* Provenance Badge */}
                      <td className="p-2.5 text-center">
                        <ProvenanceBadge status={provStatus} compact />
                      </td>
                    </tr>
                  );
                }

                if (trade === "flooring") {
                  const gross = Number(item.gross_area_sqft || item.quantity || 0);
                  const voidDed = Number(item.void_deductions_sqft || 0);
                  const net = Number(item.net_area_sqft || item.quantity || Math.max(0, gross - voidDed));
                  const elig = item.qto_eligibility || item.status || "ELIGIBLE";
                  const matName = item.finish_material_name || item.material_name || "Timber Boards";
                  const cat = (item.flooring_category || item.category || "UNASSIGNED_FINISH").replace(/_/g, " ");
                  const isBlocked = elig.startsWith("INELIGIBLE") || elig === "BLOCKED";
                  const isSuperseded = elig === "SUPERSEDED_BY_PHYSICAL_ELEMENT";
                  const isIncluded = elig === "ELIGIBLE";

                  // Clean display name
                  let elementLabel = item.finish_material_name || item.source_name || `Floor ${String(itemIdx + 1).padStart(3, "0")}`;
                  if (elementLabel.includes(":")) {
                    const parts = elementLabel.split(":");
                    elementLabel = parts[parts.length - 1].replace(/^nbl_/, "").replace(/_/g, " ");
                  } else {
                    elementLabel = elementLabel.replace(/^nbl_/, "").replace(/_/g, " ");
                  }

                  const spaceLabel = item.space_name || item.room_id || item.description || "—";

                  return (
                    <tr
                      key={guid}
                      onClick={() => onSelectGuid(guid)}
                      className={`hover:bg-[#162840]/50 transition-colors cursor-pointer ${
                        isSelected
                          ? "bg-cyan-950/70 text-cyan-200 font-bold border-l-2 border-cyan-400"
                          : isBlocked
                          ? "text-gray-500 opacity-70 bg-rose-950/10"
                          : isSuperseded
                          ? "text-gray-400 bg-purple-950/10"
                          : "text-gray-300"
                      }`}
                    >
                      {/* Element Name with GUID hover/copy */}
                      <td className="p-2.5 font-semibold text-white">
                        <div className="flex items-center space-x-1.5">
                          <span className="truncate max-w-[140px] font-sans" title={`IFC GUID: ${guid}`}>
                            {elementLabel}
                          </span>
                          <button
                            onClick={(e) => handleCopy(guid, e)}
                            className="p-0.5 text-gray-500 hover:text-cyan-300 cursor-pointer"
                            title={`Copy IFC GUID: ${guid}`}
                          >
                            {copiedGuid === guid ? (
                              <Check size={10} className="text-emerald-400" />
                            ) : (
                              <Copy size={10} />
                            )}
                          </button>
                        </div>
                      </td>

                      {/* Storey */}
                      <td className="p-2.5 text-gray-300 truncate max-w-[90px]">{item.storey_name || "Level 01"}</td>

                      {/* Room / Space */}
                      <td className="p-2.5 text-gray-300 truncate max-w-[120px]" title={spaceLabel}>
                        {spaceLabel}
                      </td>

                      {/* Finish Material */}
                      <td className="p-2.5 text-gray-200 font-semibold truncate max-w-[140px]" title={matName}>
                        {matName}
                      </td>

                      {/* Category */}
                      <td className="p-2.5 text-amber-300/90 text-[10px] font-bold uppercase truncate max-w-[120px]">
                        {cat}
                      </td>

                      {/* Gross Area */}
                      <td className="p-2.5 text-right text-gray-300 font-mono">
                        {gross.toFixed(1)}
                      </td>

                      {/* Void Deductions */}
                      <td className="p-2.5 text-right font-mono">
                        {voidDed > 0 ? (
                          <span className="text-rose-400">-{voidDed.toFixed(1)}</span>
                        ) : (
                          <span className="text-gray-500">0.0</span>
                        )}
                      </td>

                      {/* Net Floor Area SF */}
                      <td className="p-2.5 text-right font-mono">
                        {isIncluded ? (
                          <span className="text-cyan-300 font-bold">{net.toFixed(1)}</span>
                        ) : isSuperseded ? (
                          <span className="text-purple-400/80 text-[10px]">—</span>
                        ) : (
                          <span className="text-gray-500 text-[10px]">—</span>
                        )}
                      </td>

                      {/* Unit */}
                      <td className="p-2.5 text-center text-gray-400 text-[10px] font-sans">SF</td>

                      {/* Status Badge */}
                      <td className="p-2.5 text-center">
                        <span
                          className={`px-2 py-0.5 rounded text-[9px] font-bold font-sans ${
                            isIncluded
                              ? "bg-emerald-950/90 text-emerald-400 border border-emerald-700/60"
                              : isSuperseded
                              ? "bg-purple-950/90 text-purple-300 border border-purple-700/60"
                              : isBlocked
                              ? "bg-rose-950/90 text-rose-400 border border-rose-700/60"
                              : "bg-amber-950/90 text-amber-400 border border-amber-700/60"
                          }`}
                        >
                          {isIncluded
                            ? "✓ Included"
                            : isSuperseded
                            ? "↗ Superseded"
                            : isBlocked
                            ? "— Excluded"
                            : "⚠ Review"}
                        </span>
                      </td>
                    </tr>
                  );
                }

                // DRYWALL ROW RENDERING (FROZEN PHASE 2)
                const w = item;
                const line = lineItemByGuid[w.ifc_guid];
                const wallMeta = formatWallDisplay(w);

                const l = Number(line?.provenance?.length_ft ?? w.length_ft ?? 0);
                const h = Number(
                  line?.provenance?.finish_height_ft ??
                    w.drywall_finish_height_ft ??
                    w.physical_height_ft ??
                    10
                );
                const face = l * h;
                const sideALayers = w.drywall_side_a_scope ? (w.assembly?.side_a_layers ?? 1) : 0;
                const sideBLayers = w.drywall_side_b_scope ? (w.assembly?.side_b_layers ?? 1) : 0;
                const totalLayers = sideALayers + sideBLayers;
                const grossBoard = face * totalLayers;
                const opSingle = Number(
                  line?.provenance?.openings_deduction_sqft ??
                    w.openings?.reduce((sum: number, op: any) => sum + (op.area_sqft || 0), 0) ??
                    0
                );
                const opDed = opSingle * totalLayers;
                const net = Number(line?.provenance?.net_drywall_sqft ?? Math.max(0, grossBoard - opDed));
                const sheets = Math.ceil((net * (1 + wasteFactor / 100)) / 32);

                const isBlocked =
                  w.qto_eligibility === "INELIGIBLE_NON_DRYWALL" ||
                  w.qto_eligibility === "BLOCKED";
                const isReview =
                  w.qto_eligibility === "REVIEW_REQUIRED" ||
                  wallMeta.status === "UNKNOWN_UNRESOLVED";

                return (
                  <tr
                    key={w.ifc_guid}
                    onClick={() => onSelectGuid(w.ifc_guid)}
                    className={`hover:bg-[#162840]/50 transition-colors cursor-pointer ${
                      isSelected
                        ? "bg-cyan-950/70 text-cyan-200 font-bold border-l-2 border-cyan-400"
                        : "text-gray-300"
                    }`}
                  >
                    {/* GUID with Copy Button */}
                    <td className="p-2 text-cyan-400 font-semibold">
                      <div className="flex items-center space-x-1">
                        <span className="truncate max-w-[110px]" title={w.ifc_guid}>
                          {w.ifc_guid}
                        </span>
                        <button
                          onClick={(e) => handleCopy(w.ifc_guid, e)}
                          className="p-0.5 text-gray-500 hover:text-cyan-300 cursor-pointer"
                          title="Copy GUID"
                        >
                          {copiedGuid === w.ifc_guid ? (
                            <Check size={10} className="text-emerald-400" />
                          ) : (
                            <Copy size={10} />
                          )}
                        </button>
                      </div>
                    </td>

                    {/* Storey */}
                    <td className="p-2 text-gray-400 truncate max-w-[90px]">{w.storey_name}</td>

                    {/* Classification & Raw Source Name */}
                    <td className="p-2 max-w-[190px]">
                      <div className="font-semibold text-white truncate">{wallMeta.primaryLabel}</div>
                      <div className="text-[9px] text-gray-400 font-mono truncate" title={w.name}>
                        {w.name}
                      </div>
                    </td>

                    {/* Physical Length */}
                    <td className="p-2 text-right">{l.toFixed(2)}</td>

                    {/* Finish Height */}
                    <td className="p-2 text-right">{h.toFixed(1)}</td>

                    {/* Active Faces / Layers */}
                    <td className="p-2 text-center text-[10px]">
                      {w.drywall_side_a_scope && w.drywall_side_b_scope
                        ? `A(${sideALayers}L)+B(${sideBLayers}L)`
                        : w.drywall_side_a_scope
                        ? `A(${sideALayers}L)`
                        : "Excluded"}
                    </td>

                    {/* Gross Face Area */}
                    <td className="p-2 text-right">{face.toFixed(1)}</td>

                    {/* Gross Board Area */}
                    <td className="p-2 text-right">{grossBoard.toFixed(1)}</td>

                    {/* Deductions */}
                    <td className="p-2 text-right text-rose-400">
                      {opDed > 0 ? `-${opDed.toFixed(1)}` : "0.0"}
                    </td>

                    {/* Net Board Equivalent */}
                    <td className="p-2 text-right text-cyan-300 font-bold">
                      {isBlocked ? (
                        <span className="text-gray-500 font-normal">N/A</span>
                      ) : (
                        `${net.toFixed(1)} SF`
                      )}
                    </td>

                    {/* 4x8 Sheets */}
                    <td className="p-2 text-right text-amber-300">
                      {isBlocked ? <span className="text-gray-500">—</span> : `${sheets} EA`}
                    </td>

                    {/* Status */}
                    <td className="p-2 text-center">
                      <span
                        className={`px-1.5 py-0.2 rounded text-[9px] font-bold ${
                          isBlocked
                            ? "bg-rose-950 text-rose-400 border border-rose-800"
                            : isReview
                            ? "bg-amber-950 text-amber-400 border border-amber-800"
                            : "bg-emerald-950 text-emerald-400 border border-emerald-800"
                        }`}
                      >
                        {w.qto_eligibility || "ELIGIBLE"}
                      </span>
                    </td>

                    {/* Provenance Badge */}
                    <td className="p-2 text-center">
                      <ProvenanceBadge
                        status={
                          line?.provenance?.status ||
                          w.assembly?.assembly_provenance ||
                          w.length_provenance ||
                          "DERIVED_GEOMETRIC"
                        }
                        compact
                      />
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={13} className="p-8 text-center text-gray-500 font-sans space-y-1">
                  <Box size={24} className="mx-auto mb-2 opacity-40" />
                  <p className="font-semibold text-gray-400">No BOQ line items match the current filter</p>
                  <p className="text-xs text-gray-600">
                    Try switching filter options or clearing search terms.
                  </p>
                </td>
              </tr>
            )}
          </tbody>

          {/* =================================================================== */}
          {/* 3. TABLE FOOTER TOTALS (DRYWALL ONLY)                                */}
          {/* =================================================================== */}
          {trade === "drywall" && sortedItems.length > 0 && (
            <tfoot className="bg-[#0e1726] sticky bottom-0 border-t-2 border-[#162840] font-bold text-gray-200 text-[11px] z-10">
              <tr>
                <td className="p-2 text-cyan-400">TOTALS ({totals.totalItems})</td>
                <td className="p-2"></td>
                <td className="p-2 text-gray-400">
                  {totals.countEligible} Eligible · {totals.countReview} Review
                </td>
                <td className="p-2 text-right">{((totals as any).totalLengthFt || 0).toFixed(1)} LF</td>
                <td className="p-2"></td>
                <td className="p-2 text-center">—</td>
                <td className="p-2 text-right">{((totals as any).totalFaceAreaSqft || 0).toFixed(1)} SF</td>
                <td className="p-2 text-right">{((totals as any).totalGrossBoardSqft || 0).toFixed(1)} SF</td>
                <td className="p-2 text-right text-rose-400">
                  -{((totals as any).totalDeductionsSqft || 0).toFixed(1)} SF
                </td>
                <td className="p-2 text-right text-cyan-300 font-extrabold">
                  {((totals as any).totalNetBoardSqft || 0).toFixed(1)} SF
                </td>
                <td className="p-2 text-right text-amber-300 font-extrabold">
                  {((totals as any).totalSheets4x8 || 0).toLocaleString()} EA
                </td>
                <td className="p-2" colSpan={2}></td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {/* ===================================================================== */}
      {/* 4. PROFESSIONAL ROOFING SUMMARY FOOTER                                */}
      {/* ===================================================================== */}
      {trade === "roofing" && (
        <div className="bg-[#080e18] border-t-2 border-[#162840] px-4 py-2.5 flex items-center justify-between flex-wrap gap-4 text-xs font-sans flex-shrink-0 z-10">
          {/* Left: Included Roofing summary */}
          <div className="flex items-center gap-3">
            <div className="bg-[#060b14] border border-amber-800/70 px-3 py-1.5 rounded shadow-sm">
              <div className="text-[9px] font-bold text-amber-400 uppercase tracking-wider">
                ROOFING SURFACE TAKEOFF SUMMARY
              </div>
              <div className="flex items-baseline gap-2 mt-0.5 font-mono">
                <span className="text-sm font-black text-amber-300">
                  {((totals as any).totalTrueSqft || 0).toLocaleString(undefined, {
                    minimumFractionDigits: 1,
                    maximumFractionDigits: 1,
                  })}{" "}
                  SF
                </span>
                <span className="text-[10px] text-gray-400">
                  · {totals.countEligible} Verified Roof Planes
                </span>
              </div>
            </div>
            {((totals as any).countExcluded > 0 || (totals as any).countReview > 0) && (
              <div className="text-[10px] text-gray-500 font-mono flex items-center gap-2">
                <span>Audit:</span>
                {(totals as any).countReview > 0 && (
                  <span className="text-amber-400">{(totals as any).countReview} Under Review</span>
                )}
                {(totals as any).countExcluded > 0 && (
                  <span className="text-rose-400/80">{(totals as any).countExcluded} Excluded</span>
                )}
              </div>
            )}
          </div>

          {/* Middle: Material Breakdown with Percentages */}
          {((totals as any).materialBreakdown || []).length > 0 && (
            <div className="flex items-center gap-1.5 overflow-x-auto max-w-xl font-mono">
              <span className="text-[9px] font-bold text-gray-500 uppercase flex-shrink-0 font-sans">
                Materials:
              </span>
              {((totals as any).materialBreakdown || []).map((m: any) => (
                <div
                  key={m.category}
                  className="bg-[#060b14] border border-[#162840] px-2 py-0.5 rounded text-gray-300 flex items-center gap-1.5 flex-shrink-0 text-[10px]"
                >
                  <span className="font-bold text-gray-200">{m.category.replace(/_/g, " ")}:</span>
                  <span className="text-amber-300 font-bold">{m.sqft.toFixed(1)} SF</span>
                  <span className="text-gray-500 text-[9px]">({m.percentage.toFixed(1)}%)</span>
                </div>
              ))}
            </div>
          )}

          {/* Right: Net Total Hero */}
          <div className="bg-[#060b14] border border-amber-800/80 px-3.5 py-1.5 rounded flex items-center gap-2.5 shadow-sm font-mono">
            <span className="text-[10px] font-extrabold text-amber-400 uppercase tracking-wider font-sans">
              TRUE SURFACE
            </span>
            <span className="text-base font-black text-amber-300">
              {((totals as any).totalTrueSqft || 0).toLocaleString(undefined, {
                minimumFractionDigits: 1,
                maximumFractionDigits: 1,
              })}{" "}
              <span className="text-xs font-semibold text-amber-400">SF</span>
            </span>
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* 4.5. PROFESSIONAL FLOORING SUMMARY FOOTER                             */}
      {/* ===================================================================== */}
      {trade === "flooring" && (
        <div className="bg-[#080e18] border-t-2 border-[#162840] px-4 py-2.5 flex items-center justify-between flex-wrap gap-4 text-xs font-sans flex-shrink-0 z-10">
          {/* Left: Included Flooring summary */}
          <div className="flex items-center gap-3">
            <div className="bg-[#060b14] border border-cyan-800/70 px-3 py-1.5 rounded shadow-sm">
              <div className="text-[9px] font-bold text-cyan-400 uppercase tracking-wider">
                FLOORING TAKEOFF SUMMARY
              </div>
              <div className="flex items-baseline gap-2 mt-0.5 font-mono">
                <span className="text-sm font-black text-cyan-300">
                  {((totals as any).totalNetSqft || 0).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} SF
                </span>
                <span className="text-[10px] text-gray-400">
                  · {totals.countEligible} Included Elements
                </span>
              </div>
            </div>
            {((totals as any).countExcluded > 0 || (totals as any).countSuperseded > 0) && (
              <div className="text-[10px] text-gray-500 font-mono flex items-center gap-2">
                <span>Audit:</span>
                {(totals as any).countSuperseded > 0 && (
                  <span className="text-purple-400">{(totals as any).countSuperseded} Superseded</span>
                )}
                {(totals as any).countExcluded > 0 && (
                  <span className="text-rose-400/80">{(totals as any).countExcluded} Excluded</span>
                )}
              </div>
            )}
          </div>

          {/* Middle: Material Breakdown with Percentages */}
          {((totals as any).materialBreakdown || []).length > 0 && (
            <div className="flex items-center gap-1.5 overflow-x-auto max-w-xl font-mono">
              <span className="text-[9px] font-bold text-gray-500 uppercase flex-shrink-0 font-sans">
                Breakdown:
              </span>
              {((totals as any).materialBreakdown || []).map((m: any) => (
                <div
                  key={m.category}
                  className="bg-[#060b14] border border-[#162840] px-2 py-0.5 rounded text-gray-300 flex items-center gap-1.5 flex-shrink-0 text-[10px]"
                >
                  <span className="font-bold text-gray-200">{m.category.replace(/_/g, " ")}:</span>
                  <span className="text-amber-300 font-bold">{m.sqft.toFixed(1)} SF</span>
                  <span className="text-gray-500 text-[9px]">({m.percentage.toFixed(1)}%)</span>
                </div>
              ))}
            </div>
          )}

          {/* Right: Net Total Hero */}
          <div className="bg-[#060b14] border border-cyan-800/80 px-3.5 py-1.5 rounded flex items-center gap-2.5 shadow-sm font-mono">
            <span className="text-[10px] font-extrabold text-cyan-400 uppercase tracking-wider font-sans">
              TOTAL
            </span>
            <span className="text-base font-black text-cyan-300">
              {((totals as any).totalNetSqft || 0).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}{" "}
              <span className="text-xs font-semibold text-cyan-400">SF</span>
            </span>
          </div>
        </div>
      )}
    </section>
  );
}
