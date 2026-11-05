// Version diff: compares the current takeoff (detections + measurements)
// against an earlier snapshot from the undo/redo history stack, so a
// reviewer can see exactly what changed since that point — the
// lightweight equivalent of Kreo's drawing-comparison feature, scoped
// to this project's own tracked revisions rather than two uploaded PDFs.

import type { Detection, Measurement } from "@/types";

export interface DetectionChange {
  id: string;
  name: string;
  field: "status" | "name";
  before: string;
  after: string;
}

export interface DiffResult {
  addedDetections: Detection[];
  removedDetections: Detection[];
  changedDetections: DetectionChange[];
  addedMeasurements: Measurement[];
  removedMeasurements: Measurement[];
  unchanged: boolean;
}

export function computeDiff(
  before: { detections: Detection[]; measurements: Measurement[] },
  after: { detections: Detection[]; measurements: Measurement[] }
): DiffResult {
  const beforeById = new Map(before.detections.map((d) => [d.id, d]));
  const afterById = new Map(after.detections.map((d) => [d.id, d]));

  const addedDetections = after.detections.filter((d) => !beforeById.has(d.id));
  const removedDetections = before.detections.filter((d) => !afterById.has(d.id));

  const changedDetections: DetectionChange[] = [];
  for (const [id, beforeD] of beforeById) {
    const afterD = afterById.get(id);
    if (!afterD) continue;
    if (beforeD.status !== afterD.status) {
      changedDetections.push({ id, name: afterD.name, field: "status", before: beforeD.status, after: afterD.status });
    }
    if (beforeD.name !== afterD.name) {
      changedDetections.push({ id, name: afterD.name, field: "name", before: beforeD.name, after: afterD.name });
    }
  }

  const beforeMeasIds = new Set(before.measurements.map((m) => m.id));
  const afterMeasIds = new Set(after.measurements.map((m) => m.id));
  const addedMeasurements = after.measurements.filter((m) => !beforeMeasIds.has(m.id));
  const removedMeasurements = before.measurements.filter((m) => !afterMeasIds.has(m.id));

  const unchanged =
    addedDetections.length === 0 &&
    removedDetections.length === 0 &&
    changedDetections.length === 0 &&
    addedMeasurements.length === 0 &&
    removedMeasurements.length === 0;

  return { addedDetections, removedDetections, changedDetections, addedMeasurements, removedMeasurements, unchanged };
}
