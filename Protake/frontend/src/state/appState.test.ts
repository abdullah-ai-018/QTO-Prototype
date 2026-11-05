import { describe, it, expect } from "vitest";
import { appReducer, initialState, type AppState } from "./appState";
import type { Detection } from "@/types";

function makeWall(overrides: Partial<Detection>): Detection {
  return {
    id: overrides.id ?? "wall-1",
    sheetId: "sheet-1",
    kind: "wall",
    name: "Test Wall",
    trade: "drywall",
    points: [
      { x: 0.1, y: 0.2 },
      { x: 0.3, y: 0.2 },
    ],
    areaSqFt: 0,
    perimeterFt: 15,
    confidence: 0.95,
    status: "pending",
    ...overrides,
  };
}

function stateWith(detections: Detection[]): AppState {
  return {
    ...initialState,
    activeSheetId: "sheet-1",
    detections,
  };
}

describe("APPROVE_ALL gating (colors.ts getCanonicalWallCategory consistency)", () => {
  it("approves a classified wall on the active sheet", () => {
    const state = stateWith([
      makeWall({ id: "w1", wallTypeCode: "INTERIOR_PARTITION" }),
    ]);
    const next = appReducer(state, { type: "APPROVE_ALL" });
    expect(next.detections[0].status).toBe("approved");
  });

  it("skips a NEEDS_REVIEW / unclassified wall on the active sheet", () => {
    const state = stateWith([
      makeWall({ id: "w1", wallTypeCode: "unrecognized_junk" }),
    ]);
    const next = appReducer(state, { type: "APPROVE_ALL" });
    expect(next.detections[0].status).toBe("pending");
  });

  it("skips a wall that is unresolved because wallTypeCode is present-but-unresolved and wallType is forced to interior (the fall-through bug)", () => {
    const state = stateWith([
      makeWall({ id: "w1", wallTypeCode: "unrecognized_junk", wallType: "interior" }),
    ]);
    const next = appReducer(state, { type: "APPROVE_ALL" });
    expect(next.detections[0].status).toBe("pending");
  });

  it("approves a wall genuinely absent of wallTypeCode/classification via the legacy wallType fallback", () => {
    const state = stateWith([
      makeWall({ id: "w1", wallTypeCode: null, classification: null, wallType: "exterior" }),
    ]);
    const next = appReducer(state, { type: "APPROVE_ALL" });
    expect(next.detections[0].status).toBe("approved");
  });

  it("skips a low-confidence wall even with a resolvable classification", () => {
    const state = stateWith([
      makeWall({ id: "w1", wallTypeCode: "INTERIOR_PARTITION", confidence: 0.4 }),
    ]);
    const next = appReducer(state, { type: "APPROVE_ALL" });
    expect(next.detections[0].status).toBe("pending");
  });

  it("skips a wall with an unresolved schedule-vs-detail conflict even if otherwise classified", () => {
    const state = stateWith([
      makeWall({
        id: "w1",
        wallTypeCode: "INTERIOR_PARTITION",
        evidence: { conflicts: [{ field: "thickness_in", status: "CONFLICT" }] },
      }),
    ]);
    const next = appReducer(state, { type: "APPROVE_ALL" });
    expect(next.detections[0].status).toBe("pending");
  });

  it("only affects detections on the active sheet", () => {
    const state = stateWith([
      makeWall({ id: "w1", sheetId: "sheet-1", wallTypeCode: "INTERIOR_PARTITION" }),
      makeWall({ id: "w2", sheetId: "sheet-2", wallTypeCode: "INTERIOR_PARTITION" }),
    ]);
    const next = appReducer(state, { type: "APPROVE_ALL" });
    expect(next.detections.find((d) => d.id === "w1")?.status).toBe("approved");
    expect(next.detections.find((d) => d.id === "w2")?.status).toBe("pending");
  });

  it("does not attach an approvalOverride audit record for a plain gated approval", () => {
    const state = stateWith([
      makeWall({ id: "w1", wallTypeCode: "INTERIOR_PARTITION" }),
    ]);
    const next = appReducer(state, { type: "APPROVE_ALL" });
    expect(next.detections[0].approvalOverride).toBeUndefined();
  });
});

describe("APPROVE_ALL_OVERRIDE", () => {
  it("approves NEEDS_REVIEW walls that a plain APPROVE_ALL skips", () => {
    const state = stateWith([
      makeWall({ id: "w1", wallTypeCode: "unrecognized_junk" }),
    ]);
    const next = appReducer(state, {
      type: "APPROVE_ALL_OVERRIDE",
      reason: "Field-verified against as-builts",
      actor: "jdoe",
    });
    expect(next.detections[0].status).toBe("approved");
  });

  it("records reviewer, ISO timestamp, previousStatus, reason, and override=true on the overridden wall", () => {
    const state = stateWith([
      makeWall({ id: "w1", wallTypeCode: "unrecognized_junk", status: "pending" }),
    ]);
    const next = appReducer(state, {
      type: "APPROVE_ALL_OVERRIDE",
      reason: "Field-verified against as-builts",
      actor: "jdoe",
    });
    const audit = next.detections[0].approvalOverride;
    expect(audit).toBeDefined();
    expect(audit?.reviewer).toBe("jdoe");
    expect(audit?.previousStatus).toBe("pending");
    expect(audit?.reason).toBe("Field-verified against as-builts");
    expect(audit?.override).toBe(true);
    expect(() => new Date(audit!.timestamp).toISOString()).not.toThrow();
    expect(new Date(audit!.timestamp).toISOString()).toBe(audit!.timestamp);
  });

  it("falls back to 'unspecified_reviewer' when no actor/user identity is available, rather than fabricating a name", () => {
    const state = stateWith([
      makeWall({ id: "w1", wallTypeCode: "unrecognized_junk" }),
    ]);
    const next = appReducer(state, {
      type: "APPROVE_ALL_OVERRIDE",
      reason: "Reviewed manually",
    });
    expect(next.detections[0].approvalOverride?.reviewer).toBe("unspecified_reviewer");
  });

  it("does not attach an override audit record to a wall that was already eligible for a plain approval", () => {
    const state = stateWith([
      makeWall({ id: "w1", wallTypeCode: "INTERIOR_PARTITION" }),
    ]);
    const next = appReducer(state, {
      type: "APPROVE_ALL_OVERRIDE",
      reason: "Blanket override",
      actor: "jdoe",
    });
    expect(next.detections[0].status).toBe("approved");
    expect(next.detections[0].approvalOverride).toBeUndefined();
  });

  it("leaves already-approved detections untouched", () => {
    const state = stateWith([
      makeWall({ id: "w1", wallTypeCode: "unrecognized_junk", status: "approved" }),
    ]);
    const next = appReducer(state, {
      type: "APPROVE_ALL_OVERRIDE",
      reason: "Should not matter",
      actor: "jdoe",
    });
    expect(next.detections[0].approvalOverride).toBeUndefined();
  });

  it("is undoable via UNDO", () => {
    const state = stateWith([
      makeWall({ id: "w1", wallTypeCode: "unrecognized_junk" }),
    ]);
    const afterOverride = appReducer(state, {
      type: "APPROVE_ALL_OVERRIDE",
      reason: "Field-verified",
      actor: "jdoe",
    });
    expect(afterOverride.detections[0].status).toBe("approved");
    const undone = appReducer(afterOverride, { type: "UNDO" });
    expect(undone.detections[0].status).toBe("pending");
  });
});
