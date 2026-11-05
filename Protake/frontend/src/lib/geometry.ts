import type { Point } from "@/types";

export function toPixelPoints(points: Point[], w: number, h: number): number[] {
  return points.flatMap((p) => [p.x * w, p.y * h]);
}

export function pixelToNormalized(x: number, y: number, w: number, h: number): Point {
  return { x: x / w, y: y / h };
}

export function polygonArea(points: Point[]): number {
  let area = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    area += a.x * b.y - b.x * a.y;
  }
  return Math.abs(area / 2);
}

export function polygonPerimeter(points: Point[]): number {
  let perim = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    perim += Math.hypot(b.x - a.x, b.y - a.y);
  }
  return perim;
}

export function linearLength(points: Point[]): number {
  let len = 0;
  for (let i = 1; i < points.length; i++) {
    len += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
  }
  return len;
}

export function centroid(points: Point[]): Point {
  const n = points.length || 1;
  const sum = points.reduce((acc, p) => ({ x: acc.x + p.x, y: acc.y + p.y }), { x: 0, y: 0 });
  return { x: sum.x / n, y: sum.y / n };
}

export const BASE_W = 1920;
export const BASE_H = 1200;
export const DEFAULT_SCALE = 220; // ft per normalized unit (1.0 -> 1.0 spans DEFAULT_SCALE ft)

/**
 * Real-world width/height of a detection's bounding box, in feet — the
 * "complete dimensions" a click on any object (room, wall, door, window,
 * fixture, ...) should show, not just its derived area/perimeter. `scale`
 * is feet-per-normalized-unit for the sheet the object lives on (see
 * BlueprintWorkspace.tsx's own `scale` — calibrated per sheet, or
 * DEFAULT_SCALE as the same nominal fallback every measurement tool uses).
 * This is the object's axis-aligned bounding box, not its true footprint —
 * exact for a rectangular symbol (door, window, most fixtures), an upper
 * bound for an irregular polygon (an L-shaped room's bbox is bigger than
 * the room itself).
 */
export function boundingBoxDimensionsFt(points: Point[], scale: number): { widthFt: number; heightFt: number } {
  if (points.length === 0) return { widthFt: 0, heightFt: 0 };
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const widthNorm = Math.max(...xs) - Math.min(...xs);
  const heightNorm = Math.max(...ys) - Math.min(...ys);
  return { widthFt: widthNorm * scale, heightFt: heightNorm * scale };
}

export function snapValue(v: number, enabled: boolean, step = 0.01): number {
  if (!enabled) return v;
  return Math.round(v / step) * step;
}
