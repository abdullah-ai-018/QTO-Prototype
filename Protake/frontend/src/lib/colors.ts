import type { Detection } from "@/types";

export const TRADE_COLOR: Record<string, string> = {
  flooring: "#3B82F6", // Professional Blue
  drywall: "#8B5CF6",  // Vibrant Purple
  painting: "#EC4899", // Vivid Pink/Rose
  roofing: "#F97316",  // Safety Amber/Orange
  furniture: "#10B981", // Emerald Green
  openings: "#14B8A6",  // Teal for openings
};

export const EXTERIOR_AREA_COLOR = "#F59E0B";

export type CanonicalWallCategory =
  | "INTERIOR_PARTITION"
  | "EXTERIOR_PERIMETER"
  | "STRUCTURAL_BEARING"
  | "STAIR_CORE"
  | "CORRIDOR"
  | "WET_CORE"
  | "DEMISING"
  | "SHAFT"
  | "NEEDS_REVIEW";

export const CANONICAL_WALL_CATEGORIES: CanonicalWallCategory[] = [
  "INTERIOR_PARTITION",
  "EXTERIOR_PERIMETER",
  "STRUCTURAL_BEARING",
  "STAIR_CORE",
  "CORRIDOR",
  "WET_CORE",
  "DEMISING",
  "SHAFT",
  "NEEDS_REVIEW",
];

export const WALL_CATEGORY_COLORS: Record<CanonicalWallCategory, { color: string; label: string; priority: number }> = {
  INTERIOR_PARTITION: { 
    color: "#10B981", 
    label: "Interior Partition", 
    priority: 8 
  },
  EXTERIOR_PERIMETER: { 
    color: "#F97316", 
    label: "Exterior / Perimeter", 
    priority: 6 
  },
  STRUCTURAL_BEARING: { 
    color: "#A855F7", 
    label: "Structural / Bearing", 
    priority: 4 
  },
  STAIR_CORE: { 
    color: "#EAB308", 
    label: "Stair / Core", 
    priority: 2 
  },
  CORRIDOR: { 
    color: "#06B6D4", 
    label: "Corridor Wall", 
    priority: 7 
  },
  WET_CORE: { 
    color: "#3B82F6", 
    label: "Wet Core", 
    priority: 3 
  },
  DEMISING: { 
    color: "#EC4899", 
    label: "Demising Wall", 
    priority: 5 
  },
  SHAFT: { 
    color: "#8B5CF6", 
    label: "Shaft Wall", 
    priority: 1 
  },
  NEEDS_REVIEW: { 
    color: "#94A3B8", 
    label: "Needs Review / Unclassified", 
    priority: 9 
  },
};

// ═══════════════════════════════════════════════════════════════════════════════
// WALL CLASSIFICATION MAPPING LOGIC
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Normalizes any backend wall classification variant to exactly ONE of the 9
 * canonical wall categories. Unknown values return NEEDS_REVIEW.
 */
export function normalizeWallClassification(input?: string | null): CanonicalWallCategory {
  if (!input) return "NEEDS_REVIEW";
  const norm = input.trim().toLowerCase().replace(/[\s\-]+/g, "_");

  switch (norm) {
    case "interior":
    case "interior_wall":
    case "partition":
    case "interior_partition":
    case "drywall_partition":
    case "interior_partition_wall":
      return "INTERIOR_PARTITION";

    case "exterior":
    case "exterior_wall":
    case "perimeter":
    case "perimeter_wall":
    case "curtain_wall":
    case "exterior_perimeter":
    case "exterior_perimeter_wall":
      return "EXTERIOR_PERIMETER";

    case "structural":
    case "bearing":
    case "structural_bearing":
    case "structural_bearing_wall":
    case "masonry":
    case "concrete":
      return "STRUCTURAL_BEARING";

    case "stair":
    case "core":
    case "stair_core":
    case "stair_core_wall":
    case "stairs":
      return "STAIR_CORE";

    case "corridor":
    case "corridor_wall":
      return "CORRIDOR";

    case "wet_core":
    case "wet":
    case "wet_core_wall":
    case "plumbing_chase":
      return "WET_CORE";

    case "demising":
    case "demising_wall":
      return "DEMISING";

    case "shaft":
    case "shaft_wall":
      return "SHAFT";

    case "needs_review":
    case "unclassified":
    case "unknown":
    case "unknown_wall":
    default:
      return "NEEDS_REVIEW";
  }
}

/**
 * Maps backend wall classifications to canonical wall categories.
 * Handles unknown/null classifications by mapping to NEEDS_REVIEW.
 */
export function getCanonicalWallCategory(
  wallTypeCode?: string | null, 
  wallType?: string | null,
  wallTag?: string | null,
  status?: string | null,
  confidence?: number | null,
  classification?: string | null
): CanonicalWallCategory {
  // Low confidence (< 0.70) indicates genuine evidence insufficiency -> forces NEEDS_REVIEW.
  // Note: approval status (pending vs approved vs rejected) is separate from classification
  // and must NEVER override the true canonical category.
  if (confidence != null && confidence < 0.70) {
    return "NEEDS_REVIEW";
  }

  const hasWallTypeCode = !!wallTypeCode;
  const hasClassification = !!classification;

  // 1. Explicit wallTypeCode
  if (hasWallTypeCode) {
    const norm = normalizeWallClassification(wallTypeCode);
    if (norm !== "NEEDS_REVIEW") return norm;
  }

  // 2. Explicit classification
  if (hasClassification) {
    const norm = normalizeWallClassification(classification);
    if (norm !== "NEEDS_REVIEW") return norm;
  }

  // A wallTypeCode or classification value was actually present but did not
  // resolve to a known category — this is a genuinely unresolved wall and
  // must stay NEEDS_REVIEW. It must NOT fall through to the legacy wallType
  // binary check below.
  if (hasWallTypeCode || hasClassification) {
    return "NEEDS_REVIEW";
  }

  // 3. Fallback to legacy wallType — only reached when wallTypeCode AND
  // classification are BOTH genuinely absent/empty.
  if (wallType === "exterior") {
    return "EXTERIOR_PERIMETER";
  }
  if (wallType === "interior") {
    return "INTERIOR_PARTITION";
  }

  return "NEEDS_REVIEW";
}

/**
 * Single authoritative source of truth for wall classification color.
 * Guaranteed to reflect the canonical category, independent of approval state.
 */
export function getWallClassificationColor(
  categoryOrWall?: CanonicalWallCategory | Detection | string | null
): string {
  if (!categoryOrWall) return WALL_CATEGORY_COLORS.NEEDS_REVIEW.color;
  if (typeof categoryOrWall === "object" && "kind" in categoryOrWall) {
    const d = categoryOrWall as Detection;
    if (d.kind === "wall") {
      const cat = getCanonicalWallCategory(
        d.wallTypeCode,
        d.wallType,
        d.wallTag,
        d.status,
        d.confidence,
        d.classification
      );
      return WALL_CATEGORY_COLORS[cat]?.color || WALL_CATEGORY_COLORS.NEEDS_REVIEW.color;
    }
    return KIND_COLOR[d.kind] || (d.trade && TRADE_COLOR[d.trade.toLowerCase()]) || "#3B82F6";
  }
  const norm = normalizeWallClassification(categoryOrWall as string);
  return WALL_CATEGORY_COLORS[norm]?.color || WALL_CATEGORY_COLORS.NEEDS_REVIEW.color;
}

export const KIND_COLOR: Partial<Record<Detection["kind"], string>> = {
  wall: WALL_CATEGORY_COLORS.NEEDS_REVIEW.color,   // fallback for walls with no classification set
  door: "#14B8A6",   // teal
  window: "#38BDF8", // sky
  column: "#A78BFA", // violet
  fixture: "#F472B6", // pink
  stairs: "#F97316", // orange
  annotation: "#94A3B8", // muted grey
  symbol: "#FBBF24",
  object: "#FBBF24",
};

export const COLOR_NAMES: Record<string, string> = {
  "#3B82F6": "Blue",
  "#8B5CF6": "Purple",
  "#EC4899": "Pink",
  "#F97316": "Orange",
  "#F59E0B": "Amber",
  "#14B8A6": "Teal",
  "#38BDF8": "Sky Blue",
  "#A78BFA": "Violet",
  "#F472B6": "Pink",
  "#A3E635": "Lime",
  "#94A3B8": "Grey",
  "#FBBF24": "Yellow",
  "#10B981": "Emerald",
  "#22C55E": "Green",
  "#A855F7": "Purple",
  "#EAB308": "Yellow",
  "#06B6D4": "Cyan",
  "#EF4444": "Red",
};

export function getDetectionColor(d: Detection): string {
  if (d.roomType === "exterior_covered") {
    return EXTERIOR_AREA_COLOR;
  }
  if (d.kind === "wall") {
    const canonicalCategory = getCanonicalWallCategory(
      d.wallTypeCode, 
      d.wallType, 
      d.wallTag, 
      d.status, 
      d.confidence,
      d.classification
    );
    return WALL_CATEGORY_COLORS[canonicalCategory]?.color || WALL_CATEGORY_COLORS.NEEDS_REVIEW.color;
  }
  return KIND_COLOR[d.kind] || (d.trade && TRADE_COLOR[d.trade.toLowerCase()]) || "#3B82F6";
}

export function getColorName(hex: string): string {
  return COLOR_NAMES[hex.toUpperCase()] || hex;
}
