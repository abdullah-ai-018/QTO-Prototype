import type { Detection, HistoryEntry, RoomNode, Sheet, TradeId } from "@/types";

export const SAMPLE_SHEETS: Sheet[] = [
  { id: "sheet-a101", name: "Floor Plan", code: "A101", pageIndex: 0 },
  { id: "sheet-a102", name: "Ceiling Plan", code: "A102", pageIndex: 1 },
  { id: "sheet-a103", name: "Details", code: "A103", pageIndex: 2 },
];

export const SAMPLE_ROOMS: RoomNode[] = [
  { id: "room-lobby", name: "Lobby" },
  { id: "room-conf", name: "Conference Room" },
  { id: "room-office", name: "Office" },
  { id: "room-restroom", name: "Restroom" },
];

export const TRADES: { id: TradeId; label: string }[] = [
  { id: "drywall", label: "Drywall" },
  { id: "painting", label: "Painting" },
  { id: "flooring", label: "Flooring" },
  { id: "roofing", label: "Roofing" },
  { id: "furniture", label: "Furniture" },
  { id: "openings", label: "Openings" },
];

function poly(cx: number, cy: number, w: number, h: number) {
  return [
    { x: cx - w / 2, y: cy - h / 2 },
    { x: cx + w / 2, y: cy - h / 2 },
    { x: cx + w / 2, y: cy + h / 2 },
    { x: cx - w / 2, y: cy + h / 2 },
  ];
}

function polyMetrics(points: { x: number; y: number }[], scale: number) {
  // shoelace on normalized coords, scale to sq ft via a nominal sheet scale
  let area = 0;
  let perim = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    area += a.x * b.y - b.x * a.y;
    perim += Math.hypot(b.x - a.x, b.y - a.y);
  }
  area = Math.abs(area / 2);
  return {
    areaSqFt: Math.round(area * scale * scale),
    perimeterFt: Math.round(perim * scale),
  };
}

const SCALE = 220; // nominal ft per normalized unit, tuned for demo sizes

export function generateSampleDetections(sheetId: string): Detection[] {
  const specs: {
    name: string;
    trade: TradeId;
    cx: number;
    cy: number;
    w: number;
    h: number;
    kind: Detection["kind"];
    confidence: number;
    wallType?: "interior" | "exterior";
  }[] = [
      { name: "Lobby", trade: "flooring", cx: 0.22, cy: 0.28, w: 0.28, h: 0.32, kind: "room", confidence: 0.97 },
      { name: "Conference Room", trade: "drywall", cx: 0.62, cy: 0.24, w: 0.24, h: 0.22, kind: "room", confidence: 0.93 },
      { name: "Office 104", trade: "painting", cx: 0.78, cy: 0.58, w: 0.18, h: 0.24, kind: "room", confidence: 0.88 },
      { name: "Restroom", trade: "flooring", cx: 0.34, cy: 0.72, w: 0.14, h: 0.16, kind: "room", confidence: 0.91 },
      { name: "Corridor Wall", trade: "drywall", cx: 0.5, cy: 0.48, w: 0.22, h: 0.005, kind: "wall", confidence: 0.85, wallType: "interior" },
      { name: "Exterior Wall North", trade: "roofing", cx: 0.5, cy: 0.06, w: 0.9, h: 0.005, kind: "wall", confidence: 0.81, wallType: "exterior" },
      { name: "HVAC Diffuser", trade: "roofing", cx: 0.6, cy: 0.4, w: 0.03, h: 0.03, kind: "object", confidence: 0.72 },
      { name: "Office Desk", trade: "furniture", cx: 0.78, cy: 0.65, w: 0.05, h: 0.03, kind: "fixture", confidence: 0.80 },
      { name: "Conference Table", trade: "furniture", cx: 0.62, cy: 0.30, w: 0.08, h: 0.05, kind: "fixture", confidence: 0.85 },
    ];

  return specs.map((s, i) => {
    const points = poly(s.cx, s.cy, s.w, s.h);
    const { areaSqFt, perimeterFt } = polyMetrics(points, SCALE);
    return {
      id: `det-${sheetId}-${i}`,
      sheetId,
      kind: s.kind,
      name: s.name,
      trade: s.trade,
      points,
      areaSqFt,
      perimeterFt,
      wallType: s.wallType,
      confidence: s.confidence,
      status: "pending",
    };
  });
}

export function seedHistory(): HistoryEntry[] {
  const now = Date.now();
  return [
    { id: "h1", version: "v1.00", actor: "System", action: "Project created from blueprint upload", timestamp: now - 1000 * 60 * 40 },
    { id: "h2", version: "v1.01", actor: "AI Engine", action: "Detected 7 objects on sheet A101", timestamp: now - 1000 * 60 * 22 },
    { id: "h3", version: "v1.02", actor: "Jawad", action: "Approved Room 12 (Lobby)", timestamp: now - 1000 * 60 * 2 },
  ];
}
