import type { Detection, TradeId } from "@/types";
import { TRADES } from "@/lib/sampleData";

export interface TradeCoverage {
  trade: TradeId;
  label: string;
  approved: number;
  pending: number;
  rejected: number;
  total: number;
}

export interface CoverageReport {
  perTrade: TradeCoverage[];
  overallReadinessPct: number;
  gaps: string[];
}

export function computeCoverage(detections: Detection[], sheetId: string | null): CoverageReport {
  const sheetDetections = sheetId ? detections.filter((d) => d.sheetId === sheetId) : detections;

  const perTrade: TradeCoverage[] = TRADES.map(({ id, label }) => {
    const rows = sheetDetections.filter((d) => d.trade === id);
    return {
      trade: id,
      label,
      approved: rows.filter((d) => d.status === "approved").length,
      pending: rows.filter((d) => d.status === "pending").length,
      rejected: rows.filter((d) => d.status === "rejected").length,
      total: rows.length,
    };
  });

  const totalApproved = perTrade.reduce((s, t) => s + t.approved, 0);
  const totalPending = perTrade.reduce((s, t) => s + t.pending, 0);
  const denom = totalApproved + totalPending;
  const overallReadinessPct = denom ? Math.round((totalApproved / denom) * 1000) / 10 : 100;

  const gaps: string[] = [];
  perTrade.forEach((t) => {
    if (t.pending > 0) gaps.push(`${t.pending} pending ${t.label} item(s) awaiting review`);
    if (t.total > 0 && t.approved === 0) gaps.push(`No ${t.label} items approved yet — quantities will read zero`);
  });
  if (sheetDetections.length === 0) gaps.push("No AI detections on this sheet yet — run AI Scan to begin");

  return { perTrade, overallReadinessPct, gaps };
}

const VARIANCE_TOLERANCE_PCT = 8;

export interface VarianceFlag {
  detectionId: string;
  detectionName: string;
  aiAreaSqFt: number;
  manualAreaSqFt: number;
  manualMeasurementId: string;
  deviationPct: number;
}

export function computeVarianceFlags(
  detections: Detection[],
  measurements: { id: string; sheetId: string; tool: string; points: { x: number; y: number }[]; value?: number; valueLabel: string }[],
  sheetId: string | null
): VarianceFlag[] {
  const rooms = detections.filter((d) => d.sheetId === sheetId && d.kind === "room" && d.status === "approved");
  const areaMeasurements = measurements.filter((m) => m.sheetId === sheetId && m.tool === "area");

  const flags: VarianceFlag[] = [];
  for (const room of rooms) {
    const xs = room.points.map((p) => p.x);
    const ys = room.points.map((p) => p.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);

    for (const m of areaMeasurements) {
      const cx = m.points.reduce((s, p) => s + p.x, 0) / m.points.length;
      const cy = m.points.reduce((s, p) => s + p.y, 0) / m.points.length;
      const inside = cx >= minX && cx <= maxX && cy >= minY && cy <= maxY;
      if (!inside) continue;

      const manualArea = Number(m.valueLabel.replace(/[^\d.]/g, "")) || 0;
      if (room.areaSqFt <= 0 || manualArea <= 0) continue;
      const deviationPct = (Math.abs(room.areaSqFt - manualArea) / room.areaSqFt) * 100;
      if (deviationPct > VARIANCE_TOLERANCE_PCT) {
        flags.push({
          detectionId: room.id,
          detectionName: room.name,
          aiAreaSqFt: room.areaSqFt,
          manualAreaSqFt: manualArea,
          manualMeasurementId: m.id,
          deviationPct: Math.round(deviationPct * 10) / 10,
        });
      }
    }
  }
  return flags;
}
