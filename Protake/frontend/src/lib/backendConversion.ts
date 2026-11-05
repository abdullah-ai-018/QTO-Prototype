import type { BackendDetection, BackendRoom, BackendWall } from "@/api/backendApi";
import type { BackendArchitecturalWall, Detection, DetectionKind, Point, TradeId } from "@/types";
import { formatWallThickness } from "@/lib/units";
import { normalizeWallClassification, WALL_CATEGORY_COLORS } from "@/lib/colors";


/**
 * Backend Room/Wall -> frontend Detection conversion, and the room-name ->
 * trade heuristic. Single source of truth for both entry points that load
 * backend detections (a fresh upload in UploadExperience.tsx, and
 * reopening an already-processed blueprint in Workspace.tsx).
 *
 * These two call sites used to each keep their own copy. They drifted:
 * Workspace.tsx's copy hardcoded `trade: null` and had no wall conversion
 * at all, so reopening a project silently showed fewer/different
 * detections than viewing it right after upload — same backend data,
 * different result, depending on which code path rendered it.
 */

// Convert backend Room (geometry engine output) → frontend Detection format
export function roomToDetection(room: BackendRoom, sheetId: string): Detection {
  return {
    id: `backend-room-${room.id}`,
    sheetId,
    kind: "room" as const,
    name: room.name || `Room ${room.id}`,
    trade: inferTrade(room.name),
    roomType: room.room_type,
    // polygon_norm is [[x,y],[x,y],...] in 0-1 normalized coords
    points: room.polygon_norm.map(([x, y]) => ({ x, y })),
    areaSqFt: Math.round(room.area_sqft),
    perimeterFt: Math.round(room.perimeter_ft),
    confidence: Math.round(room.confidence * 100) / 100,
    status: room.status === "approved" ? "approved" : room.status === "rejected" ? "rejected" : "pending",
  };
}

// Convert canonical BackendArchitecturalWall → frontend Detection
export function architecturalWallToDetection(wall: BackendArchitecturalWall, sheetId: string): Detection {
  const canonicalCat = normalizeWallClassification(wall.classification);
  const isExterior = canonicalCat === "EXTERIOR_PERIMETER";

  // wall_tag is the architect's drawn notation (NR-1, X-2, H-1…).
  // assembly_tag is an internal engine sentinel: "DEFAULT" means no verified
  // partition schedule was found — it is NOT a display label.
  // Use wall_tag as the bracket prefix; suppress "DEFAULT" since it carries
  // no user-facing meaning.
  const drawnTag = wall.wall_tag && wall.wall_tag !== "DEFAULT" ? wall.wall_tag : null;
  const tagLabel = drawnTag ? `[${drawnTag}] ` : "";

  // Human-readable wall category label derived from canonical classification.
  const categoryLabel = WALL_CATEGORY_COLORS[canonicalCat]?.label ?? "Interior Partition";

  // Assembly provenance label — only show if there's a real (non-DEFAULT)
  // assembly_tag; otherwise say nothing (the assembly_description field is
  // always available for tooltips).
  const assemblyLabel: string = (() => {
    const at = wall.assembly_tag;
    if (!at || at === "DEFAULT") return "";
    return ` — ${at}`;
  })();

  const dims = `${Math.round(wall.length_ft)} ft × ${wall.height_ft.toFixed(1)} ft${
    wall.thickness_in ? ` • ${wall.thickness_in.toFixed(1)}" thick` : ""
  }`;
  const name = `${tagLabel}${categoryLabel}${assemblyLabel} (${dims})`;

  // Robust coordinate parser that handles both {x, y} objects and [x, y] arrays safely
  const parseNormPoint = (p: any): Point => {
    if (!p) return { x: 0, y: 0 };
    if (Array.isArray(p)) return { x: Number(p[0]) || 0, y: Number(p[1]) || 0 };
    if (typeof p === "object") return { x: Number(p.x) || 0, y: Number(p.y) || 0 };
    return { x: 0, y: 0 };
  };

  // Polygon if present, otherwise 2-point centerline
  const points: Point[] =
    wall.wall_polygon_norm && wall.wall_polygon_norm.length >= 3
      ? wall.wall_polygon_norm.map(parseNormPoint)
      : [
          parseNormPoint(wall.start_norm),
          parseNormPoint(wall.end_norm),
        ];

  const clippedSegments: Point[][] =
    wall.clipped_segments_norm && wall.clipped_segments_norm.length > 0
      ? wall.clipped_segments_norm.map((seg) =>
          Array.isArray(seg)
            ? seg.map(parseNormPoint)
            : [parseNormPoint(wall.start_norm), parseNormPoint(wall.end_norm)]
        )
      : [
          [
            parseNormPoint(wall.start_norm),
            parseNormPoint(wall.end_norm),
          ],
        ];

  return {
    id: `backend-archwall-${wall.id}`,
    sheetId,
    kind: "wall" as const,
    name,
    trade: "drywall",
    points,
    clippedSegments,
    wallPolygon:
      wall.wall_polygon_norm && wall.wall_polygon_norm.length >= 3
        ? wall.wall_polygon_norm.map(parseNormPoint)
        : undefined,
    areaSqFt: Math.round(wall.net_sf || wall.gross_sf || 0),

    perimeterFt: Math.round(wall.length_ft),
    thicknessFt: (wall.thickness_in || 4.875) / 12,
    thicknessIn: wall.thickness_in,
    thicknessSource: wall.thickness_source,
    thicknessMeasured: wall.thickness_source === "paired_geometry",
    wallType: isExterior ? "exterior" : "interior",
    wallTypeCode: canonicalCat,
    wallTag: drawnTag,
    classification: wall.classification,
    assemblyTag: wall.assembly_tag,
    assemblyDescription: wall.assembly_description,
    assemblyVerified: wall.assembly_verified,
    sidesToHang: wall.sides_to_hang,
    layersSideA: wall.layers_side_a,
    layersSideB: wall.layers_side_b,
    heightFt: wall.height_ft,
    heightProvenance: wall.height_provenance,
    grossSf: wall.gross_sf,
    openingDeductionSf: wall.opening_deduction_sf,
    netSf: wall.net_sf,
    qtoEligible: wall.qto_eligible,
    qtoBlockReason: wall.qto_block_reason,
    decisionState: wall.decision_state,
    rejectionReason: wall.rejection_reason,
    evidence: wall.evidence,
    segmentsCount: clippedSegments.length,
    openingsCount: wall.openings_count ?? 0,
    confidence: Math.round((wall.confidence ?? 0) * 100) / 100,
    status: wall.status === "approved" ? "approved" : wall.status === "rejected" ? "rejected" : "pending",
  };
}

// Convert backend Wall (geometry engine output) → frontend Detection.
// A wall is a 2-point segment, drawn as an open polyline rather than a
// closed polygon (DetectionsLayer keys that off `kind`).
export function wallToDetection(wall: BackendWall, sheetId: string): Detection {
  const canonicalCat = normalizeWallClassification(wall.wall_type_code || wall.wall_type);
  const isExterior = canonicalCat === "EXTERIOR_PERIMETER" || wall.wall_type?.toLowerCase() === "exterior";
  const categoryLabel = WALL_CATEGORY_COLORS[canonicalCat]?.label ?? (isExterior ? "Exterior Wall" : "Interior Wall");
  return {
    id: `backend-wall-${wall.id}`,
    sheetId,
    kind: "wall" as const,
    name: `${categoryLabel} (${Math.round(wall.length_ft)} ft${
      wall.thickness_measured ? ` × ${formatWallThickness(wall.thickness_ft)}` : ""
    })`,
    // A wall really is drywall + paint surface, so unlike a room it does
    // carry a single primary trade.
    trade: "drywall",
    points: [
      { x: wall.start_norm.x, y: wall.start_norm.y },
      { x: wall.end_norm.x, y: wall.end_norm.y },
    ],
    areaSqFt: Math.round(wall.area_sqft ?? 0),
    perimeterFt: Math.round(wall.length_ft),
    thicknessFt: wall.thickness_ft,
    thicknessMeasured: wall.thickness_measured ?? false,
    wallType: isExterior ? "exterior" : "interior",
    wallTypeCode: canonicalCat,
    segmentsCount: (wall as any).segments_count ?? 1,
    openingsCount: (wall as any).openings_count ?? 0,
    confidence: Math.round(wall.confidence * 100) / 100,
    status: wall.status === "approved" ? "approved" : wall.status === "rejected" ? "rejected" : "pending",
  };
}


/**
 * Symbol kinds worth rendering from the AI validation pass.
 *
 * That pass also emits `room` and `wall` findings as cross-checks against
 * the geometry engine. Those describe the very same physical rooms and walls
 * already loaded from the rooms/walls tables, so rendering them too would
 * double-draw every room outline on the canvas and double-count nothing
 * useful. Only genuinely new objects — the ones geometry cannot measure
 * because they're symbols rather than enclosed areas — come through here.
 */
const SYMBOL_DETECTION_KINDS = new Set<DetectionKind>([
  "door",
  "window",
  "column",
  "fixture",
  "stairs",
  "annotation",
  "symbol",
  "object",
]);

export function isSymbolDetection(d: BackendDetection): boolean {
  return SYMBOL_DETECTION_KINDS.has(d.kind as DetectionKind);
}

/**
 * Convert a backend AI Detection (door, window, fixture) → frontend Detection.
 *
 * A door is not an area takeoff — it has no meaningful floor area or wall
 * perimeter — so areaSqFt/perimeterFt stay 0 and it contributes nothing to
 * any trade quantity (lib/estimating.ts only sums `kind === "room"`). It is
 * a reviewable annotation on the drawing, which is exactly what the
 * DetectedObjects panel and canvas overlay present it as.
 */
export function symbolToDetection(d: BackendDetection, sheetId: string): Detection {
  let trade: TradeId | null = null;
  const k = d.kind?.toLowerCase();
  if (k === "door" || k === "window") {
    trade = "openings";
  } else if (k === "column") {
    trade = null;
  } else if (k === "stairs") {
    trade = "furniture";
  } else if (k === "fixture" || k === "object" || k === "symbol") {
    // Fixtures and generic objects default to furniture unless the label
    // carries a stronger mechanical/plumbing signal.
    const lbl = (d.label || "").toLowerCase();
    if (lbl.includes("hvac") || lbl.includes("diffuser") || lbl.includes("duct")) {
      trade = "roofing";
    } else if (lbl.includes("toilet") || lbl.includes("sink") || lbl.includes("bath") || lbl.includes("shower")) {
      trade = "flooring"; // plumbing fixtures belong to wet-area flooring trade
    } else {
      trade = "furniture";
    }
  }

  return {
    id: `backend-detection-${d.id}`,
    sheetId,
    kind: d.kind as DetectionKind,
    name: d.label,
    trade,
    points: d.polygon_norm.map(([x, y]) => ({ x, y })),
    areaSqFt: 0,
    perimeterFt: 0,
    confidence: Math.round(d.confidence * 100) / 100,
    status: d.status === "approved" ? "approved" : d.status === "rejected" ? "rejected" : "pending",
  };
}

/**
 * Recover the backend entity type + numeric ID from a frontend Detection's
 * `id` (see roomToDetection/wallToDetection/symbolToDetection above for
 * where the `backend-{source}-{id}` prefix comes from). Used to tell the AI
 * Assistant exactly what's selected on the canvas — "room 4731" rather than
 * an opaque frontend UUID it has no way to resolve. Returns null for
 * non-backend detections (e.g. the client-only sample-data demo path, or a
 * user-drawn measurement), since those have nothing on the server to ask about.
 */
export function parseBackendDetectionId(id: string): { source: "room" | "wall" | "detection" | "archwall"; backendId: number | string } | null {
  const match = /^backend-(room|wall|detection|archwall)-(.+)$/.exec(id);
  if (!match) return null;
  const num = Number(match[2]);
  return { source: match[1] as "room" | "wall" | "detection" | "archwall", backendId: isNaN(num) ? match[2] : num };
}


// A room is not "a drywall room" or "a flooring room" — its floor feeds
// flooring, its walls feed drywall and painting, and its ceiling feeds
// roofing, all simultaneously (which is exactly how lib/estimating.ts
// computes them). So this returns null unless the room's *name* carries a
// genuine trade signal, rather than inventing an attribution that isn't real.
export function inferTrade(name: string): TradeId | null {
  const n = (name || "").toLowerCase();
  if (n.includes("bath") || n.includes("toilet") || n.includes("wc") || n.includes("restroom")) return "flooring";
  if (n.includes("mech") || n.includes("hvac") || n.includes("electric") || n.includes("util")) return "drywall";
  if (n.includes("stair") || n.includes("corridor") || n.includes("lobby") || n.includes("hall")) return "flooring";
  if (n.includes("office") || n.includes("conf") || n.includes("meeting") || n.includes("board")) return "drywall";
  if (n.includes("kitchen") || n.includes("break") || n.includes("cafe") || n.includes("dining")) return "flooring";
  if (n.includes("roof") || n.includes("terrace") || n.includes("penthouse") || n.includes("deck") || n.includes("covered") || n.includes("porch") || n.includes("patio") || n.includes("balcony") || n.includes("attic")) return "roofing";
  if (n.includes("paint") || n.includes("wall") || n.includes("finish")) return "painting";
  return null;
}
