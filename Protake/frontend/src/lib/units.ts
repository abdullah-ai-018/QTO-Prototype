// Pure display-formatting helpers. Every geometric measurement stays
// canonically feet/sqft internally (matching the backend) — these only
// convert for rendering when a project's unit_system is "metric".

export type UnitSystem = "imperial" | "metric";

export const METERS_TO_FEET = 3.280839895013123;

export function formatArea(sqft: number, system: UnitSystem = "imperial"): string {
  if (system === "metric") {
    const sqm = sqft / (METERS_TO_FEET * METERS_TO_FEET);
    return `${sqm.toLocaleString(undefined, { maximumFractionDigits: 1 })} m²`;
  }
  return `${sqft.toLocaleString()} sq ft`;
}

export function formatLength(ft: number, system: UnitSystem = "imperial"): string {
  if (system === "metric") {
    const m = ft / METERS_TO_FEET;
    return `${m.toLocaleString(undefined, { maximumFractionDigits: 2 })} m`;
  }
  return `${ft.toLocaleString()} ft`;
}

// Wall thickness is the one length on a takeoff that is naturally sub-foot
// — a 25cm wall is 0.82ft, which reads as noise next to the wall's 42ft
// length. Rendered in inches (imperial) or centimetres (metric) instead,
// which is how walls are specified in both conventions.
export function formatWallThickness(ft: number, system: UnitSystem = "imperial"): string {
  if (system === "metric") {
    const cm = (ft / METERS_TO_FEET) * 100;
    return `${cm.toLocaleString(undefined, { maximumFractionDigits: 0 })} cm`;
  }
  const inches = ft * 12;
  return `${inches.toLocaleString(undefined, { maximumFractionDigits: 1 })} in`;
}
