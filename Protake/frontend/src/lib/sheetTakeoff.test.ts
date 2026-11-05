import { describe, it, expect } from "vitest";
import { computeSheetTakeoff, isTakeoffEligible, getEligibilityReason } from "./sheetTakeoff";
import { DEFAULT_DRYWALL_SETTINGS } from "./estimating";
import type { Detection, Sheet } from "@/types";

const A101: Sheet = { id: "sheet-a101", name: "Floor Plan", code: "A101", pageIndex: 0, isTakeoffEligible: true };
const A104: Sheet = { id: "sheet-a104", name: "Partition Plan", code: "A104", pageIndex: 3, isTakeoffEligible: true };
const A199_SCHEDULE: Sheet = {
  id: "sheet-a199",
  name: "Door Schedule",
  code: "A199",
  pageIndex: 5,
  isTakeoffEligible: false,
  skipReason: "Door schedule (schedule authority only)",
};

function wall(id: string, sheetId: string, perimeterFt: number, opts: Partial<Detection> = {}): Detection {
  return {
    id,
    sheetId,
    kind: "wall",
    name: id,
    trade: "drywall",
    points: [{ x: 0.1, y: 0.1 }, { x: 0.5, y: 0.1 }],
    areaSqFt: 0,
    perimeterFt,
    wallType: "interior",
    confidence: 0.95,
    status: "approved",
    ...opts,
  };
}

function opening(id: string, sheetId: string, kind: "door" | "window"): Detection {
  return {
    id,
    sheetId,
    kind,
    name: id,
    trade: null,
    points: [{ x: 0.2, y: 0.2 }, { x: 0.25, y: 0.2 }, { x: 0.25, y: 0.25 }, { x: 0.2, y: 0.25 }],
    areaSqFt: 20,
    perimeterFt: 0,
    confidence: 0.9,
    status: "approved",
  };
}

describe("computeSheetTakeoff — active-sheet isolation", () => {
  it("A101 and A104 produce different, independently-scoped results from the same detection set", () => {
    const detections: Detection[] = [
      wall("w-a101-1", "sheet-a101", 40),
      wall("w-a101-2", "sheet-a101", 60),
      wall("w-a104-1", "sheet-a104", 20),
    ];

    const a101Result = computeSheetTakeoff(A101, detections, DEFAULT_DRYWALL_SETTINGS);
    const a104Result = computeSheetTakeoff(A104, detections, DEFAULT_DRYWALL_SETTINGS);

    expect(a101Result.wallCount).toBe(2);
    expect(a104Result.wallCount).toBe(1);
    // computeSheetTakeoff() (the client engine path) always produces real
    // numbers here, never null — nullability only applies to the backend
    // page-takeoff path (buildSheetTakeoffFromBackend), which this test
    // doesn't exercise.
    expect(a101Result.netHangAreaSf).toBeGreaterThan(a104Result.netHangAreaSf!);
    expect(a101Result.sheets).not.toBe(a104Result.sheets);
  });

  it("critical: A101 -> A104 -> A101 returns identical, correctly re-isolated values each time (no cross-sheet leakage)", () => {
    const detections: Detection[] = [
      wall("w-a101-1", "sheet-a101", 40),
      wall("w-a101-2", "sheet-a101", 60),
      wall("w-a104-1", "sheet-a104", 20),
      opening("d-a104-1", "sheet-a104", "door"),
    ];

    const firstA101Pass = computeSheetTakeoff(A101, detections, DEFAULT_DRYWALL_SETTINGS);
    const a104Pass = computeSheetTakeoff(A104, detections, DEFAULT_DRYWALL_SETTINGS);
    const secondA101Pass = computeSheetTakeoff(A101, detections, DEFAULT_DRYWALL_SETTINGS);

    // Switching away and back must not mutate or leak state between sheets.
    expect(secondA101Pass).toEqual(firstA101Pass);
    // The intermediate sheet's door must not have deducted from A101's area.
    expect(secondA101Pass.wallCount).toBe(2);
    expect(a104Pass.wallCount).toBe(1);
  });

  it("a non-takeoff-eligible sheet (schedule authority) returns an honest zeroed result with a reason", () => {
    const detections: Detection[] = [wall("w-a101-1", "sheet-a101", 999)];
    const result = computeSheetTakeoff(A199_SCHEDULE, detections, DEFAULT_DRYWALL_SETTINGS);

    expect(result.eligible).toBe(false);
    expect(result.eligibilityReason).toBe(A199_SCHEDULE.skipReason);
    expect(result.sheets).toBe(0);
    expect(result.directCost).toBe(0);
    expect(result.netHangAreaSf).toBe(0);
  });

  it("isTakeoffEligible/getEligibilityReason: backend classification wins over everything else", () => {
    const sheet: Sheet = { ...A101, isTakeoffEligible: false, skipReason: "Classified as non-takeoff by blueprint processor" };
    expect(isTakeoffEligible(sheet)).toBe(false);
    expect(getEligibilityReason(sheet)).toBe("Classified as non-takeoff by blueprint processor");
  });

  it("opening deductions reduce net hang area relative to an identical wall run with no openings", () => {
    const noOpenings: Detection[] = [wall("w-1", "sheet-a101", 100)];
    const withOpenings: Detection[] = [wall("w-1", "sheet-a101", 100), opening("d-1", "sheet-a101", "door")];

    const resultNoOpenings = computeSheetTakeoff(A101, noOpenings, DEFAULT_DRYWALL_SETTINGS);
    const resultWithOpenings = computeSheetTakeoff(A101, withOpenings, DEFAULT_DRYWALL_SETTINGS);

    expect(resultWithOpenings.netHangAreaSf).toBeLessThan(resultNoOpenings.netHangAreaSf!);
  });
});
