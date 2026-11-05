import React, { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  Layers,
  Building2,
  FileSpreadsheet,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Search,
  Download,
  UploadCloud,
  Filter,
  Eye,
  EyeOff,
  Info,
  ChevronRight,
  ChevronDown,
  Box,
  DoorOpen,
  Maximize2,
  Minimize2,
  ArrowRight,
  Hash,
  Activity,
  Sparkles,
  Database,
  Grid3X3,
  SlidersHorizontal,
  Table,
  Columns,
  Square,
  Ruler,
  HelpCircle,
  Plus,
  Compass,
  FileDown,
  User,
  Settings,
  ArrowUpDown,
  Edit3,
  ExternalLink,
  Menu,
  Crosshair,
  Check,
  X,
  RefreshCw,
  AlertCircle,
  Tag,
  BarChart3,
  PieChart,
} from "lucide-react";
import { BackendApiService, type IfcTakeoffResponse } from "@/api/backendApi";
import { toast } from "sonner";
import BIM3DCanvasViewer, { CATEGORY_COLORS } from "./BIM3DCanvasViewer";
import BIMModelTree, { formatWallDisplay, CANONICAL_TREE_CATEGORIES } from "./BIMModelTree";
import BIMInspector from "./BIMInspector";
import BIMBOQSchedule from "./BIMBOQSchedule";
import BIMReviewQueue from "./BIMReviewQueue";
import { BIMAuditLog } from "./BIMAuditLog";
export { formatWallDisplay, CANONICAL_TREE_CATEGORIES };

interface BIMTakeoffWorkspaceProps {
  ifcId: string;
  initialTrade?: "drywall" | "flooring" | "roofing";
  initialViewMode?: "3D" | "2D" | "SPLIT";
}

export type WorkspaceNavTab = "MODEL" | "TAKEOFF" | "REVIEW" | "AUDIT" | "REPORTS";

export default function BIMTakeoffWorkspace({
  ifcId,
  initialTrade = "drywall",
  initialViewMode = "3D",
}: BIMTakeoffWorkspaceProps) {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isSwitchingModel, setIsSwitchingModel] = useState(false);

  const [loading, setLoading] = useState(true);
  const [loadingStep, setLoadingStep] = useState("Uploading IFC Model…");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [ifcDoc, setIfcDoc] = useState<any>(null);
  const [canonicalModel, setCanonicalModel] = useState<any>(null);
  const [takeoff, setTakeoff] = useState<IfcTakeoffResponse["qto"] | null>(null);

  // Immutable Trade Context — set once from URL, never switchable within workspace.
  // Each trade workspace is a fully independent surface; no cross-trade navigation.
  const activeTrade: "drywall" | "flooring" | "roofing" = initialTrade;

  // Navigation & View Mode (initialized from route view param)
  const [activeNavTab, setActiveNavTab] = useState<WorkspaceNavTab>("TAKEOFF");
  const [viewMode, setViewMode] = useState<"3D" | "2D" | "SPLIT">(initialViewMode);

  // Single Source of Truth Synchronization State (Decoupled per trade)
  const [selectedWallGuid, setSelectedWallGuid] = useState<string | null>(null);
  const [selectedFlooringGuid, setSelectedFlooringGuid] = useState<string | null>(null);
  const [selectedRoofGuid, setSelectedRoofGuid] = useState<string | null>(null);
  const [selectedStorey, setSelectedStorey] = useState<string>("ALL");
  const [selectedClassification, setSelectedClassification] = useState<string>("ALL");
  const [drywallScopeFilter, setDrywallScopeFilter] = useState<
    "ALL" | "ELIGIBLE" | "REVIEW_REQUIRED" | "BLOCKED" | "SINGLE_FACE" | "DOUBLE_FACE" | "UNKNOWN_ASSEMBLY"
  >("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [exporting, setExporting] = useState(false);

  // Panels & Visibility
  const [bottomDockOpen, setBottomDockOpen] = useState(true);
  const [wasteFactor, setWasteFactor] = useState<number>(10); // 10% (drywall only)
  const [expandedStoreys, setExpandedStoreys] = useState<Record<string, boolean>>({});
  const [expandedSubtrees, setExpandedSubtrees] = useState<Record<string, boolean>>({});
  const [hiddenCategories, setHiddenCategories] = useState<Set<string>>(new Set());
  const [hiddenWallGuids, setHiddenWallGuids] = useState<Set<string>>(new Set());
  const [isolatedWallGuid, setIsolatedWallGuid] = useState<string | null>(null);

  // Active IFC ID Ref to prevent async race conditions:
  // If request A completes late after switching to model B, response A is discarded.
  const activeIfcIdRef = useRef(ifcId);
  useEffect(() => {
    activeIfcIdRef.current = ifcId;
  }, [ifcId]);

  // CRITICAL P0 DATA LIFECYCLE PURGE:
  // Whenever ifcId changes, immediately wipe out all previous model data, selections, and filters.
  useEffect(() => {
    setIfcDoc(null);
    setCanonicalModel(null);
    setTakeoff(null);
    setSelectedWallGuid(null);
    setSelectedFlooringGuid(null);
    setSelectedRoofGuid(null);
    setHiddenWallGuids(new Set());
    setIsolatedWallGuid(null);
    setHiddenCategories(new Set());
    setExpandedStoreys({});
    setExpandedSubtrees({});
    setSearchQuery("");
  }, [ifcId]);

  // Load BIM Data from Backend APIs (Deterministic Single Source of Truth)
  const loadBIMData = useCallback(async () => {
    const targetId = ifcId;
    try {
      setLoading(true);
      setLoadError(null);
      // Clean slate on every load cycle
      setIfcDoc(null);
      setCanonicalModel(null);
      setTakeoff(null);

      // Step 1: Upload / Doc Metadata
      setLoadingStep("1/6 Uploading & Verifying IFC Model…");
      const docRes = await BackendApiService.getIfcDocument(targetId);
      if (activeIfcIdRef.current !== targetId) return; // Stale request guard
      setIfcDoc(docRes);

      // Step 2: Parse IFC (Only if not already parsed and cached)
      if (!docRes.has_canonical_model) {
        setLoadingStep("2/6 Parsing IFC Spatial Graph & Extrusions…");
        await BackendApiService.parseIfc(targetId).catch(() => {
          // Document may already be parsed
        });
        if (activeIfcIdRef.current !== targetId) return; // Stale request guard
      }

      // Step 3: Canonical BIM Model
      setLoadingStep("3/6 Building Canonical BIM Geometry & Topology…");
      const canonicalRes = await BackendApiService.getCanonicalModel(targetId);
      if (activeIfcIdRef.current !== targetId) return; // Stale request guard

      // Step 4 & 5: Preparing 3D and 2D
      setLoadingStep("4/6 Preparing 3D WebGL Meshes & 2D Plan View…");

      // Step 6: QTO Takeoff
      const tradeLabel = activeTrade === "flooring" ? "Flooring" : activeTrade === "roofing" ? "Roofing" : "Drywall";
      setLoadingStep(`5/6 Computing Deterministic ${tradeLabel} QTO Takeoff…`);
      const takeoffRes = await BackendApiService.calculateIfcTakeoff(
        targetId,
        activeTrade === "drywall" ? wasteFactor / 100 : 0.0,
        activeTrade
      );
      if (activeIfcIdRef.current !== targetId) return; // Stale request guard

      // CRITICAL INVARIANT VERIFICATION:
      // uploaded_file_hash == parsed_model.source_hash == canonical_model.source_hash == takeoff.source_hash
      const docHash = docRes.source_hash;
      const canonicalHash = canonicalRes?.source_hash;
      const takeoffHash = takeoffRes?.qto?.source_hash || takeoffRes?.qto?.model_sha256;

      if (docHash && canonicalHash && docHash !== canonicalHash) {
        throw new Error(
          `Data Integrity Invariant Violation: Document source_hash (${docHash.slice(0, 8)}) ` +
          `does not match Canonical Model source_hash (${canonicalHash.slice(0, 8)}). Refusing to render stale model.`
        );
      }
      if (docHash && takeoffHash && docHash !== takeoffHash) {
        throw new Error(
          `Data Integrity Invariant Violation: Document source_hash (${docHash.slice(0, 8)}) ` +
          `does not match Takeoff source_hash (${takeoffHash.slice(0, 8)}). Refusing to render stale model.`
        );
      }

      setCanonicalModel(canonicalRes);
      setTakeoff(takeoffRes.qto);
      setLoadingStep("6/6 Takeoff Workspace Ready");

      // Auto-expand storeys in model tree
      if (canonicalRes?.storeys) {
        const exp: Record<string, boolean> = {};
        const subExp: Record<string, boolean> = {};
        canonicalRes.storeys.forEach((st: any) => {
          exp[st.id] = true;
          subExp[`${st.id}-walls`] = activeTrade === "drywall";
          subExp[`${st.id}-spaces`] = activeTrade === "flooring";
          subExp[`${st.id}-openings`] = false;
          subExp[`${st.id}-roofs`] = activeTrade === "roofing";
        });
        setExpandedStoreys(exp);
        setExpandedSubtrees(subExp);
      }

      // Auto-select first element ONLY for the active trade — no cross-trade selection.
      if (activeTrade === "flooring" && canonicalRes?.flooring_elements?.length > 0) {
        setSelectedFlooringGuid(canonicalRes.flooring_elements[0].ifc_guid || canonicalRes.flooring_elements[0].id);
      } else if (activeTrade === "roofing" && canonicalRes?.roofs?.length > 0) {
        setSelectedRoofGuid(canonicalRes.roofs[0].ifc_guid || canonicalRes.roofs[0].id);
      } else if (activeTrade === "drywall" && canonicalRes?.walls?.length > 0) {
        setSelectedWallGuid(canonicalRes.walls[0].ifc_guid);
      }
    } catch (err: any) {
      const msg = err instanceof Error ? err.message : String(err);
      setLoadError(msg);
      toast.error("Failed to load BIM model", { description: msg });
    } finally {
      setLoading(false);
    }
  }, [ifcId, wasteFactor, activeTrade]);

  useEffect(() => {
    loadBIMData();
  }, [loadBIMData]);

  // Model switch action: allows estimators to directly upload a new model without leaving the workspace
  const handleSwitchModelUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    try {
      setIsSwitchingModel(true);
      toast.info(`Uploading new IFC model: ${file.name}…`);
      const uploadRes = await BackendApiService.uploadIfc(file);
      await BackendApiService.parseIfc(uploadRes.id);
      await BackendApiService.calculateIfcTakeoff(
        uploadRes.id,
        activeTrade === "drywall" ? wasteFactor / 100 : 0.0,
        activeTrade
      );
      toast.success("New IFC Model Ready", {
        description: `Switched workspace to ${file.name}`,
      });
      navigate(`/workspace?ifc_id=${uploadRes.id}&trade=${activeTrade}`);
    } catch (err: any) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error("Model Upload Failed", { description: msg });
    } finally {
      setIsSwitchingModel(false);
    }
  };

  // Trade Switch Handler REMOVED — activeTrade is immutable.
  // The workspace is trade-scoped from the URL. No runtime switching.

  // Recalculate QTO when waste factor changes (Drywall only)
  const handleWasteFactorChange = async (newWaste: number) => {
    setWasteFactor(newWaste);
    try {
      const takeoffRes = await BackendApiService.calculateIfcTakeoff(ifcId, newWaste / 100, "drywall");
      setTakeoff(takeoffRes.qto);
      toast.success(`Drywall Takeoff updated with ${newWaste}% waste allowance`);
    } catch (err: any) {
      toast.error("Takeoff recalculation failed", { description: err.message });
    }
  };

  const walls = useMemo(() => canonicalModel?.walls || [], [canonicalModel]);
  const flooringElements = useMemo(() => canonicalModel?.flooring_elements || [], [canonicalModel]);
  const roofs = useMemo(() => canonicalModel?.roofs || [], [canonicalModel]);
  const storeys = useMemo(() => canonicalModel?.storeys || [], [canonicalModel]);
  const spaces = useMemo(() => canonicalModel?.spaces || [], [canonicalModel]);
  const openings = useMemo(() => canonicalModel?.openings || [], [canonicalModel]);
  const health = useMemo(() => canonicalModel?.health_card || canonicalModel?.model_health, [canonicalModel]);

  // Trade-scoped Element Lookup Table: only indexes entities relevant to activeTrade.
  // Prevents cross-trade GUID lookups that could leak data across trade boundaries.
  const elementsByGuid = useMemo(() => {
    const map: Record<string, any> = {};
    if (activeTrade === "drywall") {
      walls.forEach((w: any) => {
        map[w.ifc_guid] = { ...w, entity_type: "IfcWall" };
      });
      openings.forEach((op: any) => {
        map[op.ifc_guid] = { ...op, entity_type: "IfcOpeningElement" };
      });
    } else if (activeTrade === "flooring") {
      spaces.forEach((sp: any) => {
        map[sp.ifc_guid] = { ...sp, entity_type: "IfcSpace" };
      });
      flooringElements.forEach((f: any) => {
        map[f.ifc_guid || f.id] = { ...f, entity_type: "IfcSlab" };
      });
    } else if (activeTrade === "roofing") {
      roofs.forEach((rf: any) => {
        map[rf.ifc_guid || rf.id] = { ...rf, entity_type: "IfcRoof" };
      });
    }
    return map;
  }, [walls, spaces, openings, roofs, flooringElements, activeTrade]);

  // Backend Line Item Map by GUID: lineItemByGuid[ifc_guid] (Single Source of Truth for QTO)
  const lineItemByGuid = useMemo(() => {
    const map: Record<string, any> = {};
    if (takeoff?.line_items) {
      takeoff.line_items.forEach((item: any) => {
        if (item.source_guid) {
          map[item.source_guid] = item;
        }
      });
    }
    return map;
  }, [takeoff]);

  // Active Selected Entity GUID based on active trade (Strictly Decoupled)
  const activeSelectedGuid =
    activeTrade === "flooring"
      ? selectedFlooringGuid
      : activeTrade === "roofing"
      ? selectedRoofGuid
      : selectedWallGuid;

  // Selected Wall Entity (Drywall Mode)
  const selectedWall = useMemo(() => {
    return walls.find((w: any) => w.ifc_guid === selectedWallGuid) || null;
  }, [walls, selectedWallGuid]);

  // Selected Flooring Entity (Flooring Mode - Canonical selectedFlooringGuid)
  const selectedFlooring = useMemo(() => {
    return flooringElements.find((f: any) => (f.ifc_guid || f.id) === selectedFlooringGuid) || null;
  }, [flooringElements, selectedFlooringGuid]);

  // Selected Roof Entity (Roofing Mode - Canonical selectedRoofGuid)
  const selectedRoof = useMemo(() => {
    return roofs.find((r: any) => (r.ifc_guid || r.id) === selectedRoofGuid) || null;
  }, [roofs, selectedRoofGuid]);

  // Selected Wall Line Item from Backend QTO
  const selectedWallLineItem = useMemo(() => {
    return selectedWallGuid ? lineItemByGuid[selectedWallGuid] : null;
  }, [selectedWallGuid, lineItemByGuid]);

  // Trade-scoped Review Queue Items — only items for the active trade.
  // Drywall: wall eligibility issues. Flooring: space issues. Roofing: roof issues.
  const reviewQueueItems = useMemo(() => {
    const items: Array<{
      guid: string;
      name: string;
      storey: string;
      reason: string;
      status: string;
      classification: string;
    }> = [];

    if (activeTrade === "drywall") {
      walls.forEach((w: any) => {
        if (w.qto_eligibility === "REVIEW_REQUIRED") {
          items.push({
            guid: w.ifc_guid,
            name: w.name,
            storey: w.storey_name,
            reason: w.eligibility_reasons?.join("; ") || "Ambiguous wall classification; estimator review required.",
            status: "REVIEW_REQUIRED",
            classification: w.wall_classification,
          });
        } else if (w.qto_eligibility === "INELIGIBLE_INVALID_GEOMETRY") {
          items.push({
            guid: w.ifc_guid,
            name: w.name,
            storey: w.storey_name,
            reason: "Zero or negative analytical geometry dimensions.",
            status: "INELIGIBLE_INVALID_GEOMETRY",
            classification: w.wall_classification,
          });
        } else if (w.qto_eligibility === "INELIGIBLE_NON_DRYWALL") {
          items.push({
            guid: w.ifc_guid,
            name: w.name,
            storey: w.storey_name,
            reason: `${w.wall_classification?.replace("_", " ")} — non-drywall scope.`,
            status: "INELIGIBLE_NON_DRYWALL",
            classification: w.wall_classification,
          });
        }
      });
    }

    if (activeTrade === "flooring") {
      spaces.forEach((sp: any) => {
        if (sp.provenance_status === "UNKNOWN_UNRESOLVED" || sp.net_floor_area_sqft <= 0) {
          items.push({
            guid: sp.ifc_guid,
            name: sp.name,
            storey: sp.storey_id,
            reason: "Missing explicit area/boundary properties from IFC.",
            status: "UNKNOWN_UNRESOLVED",
            classification: "SPACE",
          });
        }
      });
    }

    if (activeTrade === "roofing") {
      roofs.forEach((rf: any) => {
        if (rf.qto_eligibility === "REVIEW_REQUIRED") {
          items.push({
            guid: rf.ifc_guid || rf.id,
            name: rf.source_name || rf.name,
            storey: rf.storey_name || rf.storey_id,
            reason: rf.review_reasons?.join("; ") || "Missing explicit slope or geometry evidence.",
            status: "REVIEW_REQUIRED",
            classification: "ROOF",
          });
        }
      });
    }

    return items;
  }, [walls, spaces, roofs, activeTrade]);

  // Filtered BOQ / Wall List
  const filteredWalls = useMemo(() => {
    return walls.filter((w: any) => {
      const matchStorey = selectedStorey === "ALL" || w.storey_name === selectedStorey || w.storey_id === selectedStorey;
      const matchClassification = selectedClassification === "ALL" || w.wall_classification === selectedClassification;

      let matchScope = true;
      if (drywallScopeFilter === "ELIGIBLE") matchScope = w.qto_eligibility === "ELIGIBLE";
      else if (drywallScopeFilter === "REVIEW_REQUIRED") matchScope = w.qto_eligibility === "REVIEW_REQUIRED";
      else if (drywallScopeFilter === "BLOCKED") matchScope = w.qto_eligibility?.startsWith("INELIGIBLE");
      else if (drywallScopeFilter === "SINGLE_FACE") matchScope = w.drywall_side_a_scope && !w.drywall_side_b_scope;
      else if (drywallScopeFilter === "DOUBLE_FACE") matchScope = w.drywall_side_a_scope && w.drywall_side_b_scope;
      else if (drywallScopeFilter === "UNKNOWN_ASSEMBLY") {
        matchScope =
          w.assembly?.assembly_provenance === "CONFIGURED_ASSUMPTION" ||
          w.assembly?.assembly_provenance === "UNKNOWN_UNRESOLVED";
      }

      const matchSearch =
        searchQuery === "" ||
        w.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        w.ifc_guid?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        w.wall_classification?.toLowerCase().includes(searchQuery.toLowerCase());

      return matchStorey && matchClassification && matchScope && matchSearch;
    });
  }, [walls, selectedStorey, selectedClassification, drywallScopeFilter, searchQuery]);

  // Stale Selection Prevention: Ensure selectedRoofGuid / selectedFlooringGuid / selectedWallGuid remain valid within active trade elements
  useEffect(() => {
    if (activeTrade === "roofing") {
      if (selectedRoofGuid && roofs.length > 0) {
        const isStillVisible = roofs.some(
          (e: any) => (e.ifc_guid && e.ifc_guid === selectedRoofGuid) || (e.id && e.id === selectedRoofGuid)
        );
        if (!isStillVisible) {
          setSelectedRoofGuid(roofs[0].ifc_guid || roofs[0].id);
        }
      } else if (!selectedRoofGuid && roofs.length > 0) {
        setSelectedRoofGuid(roofs[0].ifc_guid || roofs[0].id);
      }
    } else if (activeTrade === "flooring") {
      if (selectedFlooringGuid && flooringElements.length > 0) {
        const isStillVisible = flooringElements.some(
          (e: any) => (e.ifc_guid && e.ifc_guid === selectedFlooringGuid) || (e.id && e.id === selectedFlooringGuid)
        );
        if (!isStillVisible) {
          setSelectedFlooringGuid(flooringElements[0].ifc_guid || flooringElements[0].id);
        }
      } else if (!selectedFlooringGuid && flooringElements.length > 0) {
        setSelectedFlooringGuid(flooringElements[0].ifc_guid || flooringElements[0].id);
      }
    } else {
      if (selectedWallGuid && filteredWalls.length > 0) {
        const isStillVisible = filteredWalls.some(
          (e: any) => e.ifc_guid && e.ifc_guid === selectedWallGuid
        );
        if (!isStillVisible) {
          setSelectedWallGuid(filteredWalls[0].ifc_guid);
        }
      } else if (!selectedWallGuid && filteredWalls.length > 0) {
        setSelectedWallGuid(filteredWalls[0].ifc_guid);
      }
    }
  }, [filteredWalls, flooringElements, roofs, selectedWallGuid, selectedFlooringGuid, selectedRoofGuid, activeTrade]);

  // Synchronized Selection Handler (Updates 3D, 2D, Tree, Inspector, BOQ simultaneously with strict trade-boundary gating)
  const handleSelectGuid = useCallback((guid: string | null) => {
    if (!guid) {
      if (activeTrade === "flooring") setSelectedFlooringGuid(null);
      else if (activeTrade === "roofing") setSelectedRoofGuid(null);
      else setSelectedWallGuid(null);
      return;
    }
    // Strict trade boundary check: reject cross-trade or foreign GUIDs (Negative Test Protection)
    if (!elementsByGuid[guid]) {
      return; // REJECTED / IGNORED: cross-trade GUID cannot pollute active trade selection
    }
    if (activeTrade === "flooring") {
      setSelectedFlooringGuid(guid);
    } else if (activeTrade === "roofing") {
      setSelectedRoofGuid(guid);
    } else {
      setSelectedWallGuid(guid);
    }
  }, [activeTrade, elementsByGuid]);

  // Visibility Controls
  const toggleWallVisibility = (guid: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    setHiddenWallGuids((prev) => {
      const next = new Set(prev);
      if (next.has(guid)) next.delete(guid);
      else next.add(guid);
      return next;
    });
  };

  const handleIsolateWall = (guid: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    if (isolatedWallGuid === guid) {
      setIsolatedWallGuid(null);
      setHiddenWallGuids(new Set());
      toast.info("Model Isolation Reset");
    } else {
      setIsolatedWallGuid(guid);
      const toHide = new Set<string>(walls.filter((w: any) => w.ifc_guid !== guid).map((w: any) => String(w.ifc_guid)));
      setHiddenWallGuids(toHide);
      toast.success(`Isolated element: ${guid}`);
    }
  };

  // Export Excel BOQ Workbook
  async function handleExportExcel() {
    try {
      setExporting(true);
      const blob = await BackendApiService.exportIfcExcel(ifcId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `PROTAKEOFF_${ifcDoc?.filename?.replace(/\.ifc$/i, "") || "Model"}_QTO.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Professional BOQ Excel workbook exported!");
    } catch (err: any) {
      toast.error("Export failed", { description: err.message });
    } finally {
      setExporting(false);
    }
  }

  // Provenance Badge Component
  const ProvenanceBadge = ({ status }: { status?: string }) => {
    if (status === "VERIFIED_EXPLICIT") {
      return (
        <span
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-emerald-950/80 text-emerald-400 border border-emerald-700/60"
          title="Directly from IFC Property Set / Material Layer"
        >
          <CheckCircle2 size={10} />
          <span>VERIFIED EXPLICIT</span>
        </span>
      );
    }
    if (status === "DERIVED_GEOMETRIC") {
      return (
        <span
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-sky-950/80 text-sky-400 border border-sky-700/60"
          title="Calculated from 3D Solid / Curve Boundary Geometry"
        >
          <Box size={10} />
          <span>DERIVED GEOMETRIC</span>
        </span>
      );
    }
    if (status === "CONFIGURED_ASSUMPTION") {
      return (
        <span
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-amber-950/80 text-amber-400 border border-amber-700/60"
          title="Derived from Estimator Profile / Project Configuration"
        >
          <AlertTriangle size={10} />
          <span>CONFIGURED ASSUMPTION</span>
        </span>
      );
    }
    return (
      <span
        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-rose-950/80 text-rose-400 border border-rose-700/60"
        title="Missing from IFC; Estimator Review Required"
      >
        <AlertCircle size={10} />
        <span>UNKNOWN UNRESOLVED</span>
      </span>
    );
  };

  // Error State Display
  if (loadError) {
    return (
      <div className="h-screen w-screen bg-[#060b14] flex flex-col items-center justify-center text-white space-y-4 font-sans p-6">
        <div className="w-16 h-16 rounded-2xl bg-rose-950/60 border border-rose-700/60 flex items-center justify-center text-rose-400">
          <AlertCircle size={32} />
        </div>
        <div className="text-center space-y-2 max-w-md">
          <h3 className="text-lg font-bold text-gray-100">BIM Ingestion Failed</h3>
          <p className="text-xs font-mono text-rose-400 bg-rose-950/40 p-3 rounded border border-rose-800/40 text-left">
            {loadError}
          </p>
          <p className="text-xs text-gray-400">
            Please check that the IFC document is valid and reachable on the backend server.
          </p>
        </div>
        <button
          onClick={loadBIMData}
          className="px-4 py-2 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs flex items-center gap-2"
        >
          <RefreshCw size={14} />
          <span>Retry Loading</span>
        </button>
      </div>
    );
  }

  // Loading State Display
  if (loading) {
    return (
      <div className="h-screen w-screen bg-[#060b14] flex flex-col items-center justify-center text-white space-y-4 font-sans">
        <div className="relative">
          <div className="w-16 h-16 border-4 border-[#0284c7]/20 border-t-[#0284c7] rounded-full animate-spin" />
          <Box size={24} className="absolute inset-0 m-auto text-cyan-400 animate-pulse" />
        </div>
        <div className="text-center space-y-1">
          <h3 className="text-base font-bold tracking-wide text-gray-200">PROTAKEOFF BIM WORKSPACE</h3>
          <p className="text-xs font-mono text-cyan-400">{loadingStep}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen bg-[#060b14] text-gray-200 flex flex-col overflow-hidden font-sans select-none">
      {/* ========================================================================= */}
      {/* 1. TOP NAVIGATION / PROJECT STATUS BAR                                    */}
      {/* ========================================================================= */}
      <header className="h-12 border-b border-[#162840] bg-[#0a121e] px-4 flex items-center justify-between flex-shrink-0 z-20">
        <div className="flex items-center space-x-6">
          <div className="flex items-center space-x-2">
            <div className="w-6 h-6 rounded bg-cyan-600 flex items-center justify-center font-black text-black text-xs shadow-md shadow-cyan-500/20">
              BIM
            </div>
            <div className="flex items-center space-x-2">
              <span className="font-extrabold text-xs tracking-wider text-white">PROTAKEOFF</span>
              <span className="text-[10px] font-mono text-gray-400 ml-1 border-l border-gray-700 pl-2">
                {ifcDoc?.filename || "Building Model.ifc"}
              </span>
              {ifcDoc?.source_hash && (
                <span
                  className="text-[9px] font-mono text-cyan-400/90 px-1.5 py-0.5 rounded bg-cyan-950/60 border border-cyan-800/50 select-text"
                  title={`SHA-256 Content Hash: ${ifcDoc.source_hash}`}
                >
                  SHA:{ifcDoc.source_hash.slice(0, 8)}
                </span>
              )}
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isSwitchingModel}
                className="flex items-center gap-1 px-2 py-0.5 rounded bg-[#162840] hover:bg-cyan-700/60 text-cyan-300 text-[10px] font-semibold transition-all cursor-pointer border border-cyan-700/40 disabled:opacity-50"
                title="Upload and switch to a new IFC model (clears all prior state)"
              >
                <UploadCloud size={11} />
                <span>{isSwitchingModel ? "Switching…" : "Switch Model"}</span>
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".ifc,.ifcxml,.ifczip"
                className="hidden"
                onChange={handleSwitchModelUpload}
              />
            </div>
          </div>

          {/* Primary Navigation Tabs */}
          <nav className="flex items-center space-x-1 bg-[#060b14] p-0.5 rounded border border-[#162840]">
            {(["MODEL", "TAKEOFF", "REVIEW", "AUDIT", "REPORTS"] as WorkspaceNavTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveNavTab(tab)}
                className={`px-3 py-1 rounded text-xs font-bold transition-all cursor-pointer ${
                  activeNavTab === tab
                    ? "bg-[#0284c7] text-white shadow-sm font-black"
                    : "text-gray-400 hover:text-gray-200 hover:bg-gray-800/40"
                }`}
              >
                {tab}
              </button>
            ))}
          </nav>
        </div>

        {/* Model Health Indicator & Controls */}
        <div className="flex items-center space-x-3">
          {/* Immutable Trade Context Badge — NO trade-switch controls.
             The workspace is fully scoped to one trade from the URL. */}
          <div className="flex items-center px-2.5 py-1 rounded bg-[#060b14] border border-[#162840]">
            <span className={`px-2.5 py-1 rounded text-xs font-black ${
              activeTrade === "drywall"
                ? "bg-cyan-600 text-white shadow-sm"
                : activeTrade === "flooring"
                ? "bg-amber-600 text-white shadow-sm"
                : "bg-amber-600 text-white shadow-sm"
            }`}>
              {activeTrade.toUpperCase()} WORKSPACE
            </span>
          </div>

          {health && (
            <div className="flex items-center space-x-2 px-2.5 py-1 rounded bg-[#060b14] border border-[#162840] text-xs">
              <span className="text-[10px] font-mono text-gray-400">SCHEMA:</span>
              <span className="font-mono text-cyan-400 font-bold text-[11px]">{health.schema_version}</span>
              <span className="text-gray-600">|</span>
              <span className="text-[10px] font-mono text-gray-400">READINESS:</span>
              <span
                className={`font-mono text-[10px] font-bold px-1.5 py-0.5 rounded ${
                  health.readiness === "READY_FOR_QTO"
                    ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                    : "bg-amber-950 text-amber-400 border border-amber-800"
                }`}
              >
                {health.readiness}
              </span>
            </div>
          )}

          {/* Storey Selector */}
          <div className="flex items-center space-x-1 bg-[#060b14] px-2 py-1 rounded border border-[#162840] text-xs">
            <Layers size={13} className="text-gray-400" />
            <select
              value={selectedStorey}
              onChange={(e) => setSelectedStorey(e.target.value)}
              className="bg-transparent text-xs font-mono text-gray-200 outline-none cursor-pointer"
            >
              <option value="ALL" className="bg-[#0a121e]">
                All Storeys ({storeys.length})
              </option>
              {storeys.map((s: any) => (
                <option key={s.id} value={s.name} className="bg-[#0a121e]">
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          {/* Export Excel Button */}
          <button
            onClick={handleExportExcel}
            disabled={exporting}
            className="flex items-center space-x-1.5 px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-all shadow-md shadow-emerald-600/20 cursor-pointer disabled:opacity-50"
            title="Export full auditable QTO schedule to Excel (.xlsx)"
          >
            <FileSpreadsheet size={13} />
            <span>{exporting ? "Exporting…" : "Export BOQ"}</span>
          </button>
        </div>
      </header>

      {/* ========================================================================= */}
      {/* 1.5. TOP FLOORING SUMMARY / KPI STRIP (WHEN IN FLOORING TRADE MODE)       */}
      {/* ========================================================================= */}
      {activeTrade === "flooring" && activeNavTab === "TAKEOFF" && (() => {
        const eligibleList = flooringElements.filter((f: any) => f.qto_eligibility === "ELIGIBLE");
        const totalNet = eligibleList.reduce((sum: number, f: any) => sum + (Number(f.net_area_sqft) || 0), 0);
        const reviewCount = flooringElements.filter((f: any) => f.qto_eligibility === "REVIEW_REQUIRED").length;
        const supersededCount = flooringElements.filter((f: any) => f.qto_eligibility === "SUPERSEDED_BY_PHYSICAL_ELEMENT").length;
        const excludedCount = flooringElements.filter((f: any) => (f.qto_eligibility || "").startsWith("INELIGIBLE")).length;
        
        // Material percentage breakdown
        const matMap: Record<string, number> = {};
        eligibleList.forEach((f: any) => {
          const cat = f.flooring_category || "OTHER";
          matMap[cat] = (matMap[cat] || 0) + (Number(f.net_area_sqft) || 0);
        });
        const matBreakdown = Object.entries(matMap)
          .map(([cat, sqft]) => ({
            category: cat,
            sqft,
            pct: totalNet > 0 ? (sqft / totalNet) * 100 : 0,
          }))
          .sort((a, b) => b.sqft - a.sqft);

        return (
          <div className="bg-[#080e18] border-b border-[#162840] px-4 py-2 flex items-center justify-between flex-shrink-0 flex-wrap gap-3">
            {/* KPI Cards Row */}
            <div className="flex items-center gap-2.5">
              {/* Total Flooring Hero Card */}
              <div className="bg-[#060b14] border border-cyan-800/70 bg-gradient-to-br from-cyan-950/40 to-[#060b14] px-3.5 py-1.5 rounded-md shadow-sm">
                <div className="text-[9px] font-bold text-cyan-400 uppercase tracking-wider">
                  Total Flooring
                </div>
                <div className="text-base font-black text-cyan-300 font-mono leading-tight">
                  {totalNet.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}{" "}
                  <span className="text-xs font-semibold text-cyan-400/80">SF</span>
                </div>
              </div>

              {/* Included Items Card */}
              <div className="bg-[#060b14] border border-emerald-800/50 px-3 py-1.5 rounded-md shadow-sm">
                <div className="text-[9px] font-bold text-emerald-400 uppercase tracking-wider">
                  Included
                </div>
                <div className="text-sm font-black text-emerald-300 font-mono leading-tight">
                  {eligibleList.length}{" "}
                  <span className="text-[10px] font-normal text-gray-400">items</span>
                </div>
              </div>

              {/* Material Types Card (Strictly non-zero eligible categories) */}
              <div className="bg-[#060b14] border border-amber-800/50 px-3 py-1.5 rounded-md shadow-sm">
                <div className="text-[9px] font-bold text-amber-400 uppercase tracking-wider">
                  Material Types
                </div>
                <div className="text-sm font-black text-amber-300 font-mono leading-tight">
                  {matBreakdown.length}
                </div>
              </div>

              {/* Review Card */}
              <div className={`bg-[#060b14] border px-3 py-1.5 rounded-md shadow-sm ${
                reviewCount > 0 ? "border-amber-700/60 bg-amber-950/20" : "border-[#162840]"
              }`}>
                <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider">
                  Review
                </div>
                <div className={`text-sm font-black font-mono leading-tight ${
                  reviewCount > 0 ? "text-amber-400" : "text-gray-400"
                }`}>
                  {reviewCount}
                </div>
              </div>

              {/* Superseded Card */}
              <div className={`bg-[#060b14] border px-3 py-1.5 rounded-md shadow-sm ${
                supersededCount > 0 ? "border-purple-800/50 bg-purple-950/20" : "border-[#162840]"
              }`}>
                <div className="text-[9px] font-bold text-purple-400 uppercase tracking-wider">
                  Superseded
                </div>
                <div className="text-sm font-black text-purple-300 font-mono leading-tight">
                  {supersededCount}
                </div>
              </div>

              {/* Excluded Card */}
              {excludedCount > 0 && (
                <div className="bg-[#060b14] border border-gray-800 px-3 py-1.5 rounded-md shadow-sm">
                  <div className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">
                    Excluded
                  </div>
                  <div className="text-sm font-bold text-gray-400 font-mono leading-tight">
                    {excludedCount}
                  </div>
                </div>
              )}

              {/* Total Audit Items Card */}
              <div className="bg-[#060b14] border border-[#162840] px-3 py-1.5 rounded-md shadow-sm">
                <div className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">
                  Total Audit Items
                </div>
                <div className="text-sm font-bold text-gray-300 font-mono leading-tight">
                  {flooringElements.length}
                </div>
              </div>
            </div>

            {/* Material Distribution Pill Strip */}
            <div className="flex items-center gap-1.5 text-[10px] font-mono overflow-x-auto max-w-xl">
              <span className="text-[9px] text-gray-500 uppercase font-sans font-bold flex-shrink-0">
                Mix:
              </span>
              {matBreakdown.map((m) => (
                <div
                  key={m.category}
                  className="bg-[#060b14] border border-[#162840] px-2 py-0.5 rounded text-gray-300 flex items-center gap-1.5 flex-shrink-0"
                >
                  <span className="font-semibold text-white">
                    {m.category.replace(/_/g, " ")}
                  </span>
                  <span className="text-cyan-300 font-bold">
                    {m.sqft.toFixed(0)} SF
                  </span>
                  <span className="text-gray-500 text-[9px]">
                    ({m.pct.toFixed(1)}%)
                  </span>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* ========================================================================= */}
      {/* 1.6. TOP ROOFING SUMMARY / KPI STRIP (WHEN IN ROOFING TRADE MODE)         */}
      {/* ========================================================================= */}
      {activeTrade === "roofing" && activeNavTab === "TAKEOFF" && (() => {
        const eligibleList = roofs.filter((r: any) => r.qto_eligibility === "ELIGIBLE");
        const totalSurfaceArea = eligibleList.reduce(
          (sum: number, r: any) => sum + (Number(r.true_surface_area_sqft) || 0),
          0
        );
        const reviewCount = roofs.filter((r: any) => r.qto_eligibility === "REVIEW_REQUIRED").length;
        const blockedCount = roofs.filter((r: any) => (r.qto_eligibility || "").startsWith("INELIGIBLE")).length;

        // Type breakdown
        const typeMap: Record<string, number> = {};
        eligibleList.forEach((r: any) => {
          const t = r.roof_type || "UNKNOWN";
          typeMap[t] = (typeMap[t] || 0) + (Number(r.true_surface_area_sqft) || 0);
        });
        const typeBreakdown = Object.entries(typeMap)
          .map(([type, sqft]) => ({
            type,
            sqft,
            pct: totalSurfaceArea > 0 ? (sqft / totalSurfaceArea) * 100 : 0,
          }))
          .sort((a, b) => b.sqft - a.sqft);

        return (
          <div className="bg-[#080e18] border-b border-[#162840] px-4 py-2 flex items-center justify-between flex-shrink-0 flex-wrap gap-3">
            <div className="flex items-center gap-2.5">
              {/* Total Roof Surface Hero Card */}
              <div className="bg-[#060b14] border border-amber-800/70 bg-gradient-to-br from-amber-950/40 to-[#060b14] px-3.5 py-1.5 rounded-md shadow-sm">
                <div className="text-[9px] font-bold text-amber-400 uppercase tracking-wider">
                  Total Roof Surface
                </div>
                <div className="text-base font-black text-amber-300 font-mono leading-tight">
                  {totalSurfaceArea.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}{" "}
                  <span className="text-xs font-semibold text-amber-400/80">SF TRUE</span>
                </div>
              </div>

              {/* Selected Roof Plane Card */}
              {selectedRoof && (
                <div className="bg-[#060b14] border border-cyan-800/70 bg-gradient-to-br from-cyan-950/30 to-[#060b14] px-3.5 py-1.5 rounded-md shadow-sm">
                  <div className="text-[9px] font-bold text-cyan-400 uppercase tracking-wider">
                    Selected Plane
                  </div>
                  <div className="text-sm font-black text-cyan-300 font-mono leading-tight">
                    {Number(selectedRoof.true_surface_area_sqft || selectedRoof.plan_area_sqft || 0).toFixed(1)}{" "}
                    <span className="text-[10px] font-normal text-cyan-400/80">SF</span>
                  </div>
                </div>
              )}

              {/* Included Roof Planes */}
              <div className="bg-[#060b14] border border-emerald-800/50 px-3 py-1.5 rounded-md shadow-sm">
                <div className="text-[9px] font-bold text-emerald-400 uppercase tracking-wider">
                  Included Planes
                </div>
                <div className="text-sm font-black text-emerald-300 font-mono leading-tight">
                  {eligibleList.length}{" "}
                  <span className="text-[10px] font-normal text-gray-400">planes</span>
                </div>
              </div>

              {/* Roof Types */}
              <div className="bg-[#060b14] border border-cyan-800/50 px-3 py-1.5 rounded-md shadow-sm">
                <div className="text-[9px] font-bold text-cyan-400 uppercase tracking-wider">
                  Roof Types
                </div>
                <div className="text-sm font-black text-cyan-300 font-mono leading-tight">
                  {typeBreakdown.length}
                </div>
              </div>

              {/* Review Card */}
              <div
                className={`bg-[#060b14] border px-3 py-1.5 rounded-md shadow-sm ${
                  reviewCount > 0 ? "border-amber-700/60 bg-amber-950/20" : "border-[#162840]"
                }`}
              >
                <div className="text-[9px] font-bold text-gray-400 uppercase tracking-wider">
                  Review
                </div>
                <div
                  className={`text-sm font-black font-mono leading-tight ${
                    reviewCount > 0 ? "text-amber-400" : "text-gray-400"
                  }`}
                >
                  {reviewCount}
                </div>
              </div>

              {/* Excluded Card */}
              {blockedCount > 0 && (
                <div className="bg-[#060b14] border border-gray-800 px-3 py-1.5 rounded-md shadow-sm">
                  <div className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">
                    Excluded
                  </div>
                  <div className="text-sm font-bold text-gray-400 font-mono leading-tight">
                    {blockedCount}
                  </div>
                </div>
              )}

              {/* Total Audit Items */}
              <div className="bg-[#060b14] border border-[#162840] px-3 py-1.5 rounded-md shadow-sm">
                <div className="text-[9px] font-bold text-gray-500 uppercase tracking-wider">
                  Total Audit Elements
                </div>
                <div className="text-sm font-bold text-gray-300 font-mono leading-tight">
                  {roofs.length}
                </div>
              </div>
            </div>

            {/* Type Breakdown Pills */}
            <div className="flex items-center gap-1.5 text-[10px] font-mono overflow-x-auto max-w-xl">
              <span className="text-[9px] text-gray-500 uppercase font-sans font-bold flex-shrink-0">
                Types:
              </span>
              {typeBreakdown.map((t) => (
                <div
                  key={t.type}
                  className="bg-[#060b14] border border-[#162840] px-2 py-0.5 rounded text-gray-300 flex items-center gap-1.5 flex-shrink-0"
                >
                  <span className="font-semibold text-white">{t.type}</span>
                  <span className="text-amber-300 font-bold">{t.sqft.toFixed(0)} SF</span>
                  <span className="text-gray-500 text-[9px]">({t.pct.toFixed(1)}%)</span>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      {/* ========================================================================= */}
      {/* 2. MAIN 3-COLUMN WORKSPACE BODY                                           */}
      {/* ========================================================================= */}
      <div className="flex-1 flex overflow-hidden">
        {/* ======================================================================= */}
        {/* LEFT COLUMN: HIERARCHICAL MODEL TREE                                    */}
        {/* ======================================================================= */}
        <aside className="w-80 border-r border-[#162840] bg-[#0a121e] flex flex-col flex-shrink-0">
          <BIMModelTree
            projectName={ifcDoc?.filename?.replace(/\.ifc$/i, "") || "BIM Project Model"}
            buildingName="Main Building"
            storeys={storeys}
            walls={activeTrade === "drywall" ? walls : []}
            spaces={activeTrade === "flooring" ? spaces : []}
            slabs={activeTrade === "flooring" ? (canonicalModel?.slabs || []) : []}
            roofs={activeTrade === "roofing" ? roofs : []}
            flooringElements={activeTrade === "flooring" ? flooringElements : []}
            trade={activeTrade}
            selectedWallGuid={activeSelectedGuid}
            onSelectGuid={handleSelectGuid}
            hiddenGuids={hiddenWallGuids}
            onToggleVisibility={toggleWallVisibility}
            isolatedGuid={isolatedWallGuid}
            onIsolateGuid={handleIsolateWall}
            onShowAll={() => {
              setHiddenWallGuids(new Set());
              setIsolatedWallGuid(null);
              toast.info("All model elements visible");
            }}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            selectedStoreyFilter={selectedStorey}
            onStoreyFilterChange={setSelectedStorey}
            selectedClassificationFilter={selectedClassification}
            onClassificationFilterChange={setSelectedClassification}
          />
        </aside>

        {/* ======================================================================= */}
        {/* CENTER COLUMN: 3D / 2D / SPLIT VIEWPORT & ACTIVE TAB VIEWS              */}
        {/* ======================================================================= */}
        <main className="flex-1 flex flex-col min-w-0 bg-[#060b14] overflow-hidden">
          {/* Main Visualizer or Active Nav Tab View */}
          {activeNavTab === "REVIEW" ? (
            /* =================================================================== */
            /* PRODUCTION-GRADE BIM REVIEW QUEUE                                  */
            /* =================================================================== */
            <BIMReviewQueue
              walls={activeTrade === "drywall" ? walls : []}
              spaces={activeTrade === "flooring" ? spaces : []}
              lineItemByGuid={lineItemByGuid}
              selectedWallGuid={activeSelectedGuid}
              onSelectGuid={handleSelectGuid}
              onNavigateToTakeoff={(guid) => {
                handleSelectGuid(guid);
                setActiveNavTab("TAKEOFF");
              }}
            />
          ) : activeNavTab === "AUDIT" ? (
            /* =================================================================== */
            /* PRODUCTION-GRADE DETERMINISTIC AUDIT LOG                           */
            /* =================================================================== */
            <BIMAuditLog
              ifcDoc={ifcDoc}
              takeoff={takeoff}
              walls={activeTrade === "drywall" ? walls : []}
              spaces={activeTrade === "flooring" ? spaces : []}
              selectedWallGuid={activeSelectedGuid}
              onSelectGuid={handleSelectGuid}
              onExportExcel={handleExportExcel}
            />
          ) : activeNavTab === "REPORTS" ? (
            /* =================================================================== */
            /* REPORTS / EXECUTIVE BOQ VIEW                                       */
            /* =================================================================== */
            <div className="flex-1 p-6 overflow-y-auto space-y-6">
              <div className="flex items-center justify-between border-b border-[#162840] pb-4">
                <div>
                  <h2 className="text-lg font-black text-white flex items-center gap-2">
                    <BarChart3 size={20} className="text-cyan-400" />
                    <span>
                      {activeTrade === "roofing"
                        ? "Roofing Surface Quantity Takeoff Executive Report"
                        : activeTrade === "flooring"
                        ? "Flooring Surface Quantity Takeoff Executive Report"
                        : "Drywall Quantity Takeoff Executive Report"}
                    </span>
                  </h2>
                  <p className="text-xs text-gray-400 font-mono">
                    Project: {ifcDoc?.filename || "Building Model.ifc"} · Engine: {takeoff?.engine_version || "1.0.0"}
                  </p>
                </div>
                <button
                  onClick={handleExportExcel}
                  className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-1.5"
                >
                  <FileSpreadsheet size={14} />
                  <span>Download Excel Schedule (.xlsx)</span>
                </button>
              </div>

              {activeTrade === "roofing" ? (
                <>
                  <div className="grid grid-cols-4 gap-4">
                    <div className="p-3.5 rounded-lg bg-[#0a121e] border border-amber-800/60 bg-amber-950/20">
                      <span className="text-[10px] font-mono text-amber-400 uppercase">Total Roof Surface</span>
                      <div className="text-lg font-bold text-amber-300 font-mono mt-1">
                        {((takeoff as any)?.total_true_surface_area_sqft || (takeoff as any)?.total_surface_area_sqft || 0).toLocaleString()} SF
                      </div>
                    </div>
                    <div className="p-3.5 rounded-lg bg-[#0a121e] border border-[#162840]">
                      <span className="text-[10px] font-mono text-gray-400 uppercase">Eligible Roof Planes</span>
                      <div className="text-lg font-bold text-emerald-400 font-mono mt-1">
                        {takeoff?.line_items?.length || 0}
                      </div>
                    </div>
                    <div className="p-3.5 rounded-lg bg-[#0a121e] border border-[#162840]">
                      <span className="text-[10px] font-mono text-gray-400 uppercase">Roof Types</span>
                      <div className="text-lg font-bold text-cyan-300 font-mono mt-1">
                        {new Set(roofs.map((r: any) => r.roof_type)).size}
                      </div>
                    </div>
                    <div className="p-3.5 rounded-lg bg-[#0a121e] border border-[#162840]">
                      <span className="text-[10px] font-mono text-gray-400 uppercase">Accessories Excluded</span>
                      <div className="text-lg font-bold text-emerald-300 font-mono mt-1">
                        0 (CANONICAL SURFACE ONLY)
                      </div>
                    </div>
                  </div>
                </>
              ) : activeTrade === "flooring" ? (
                <>
                  <div className="grid grid-cols-4 gap-4">
                    <div className="p-3.5 rounded-lg bg-[#0a121e] border border-cyan-800/60 bg-cyan-950/20">
                      <span className="text-[10px] font-mono text-cyan-400 uppercase">Total Net Flooring</span>
                      <div className="text-lg font-bold text-cyan-300 font-mono mt-1">
                        {((takeoff as any)?.total_floor_area_sqft || (takeoff as any)?.total_net_area_sqft || 0).toLocaleString()} SF
                      </div>
                    </div>
                    <div className="p-3.5 rounded-lg bg-[#0a121e] border border-[#162840]">
                      <span className="text-[10px] font-mono text-gray-400 uppercase">Eligible Elements</span>
                      <div className="text-lg font-bold text-emerald-400 font-mono mt-1">
                        {takeoff?.line_items?.length || 0}
                      </div>
                    </div>
                    <div className="p-3.5 rounded-lg bg-[#0a121e] border border-[#162840]">
                      <span className="text-[10px] font-mono text-gray-400 uppercase">Material Categories</span>
                      <div className="text-lg font-bold text-amber-300 font-mono mt-1">
                        {new Set(flooringElements.map((f: any) => f.flooring_category)).size}
                      </div>
                    </div>
                    <div className="p-3.5 rounded-lg bg-[#0a121e] border border-[#162840]">
                      <span className="text-[10px] font-mono text-gray-400 uppercase">Packaging Assumptions</span>
                      <div className="text-lg font-bold text-emerald-300 font-mono mt-1">
                        0 (EXCLUDED)
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  {/* KPI Summary Cards */}
                  <div className="grid grid-cols-4 gap-4">
                    <div className="p-3.5 rounded-lg bg-[#0a121e] border border-[#162840]">
                      <span className="text-[10px] font-mono text-gray-400 uppercase">Gross Wall Face Area</span>
                      <div className="text-lg font-bold text-white font-mono mt-1">
                        {takeoff?.total_gross_wall_area_sqft?.toLocaleString()} SF
                      </div>
                    </div>
                    <div className="p-3.5 rounded-lg bg-[#0a121e] border border-[#162840]">
                      <span className="text-[10px] font-mono text-gray-400 uppercase">Opening Deductions</span>
                      <div className="text-lg font-bold text-rose-400 font-mono mt-1">
                        -{takeoff?.total_opening_deduction_sqft?.toLocaleString()} SF
                      </div>
                    </div>
                    <div className="p-3.5 rounded-lg bg-[#0a121e] border border-cyan-800/60 bg-cyan-950/20">
                      <span className="text-[10px] font-mono text-cyan-400 uppercase">Net Drywall Board Area</span>
                      <div className="text-lg font-bold text-cyan-300 font-mono mt-1">
                        {takeoff?.total_net_drywall_area_sqft?.toLocaleString()} SF
                      </div>
                    </div>
                    <div className="p-3.5 rounded-lg bg-[#0a121e] border border-amber-800/60 bg-amber-950/20">
                      <span className="text-[10px] font-mono text-amber-400 uppercase">Est. 4×8 Gypsum Sheets</span>
                      <div className="text-lg font-bold text-amber-300 font-mono mt-1">
                        {takeoff?.estimated_drywall_sheets_4x8?.toLocaleString()} EA
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          ) : (
            /* =================================================================== */
            /* VIEWPORT (3D / 2D / SPLIT) WITH FLOATING CONTROLS                   */
            /* =================================================================== */
            <div className="flex-1 relative overflow-hidden">
              <BIM3DCanvasViewer
                walls={activeTrade === "drywall" ? walls : []}
                contextWalls={walls}
                storeys={storeys}
                spaces={activeTrade === "flooring" ? spaces : []}
                roofs={activeTrade === "roofing" ? roofs : []}
                flooringElements={activeTrade === "flooring" ? flooringElements : []}
                selectedTrade={activeTrade}
                selectedWallGuid={activeSelectedGuid}
                onSelectWall={handleSelectGuid}
                selectedStorey={selectedStorey}
                onSelectStorey={setSelectedStorey}
                hiddenCategories={hiddenCategories}
                hiddenWallGuids={hiddenWallGuids}
                externalViewMode={viewMode}
                onViewModeChange={setViewMode}
              />
            </div>
          )}

          {/* ===================================================================== */}
          {/* BOTTOM DOCK: PRODUCTION-GRADE AUDITABLE BOQ SCHEDULE                  */}
          {/* ===================================================================== */}
          {activeNavTab !== "REPORTS" && activeNavTab !== "REVIEW" && (
            <div className="h-64 flex-shrink-0 overflow-hidden">
              <BIMBOQSchedule
                walls={activeTrade === "drywall" ? walls : []}
                roofs={activeTrade === "roofing" ? roofs : []}
                lineItemByGuid={lineItemByGuid}
                takeoff={takeoff}
                selectedWallGuid={activeSelectedGuid}
                onSelectGuid={handleSelectGuid}
                wasteFactor={wasteFactor}
                onWasteFactorChange={handleWasteFactorChange}
                onExportExcel={handleExportExcel}
                exporting={exporting}
                trade={activeTrade}
                flooringElements={activeTrade === "flooring" ? flooringElements : []}
              />
            </div>
          )}
        </main>

        {/* ======================================================================= */}
        {/* RIGHT COLUMN: PRODUCTION-GRADE BIM INSPECTOR (CANONICAL TRUTH & AUDIT) */}
        {/* ======================================================================= */}
        <aside className="w-80 border-l border-[#162840] bg-[#0a121e] flex flex-col flex-shrink-0 overflow-hidden">
          <BIMInspector
            selectedGuid={activeSelectedGuid}
            wall={activeTrade === "drywall" ? selectedWall : null}
            lineItem={activeTrade === "drywall" ? selectedWallLineItem : null}
            filteredWalls={
              activeTrade === "flooring"
                ? flooringElements
                : activeTrade === "roofing"
                ? roofs
                : filteredWalls
            }
            onSelectGuid={handleSelectGuid}
            wasteFactor={wasteFactor}
            storeyName={
              activeTrade === "drywall"
                ? selectedWall?.storey_name
                : activeTrade === "flooring"
                ? (selectedFlooring as any)?.storey_name
                : (selectedRoof as any)?.storey_name
            }
            selectedFlooringElement={activeTrade === "flooring" ? selectedFlooring : null}
            selectedRoofElement={activeTrade === "roofing" ? selectedRoof : null}
            trade={activeTrade}
          />
        </aside>
      </div>
    </div>
  );
}
