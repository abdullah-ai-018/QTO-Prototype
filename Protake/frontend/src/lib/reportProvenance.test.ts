import { describe, it, expect, vi } from "vitest";
import {
  NOT_AVAILABLE_FROM_SOURCE,
  getLineItemProofDisplay,
  getLineItemNavigationTarget,
  buildLineItemNavigationActions,
  computePlateHeightDisplay,
  computeAssemblyDisplay,
  computeOpeningDeductionsDisplay,
  type ReportLineItem,
} from "./reportProvenance";

describe("Report line-item proof/provenance display", () => {
  it("renders the real sheet + confidence when a line item genuinely carries them", () => {
    const li: ReportLineItem = { label: "Internal Wall Linear Feet", qty: 120, unit: "LF", sheetLabel: "A-204", confidence: 0.87 };
    expect(getLineItemProofDisplay(li)).toBe("Proof: Sheet A-204 • Conf 87%");
    // Must not be the old fabricated literal.
    expect(getLineItemProofDisplay(li)).not.toContain("A-101");
    expect(getLineItemProofDisplay(li)).not.toContain("98%");
  });

  it("renders the honest fallback when a line item has no traceable sheet/confidence", () => {
    const li: ReportLineItem = { label: "Drywall Sheets (4x8)", qty: 42, unit: "sheets" };
    expect(getLineItemProofDisplay(li)).toBe(`Proof: ${NOT_AVAILABLE_FROM_SOURCE}`);
  });

  it("only reports a navigation target when both a sheetId and a detection/wall id are present", () => {
    expect(getLineItemNavigationTarget({ label: "x", qty: 1, unit: "LF" })).toBeNull();
    expect(getLineItemNavigationTarget({ label: "x", qty: 1, unit: "LF", sheetId: "sheet-1" })).toBeNull();
    expect(getLineItemNavigationTarget({ label: "x", qty: 1, unit: "LF", detectionId: "wall-7" })).toBeNull();
    expect(getLineItemNavigationTarget({ label: "x", qty: 1, unit: "LF", sheetId: "sheet-1", wallId: "wall-7" })).toEqual({
      sheetId: "sheet-1",
      detectionId: "wall-7",
    });
  });
});

describe("Report line-item click -> dispatch actions", () => {
  it("returns null (no fabricated navigation) for an untraceable line item", () => {
    const li: ReportLineItem = { label: "Total Drywall Surface Area", qty: 3400, unit: "sq ft" };
    expect(buildLineItemNavigationActions(li)).toBeNull();
  });

  it("builds the expected sheet-switch + selection actions for a line item with a real detection reference", () => {
    const li: ReportLineItem = {
      label: "Interior Partition Wall #12",
      qty: 24,
      unit: "LF",
      sheetId: "sheet-a204",
      detectionId: "wall-12",
      sheetLabel: "A-204",
      confidence: 0.91,
    };
    const actions = buildLineItemNavigationActions(li);
    expect(actions).toEqual([
      { type: "SET_ACTIVE_SHEET", sheetId: "sheet-a204" },
      { type: "SELECT_DETECTION", id: "wall-12" },
    ]);

    // Simulate the component wiring: each returned action plus a close, run through dispatch.
    const dispatch = vi.fn();
    actions!.forEach((a) => dispatch(a));
    dispatch({ type: "CLOSE_REPORT" });

    expect(dispatch).toHaveBeenCalledTimes(3);
    expect(dispatch).toHaveBeenNthCalledWith(1, { type: "SET_ACTIVE_SHEET", sheetId: "sheet-a204" });
    expect(dispatch).toHaveBeenNthCalledWith(2, { type: "SELECT_DETECTION", id: "wall-12" });
    expect(dispatch).toHaveBeenNthCalledWith(3, { type: "CLOSE_REPORT" });
  });
});

describe("Engineering disclosures panel — real values only", () => {
  it("plate height: shows the real configured wall height, not a hardcoded 8.00 FT", () => {
    expect(computePlateHeightDisplay(9, 9)).toEqual({ display: "9.00 FT", isDefault: true });
    expect(computePlateHeightDisplay(10.5, 9)).toEqual({ display: "10.50 FT", isDefault: false });
  });

  it("plate height: falls back honestly when no height is configured", () => {
    expect(computePlateHeightDisplay(undefined, 9)).toEqual({ display: NOT_AVAILABLE_FROM_SOURCE, isDefault: false });
  });

  it("assembly: reports the real single assembly description shared by all walls", () => {
    const walls = [{ assemblyDescription: "3-5/8\" Metal Stud, 5/8\" GWB Each Side" }, { assemblyDescription: "3-5/8\" Metal Stud, 5/8\" GWB Each Side" }];
    expect(computeAssemblyDisplay(walls)).toBe("3-5/8\" Metal Stud, 5/8\" GWB Each Side");
  });

  it("assembly: honestly reports disagreement instead of picking one to present as universal", () => {
    const walls = [{ assemblyDescription: "Assembly A" }, { assemblyDescription: "Assembly B" }];
    expect(computeAssemblyDisplay(walls)).toBe("2 distinct assemblies across 2 walls");
  });

  it("assembly: falls back honestly when no wall carries the field", () => {
    expect(computeAssemblyDisplay([{ assemblyDescription: null }, {}])).toBe(NOT_AVAILABLE_FROM_SOURCE);
  });

  it("opening deductions: sums the real per-wall openingDeductionSf field over the fabricated -1,714 SF literal", () => {
    const walls = [{ openingDeductionSf: 220.4 }, { openingDeductionSf: 96 }];
    expect(computeOpeningDeductionsDisplay(walls)).toBe("-316 SF");
  });

  it("opening deductions: falls back to the local engine's own computed total when no wall has per-wall data", () => {
    expect(computeOpeningDeductionsDisplay([{}, {}], 512)).toBe("-512 SF");
  });

  it("opening deductions: falls back honestly when neither source has real data", () => {
    expect(computeOpeningDeductionsDisplay([{}, {}])).toBe(NOT_AVAILABLE_FROM_SOURCE);
  });
});
