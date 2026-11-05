import { describe, expect, it } from "vitest";
import { isVisibleForActiveTrade, shouldDeemphasizeRoom, ROOM_DEEMPHASIZED_TRADES } from "./tradeVisualization";

// Minimal representative detections — one of each kind that appears on
// the canvas, covering the fields these functions actually read.
const room = { kind: "room" as const, trade: null, roomType: null };
const exteriorCoveredRoom = { kind: "room" as const, trade: null, roomType: "exterior_covered" };
const wall = { kind: "wall" as const, trade: "drywall" as const, roomType: null };
const door = { kind: "door" as const, trade: null, roomType: null };
const window_ = { kind: "window" as const, trade: null, roomType: null };
const furnitureSymbol = { kind: "symbol" as const, trade: "furniture" as const, roomType: null };
const openingsSymbol = { kind: "symbol" as const, trade: "openings" as const, roomType: null };
const roofingTaggedRoom = { kind: "room" as const, trade: "roofing" as const, roomType: null };

describe("isVisibleForActiveTrade", () => {
  it("shows everything when no trade tab is active (general/default view)", () => {
    for (const d of [room, wall, door, window_, furnitureSymbol]) {
      expect(isVisibleForActiveTrade(d, null)).toBe(true);
    }
  });

  it("Drywall: shows wall runs and openings, hides exterior-covered rooms", () => {
    expect(isVisibleForActiveTrade(wall, "drywall")).toBe(true);
    expect(isVisibleForActiveTrade(door, "drywall")).toBe(true);
    expect(isVisibleForActiveTrade(window_, "drywall")).toBe(true);
    expect(isVisibleForActiveTrade(room, "drywall")).toBe(true);
    expect(isVisibleForActiveTrade(exteriorCoveredRoom, "drywall")).toBe(false);
    expect(isVisibleForActiveTrade(furnitureSymbol, "drywall")).toBe(false);
  });

  it("Painting: shows wall runs and openings, hides exterior-covered rooms", () => {
    expect(isVisibleForActiveTrade(wall, "painting")).toBe(true);
    expect(isVisibleForActiveTrade(door, "painting")).toBe(true);
    expect(isVisibleForActiveTrade(window_, "painting")).toBe(true);
    expect(isVisibleForActiveTrade(room, "painting")).toBe(true);
    expect(isVisibleForActiveTrade(exteriorCoveredRoom, "painting")).toBe(false);
  });

  it("Flooring: rooms visible (primary evidence), walls/openings hidden", () => {
    expect(isVisibleForActiveTrade(room, "flooring")).toBe(true);
    expect(isVisibleForActiveTrade(exteriorCoveredRoom, "flooring")).toBe(true); // room-kind filter itself doesn't exclude here — flooring keeps all rooms
    expect(isVisibleForActiveTrade(wall, "flooring")).toBe(false);
    expect(isVisibleForActiveTrade(door, "flooring")).toBe(false);
  });

  it("Roofing: rooms visible (only available context), plain walls hidden", () => {
    expect(isVisibleForActiveTrade(room, "roofing")).toBe(true);
    expect(isVisibleForActiveTrade(wall, "roofing")).toBe(false);
    expect(isVisibleForActiveTrade(roofingTaggedRoom, "roofing")).toBe(true);
  });

  it("Furniture: only furniture-tagged detections", () => {
    expect(isVisibleForActiveTrade(furnitureSymbol, "furniture")).toBe(true);
    expect(isVisibleForActiveTrade(room, "furniture")).toBe(false);
    expect(isVisibleForActiveTrade(wall, "furniture")).toBe(false);
  });

  it("Openings: only openings-tagged detections", () => {
    expect(isVisibleForActiveTrade(openingsSymbol, "openings")).toBe(true);
    expect(isVisibleForActiveTrade(door, "openings")).toBe(false); // a raw door detection isn't trade-tagged "openings" itself
  });
});

describe("shouldDeemphasizeRoom", () => {
  it("never de-emphasizes non-room detections", () => {
    expect(shouldDeemphasizeRoom(wall, "drywall", false)).toBe(false);
    expect(shouldDeemphasizeRoom(door, "drywall", false)).toBe(false);
  });

  it("never de-emphasizes rooms in the general/default view (no active trade)", () => {
    expect(shouldDeemphasizeRoom(room, null, false)).toBe(false);
  });

  it("de-emphasizes rooms by default in Drywall, Painting, and Roofing", () => {
    expect(shouldDeemphasizeRoom(room, "drywall", false)).toBe(true);
    expect(shouldDeemphasizeRoom(room, "painting", false)).toBe(true);
    expect(shouldDeemphasizeRoom(room, "roofing", false)).toBe(true);
  });

  it("never de-emphasizes rooms in Flooring — they're the primary evidence there", () => {
    expect(shouldDeemphasizeRoom(room, "flooring", false)).toBe(false);
  });

  it("the Geometry/Rooms toggle restores full room visibility in any trade", () => {
    expect(shouldDeemphasizeRoom(room, "drywall", true)).toBe(false);
    expect(shouldDeemphasizeRoom(room, "painting", true)).toBe(false);
    expect(shouldDeemphasizeRoom(room, "roofing", true)).toBe(false);
  });

  it("ROOM_DEEMPHASIZED_TRADES is exactly {drywall, painting, roofing}", () => {
    expect([...ROOM_DEEMPHASIZED_TRADES].sort()).toEqual(["drywall", "painting", "roofing"]);
  });
});
