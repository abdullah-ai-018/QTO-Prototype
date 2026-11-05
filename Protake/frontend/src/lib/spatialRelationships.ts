/**
 * lib/spatialRelationships.ts
 *
 * Single source of truth for wall↔room↔fixture spatial-adjacency queries.
 * All results are derived from real detected/drawn polygon geometry
 * (point-in-polygon / distance-to-segment tests) — never fabricated or
 * defaulted to empty arrays as a placeholder.
 *
 * Used by lib/wallInspectorModel.ts (wall inspector panels) and
 * state/DataScopeContext.tsx (WallScope/RoomScope relationship fields) so
 * both consume the exact same adjacency logic.
 */

import type { Detection, Point } from "@/types";

const BORDER_TOLERANCE = 0.02; // normalized-unit distance treated as "touching"
const OPENING_WALL_TOLERANCE = 0.03; // normalized-unit distance treated as "on this wall"

/** Distance from point `p` to line segment `v`-`w`, in normalized coords. */
export function distToSegment(p: Point, v: Point, w: Point): number {
  const l2 = (v.x - w.x) ** 2 + (v.y - w.y) ** 2;
  if (l2 === 0) return Math.hypot(p.x - v.x, p.y - v.y);
  let t = ((p.x - v.x) * (w.x - v.x) + (p.y - v.y) * (w.y - v.y)) / l2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(p.x - (v.x + t * (w.x - v.x)), p.y - (v.y + t * (w.y - v.y)));
}

/** Point-in-polygon test (ray casting), normalized coords. */
export function pointInPolygon(p: Point, vs: Point[]): boolean {
  let inside = false;
  for (let i = 0, j = vs.length - 1; i < vs.length; j = i++) {
    const xi = vs[i].x, yi = vs[i].y;
    const xj = vs[j].x, yj = vs[j].y;
    const intersect = ((yi > p.y) !== (yj > p.y)) && (p.x < (xj - xi) * (p.y - yi) / (yj - yi) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

function midpointOf(points: Point[]): Point | null {
  if (points.length < 2) return null;
  return { x: (points[0].x + points[1].x) / 2, y: (points[0].y + points[1].y) / 2 };
}

function bordersRoom(refPoint: Point, room: Detection): boolean {
  if (!room.points || room.points.length < 3) return false;
  if (pointInPolygon(refPoint, room.points)) return true;
  for (let i = 0; i < room.points.length; i++) {
    const p1 = room.points[i];
    const p2 = room.points[(i + 1) % room.points.length];
    if (distToSegment(refPoint, p1, p2) < BORDER_TOLERANCE) return true;
  }
  return false;
}

/**
 * Rooms whose polygon touches or contains the wall's midpoint, on the same
 * sheet. Order is not guaranteed to be "left"/"right" — callers that need a
 * side label should treat index [0]/[1] as "first"/"second" bordering room.
 */
export function findBorderingRooms(wall: Detection, allDetections: Detection[]): Detection[] {
  if (!wall.points || wall.points.length < 2) return [];
  const midPoint = midpointOf(wall.points);
  if (!midPoint) return [];
  const rooms = allDetections.filter(
    (d) => d.sheetId === wall.sheetId && d.kind === "room" && d.status !== "rejected" && d.points?.length >= 3,
  );
  return rooms.filter((r) => bordersRoom(midPoint, r));
}

/** Walls whose midpoint touches or falls inside this room's polygon. */
export function findBorderingWalls(room: Detection, allDetections: Detection[]): Detection[] {
  if (!room.points || room.points.length < 3) return [];
  const walls = allDetections.filter(
    (d) => d.sheetId === room.sheetId && d.kind === "wall" && d.status !== "rejected",
  );
  return walls.filter((w) => {
    const mid = midpointOf(w.points);
    return mid ? bordersRoom(mid, room) : false;
  });
}

/** Fixtures (kind === "fixture") whose centroid falls inside this room. */
export function findContainedFixtures(room: Detection, allDetections: Detection[]): Detection[] {
  if (!room.points || room.points.length < 3) return [];
  const fixtures = allDetections.filter(
    (d) => d.sheetId === room.sheetId && d.kind === "fixture" && d.status !== "rejected" && d.points?.length > 0,
  );
  return fixtures.filter((f) => {
    const cx = f.points.reduce((s, p) => s + p.x, 0) / f.points.length;
    const cy = f.points.reduce((s, p) => s + p.y, 0) / f.points.length;
    return pointInPolygon({ x: cx, y: cy }, room.points);
  });
}

/**
 * Rooms adjacent to `room` — defined as sharing at least one bordering wall.
 * Excludes `room` itself.
 */
export function findAdjacentRooms(room: Detection, allDetections: Detection[]): Detection[] {
  const sharedWalls = findBorderingWalls(room, allDetections);
  const seen = new Set<string>();
  const adjacent: Detection[] = [];
  for (const wall of sharedWalls) {
    const roomsOnWall = findBorderingRooms(wall, allDetections);
    for (const r of roomsOnWall) {
      if (r.id === room.id || seen.has(r.id)) continue;
      seen.add(r.id);
      adjacent.push(r);
    }
  }
  return adjacent;
}

/**
 * The wall whose centerline passes closest to an opening's (door/window)
 * centroid, on the same sheet, within tolerance. Null if no wall is close
 * enough to be confidently identified as the host wall — callers must show
 * "Not available from source" rather than guessing.
 */
export function findParentWall(opening: Detection, allDetections: Detection[]): Detection | null {
  if (!opening.points || opening.points.length === 0) return null;
  const centroid: Point = {
    x: opening.points.reduce((s, p) => s + p.x, 0) / opening.points.length,
    y: opening.points.reduce((s, p) => s + p.y, 0) / opening.points.length,
  };
  const walls = allDetections.filter(
    (d) => d.sheetId === opening.sheetId && d.kind === "wall" && d.status !== "rejected" && d.points?.length >= 2,
  );

  let closest: Detection | null = null;
  let closestDist = Infinity;
  for (const wall of walls) {
    for (let i = 0; i < wall.points.length - 1; i++) {
      const dist = distToSegment(centroid, wall.points[i], wall.points[i + 1]);
      if (dist < closestDist) {
        closestDist = dist;
        closest = wall;
      }
    }
  }
  return closestDist < OPENING_WALL_TOLERANCE ? closest : null;
}
