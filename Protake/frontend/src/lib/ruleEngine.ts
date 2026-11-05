// Mirrors the backend's app/rules/rule_engine.py registry: the exact
// named formulas the trade engines are built from, exposed here as a
// standalone calculator so a human QA reviewer can hand-verify any
// quantity without needing the full app/blueprint state.

export interface RuleParam {
  key: string;
  label: string;
  unit?: string;
  default?: number;
}

export interface RuleDef {
  name: string;
  label: string;
  description: string;
  params: RuleParam[];
  unit: string;
  evaluate: (inputs: Record<string, number>) => number;
}

function requireParams(inputs: Record<string, number>, keys: string[]) {
  for (const key of keys) {
    if (inputs[key] === undefined || Number.isNaN(inputs[key])) {
      throw new Error(`Missing input: ${key}`);
    }
  }
}

export const RULES: RuleDef[] = [
  {
    name: "wall_area",
    label: "Wall Area",
    description: "Wall Area = Perimeter × Height",
    unit: "sq ft",
    params: [
      { key: "perimeter_ft", label: "Perimeter", unit: "ft" },
      { key: "height_ft", label: "Height", unit: "ft", default: 9 },
    ],
    evaluate: (i) => {
      requireParams(i, ["perimeter_ft", "height_ft"]);
      return Math.round(i.perimeter_ft * i.height_ft * 100) / 100;
    },
  },
  {
    name: "units_with_waste",
    label: "Units With Waste",
    description: "ceil((Quantity × (1 + Waste%)) / Coverage per Unit)",
    unit: "units",
    params: [
      { key: "quantity", label: "Quantity" },
      { key: "coverage_per_unit", label: "Coverage per Unit" },
      { key: "waste_pct", label: "Waste", unit: "%", default: 10 },
    ],
    evaluate: (i) => {
      requireParams(i, ["quantity", "coverage_per_unit", "waste_pct"]);
      if (i.coverage_per_unit <= 0) throw new Error("coverage_per_unit must be positive");
      return Math.ceil((i.quantity * (1 + i.waste_pct / 100)) / i.coverage_per_unit);
    },
  },
  {
    name: "drywall_sheets",
    label: "Drywall Sheets",
    description: "Drywall Sheets = Wall Area ÷ Sheet Coverage (with waste)",
    unit: "sheets",
    params: [
      { key: "area_sqft", label: "Area", unit: "sq ft" },
      { key: "sheet_coverage_sqft", label: "Sheet Coverage", unit: "sq ft", default: 32 },
      { key: "waste_pct", label: "Waste", unit: "%", default: 10 },
    ],
    evaluate: (i) => {
      requireParams(i, ["area_sqft", "sheet_coverage_sqft", "waste_pct"]);
      if (i.sheet_coverage_sqft <= 0) throw new Error("sheet_coverage_sqft must be positive");
      return Math.ceil((i.area_sqft * (1 + i.waste_pct / 100)) / i.sheet_coverage_sqft);
    },
  },
  {
    name: "paint_gallons",
    label: "Paint Gallons",
    description: "Paint Gallons = (Area × Coats) ÷ Coverage (with waste)",
    unit: "gal",
    params: [
      { key: "area_sqft", label: "Area", unit: "sq ft" },
      { key: "coats", label: "Coats", default: 2 },
      { key: "coverage_sqft_per_gallon", label: "Coverage per Gallon", unit: "sq ft", default: 350 },
      { key: "waste_pct", label: "Waste", unit: "%", default: 5 },
    ],
    evaluate: (i) => {
      requireParams(i, ["area_sqft", "coats", "coverage_sqft_per_gallon", "waste_pct"]);
      if (i.coverage_sqft_per_gallon <= 0) throw new Error("coverage_sqft_per_gallon must be positive");
      return Math.ceil((i.area_sqft * i.coats * (1 + i.waste_pct / 100)) / i.coverage_sqft_per_gallon);
    },
  },
  {
    name: "flooring_boxes",
    label: "Flooring Boxes",
    description: "Boxes = Floor Area ÷ Coverage per Box (with waste)",
    unit: "boxes",
    params: [
      { key: "floor_area_sqft", label: "Floor Area", unit: "sq ft" },
      { key: "box_coverage_sqft", label: "Box Coverage", unit: "sq ft", default: 22 },
      { key: "waste_pct", label: "Waste", unit: "%", default: 8 },
    ],
    evaluate: (i) => {
      requireParams(i, ["floor_area_sqft", "box_coverage_sqft", "waste_pct"]);
      if (i.box_coverage_sqft <= 0) throw new Error("box_coverage_sqft must be positive");
      return Math.ceil((i.floor_area_sqft * (1 + i.waste_pct / 100)) / i.box_coverage_sqft);
    },
  },
  {
    name: "roof_pitch_factor",
    label: "Roof Pitch Factor",
    description: "factor = hypot(rise, 12) ÷ 12 — multiply flat area by this to get sloped area",
    unit: "×",
    params: [{ key: "rise_per_12", label: "Rise per 12", default: 6 }],
    evaluate: (i) => {
      requireParams(i, ["rise_per_12"]);
      return Math.round((Math.hypot(i.rise_per_12, 12) / 12) * 10000) / 10000;
    },
  },
  {
    name: "roof_bundles",
    label: "Roof Bundles",
    description: "Bundles = Sloped Roof Area ÷ Bundle Coverage (with waste)",
    unit: "bundles",
    params: [
      { key: "sloped_area_sqft", label: "Sloped Area", unit: "sq ft" },
      { key: "bundle_coverage_sqft", label: "Bundle Coverage", unit: "sq ft", default: 33.3 },
      { key: "waste_pct", label: "Waste", unit: "%", default: 12 },
    ],
    evaluate: (i) => {
      requireParams(i, ["sloped_area_sqft", "bundle_coverage_sqft", "waste_pct"]);
      if (i.bundle_coverage_sqft <= 0) throw new Error("bundle_coverage_sqft must be positive");
      return Math.ceil((i.sloped_area_sqft * (1 + i.waste_pct / 100)) / i.bundle_coverage_sqft);
    },
  },
  {
    name: "labor_hours",
    label: "Labor Hours",
    description: "Labor Hours = Quantity ÷ Crew Productivity Rate",
    unit: "hrs",
    params: [
      { key: "quantity", label: "Quantity" },
      { key: "productivity_per_hour", label: "Productivity", unit: "/hr" },
    ],
    evaluate: (i) => {
      requireParams(i, ["quantity", "productivity_per_hour"]);
      if (i.productivity_per_hour <= 0) throw new Error("productivity_per_hour must be positive");
      return Math.round((i.quantity / i.productivity_per_hour) * 100) / 100;
    },
  },
  {
    name: "apply_markup",
    label: "Apply Markup",
    description: "Amount = Base × Percent ÷ 100",
    unit: "$",
    params: [
      { key: "base_amount", label: "Base Amount", unit: "$" },
      { key: "pct", label: "Percent", unit: "%" },
    ],
    evaluate: (i) => {
      requireParams(i, ["base_amount", "pct"]);
      return Math.round(i.base_amount * (i.pct / 100) * 100) / 100;
    },
  },
];

export function getRule(name: string): RuleDef | undefined {
  return RULES.find((r) => r.name === name);
}
