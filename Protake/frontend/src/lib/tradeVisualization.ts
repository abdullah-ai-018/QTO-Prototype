import type { Detection } from "@/types";
import { boundingBoxDimensionsFt, DEFAULT_SCALE } from "@/lib/geometry";

// Round to nearest 0.5 ft so minor detection variance (e.g. 2.9 vs 3.1 ft)
// doesn't create spurious unique groups. Standard door widths cluster at
// 2.0, 2.5, 3.0, 3.5 ft — 0.5 ft buckets capture that without over-splitting.
function snapToHalfFt(v: number): number {
  return Math.round(v * 2) / 2;
}

export function getDoorWindowCodes(detections: Detection[], calibration: Record<string, number>): Record<string, string> {
  const doors = detections.filter((d) => d.kind === "door");
  const windows = detections.filter((d) => d.kind === "window");

  const getSortedSizes = (items: Detection[]) => {
    const sizeMap = new Map<string, { width: number; height: number }>();
    items.forEach((d) => {
      const scale = calibration[d.sheetId] ?? DEFAULT_SCALE;
      const bbox = boundingBoxDimensionsFt(d.points, scale);
      const w = snapToHalfFt(bbox.widthFt);
      const h = snapToHalfFt(bbox.heightFt);
      const key = `${w.toFixed(1)}x${h.toFixed(1)}`;
      sizeMap.set(key, { width: w, height: h });
    });

    return Array.from(sizeMap.entries())
      .sort((a, b) => b[1].width - a[1].width || b[1].height - a[1].height)
      .map(([key]) => key);
  };

  const doorSizes = getSortedSizes(doors);
  const windowSizes = getSortedSizes(windows);

  const codes: Record<string, string> = {};
  doors.forEach((d) => {
    // Prefer an OCR-read code embedded in the label name
    const codeMatch = d.name.match(/\b(D\d{1,2}[A-Z]?|WD\d{1,2}[A-Z]?)\b/i);
    if (codeMatch) {
      codes[d.id] = codeMatch[1].toUpperCase();
      return;
    }

    const scale = calibration[d.sheetId] ?? DEFAULT_SCALE;
    const bbox = boundingBoxDimensionsFt(d.points, scale);
    const w = snapToHalfFt(bbox.widthFt);
    const h = snapToHalfFt(bbox.heightFt);
    const key = `${w.toFixed(1)}x${h.toFixed(1)}`;
    const idx = doorSizes.indexOf(key);
    if (idx !== -1) {
      codes[d.id] = `D${idx + 1}`;
    }
  });

  windows.forEach((d) => {
    const codeMatch = d.name.match(/\b(W\d{1,2}[A-Z]?)\b/i);
    if (codeMatch) {
      codes[d.id] = codeMatch[1].toUpperCase();
      return;
    }

    const scale = calibration[d.sheetId] ?? DEFAULT_SCALE;
    const bbox = boundingBoxDimensionsFt(d.points, scale);
    const w = snapToHalfFt(bbox.widthFt);
    const h = snapToHalfFt(bbox.heightFt);
    const key = `${w.toFixed(1)}x${h.toFixed(1)}`;
    const idx = windowSizes.indexOf(key);
    if (idx !== -1) {
      codes[d.id] = `W${idx + 1}`;
    }
  });

  return codes;
}

/**
 * Which detection kinds render on the canvas for a given active trade tab
 * — the frontend-only visualization split requested for each trade
 * (see DetectionsLayer.tsx). This never touches the shared Room/Wall
 * geometry itself or any trade quantity calculation: it only decides
 * what's drawn.
 *
 * - Drywall/Painting: wall runs are the primary evidence, so walls +
 *   doors/windows (the openings that get deducted from wall area) render;
 *   room polygons still render (for context / selection) but see
 *   `shouldDeemphasizeRoom` below — they're drawn de-emphasized, not
 *   filled, by default.
 * - Flooring: rooms ARE the primary evidence (floor area), so they
 *   render at full prominence, same as before.
 * - Roofing: no dedicated roof-plane geometry reaches the frontend yet
 *   (that would be a backend/data change, out of scope here) — rooms
 *   still render as the only available spatial context, but de-emphasized
 *   for the same reason as drywall/painting: a filled room polygon isn't
 *   actually roofing evidence.
 * - Furniture/Openings: unchanged — filtered to their own tagged trade.
 * - No active trade tab (Labor/Costs/Grid, or nothing selected): show
 *   everything, matching the existing general/default view.
 */
export function isVisibleForActiveTrade(
  d: Pick<Detection, "kind" | "trade" | "roomType">,
  activeTradeId: string | null
): boolean {
  if (!activeTradeId) return true;

  if (activeTradeId === "furniture") {
    return d.trade === "furniture";
  }
  if (activeTradeId === "painting" || activeTradeId === "drywall") {
    return (
      d.kind === "wall" ||
      d.kind === "door" ||
      d.kind === "window" ||
      (d.kind === "room" && d.roomType !== "exterior_covered")
    );
  }
  if (activeTradeId === "flooring" || activeTradeId === "roofing") {
    return d.kind === "room" || d.trade === activeTradeId;
  }
  if (activeTradeId === "openings") {
    return d.trade === "openings";
  }
  return true;
}

/**
 * Trade views where a filled/prominent room polygon is NOT the trade's
 * primary evidence — wall runs (drywall/painting) or (eventually) actual
 * roof-plane geometry (roofing) are. Flooring is deliberately absent:
 * room floor area IS its primary takeoff evidence, so rooms stay fully
 * visible there, same as the general/default view.
 */
export const ROOM_DEEMPHASIZED_TRADES: ReadonlySet<string> = new Set(["drywall", "painting", "roofing"]);

/**
 * Whether a room polygon should render de-emphasized (no fill, a faint
 * outline only, small label) instead of the full trade-colored wash.
 * Never hides the room or removes it from the canonical geometry — it
 * stays selectable and editable, just visually quiet by default so it
 * doesn't read as "this filled colored area is this trade's takeoff."
 * The Geometry/Rooms toggle (`showRoomGeometry`) opts back into the full
 * view for any trade.
 */
export function shouldDeemphasizeRoom(
  d: Pick<Detection, "kind">,
  activeTradeId: string | null,
  showRoomGeometry: boolean
): boolean {
  if (d.kind !== "room") return false;
  if (!activeTradeId) return false;
  if (showRoomGeometry) return false;
  return ROOM_DEEMPHASIZED_TRADES.has(activeTradeId);
}
