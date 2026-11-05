import type { Detection, TradeId, TradeMetrics } from "@/types";

// Simplified but internally consistent estimating rules per trade.
// All quantities derive from APPROVED detection area/perimeter only.

export const TRADE_LABOR_RATES: Record<TradeId, number> = {
  drywall: 42,
  painting: 38,
  flooring: 40,
  roofing: 45,
  furniture: 42,
  openings: 45,
};

export const WASTE_FACTOR = 1.1;

/**
 * User-configurable drywall assembly assumptions (see components/common/
 * SettingsModal.tsx). Not hardcoded per the takeoff's own requirement —
 * different assemblies (residential vs. commercial vs. a custom spec) hang
 * drywall on a different number of wall faces, so the sides-per-wall-type
 * multiplier has to be a setting, not a constant.
 */
export interface DrywallSettings {
  wallHeightFt: number;
  internalWallSides: number;
  externalWallSides: number;
}

export const DEFAULT_DRYWALL_SETTINGS: DrywallSettings = {
  wallHeightFt: 9,
  internalWallSides: 2,
  externalWallSides: 1,
};

export interface DrywallWallTypeDetail {
  linearFeet: number;
  heightFt: number;
  sides: number;
  areaSqFt: number;
}

export interface TradeBreakdown {
  trade: TradeId;
  metrics: TradeMetrics;
  lineItems: { label: string; qty: number; unit: string }[];
  // Drywall only — the internal/external LF × height × sides breakdown
  // requirement #6 asks the UI to render as a dedicated summary, not just
  // buried in the generic line-items table.
  drywallDetail?: {
    internal: DrywallWallTypeDetail;
    external: DrywallWallTypeDetail;
    totalAreaSqFt: number;
  };
}

/**
 * Rooms that count toward a trade's quantities.
 */
function activeRooms(detections: Detection[]) {
  return detections.filter((d) => d.status !== "rejected" && (d.kind === "room" || !d.kind));
}

/** A covered exterior area (porch/deck) — real floor and roof, but no walls. */
export const EXTERIOR_AREA_ROOM_TYPE = "exterior_covered";

function isExteriorArea(d: Detection) {
  return d.roomType === EXTERIOR_AREA_ROOM_TYPE;
}

/**
 * Rooms with actual enclosing walls.
 */
function walledRooms(detections: Detection[]) {
  return activeRooms(detections).filter((d) => !isExteriorArea(d));
}

/**
 * Drywall takeoff, aligned with backend DrywallEngine & TradeConfig defaults.
 */
export function computeDrywall(detections: Detection[], settings: DrywallSettings = DEFAULT_DRYWALL_SETTINGS): TradeBreakdown {
  const walls = detections.filter((d) => d.status !== "rejected" && d.kind === "wall");
  const hasBackendQto = walls.some((w) => w.grossSf !== undefined && w.netSf !== undefined);

  let internalLF = 0;
  let externalLF = 0;
  let grossWallAreaSqFt = 0;
  let totalOpeningDeductionsSqFt = 0;
  let netWallAreaSqFt = 0;
  let internalGrossAreaSqFt = 0;
  let externalGrossAreaSqFt = 0;

  if (hasBackendQto) {
    // Single source of truth: directly consume backend canonical architectural wall QTO
    for (const w of walls) {
      if (w.qtoEligible === false || w.status === "rejected") continue;
      const isInternal = w.wallType === "interior";
      const lf = w.perimeterFt || 0;
      const gross = w.grossSf ?? 0;
      const ded = w.openingDeductionSf ?? 0;
      const net = w.netSf ?? Math.max(0, gross - ded);

      if (isInternal) {
        internalLF += lf;
        internalGrossAreaSqFt += gross;
      } else {
        externalLF += lf;
        externalGrossAreaSqFt += gross;
      }
      grossWallAreaSqFt += gross;
      totalOpeningDeductionsSqFt += ded;
      netWallAreaSqFt += net;
    }
    internalLF = Math.round(internalLF);
    externalLF = Math.round(externalLF);
    internalGrossAreaSqFt = Math.round(internalGrossAreaSqFt);
    externalGrossAreaSqFt = Math.round(externalGrossAreaSqFt);
    grossWallAreaSqFt = Math.round(grossWallAreaSqFt);
    totalOpeningDeductionsSqFt = Math.round(totalOpeningDeductionsSqFt);
    netWallAreaSqFt = Math.round(netWallAreaSqFt);
  } else {
    // Fallback heuristic for ad-hoc user sketches
    const internalWalls = walls.filter((w) => w.wallType === "interior");
    const externalWalls = walls.filter((w) => w.wallType !== "interior");

    internalLF = Math.round(internalWalls.reduce((sum, w) => sum + (w.perimeterFt || 0), 0));
    externalLF = Math.round(externalWalls.reduce((sum, w) => sum + (w.perimeterFt || 0), 0));

    internalGrossAreaSqFt = Math.round(internalLF * settings.wallHeightFt * settings.internalWallSides);
    externalGrossAreaSqFt = Math.round(externalLF * settings.wallHeightFt * settings.externalWallSides);
    grossWallAreaSqFt = internalGrossAreaSqFt + externalGrossAreaSqFt;

    // Opening deductions (doors & windows)
    const doors = detections.filter((d) => d.status !== "rejected" && d.kind === "door");
    const windows = detections.filter((d) => d.status !== "rejected" && d.kind === "window");
    const doorDeductionSqFt = Math.round(doors.length * 3.15 * 7.0 * settings.internalWallSides);
    const windowDeductionSqFt = Math.round(windows.length * 4.80 * 4.5 * settings.externalWallSides);
    totalOpeningDeductionsSqFt = doorDeductionSqFt + windowDeductionSqFt;

    netWallAreaSqFt = Math.max(0, grossWallAreaSqFt - totalOpeningDeductionsSqFt);
  }

  // Ceiling drywall inclusion (matching backend DrywallEngine)
  const ceilingRooms = activeRooms(detections);
  const ceilingAreaSqFt = Math.round(ceilingRooms.reduce((sum, r) => sum + (r.areaSqFt || 0), 0));
  const totalDrywallAreaSqFt = netWallAreaSqFt + ceilingAreaSqFt;

  const sheets = Math.ceil((totalDrywallAreaSqFt * WASTE_FACTOR) / 32); // 4x8 sheets = 32 sqft
  const compoundBuckets = Math.ceil(totalDrywallAreaSqFt / 370); // 370 sqft/bucket
  const screws = sheets * 32;
  const hangHours = totalDrywallAreaSqFt / 55;
  const finishHours = totalDrywallAreaSqFt / 90;
  const laborHours = Math.round((hangHours + finishHours) * 10) / 10;
  const laborRate = TRADE_LABOR_RATES.drywall;
  const directCost = Math.round(sheets * 14.5 + compoundBuckets * 22 + screws * 0.032 + laborHours * laborRate);
  return {
    trade: "drywall",
    metrics: { materialQuantity: sheets, materialUnit: "sheets", laborHours, directCost },
    lineItems: [
      { label: "Internal Wall Linear Feet", qty: internalLF, unit: "LF" },
      { label: "External Wall Linear Feet", qty: externalLF, unit: "LF" },
      { label: "Gross Wall Area", qty: grossWallAreaSqFt, unit: "sq ft" },
      { label: "Opening Deductions", qty: totalOpeningDeductionsSqFt, unit: "sq ft" },
      { label: "Net Wall Drywall Subtotal", qty: netWallAreaSqFt, unit: "sq ft" },
      { label: "Ceiling Drywall Subtotal", qty: ceilingAreaSqFt, unit: "sq ft" },
      { label: "Total Drywall Surface Area", qty: totalDrywallAreaSqFt, unit: "sq ft" },
      { label: "Drywall Sheets (4x8)", qty: sheets, unit: "sheets" },
      { label: "Joint Compound", qty: compoundBuckets, unit: "buckets" },
      { label: "Screws", qty: screws, unit: "pcs" },
      { label: "Labor", qty: laborHours, unit: "hrs" },
    ],
    drywallDetail: {
      internal: { linearFeet: internalLF, heightFt: settings.wallHeightFt, sides: settings.internalWallSides, areaSqFt: internalGrossAreaSqFt },
      external: { linearFeet: externalLF, heightFt: settings.wallHeightFt, sides: settings.externalWallSides, areaSqFt: externalGrossAreaSqFt },
      totalAreaSqFt: totalDrywallAreaSqFt,
    },
  };
}

export function computePainting(detections: Detection[]): TradeBreakdown {
  const rooms = walledRooms(detections);
  const baseWallArea = rooms.reduce((sum, d) => sum + d.perimeterFt * 9, 0);

  const doorsCount = detections.filter((d) => d.status !== "rejected" && d.kind === "door").length;
  const windowsCount = detections.filter((d) => d.status !== "rejected" && d.kind === "window").length;

  const doorArea = doorsCount * 21; // Standard door: 3ft x 7ft = 21 sq ft
  const windowArea = windowsCount * 15; // Standard window: 3ft x 5ft = 15 sq ft

  const wallAreaSqFt = Math.max(0, baseWallArea - doorArea - windowArea);
  const gallons = Math.ceil((wallAreaSqFt * 1.05) / 350); // 5% waste factor, 350 sqft/gal coverage
  const primerGallons = Math.ceil(wallAreaSqFt / 400);
  const laborHours = Math.round((wallAreaSqFt / 150) * 10) / 10;
  const laborRate = TRADE_LABOR_RATES.painting;
  const directCost = Math.round(gallons * 38 + primerGallons * 29 + laborHours * laborRate);
  return {
    trade: "painting",
    metrics: { materialQuantity: gallons, materialUnit: "gal", laborHours, directCost },
    lineItems: [
      { label: "Paintable Wall Surface", qty: wallAreaSqFt, unit: "sq ft" },
      { label: "Paint Gallons", qty: gallons, unit: "gal" },
      { label: "Primer Gallons", qty: primerGallons, unit: "gal" },
      { label: "Labor", qty: laborHours, unit: "hrs" },
    ],
  };
}

export function computeFlooring(detections: Detection[]): TradeBreakdown {
  const rooms = activeRooms(detections);
  const areaSqFt = Math.round(rooms.reduce((sum, d) => sum + d.areaSqFt, 0) * 100) / 100;
  const directCost = Math.round(areaSqFt * 3.5);
  return {
    trade: "flooring",
    metrics: { materialQuantity: areaSqFt, materialUnit: "sqft", laborHours: 0, directCost },
    lineItems: [
      { label: "Net Flooring Surface Area", qty: areaSqFt, unit: "sqft" },
    ],
  };
}

export function computeRoofing(detections: Detection[]): TradeBreakdown {
  const rooms = activeRooms(detections);
  
  let slopedAreaSqFt = 0;
  rooms.forEach((d) => {
    const nameLower = d.name.toLowerCase();
    let pitchFactor = 1.0;
    
    const pitchMatch = nameLower.match(/(\d+(?:\.\d+)?)\s*:\s*12/);
    if (pitchMatch) {
      const rise = parseFloat(pitchMatch[1]);
      pitchFactor = Math.sqrt(1 + Math.pow(rise / 12, 2));
    } else if (nameLower.includes("roof") || nameLower.includes("terrace") || nameLower.includes("slope")) {
      pitchFactor = 1.118;
    }
    slopedAreaSqFt += d.areaSqFt * pitchFactor;
  });

  const areaSqFt = Math.round(slopedAreaSqFt);
  const squares = Math.ceil((areaSqFt * 1.12) / 100); // 12% waste, roofing square = 100 sqft
  const laborHours = Math.round((squares / 0.6) * 10) / 10;
  const laborRate = TRADE_LABOR_RATES.roofing;
  const directCost = Math.round(squares * 240 + laborHours * laborRate);
  return {
    trade: "roofing",
    metrics: { materialQuantity: squares, materialUnit: "sq", laborHours, directCost },
    lineItems: [
      { label: "Sloped Ceiling / Roof Area", qty: areaSqFt, unit: "sq ft" },
      { label: "Roofing Squares", qty: squares, unit: "sq" },
      { label: "Labor", qty: laborHours, unit: "hrs" },
    ],
  };
}

export function computeFurniture(detections: Detection[]): TradeBreakdown {
  const items = detections.filter(
    (d) => d.status !== "rejected" && d.trade === "furniture" && (d.kind === "fixture" || d.kind === "object" || d.kind === "symbol")
  );
  const count = items.length;
  const laborHours = Math.round(count * 0.75 * 10) / 10;
  const laborRate = TRADE_LABOR_RATES.furniture;
  const directCost = Math.round(count * 320 + laborHours * laborRate);
  return {
    trade: "furniture",
    metrics: { materialQuantity: count, materialUnit: "items", laborHours, directCost },
    lineItems: [
      { label: "Furniture Items Detected", qty: count, unit: "pcs" },
      { label: "Assembly Labor", qty: laborHours, unit: "hrs" },
    ],
  };
}

export function computeOpenings(detections: Detection[]): TradeBreakdown {
  const doors = detections.filter((d) => d.status !== "rejected" && d.kind === "door");
  const windows = detections.filter((d) => d.status !== "rejected" && d.kind === "window");
  
  const doorCount = doors.length;
  const windowCount = windows.length;
  const totalCount = doorCount + windowCount;
  
  const laborHours = Math.round((doorCount * 2.0 + windowCount * 1.5) * 10) / 10;
  const laborRate = TRADE_LABOR_RATES.openings;
  const directCost = Math.round(doorCount * 450 + windowCount * 350 + laborHours * laborRate);
  
  return {
    trade: "openings",
    metrics: { materialQuantity: totalCount, materialUnit: "items", laborHours, directCost },
    lineItems: [
      { label: "Exterior / Interior Doors", qty: doorCount, unit: "pcs" },
      { label: "Glazed Window Assemblies", qty: windowCount, unit: "pcs" },
      { label: "Total Openings", qty: totalCount, unit: "pcs" },
      { label: "Installation Labor", qty: laborHours, unit: "hrs" },
    ],
  };
}

export function computeAllTrades(
  detections: Detection[],
  drywallSettings: DrywallSettings = DEFAULT_DRYWALL_SETTINGS,
  activeTrade?: TradeId | null
): Record<TradeId, TradeBreakdown> {
  const result = {} as Record<TradeId, TradeBreakdown>;

  if (!activeTrade || activeTrade === "drywall") {
    result.drywall = computeDrywall(detections, drywallSettings);
  } else {
    result.drywall = { trade: "drywall", metrics: { materialQuantity: 0, materialUnit: "sheets", laborHours: 0, directCost: 0 }, lineItems: [] };
  }

  if (!activeTrade || activeTrade === "painting") {
    result.painting = computePainting(detections);
  } else {
    result.painting = { trade: "painting", metrics: { materialQuantity: 0, materialUnit: "gal", laborHours: 0, directCost: 0 }, lineItems: [] };
  }

  if (!activeTrade || activeTrade === "flooring") {
    result.flooring = computeFlooring(detections);
  } else {
    result.flooring = { trade: "flooring", metrics: { materialQuantity: 0, materialUnit: "sqft", laborHours: 0, directCost: 0 }, lineItems: [] };
  }

  if (!activeTrade || activeTrade === "roofing") {
    result.roofing = computeRoofing(detections);
  } else {
    result.roofing = { trade: "roofing", metrics: { materialQuantity: 0, materialUnit: "sq", laborHours: 0, directCost: 0 }, lineItems: [] };
  }

  if (!activeTrade || activeTrade === "furniture") {
    result.furniture = computeFurniture(detections);
  } else {
    result.furniture = { trade: "furniture", metrics: { materialQuantity: 0, materialUnit: "items", laborHours: 0, directCost: 0 }, lineItems: [] };
  }

  if (!activeTrade || activeTrade === "openings") {
    result.openings = computeOpenings(detections);
  } else {
    result.openings = { trade: "openings", metrics: { materialQuantity: 0, materialUnit: "items", laborHours: 0, directCost: 0 }, lineItems: [] };
  }

  return result;
}

export interface CostSummary {
  materialCost: number;
  laborCost: number;
  overhead: number;
  profit: number;
  contingency: number;
  finalBid: number;
  totalLaborHours: number;
}

export function computeCostSummary(breakdowns: Record<TradeId, TradeBreakdown>, focusedTradeId?: TradeId | null): CostSummary {
  const trades = Object.values(breakdowns).filter((t) => !focusedTradeId || t.trade === focusedTradeId);
  const laborCost = Math.round(trades.reduce((s, t) => s + t.metrics.laborHours * (TRADE_LABOR_RATES[t.trade] || 42), 0));
  const directCost = trades.reduce((s, t) => s + t.metrics.directCost, 0);
  const materialCost = Math.max(directCost - laborCost, 0);
  const overhead = Math.round(directCost * 0.12); // 12% Overhead (matches backend EstimateGenerateRequest)
  const contingency = Math.round(directCost * 0.05); // 5% Contingency
  const profit = Math.round((directCost + overhead + contingency) * 0.15); // 15% Profit
  const finalBid = Math.round(directCost + overhead + contingency + profit);
  const totalLaborHours = Math.round(trades.reduce((s, t) => s + t.metrics.laborHours, 0) * 10) / 10;
  return { materialCost, laborCost, overhead, profit, contingency, finalBid, totalLaborHours };
}

