import React, { useEffect, useRef, useState, useCallback, useMemo } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import {
  Box,
  Square,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Sparkles,
  Layers,
  Compass,
  Sun,
  Eye,
  EyeOff,
  Crosshair,
  Sliders,
  RotateCcw,
  Target,
  Navigation,
  Ruler,
  DoorOpen,
  Tag,
  Hash,
  Grid,
  Info,
  Building2,
  Sparkle,
  Columns,
  GripVertical,
  MousePointer,
  Hand,
  Filter,
  CheckCircle2,
  AlertTriangle,
  Ban,
} from "lucide-react";
import BIM2DFlooringPlan, { FLOORING_PALETTE } from "./BIM2DFlooringPlan";
import BIM2DRoofPlan, { ROOFING_PALETTE } from "./BIM2DRoofPlan";

export const CATEGORY_COLORS: Record<
  string,
  { hex: number; css: string; label: string; edgeHex: number; fillAlpha: string; code: string; spec: string; stroke: string }
> = {
  INTERIOR_PARTITION: {
    hex: 0x38bdf8,
    css: "#38bdf8",
    stroke: "#7dd3fc",
    label: "Interior Drywall (1-Hr)",
    edgeHex: 0x7dd3fc,
    fillAlpha: "#38bdf825",
    code: "W1",
    spec: '5/8" Gypsum (2-sides) · 3-5/8" 25GA Studs @ 16" o.c.',
  },
  DEMISING_WALL: {
    hex: 0xd946ef,
    css: "#d946ef",
    stroke: "#f0abfc",
    label: "Demising Wall (2-Hr)",
    edgeHex: 0xf0abfc,
    fillAlpha: "#d946ef25",
    code: "W2",
    spec: 'Double 5/8" Type X (4 layers) · 3-5/8" 20GA Studs · R-13 Batt',
  },
  SHAFT_WALL: {
    hex: 0xf59e0b,
    css: "#f59e0b",
    stroke: "#fde68a",
    label: "Shaft Wall Assembly",
    edgeHex: 0xfde68a,
    fillAlpha: "#f59e0b25",
    code: "W3",
    spec: '1" Shaftliner + 2× 5/8" Type X · C-H Studs @ 24" o.c. (2-Hr Fire)',
  },
  EXTERIOR_WALL: {
    hex: 0x0284c7,
    css: "#0284c7",
    stroke: "#38bdf8",
    label: "Exterior Envelope",
    edgeHex: 0x38bdf8,
    fillAlpha: "#0284c730",
    code: "EW1",
    spec: '5/8" DensGlass Sheathing · 6" 16GA Heavy Studs · R-19 Batt',
  },
  STRUCTURAL_CONCRETE: {
    hex: 0xf43f5e,
    css: "#f43f5e",
    stroke: "#fda4af",
    label: "Structural Concrete",
    edgeHex: 0xfda4af,
    fillAlpha: "#f43f5e25",
    code: "CW1",
    spec: '8" Cast-in-Place Reinforced Concrete Shear Core',
  },
  CURTAIN_WALL: {
    hex: 0x10b981,
    css: "#10b981",
    stroke: "#6ee7b7",
    label: "Curtain / Storefront",
    edgeHex: 0x6ee7b7,
    fillAlpha: "#10b98125",
    code: "GL1",
    spec: '1" Insulated Double Glazing · 2-1/2"×6" Thermal Break Aluminum',
  },
  MASONRY: {
    hex: 0xf97316,
    css: "#f97316",
    stroke: "#fdba74",
    label: "Masonry / CMU",
    edgeHex: 0xfdba74,
    fillAlpha: "#f9731625",
    code: "CMU",
    spec: '8" CMU Block Wall · Solid Grouted #5 Rebar @ 32" o.c.',
  },
  UNKNOWN: {
    hex: 0x64748b,
    css: "#64748b",
    stroke: "#94a3b8",
    label: "Unclassified",
    edgeHex: 0x94a3b8,
    fillAlpha: "#64748b25",
    code: "GEN",
    spec: "Standard Partition Assembly",
  },
};

/** Formats feet decimal into architectural feet & inches string (e.g. 18.5 -> 18'-6") */
function formatArchitecturalFeet(ft: number): string {
  if (isNaN(ft) || ft === 0) return "0'-0\"";
  const feet = Math.floor(Math.abs(ft));
  const inchesDecimal = (Math.abs(ft) - feet) * 12;
  const wholeInches = Math.floor(inchesDecimal);
  const fraction16 = Math.round((inchesDecimal - wholeInches) * 16);

  let fracStr = "";
  if (fraction16 === 16) {
    return `${ft < 0 ? "-" : ""}${feet}'-${wholeInches + 1}"`;
  } else if (fraction16 > 0) {
    // Simplify fractions (e.g. 8/16 -> 1/2, 4/16 -> 1/4)
    if (fraction16 === 8) fracStr = " 1/2";
    else if (fraction16 === 4) fracStr = " 1/4";
    else if (fraction16 === 12) fracStr = " 3/4";
    else if (fraction16 % 2 === 0) fracStr = ` ${fraction16 / 2}/8`;
    else fracStr = ` ${fraction16}/16`;
  }

  return `${ft < 0 ? "-" : ""}${feet}'-${wholeInches}${fracStr}"`;
}

interface BIM3DCanvasViewerProps {
  walls: any[];
  contextWalls?: any[];
  storeys: any[];
  spaces?: any[];
  slabs?: any[];
  roofs?: any[];
  flooringElements?: any[];
  flooringByAssembly?: Record<string, any[]>;
  selectedTrade?: "drywall" | "flooring" | "roofing";
  selectedWallGuid: string | null;
  onSelectWall: (guid: string) => void;
  selectedStorey: string;
  onSelectStorey?: (storeyName: string) => void;
  hiddenCategories?: Set<string>;
  hiddenWallGuids?: Set<string>;
  externalViewMode?: "3D" | "2D" | "SPLIT";
  onViewModeChange?: (mode: "3D" | "2D" | "SPLIT") => void;
}

export type Canvas2DTool = "select" | "pan" | "measure-distance" | "measure-area";
export type Takeoff2DFilter = "ALL" | "ELIGIBLE" | "SINGLE_FACE" | "DOUBLE_FACE" | "REVIEW_REQUIRED" | "BLOCKED";

/**
 * Extracts a clean, planar, non-self-intersecting 2D polygon footprint for a 3D flooring element.
 * 1. Flattens 3D vertices and deduplicates identical (x, y) projections.
 * 2. If 4 corners (standard rectangular room/slab), sorts them counter-clockwise around centroid
 *    to prevent figure-8 crossing diagonals.
 * 3. Falls back gracefully to bounding box if vertices are corrupt or < 3.
 */
function extractCleanPlanarFlooringPolygon(elem: any): Array<[number, number]> {
  const rawVerts = elem.vertices || [];
  if (rawVerts.length >= 3) {
    const pts2d: Array<[number, number]> = [];
    const seen = new Set<string>();

    for (const pt of rawVerts) {
      if (!Array.isArray(pt) || pt.length < 2) continue;
      const x = Number(pt[0]);
      const y = Number(pt[1]);
      if (isNaN(x) || isNaN(y)) continue;
      // 0.05ft (~0.6 inch) tolerance snapping to collapse micro-deviations
      const key = `${Math.round(x * 20)},${Math.round(y * 20)}`;
      if (!seen.has(key)) {
        seen.add(key);
        pts2d.push([x, y]);
      }
    }

    if (pts2d.length === 4) {
      // Sort CCW around centroid to ensure clean convex polygon loop
      const cx = (pts2d[0][0] + pts2d[1][0] + pts2d[2][0] + pts2d[3][0]) / 4;
      const cy = (pts2d[0][1] + pts2d[1][1] + pts2d[2][1] + pts2d[3][1]) / 4;
      pts2d.sort((a, b) => Math.atan2(a[1] - cy, a[0] - cx) - Math.atan2(b[1] - cy, b[0] - cx));
      return pts2d;
    }

    if (pts2d.length >= 3 && pts2d.length <= 64) {
      return pts2d;
    }
  }

  if (elem.bbox) {
    const minX = Number(elem.bbox.min_x);
    const maxX = Number(elem.bbox.max_x);
    const minY = Number(elem.bbox.min_y);
    const maxY = Number(elem.bbox.max_y);
    if (!isNaN(minX) && !isNaN(maxX) && !isNaN(minY) && !isNaN(maxY)) {
      return [
        [minX, minY],
        [maxX, minY],
        [maxX, maxY],
        [minX, maxY],
      ];
    }
  }

  return [];
}

const roofTextureCache = new Map<string, THREE.Texture>();

function getProceduralRoofTexture(matKey: string): THREE.Texture {
  if (roofTextureCache.has(matKey)) {
    return roofTextureCache.get(matKey)!;
  }
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    const fallback = new THREE.Texture();
    roofTextureCache.set(matKey, fallback);
    return fallback;
  }

  if (matKey.includes("METAL")) {
    // Standing Seam Metal Panels
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(0, 0, 256, 256);
    const grad = ctx.createLinearGradient(0, 0, 64, 0);
    grad.addColorStop(0, "#1e3a5f");
    grad.addColorStop(0.5, "#2563eb");
    grad.addColorStop(0.95, "#1e3a5f");
    grad.addColorStop(1, "#0f172a");
    for (let x = 0; x < 256; x += 64) {
      ctx.fillStyle = grad;
      ctx.fillRect(x, 0, 64, 256);
      ctx.fillStyle = "#38bdf8"; // metallic rib highlight
      ctx.fillRect(x + 62, 0, 1.5, 256);
      ctx.fillStyle = "#0c1829"; // shadow
      ctx.fillRect(x + 63.5, 0, 1.5, 256);
    }
  } else if (matKey.includes("TILE")) {
    // Terracotta Clay / Concrete Tiles
    ctx.fillStyle = "#9a3412";
    ctx.fillRect(0, 0, 256, 256);
    for (let y = 0; y < 256; y += 32) {
      for (let x = 0; x < 256; x += 32) {
        const barrelGrad = ctx.createLinearGradient(x, y, x + 32, y);
        barrelGrad.addColorStop(0, "#7c2d12");
        barrelGrad.addColorStop(0.35, "#c2410c");
        barrelGrad.addColorStop(0.7, "#ea580c");
        barrelGrad.addColorStop(1, "#431407");
        ctx.fillStyle = barrelGrad;
        ctx.fillRect(x, y, 32, 30);
        ctx.fillStyle = "rgba(0, 0, 0, 0.35)";
        ctx.fillRect(x, y + 29, 32, 3);
      }
    }
  } else if (matKey.includes("MEMBRANE") || matKey.includes("TPO")) {
    // Commercial Flat Membrane with Heat-Welded Seams
    ctx.fillStyle = "#475569";
    ctx.fillRect(0, 0, 256, 256);
    ctx.strokeStyle = "#64748b";
    ctx.lineWidth = 2;
    ctx.strokeRect(0, 0, 256, 256);
    ctx.strokeStyle = "#334155";
    ctx.lineWidth = 1;
    ctx.strokeRect(2, 2, 252, 252);
  } else {
    // Architectural Asphalt Shingle (Default)
    ctx.fillStyle = "#334155";
    ctx.fillRect(0, 0, 256, 256);
    const courseH = 32;
    const tabW = 64;
    for (let y = 0; y < 256; y += courseH) {
      const rowIdx = y / courseH;
      const xOffset = (rowIdx % 2) * (tabW / 2);
      ctx.fillStyle = "#475569";
      ctx.fillRect(0, y, 256, 2);
      for (let x = -tabW + xOffset; x < 256 + tabW; x += tabW) {
        const tabGrad = ctx.createLinearGradient(x, y + 2, x, y + courseH);
        tabGrad.addColorStop(0, "#384556");
        tabGrad.addColorStop(0.85, "#1e293b");
        tabGrad.addColorStop(1, "#0f172a");
        ctx.fillStyle = tabGrad;
        ctx.fillRect(x, y + 2, tabW - 2, courseH - 2);
        ctx.fillStyle = "#090d16";
        ctx.fillRect(x + tabW - 2, y + 2, 2, courseH - 2);
      }
    }
    // Granular mineral granules
    ctx.fillStyle = "rgba(255, 255, 255, 0.05)";
    for (let i = 0; i < 240; i++) {
      ctx.fillRect(Math.random() * 256, Math.random() * 256, 1.5, 1.5);
    }
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(6, 6);
  texture.needsUpdate = true;
  roofTextureCache.set(matKey, texture);
  return texture;
}

const flooringTextureCache = new Map<string, THREE.Texture>();

function getProceduralFlooringTexture(catKey: string): THREE.Texture {
  if (flooringTextureCache.has(catKey)) {
    return flooringTextureCache.get(catKey)!;
  }
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    const fallback = new THREE.Texture();
    flooringTextureCache.set(catKey, fallback);
    return fallback;
  }

  if (catKey === "HARDWOOD_FLOORING") {
    // Warm architectural hardwood planks with bevels & grain
    ctx.fillStyle = "#78350f";
    ctx.fillRect(0, 0, 256, 256);
    const plankH = 32;
    const plankW = 128;
    for (let y = 0; y < 256; y += plankH) {
      const row = Math.floor(y / plankH);
      const xOffset = (row % 2) * (plankW / 2);
      for (let x = -plankW; x < 256 + plankW; x += plankW) {
        const px = x + xOffset;
        const toneAlpha = 0.88 + ((row * 3 + px / 32) % 4) * 0.04;
        ctx.fillStyle = `rgba(180, 83, 9, ${toneAlpha})`;
        ctx.fillRect(px + 1, y + 1, plankW - 2, plankH - 2);
        // Micro wood grain
        ctx.strokeStyle = "rgba(69, 26, 3, 0.35)";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(px + 4, y + plankH * 0.35);
        ctx.lineTo(px + plankW - 4, y + plankH * 0.37);
        ctx.moveTo(px + 12, y + plankH * 0.72);
        ctx.lineTo(px + plankW - 10, y + plankH * 0.7);
        ctx.stroke();
      }
      ctx.fillStyle = "#270e04";
      ctx.fillRect(0, y, 256, 1.5);
    }
  } else if (catKey === "LAMINATE_FLOORING") {
    // Scandinavian ash/grey modern laminate planks
    ctx.fillStyle = "#57534e";
    ctx.fillRect(0, 0, 256, 256);
    const plankH = 28;
    const plankW = 96;
    for (let y = 0; y < 256; y += plankH) {
      const row = Math.floor(y / plankH);
      const xOffset = (row % 3) * (plankW / 3);
      for (let x = -plankW; x < 256 + plankW; x += plankW) {
        const px = x + xOffset;
        ctx.fillStyle = (row + px) % 2 === 0 ? "#78716c" : "#68625d";
        ctx.fillRect(px + 1, y + 1, plankW - 2, plankH - 2);
      }
      ctx.fillStyle = "#1c1917";
      ctx.fillRect(0, y, 256, 1.2);
    }
  } else if (catKey === "TILE_CERAMIC_PORCELAIN" || catKey === "STONE_MASONRY_FLOORING") {
    // Architectural 24"x24" porcelain grid with subtle grout
    ctx.fillStyle = "#0f172a"; // grout line
    ctx.fillRect(0, 0, 256, 256);
    const tileSize = 64;
    for (let y = 0; y < 256; y += tileSize) {
      for (let x = 0; x < 256; x += tileSize) {
        ctx.fillStyle = "#1e293b";
        ctx.fillRect(x + 1.5, y + 1.5, tileSize - 3, tileSize - 3);
        ctx.fillStyle = "rgba(255, 255, 255, 0.035)";
        ctx.fillRect(x + 4, y + 4, tileSize - 8, tileSize - 8);
      }
    }
  } else if (catKey.startsWith("CARPET")) {
    // Woven carpet modular tiles
    ctx.fillStyle = "#1e1b4b";
    ctx.fillRect(0, 0, 256, 256);
    ctx.strokeStyle = "rgba(99, 102, 241, 0.14)";
    ctx.lineWidth = 1;
    for (let i = 0; i < 256; i += 8) {
      ctx.beginPath();
      ctx.moveTo(i, 0);
      ctx.lineTo(i, 256);
      ctx.moveTo(0, i);
      ctx.lineTo(256, i);
      ctx.stroke();
    }
    ctx.strokeStyle = "#0d0c22";
    ctx.lineWidth = 1.5;
    for (let i = 0; i < 256; i += 64) {
      ctx.strokeRect(i, 0, 64, 256);
      ctx.strokeRect(0, i, 256, 64);
    }
  } else if (catKey === "RESILIENT_VINYL_LVT") {
    // Luxury vinyl tile
    ctx.fillStyle = "#134e4a";
    ctx.fillRect(0, 0, 256, 256);
    const plankH = 32;
    for (let y = 0; y < 256; y += plankH) {
      ctx.fillStyle = y % 64 === 0 ? "#0f766e" : "#115e59";
      ctx.fillRect(0, y + 1, 256, plankH - 2);
      ctx.fillStyle = "#042f2e";
      ctx.fillRect(0, y, 256, 1);
    }
  } else {
    // Subtle architectural polished finish
    ctx.fillStyle = "#1e293b";
    ctx.fillRect(0, 0, 256, 256);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(0, 0, 128, 128);
    ctx.strokeRect(128, 0, 128, 128);
    ctx.strokeRect(0, 128, 128, 128);
    ctx.strokeRect(128, 128, 128, 128);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(4, 4);
  texture.needsUpdate = true;
  flooringTextureCache.set(catKey, texture);
  return texture;
}

/**
 * Builds clean, solid architectural 3D roof geometry with real fascia depth (0.35ft / 4.2")
 * and zero fan-triangulation tearing.
 */
function buildCleanArchitecturalRoofGeometry(elem: any): {
  geometry: THREE.BufferGeometry;
  ridgePoints?: [THREE.Vector3, THREE.Vector3] | null;
} {
  const rawVerts = elem.vertices || [];
  if (rawVerts.length < 3) {
    return { geometry: new THREE.BufferGeometry(), ridgePoints: null };
  }

  // Convert vertices to Three.js coordinates (X, Z_elev, -Y)
  const pts3d: THREE.Vector3[] = [];
  const seen = new Set<string>();

  for (const pt of rawVerts) {
    if (!Array.isArray(pt) || pt.length < 2) continue;
    const x = Number(pt[0]);
    const y = Number(pt[1]);
    const z = Number(pt[2] || elem.elevation_ft || 20);
    if (isNaN(x) || isNaN(y) || isNaN(z)) continue;
    const key = `${Math.round(x * 20)},${Math.round(y * 20)},${Math.round(z * 20)}`;
    if (!seen.has(key)) {
      seen.add(key);
      pts3d.push(new THREE.Vector3(x, z, -y));
    }
  }

  if (pts3d.length < 3) {
    return { geometry: new THREE.BufferGeometry(), ridgePoints: null };
  }

  // 1. Calculate Centroid
  const centroid = new THREE.Vector3(0, 0, 0);
  pts3d.forEach((p) => centroid.add(p));
  centroid.multiplyScalar(1 / pts3d.length);

  // 2. Calculate Plane Normal using Newell's method
  let nx = 0, ny = 0, nz = 0;
  for (let i = 0; i < pts3d.length; i++) {
    const j = (i + 1) % pts3d.length;
    nx += (pts3d[i].y - pts3d[j].y) * (pts3d[i].z + pts3d[j].z);
    ny += (pts3d[i].z - pts3d[j].z) * (pts3d[i].x + pts3d[j].x);
    nz += (pts3d[i].x - pts3d[j].x) * (pts3d[i].y + pts3d[j].y);
  }
  let normal = new THREE.Vector3(nx, ny, nz).normalize();
  if (normal.lengthSq() < 0.001) normal.set(0, 1, 0);
  if (normal.y < 0) normal.negate(); // ensure normal faces upwards

  // 3. Orthonormal basis on the roof plane
  const upRef = Math.abs(normal.y) > 0.9 ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(0, 1, 0);
  const u = new THREE.Vector3().crossVectors(normal, upRef).normalize();
  const v = new THREE.Vector3().crossVectors(normal, u).normalize();

  // 4. Project 3D points into 2D plane coordinates (u, v)
  const ptsUV: Array<[number, number]> = [];
  pts3d.forEach((p) => {
    const diff = new THREE.Vector3().subVectors(p, centroid);
    ptsUV.push([diff.dot(u), diff.dot(v)]);
  });

  // 5. Compute 2D Convex Hull in UV space to eliminate criss-crossing triangulation tearing
  const sorted = [...ptsUV].sort((a, b) => (a[0] === b[0] ? a[1] - b[1] : a[0] - b[0]));
  const cross = (o: [number, number], a: [number, number], b: [number, number]) =>
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);

  const lower: Array<[number, number]> = [];
  for (const p of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) {
      lower.pop();
    }
    lower.push(p);
  }

  const upper: Array<[number, number]> = [];
  for (let i = sorted.length - 1; i >= 0; i--) {
    const p = sorted[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) {
      upper.pop();
    }
    upper.push(p);
  }

  lower.pop();
  upper.pop();
  const hullUV = lower.concat(upper);

  if (hullUV.length < 3) {
    return { geometry: new THREE.BufferGeometry(), ridgePoints: null };
  }

  // 6. Build THREE.Shape from clean hull loop
  const shape = new THREE.Shape();
  shape.moveTo(hullUV[0][0], hullUV[0][1]);
  for (let k = 1; k < hullUV.length; k++) {
    shape.lineTo(hullUV[k][0], hullUV[k][1]);
  }
  shape.closePath();

  // 7. Architectural Solid Extrusion (0.35ft / 4.2" fascia thickness)
  const extrudeGeom = new THREE.ExtrudeGeometry(shape, {
    depth: 0.35,
    bevelEnabled: true,
    bevelThickness: 0.03,
    bevelSize: 0.03,
    bevelSegments: 1,
  });

  // 8. Transform ExtrudeGeometry from local (u, v, +z) to world (X, Y, Z) space
  // Extrude in -normal direction (downwards under the roof)
  const matrix = new THREE.Matrix4();
  const negNormal = normal.clone().negate();
  matrix.makeBasis(u, v, negNormal);
  matrix.setPosition(centroid);
  extrudeGeom.applyMatrix4(matrix);
  extrudeGeom.computeVertexNormals();

  // 9. Detect Ridge Line (highest Z points)
  let ridgePoints: [THREE.Vector3, THREE.Vector3] | null = null;
  const ridgeVerts = elem.ridge_vertices || elem.provenance?.ridge_vertices;
  if (ridgeVerts && ridgeVerts.length >= 2) {
    ridgePoints = [
      new THREE.Vector3(ridgeVerts[0][0], ridgeVerts[0][2] || centroid.y, -ridgeVerts[0][1]),
      new THREE.Vector3(ridgeVerts[1][0], ridgeVerts[1][2] || centroid.y, -ridgeVerts[1][1]),
    ];
  }

  return { geometry: extrudeGeom, ridgePoints };
}

export default function BIM3DCanvasViewer({
  walls,
  contextWalls = [],
  storeys,
  spaces = [],
  slabs = [],
  roofs = [],
  flooringElements = [],
  flooringByAssembly,
  selectedTrade = "drywall",
  selectedWallGuid,
  onSelectWall,
  selectedStorey,
  onSelectStorey,
  hiddenCategories = new Set(),
  hiddenWallGuids = new Set(),
  externalViewMode,
  onViewModeChange,
}: BIM3DCanvasViewerProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const canvas2DRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const meshesByGuidRef = useRef<Map<string, THREE.Object3D>>(new Map());
  const highlightBoxRef = useRef<THREE.BoxHelper | null>(null);
  const gridHelperRef = useRef<THREE.GridHelper | null>(null);

  const targetCamPos = useRef<THREE.Vector3 | null>(null);
  const targetLookAt = useRef<THREE.Vector3 | null>(null);
  const isTransitioning = useRef<boolean>(false);

  const wallsRef = useRef(walls);
  wallsRef.current = walls;
  const flooringRef = useRef(flooringElements);
  flooringRef.current = flooringElements;
  const roofsRef = useRef(roofs);
  roofsRef.current = roofs;
  const selectedTradeRef = useRef(selectedTrade);
  selectedTradeRef.current = selectedTrade;

  // View Mode & Split State
  const [internalViewMode, setInternalViewMode] = useState<"3D" | "2D" | "SPLIT">("3D");
  const viewMode = externalViewMode || internalViewMode;
  const [splitRatio, setSplitRatio] = useState<number>(0.5); // 0.2 to 0.8
  const [isDraggingSplitter, setIsDraggingSplitter] = useState(false);

  const setViewMode = (m: "3D" | "2D" | "SPLIT") => {
    setInternalViewMode(m);
    onViewModeChange?.(m);
  };

  const [renderStyle, setRenderStyle] = useState<"solid" | "glass" | "wireframe">("solid");
  const [hoveredWall, setHoveredWall] = useState<any | null>(null);
  const [hoveredRoom, setHoveredRoom] = useState<any | null>(null);

  // 3D Estimator Viewport Controls
  const [cameraPreset, setCameraPreset] = useState<"ISO" | "TOP" | "FRONT" | "SIDE" | "FIT" | "SELECTED">("ISO");
  const [showFullBuildingContext, setShowFullBuildingContext] = useState(false);

  // 2D Tools, Toggles & Filters
  const [activeCanvasTool, setActiveCanvasTool] = useState<Canvas2DTool>("select");
  const [takeoffFilter, setTakeoffFilter] = useState<Takeoff2DFilter>("ALL");
  const [showDimensions, setShowDimensions] = useState(true);
  const [showRoomTags, setShowRoomTags] = useState(true);
  const [showGridBubbles, setShowGridBubbles] = useState(true);
  const [showHatches, setShowHatches] = useState(true);
  const [showLegend, setShowLegend] = useState(false);

  // 2D Canvas Transform State (Pan & Zoom)
  const [pan2D, setPan2D] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [zoom2D, setZoom2D] = useState<number>(20);
  const [isDragging2D, setIsDragging2D] = useState(false);
  const dragStart2D = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  // Interactive Measurement State (Client-Side Visual Only)
  const [measurePoints, setMeasurePoints] = useState<Array<{ x: number; y: number }>>([]);
  const [liveCursorWorld, setLiveCursorWorld] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const boundsCenterRef = useRef<THREE.Vector3>(new THREE.Vector3(0, 0, 0));
  const boundsSizeRef = useRef<THREE.Vector3>(new THREE.Vector3(60, 30, 60));

  // Resizable Splitter Drag Handler
  const handleSplitterMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDraggingSplitter(true);
  }, []);

  useEffect(() => {
    if (!isDraggingSplitter) return;

    const onMouseMove = (e: MouseEvent) => {
      const container = containerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const newRatio = Math.max(0.2, Math.min(0.8, x / rect.width));
      setSplitRatio(newRatio);
    };

    const onMouseUp = () => {
      setIsDraggingSplitter(false);
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, [isDraggingSplitter]);

  // Filtered display walls with Storey-Aware Scoping for Flooring Estimator
  const displayWalls = useMemo(() => {
    const sourceWalls = selectedTrade === "drywall" ? walls : (contextWalls.length > 0 ? contextWalls : walls);
    return sourceWalls.filter((w) => {
      let matchStorey = selectedStorey === "ALL" || w.storey_name === selectedStorey || w.storey_id === selectedStorey;

      // In Flooring mode: subordinate surrounding context to active storey unless explicitly toggled
      if (selectedTrade === "flooring" && !showFullBuildingContext) {
        let activeTargetStorey = selectedStorey;
        if (selectedWallGuid) {
          const selFloor = flooringElements.find((f: any) => (f.ifc_guid || f.id) === selectedWallGuid);
          if (selFloor?.storey_name) activeTargetStorey = selFloor.storey_name;
        } else if (activeTargetStorey === "ALL") {
          const firstFloor = flooringElements.find((f: any) => f.storey_name);
          if (firstFloor?.storey_name) activeTargetStorey = firstFloor.storey_name;
        }
        if (activeTargetStorey !== "ALL") {
          matchStorey = w.storey_name === activeTargetStorey || w.storey_id === activeTargetStorey;
        }
      }

      const isVisibleCat = !hiddenCategories.has(w.wall_classification || "INTERIOR_PARTITION");
      const isVisibleWall = !hiddenWallGuids.has(w.ifc_guid);

      let matchTakeoff = true;
      if (selectedTrade === "drywall") {
        if (takeoffFilter === "ELIGIBLE") matchTakeoff = w.qto_eligibility === "ELIGIBLE";
        else if (takeoffFilter === "SINGLE_FACE") matchTakeoff = w.drywall_side_a_scope && !w.drywall_side_b_scope;
        else if (takeoffFilter === "DOUBLE_FACE") matchTakeoff = w.drywall_side_a_scope && w.drywall_side_b_scope;
        else if (takeoffFilter === "REVIEW_REQUIRED") matchTakeoff = w.qto_eligibility === "REVIEW_REQUIRED";
        else if (takeoffFilter === "BLOCKED") matchTakeoff = w.qto_eligibility?.startsWith("INELIGIBLE");
      }

      return matchStorey && isVisibleCat && isVisibleWall && matchTakeoff;
    });
  }, [walls, contextWalls, selectedTrade, selectedStorey, hiddenCategories, hiddenWallGuids, takeoffFilter, showFullBuildingContext, flooringElements, selectedWallGuid]);

  // Selected Wall Entity
  const selectedWall = useMemo(() => {
    return walls.find((w) => w.ifc_guid === selectedWallGuid) || null;
  }, [walls, selectedWallGuid]);

  // Total Openings in View
  const openingsCount = useMemo(() => {
    return displayWalls.reduce((sum, w) => sum + (w.openings?.length || 0), 0);
  }, [displayWalls]);

  // Active Storey Spaces
  const currentSpaces = useMemo(() => {
    return spaces.filter((sp) => {
      return selectedStorey === "ALL" || sp.storey_id === selectedStorey || sp.storey_id === selectedStorey;
    });
  }, [spaces, selectedStorey]);

  // Auto-Fit 2D Canvas to bounding box of display elements with intelligent margin & vertical balancing
  const autoFit2D = useCallback(() => {
    if (displayWalls.length === 0) return;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    displayWalls.forEach((w) => {
      const sx = w.start_point?.[0] || 0;
      const sy = w.start_point?.[1] || 0;
      const ex = w.end_point?.[0] || sx + (w.length_ft || 10);
      const ey = w.end_point?.[1] || sy;
      minX = Math.min(minX, sx, ex);
      maxX = Math.max(maxX, sx, ex);
      minY = Math.min(minY, sy, ey);
      maxY = Math.max(maxY, sy, ey);
    });

    const canvas = canvas2DRef.current;
    const w = canvas?.parentElement?.clientWidth || 800;
    const h = canvas?.parentElement?.clientHeight || 600;

    const spanX = Math.max(maxX - minX, 10);
    const spanY = Math.max(maxY - minY, 10);
    const midX = (minX + maxX) / 2;
    const midY = (minY + maxY) / 2;

    // Generous 20-25% margin to prevent title block or toolbars from obscuring drawing elements
    const fitZoom = Math.min((w * 0.62) / spanX, (h * 0.58) / spanY, 32);
    const finalZoom = Math.max(8, fitZoom);
    setZoom2D(finalZoom);
    // Vertical upward bias to comfortably clear the bottom sheet title block
    setPan2D({ x: -midX * finalZoom, y: midY * finalZoom - 12 });
  }, [displayWalls]);

  useEffect(() => {
    if (viewMode === "2D" || viewMode === "SPLIT") {
      autoFit2D();
    }
  }, [viewMode, selectedStorey, autoFit2D]);

  // 1. Initialize Three.js 3D Scene
  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 600;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x070e1a);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(38, width / height, 0.1, 10000);
    camera.position.set(110, 95, 140);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.35;
    container.innerHTML = "";
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.rotateSpeed = 0.85;
    controls.zoomSpeed = 1.0;
    controls.panSpeed = 0.85;
    controls.screenSpacePanning = true;
    controls.maxPolarAngle = Math.PI / 2 - 0.01;
    controls.minDistance = 1;
    controls.maxDistance = 5000;
    controlsRef.current = controls;

    function interruptAnimation() {
      isTransitioning.current = false;
    }
    controls.addEventListener("start", interruptAnimation);
    renderer.domElement.addEventListener("wheel", interruptAnimation, { passive: true });
    renderer.domElement.addEventListener("pointerdown", interruptAnimation);

    // Studio Lighting
    const hemiLight = new THREE.HemisphereLight(0xe0f2fe, 0x0c1a2e, 1.5);
    scene.add(hemiLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 2.0);
    dirLight1.position.set(120, 200, 100);
    dirLight1.castShadow = true;
    dirLight1.shadow.mapSize.width = 2048;
    dirLight1.shadow.mapSize.height = 2048;
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x38bdf8, 1.2);
    dirLight2.position.set(-100, 80, -120);
    scene.add(dirLight2);

    const grid = new THREE.GridHelper(500, 100, 0x0284c7, 0x162840);
    grid.position.y = -0.05;
    scene.add(grid);
    gridHelperRef.current = grid;

    // Raycasting for 3D selection
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    function onPointerMove(event: MouseEvent) {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const meshes: THREE.Object3D[] = [];
      meshesByGuidRef.current.forEach((obj) => meshes.push(obj));
      const intersects = raycaster.intersectObjects(meshes, true);

      if (intersects.length > 0) {
        let hitObj: THREE.Object3D | null = intersects[0].object;
        while (hitObj && !hitObj.userData?.ifc_guid && hitObj.parent) {
          hitObj = hitObj.parent;
        }
        const guid = hitObj?.userData?.ifc_guid;
        let matched = null;
        if (selectedTradeRef.current === "flooring") {
          matched = flooringRef.current.find((f: any) => (f.ifc_guid || f.id) === guid);
        } else if (selectedTradeRef.current === "roofing") {
          matched = roofsRef.current.find((r: any) => (r.ifc_guid || r.id) === guid);
        } else {
          matched = wallsRef.current.find((w: any) => w.ifc_guid === guid);
        }
        setHoveredWall(matched || null);
        if (container) container.style.cursor = "pointer";
      } else {
        setHoveredWall(null);
        if (container) container.style.cursor = "default";
      }
    }

    function onPointerClick(event: MouseEvent) {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const meshes: THREE.Object3D[] = [];
      meshesByGuidRef.current.forEach((obj) => meshes.push(obj));
      const intersects = raycaster.intersectObjects(meshes, true);

      if (intersects.length > 0) {
        let hitObj: THREE.Object3D | null = intersects[0].object;
        while (hitObj && !hitObj.userData?.ifc_guid && hitObj.parent) {
          hitObj = hitObj.parent;
        }
        const guid = hitObj?.userData?.ifc_guid;
        if (guid) onSelectWall(guid);
      }
    }

    renderer.domElement.addEventListener("mousemove", onPointerMove);
    renderer.domElement.addEventListener("click", onPointerClick);

    let animationFrameId: number;
    function animate() {
      animationFrameId = requestAnimationFrame(animate);

      if (isTransitioning.current && targetCamPos.current && targetLookAt.current) {
        camera.position.lerp(targetCamPos.current, 0.08);
        controls.target.lerp(targetLookAt.current, 0.08);

        if (
          camera.position.distanceTo(targetCamPos.current) < 0.4 &&
          controls.target.distanceTo(targetLookAt.current) < 0.4
        ) {
          camera.position.copy(targetCamPos.current);
          controls.target.copy(targetLookAt.current);
          isTransitioning.current = false;
        }
      }

      controls.update();
      renderer.render(scene, camera);
    }
    animate();

    function handleResize() {
      if (!container) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      if (w === 0 || h === 0) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    }
    window.addEventListener("resize", handleResize);

    const resizeObserver = new ResizeObserver(() => {
      handleResize();
    });
    if (container) resizeObserver.observe(container);

    return () => {
      window.removeEventListener("resize", handleResize);
      resizeObserver.disconnect();
      cancelAnimationFrame(animationFrameId);
      controls.removeEventListener("start", interruptAnimation);
      renderer.domElement.removeEventListener("wheel", interruptAnimation);
      renderer.domElement.removeEventListener("pointerdown", interruptAnimation);
      renderer.domElement.removeEventListener("mousemove", onPointerMove);
      renderer.domElement.removeEventListener("click", onPointerClick);
      renderer.dispose();
      renderer.forceContextLoss();
      if (renderer.domElement && renderer.domElement.parentNode) {
        renderer.domElement.parentNode.removeChild(renderer.domElement);
      }
    };
  }, []);

  const smoothAnimateCamera = useCallback((toPos: THREE.Vector3, toTarget: THREE.Vector3) => {
    targetCamPos.current = toPos.clone();
    targetLookAt.current = toTarget.clone();
    isTransitioning.current = true;
  }, []);

  const handleFitToFlooring = useCallback((targetGuid?: string | null, preset: "ISO" | "TOP" | "FRONT" | "SIDE" | "FIT" | "SELECTED" = "ISO") => {
    if (!flooringElements || flooringElements.length === 0) return;
    const bounds = new THREE.Box3();
    const activeGuid = targetGuid !== undefined ? targetGuid : selectedWallGuid;

    // A. Focus on selected canonical flooring element geometry if available
    if (activeGuid && preset !== "FIT") {
      const selectedMesh = meshesByGuidRef.current.get(activeGuid);
      if (selectedMesh) {
        bounds.expandByObject(selectedMesh);
      }
    }

    // B. If no element selected, or explicitly FIT: frame active storey extents
    if (bounds.isEmpty()) {
      let targetStorey = selectedStorey;
      if (targetStorey === "ALL") {
        const firstWithStorey = flooringElements.find((f: any) => f.storey_name);
        targetStorey = firstWithStorey?.storey_name || "ALL";
      }

      const displayFlooring = flooringElements.filter((elem: any) => {
        if (targetStorey === "ALL") return true;
        return elem.storey_name === targetStorey || elem.storey_id === targetStorey;
      });

      displayFlooring.forEach((elem) => {
        const guid = elem.ifc_guid || elem.id;
        const mesh = meshesByGuidRef.current.get(guid);
        if (mesh) bounds.expandByObject(mesh);
      });
    }

    if (bounds.isEmpty()) {
      meshesByGuidRef.current.forEach((mesh) => bounds.expandByObject(mesh));
    }

    if (!bounds.isEmpty()) {
      const center = bounds.getCenter(new THREE.Vector3());
      const size = bounds.getSize(new THREE.Vector3());
      const isSingle = Boolean(activeGuid && preset !== "FIT");
      const footprintDim = Math.max(size.x, size.z, 10);
      
      // Optimal framing distance: single surface fills ~70% of viewport, storey fills ~75%
      const dist = isSingle ? Math.max(footprintDim * 1.5, 14) : Math.max(footprintDim * 1.25, 22);

      let targetPos: THREE.Vector3;
      if (preset === "TOP") {
        targetPos = new THREE.Vector3(center.x, center.y + dist * 1.45, center.z + 0.01);
      } else if (preset === "FRONT") {
        targetPos = new THREE.Vector3(center.x, center.y + dist * 0.28, center.z + dist * 1.15);
      } else if (preset === "SIDE") {
        targetPos = new THREE.Vector3(center.x + dist * 1.15, center.y + dist * 0.28, center.z);
      } else {
        // Clean 3/4 BIM Isometric angle (45 deg azimuth, 35 deg elevation)
        targetPos = new THREE.Vector3(
          center.x + dist * 0.82,
          center.y + dist * 0.88,
          center.z + dist * 0.82
        );
      }
      smoothAnimateCamera(targetPos, center);
    }
  }, [flooringElements, selectedStorey, selectedWallGuid, smoothAnimateCamera]);

  const handleFitToRoofing = useCallback(() => {
    if (!roofs || roofs.length === 0) return;
    const bounds = new THREE.Box3();

    if (selectedWallGuid) {
      const selectedMesh = meshesByGuidRef.current.get(selectedWallGuid);
      if (selectedMesh) {
        bounds.expandByObject(selectedMesh);
      }
    }

    if (bounds.isEmpty()) {
      const displayRoofs = roofs.filter((elem: any) => {
        if (selectedStorey === "ALL") return true;
        return elem.storey_name === selectedStorey || elem.storey_id === selectedStorey;
      });

      displayRoofs.forEach((elem) => {
        const guid = elem.ifc_guid || elem.id;
        const mesh = meshesByGuidRef.current.get(guid);
        if (mesh) bounds.expandByObject(mesh);
      });
    }

    if (bounds.isEmpty()) {
      meshesByGuidRef.current.forEach((mesh) => bounds.expandByObject(mesh));
    }

    if (!bounds.isEmpty()) {
      const center = bounds.getCenter(new THREE.Vector3());
      const size = bounds.getSize(new THREE.Vector3());
      const maxDim = Math.max(size.x, size.y, size.z, 20);
      const dist = maxDim * 1.4;
      const targetPos = new THREE.Vector3(center.x + dist * 0.85, center.y + dist * 0.95, center.z + dist * 0.85);
      smoothAnimateCamera(targetPos, center);
    }
  }, [roofs, selectedStorey, selectedWallGuid, smoothAnimateCamera]);

  useEffect(() => {
    if (selectedTrade === "flooring") {
      const timer = setTimeout(() => {
        handleFitToFlooring(selectedWallGuid, cameraPreset);
      }, 120);
      return () => clearTimeout(timer);
    } else if (selectedTrade === "roofing") {
      const timer = setTimeout(() => {
        handleFitToRoofing();
      }, 150);
      return () => clearTimeout(timer);
    }
  }, [selectedTrade, selectedStorey, selectedWallGuid, cameraPreset, handleFitToFlooring, handleFitToRoofing]);

  // 2. Build 3D Solid Meshes
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;

    meshesByGuidRef.current.forEach((mesh) => scene.remove(mesh));
    meshesByGuidRef.current.clear();
    if (highlightBoxRef.current) {
      scene.remove(highlightBoxRef.current);
      highlightBoxRef.current = null;
    }

    const bounds = new THREE.Box3();
    let selectedMeshRef: THREE.Object3D | null = null;

    // Dynamically adjust GridHelper position & opacity according to active trade/storey
    if (gridHelperRef.current) {
      if (selectedTrade === "flooring") {
        let activeZ = 0;
        if (selectedWallGuid) {
          const selFloor = flooringElements.find((f: any) => (f.ifc_guid || f.id) === selectedWallGuid);
          if (selFloor) activeZ = selFloor.elevation_ft ?? selFloor.vertices?.[0]?.[2] ?? 0;
        } else {
          let targetStorey = selectedStorey;
          if (targetStorey === "ALL") {
            const first = flooringElements.find((f: any) => f.storey_name);
            targetStorey = first?.storey_name || "ALL";
          }
          const matchedFloor = flooringElements.find(
            (f: any) => targetStorey === "ALL" || f.storey_name === targetStorey || f.storey_id === targetStorey
          );
          if (matchedFloor) activeZ = matchedFloor.elevation_ft ?? matchedFloor.vertices?.[0]?.[2] ?? 0;
        }
        gridHelperRef.current.position.y = activeZ - 0.08;
        const gridMat = gridHelperRef.current.material as THREE.LineBasicMaterial;
        if (gridMat) {
          gridMat.transparent = true;
          gridMat.opacity = 0.15;
          gridMat.color.setHex(0x162840);
        }
      } else {
        gridHelperRef.current.position.y = -0.05;
        const gridMat = gridHelperRef.current.material as THREE.LineBasicMaterial;
        if (gridMat) {
          gridMat.transparent = true;
          gridMat.opacity = 0.35;
          gridMat.color.setHex(0x0284c7);
        }
      }
    }

    displayWalls.forEach((wall) => {
      const length = Number(wall.length_ft || 0);
      if (length <= 0) return; // Strict geometry truth: Never fabricate 3D mesh for zero-length walls!

      const height = Number(wall.physical_height_ft || wall.drywall_finish_height_ft || 0);
      if (height <= 0) return;

      const startX = wall.start_point?.[0] || 0;
      const startY = wall.start_point?.[1] || 0;
      const startZ = wall.start_point?.[2] || wall.elevation_ft || 0;
      const thickness = (wall.nominal_thickness_in || 6) / 12;
      const endX = wall.end_point?.[0] ?? (startX + length);
      const endY = wall.end_point?.[1] ?? startY;

      const classification = wall.wall_classification || "INTERIOR_PARTITION";
      const catConfig = CATEGORY_COLORS[classification] || CATEGORY_COLORS.INTERIOR_PARTITION;
      const isSelected = wall.ifc_guid === selectedWallGuid;
      const isExterior = classification === "EXTERIOR_WALL";

      let geometry: THREE.BufferGeometry;
      const wallOpenings = (wall.openings && Array.isArray(wall.openings)) ? wall.openings : [];
      // Strict H-03: Filter strictly to openings with verified IFC placement.
      // NEVER fabricate synthetic positions using (opIdx + 1) / (N + 1).
      const validPlacementOpenings = wallOpenings.filter((op: any) =>
        op.position_along_wall_ft != null && !isNaN(Number(op.position_along_wall_ft)) && length > 0
      );
      if (validPlacementOpenings.length > 0) {
        // Construct true 3D extruded wall with real opening voids for doors & windows
        const shape = new THREE.Shape();
        shape.moveTo(0, 0);
        shape.lineTo(length, 0);
        shape.lineTo(length, height);
        shape.lineTo(0, height);
        shape.closePath();

        validPlacementOpenings.forEach((op: any) => {
          const opWidth = Math.min(Number(op.width_ft || 3), length * 0.45);
          const opHeight = Math.min(Number(op.height_ft || 7), height * 0.95);
          const opFrac = Math.max(0.05, Math.min(0.95, Number(op.position_along_wall_ft) / length));
          const opCenterX = opFrac * length;
          const opStartX = Math.max(0.05, opCenterX - opWidth / 2);
          const sillHeight = op.opening_type === "DOOR"
            ? 0
            : (op.sill_height_ft != null ? Math.max(0, Math.min(Number(op.sill_height_ft), height - opHeight)) : Math.max(0, (height - opHeight) * 0.4));

          const hole = new THREE.Path();
          hole.moveTo(opStartX, sillHeight);
          hole.lineTo(opStartX + opWidth, sillHeight);
          hole.lineTo(opStartX + opWidth, sillHeight + opHeight);
          hole.lineTo(opStartX, sillHeight + opHeight);
          hole.closePath();
          shape.holes.push(hole);
        });

        const extrudeGeom = new THREE.ExtrudeGeometry(shape, {
          depth: thickness,
          bevelEnabled: false,
        });
        extrudeGeom.translate(-length / 2, -height / 2, -thickness / 2);
        geometry = extrudeGeom;
      } else {
        geometry = new THREE.BoxGeometry(length, height, thickness);
      }

      let baseColor = isSelected ? 0x00f0ff : catConfig.hex;
      let roughness = 0.5;
      let metalness = 0.1;
      let isTransparent = false;
      let opacity = 1.0;
      let emissive = isSelected ? 0x0284c7 : 0x000000;
      let emissiveIntensity = isSelected ? 1.0 : 0.0;

      if (selectedTrade === "flooring") {
        // In Flooring mode: subordinate surrounding walls to subtle 8% dark slate architectural context
        baseColor = 0x0f172a;
        roughness = 0.90;
        metalness = 0.02;
        isTransparent = true;
        opacity = isSelected ? 0.70 : 0.08;
      } else if (selectedTrade === "roofing") {
        // In Roofing mode: ghost walls as clean frosted architectural room envelopes
        baseColor = 0x1e293b;
        roughness = 0.85;
        metalness = 0.05;
        isTransparent = true;
        opacity = isSelected ? 0.75 : 0.16;
      } else if (renderStyle === "glass") {
        roughness = 0.15;
        metalness = 0.1;
        isTransparent = true;
        opacity = isSelected ? 0.95 : 0.35;
      } else if (renderStyle === "solid") {
        roughness = 0.55;
        metalness = 0.12;
        isTransparent = false;
        opacity = 1.0; // Solid clean opaque architecture
      } else if (renderStyle === "wireframe") {
        isTransparent = true;
        opacity = 0.6;
      }

      const material = new THREE.MeshStandardMaterial({
        color: baseColor,
        roughness,
        metalness,
        transparent: isTransparent,
        opacity,
        emissive,
        emissiveIntensity,
        wireframe: renderStyle === "wireframe",
        side: THREE.DoubleSide,
      });

      const mesh = new THREE.Mesh(geometry, material);
      mesh.castShadow = selectedTrade !== "flooring" && selectedTrade !== "roofing";
      mesh.receiveShadow = true;

      const midX = (startX + endX) / 2;
      const midY = (startY + endY) / 2;
      const elevZ = startZ + height / 2;
      const angle = Math.atan2(endY - startY, endX - startX);

      const wallGroup = new THREE.Group();
      wallGroup.position.set(midX, elevZ, -midY);
      wallGroup.rotation.y = -angle;
      wallGroup.userData = { ifc_guid: wall.ifc_guid, name: wall.name };

      wallGroup.add(mesh);

      if (renderStyle !== "wireframe") {
        const edges = new THREE.EdgesGeometry(geometry, 24);
        const edgeColor = isSelected
          ? 0x00f0ff
          : selectedTrade === "flooring"
          ? 0x1e293b
          : selectedTrade === "roofing"
          ? 0x475569
          : renderStyle === "solid"
          ? 0x0f172a
          : isExterior
          ? 0x38bdf8
          : catConfig.edgeHex;
        const edgeMaterial = new THREE.LineBasicMaterial({
          color: edgeColor,
          linewidth: isSelected ? 3 : 1,
          transparent: true,
          opacity: isSelected
            ? 1.0
            : selectedTrade === "flooring"
            ? 0.12
            : selectedTrade === "roofing"
            ? 0.35
            : renderStyle === "solid"
            ? 1.0
            : 0.75,
        });
        const edgeLine = new THREE.LineSegments(edges, edgeMaterial);
        wallGroup.add(edgeLine);
      }

      scene.add(wallGroup);
      meshesByGuidRef.current.set(wall.ifc_guid, wallGroup);
      bounds.expandByObject(wallGroup);

      if (isSelected) {
        selectedMeshRef = wallGroup;
      }
    });

    // -----------------------------------------------------------------------
    // B. Build Canonical Flooring 3D Surfaces (Primary Subject in Flooring Mode)
    // -----------------------------------------------------------------------
    if (selectedTrade === "flooring" && flooringElements && flooringElements.length > 0) {
      const displayFlooring = flooringElements.filter((elem: any) => {
        // A. Filter by storey
        const matchStorey = selectedStorey === "ALL" || elem.storey_name === selectedStorey || elem.storey_id === selectedStorey;
        if (!matchStorey) return false;

        // B. Exclude Roof Slabs / Decks from Flooring Trade (Prevents top slanted roof plate from floating over floors)
        const isRoof = elem.qto_eligibility === "INELIGIBLE_ROOF_SLAB" ||
                       elem.is_roof === true ||
                       /roof/i.test(elem.source_name || "") ||
                       /deck/i.test(elem.source_name || "");
        if (isRoof) return false;

        // C. Exclude small foundation footings or isolated pad bases
        const isFooting = /footing|pad|column base|pile/i.test(elem.source_name || "") ||
                          (elem.gross_area_sqft && elem.gross_area_sqft < 15 && elem.source_entity_type === "IFC_SLAB");
        if (isFooting) return false;

        return true;
      });

      displayFlooring.forEach((elem: any) => {
        const poly = extractCleanPlanarFlooringPolygon(elem);
        if (poly.length < 3) return;

        const shape = new THREE.Shape();
        shape.moveTo(poly[0][0], -poly[0][1]);
        for (let i = 1; i < poly.length; i++) {
          shape.lineTo(poly[i][0], -poly[i][1]);
        }
        shape.closePath();

        const guid = elem.ifc_guid || elem.id;
        const isSelected = guid === selectedWallGuid;
        const isStructuralSlab = elem.source_entity_type === "IFC_SLAB" && elem.qto_eligibility !== "ELIGIBLE";
        const isSpatial = elem.evidence_type === "SPATIAL_SPACE_FINISH";
        const cat = elem.flooring_category || "UNASSIGNED_FINISH";
        const pal = FLOORING_PALETTE[cat] || FLOORING_PALETTE.UNASSIGNED_FINISH;

        // Architectural depth: 0.75" to 1.25" visual thickness with micro-chamfer
        const thickFt = isStructuralSlab ? 0.20 : Math.max(0.06, Math.min(0.14, (elem.thickness_in || 0.75) / 12));
        const geometry = new THREE.ExtrudeGeometry(shape, {
          depth: thickFt,
          bevelEnabled: true,
          bevelSegments: 1,
          steps: 1,
          bevelSize: 0.015,
          bevelThickness: 0.015,
        });

        // Surface Material Shading
        let baseColor = pal.hex;
        let roughness = 0.35;
        let metalness = 0.08;
        let opacity = 0.94;
        let isTransparent = false;

        if (isSelected) {
          baseColor = 0x00f0ff;
          roughness = 0.2;
          metalness = 0.15;
          opacity = 1.0;
        } else if (isStructuralSlab) {
          // Structural substrate under flooring: subtle dark architectural concrete
          baseColor = 0x1e293b;
          roughness = 0.85;
          metalness = 0.05;
          isTransparent = true;
          opacity = 0.28;
        } else if (cat === "TILE_CERAMIC_PORCELAIN") {
          roughness = 0.22;
          metalness = 0.12;
        } else if (cat === "HARDWOOD_FLOORING" || cat === "LAMINATE_FLOORING") {
          roughness = 0.42;
          metalness = 0.04;
        } else if (cat === "RESILIENT_VINYL_LVT") {
          roughness = 0.48;
          metalness = 0.05;
        } else if (cat.startsWith("CARPET")) {
          roughness = 0.88;
          metalness = 0.0;
        } else if (isSpatial) {
          opacity = 0.85;
          isTransparent = true;
        }

        const flooringTex = !isStructuralSlab ? getProceduralFlooringTexture(cat) : undefined;

        const material = new THREE.MeshStandardMaterial({
          color: isSelected ? 0x67e8f9 : baseColor,
          map: flooringTex,
          roughness,
          metalness,
          transparent: isTransparent || isSelected,
          opacity: isSelected ? 1.0 : opacity,
          emissive: isSelected ? 0x0284c7 : 0x000000,
          emissiveIntensity: isSelected ? 0.85 : 0.0,
          side: THREE.DoubleSide,
        });

        const mesh = new THREE.Mesh(geometry, material);
        mesh.receiveShadow = true;
        mesh.castShadow = !isStructuralSlab;

        const floorGroup = new THREE.Group();
        floorGroup.rotation.x = -Math.PI / 2;
        // Clean elevation placement: finish zones sit just above structural slab
        const rawZ = elem.elevation_ft ?? elem.vertices?.[0]?.[2] ?? 0;
        const zOffset = isSelected ? 0.09 : isStructuralSlab ? -0.02 : 0.04;
        floorGroup.position.set(0, rawZ + zOffset, 0);
        floorGroup.userData = {
          ifc_guid: guid,
          name: elem.source_name || elem.name,
          category: cat,
          area_sqft: elem.net_area_sqft || elem.gross_area_sqft || 0,
          storey: elem.storey_name || "Level 01",
          isFlooring: true,
        };
        floorGroup.add(mesh);

        // Edge Outlines: Strict 28-degree threshold completely eliminates coplanar internal diagonals!
        const edges = new THREE.EdgesGeometry(geometry, 28);
        const edgeColor = isSelected
          ? 0x00f0ff
          : isStructuralSlab
          ? 0x334155
          : pal.hex;
        const edgeMat = new THREE.LineBasicMaterial({
          color: edgeColor,
          linewidth: isSelected ? 3 : isStructuralSlab ? 1 : 1.6,
          transparent: true,
          opacity: isSelected ? 1.0 : isStructuralSlab ? 0.35 : 0.90,
        });
        floorGroup.add(new THREE.LineSegments(edges, edgeMat));

        scene.add(floorGroup);
        meshesByGuidRef.current.set(guid, floorGroup);
        bounds.expandByObject(floorGroup);

        if (isSelected) {
          selectedMeshRef = floorGroup;
        }
      });
    }

    // -----------------------------------------------------------------------
    // C. Build Canonical Roofing 3D Surfaces (Primary Subject in Roofing Mode)
    // -----------------------------------------------------------------------
    if (selectedTrade === "roofing" && roofs && roofs.length > 0) {
      const displayRoofs = roofs.filter((elem: any) => {
        if (selectedStorey === "ALL") return true;
        return elem.storey_name === selectedStorey || elem.storey_id === selectedStorey;
      });

      displayRoofs.forEach((elem: any) => {
        const guid = elem.ifc_guid || elem.id;
        const isSelected = guid === selectedWallGuid;
        const mat = elem.primary_material || elem.material || "SHINGLE_ASPHALT";
        const pal = ROOFING_PALETTE[mat] || ROOFING_PALETTE.UNASSIGNED_ROOF;

        // 1. Build Solid Architectural 3D Roof Geometry (Zero Tearing, 4.2" Fascia Depth)
        const { geometry, ridgePoints } = buildCleanArchitecturalRoofGeometry(elem);
        if (!geometry.attributes.position || geometry.attributes.position.count === 0) return;

        // 2. Procedural PBR Architectural Texture
        const roofTexture = getProceduralRoofTexture(mat);
        const isMetal = mat.includes("METAL");
        const isTile = mat.includes("TILE");

        const material = new THREE.MeshStandardMaterial({
          map: roofTexture,
          color: isSelected ? 0x00f0ff : isMetal ? 0x38bdf8 : isTile ? 0xea580c : pal.hex,
          roughness: isMetal ? 0.28 : isTile ? 0.75 : 0.62,
          metalness: isMetal ? 0.50 : 0.05,
          transparent: isSelected,
          opacity: isSelected ? 0.98 : 1.0,
          emissive: isSelected ? 0x0284c7 : 0x000000,
          emissiveIntensity: isSelected ? 1.8 : 0.0,
          side: THREE.DoubleSide,
        });

        const mesh = new THREE.Mesh(geometry, material);
        mesh.receiveShadow = true;
        mesh.castShadow = true;

        const roofGroup = new THREE.Group();
        roofGroup.position.set(0, 0, 0);
        roofGroup.rotation.set(0, 0, 0);

        roofGroup.userData = {
          ifc_guid: guid,
          name: elem.source_name || elem.name,
          roof_type: elem.roof_type,
          area_sqft: elem.true_surface_area_sqft || elem.plan_area_sqft || 0,
          storey: elem.storey_name || "Roof Level",
          isRoof: true,
        };
        roofGroup.add(mesh);

        // 3. 3D Architectural Ridge Cap Extrusion
        if (ridgePoints) {
          const rStart = ridgePoints[0];
          const rEnd = ridgePoints[1];
          const ridgeLen = rStart.distanceTo(rEnd);
          if (ridgeLen > 0.5) {
            const capGeom = new THREE.CylinderGeometry(0.16, 0.16, ridgeLen, 8);
            const capMat = new THREE.MeshStandardMaterial({
              color: isSelected ? 0x00f0ff : 0x1e293b,
              roughness: 0.35,
              metalness: isMetal ? 0.6 : 0.15,
            });
            const capMesh = new THREE.Mesh(capGeom, capMat);
            const mid = new THREE.Vector3().addVectors(rStart, rEnd).multiplyScalar(0.5);
            capMesh.position.copy(mid);
            capMesh.position.y += 0.14; // Sit precisely on top of roof apex
            const dir = new THREE.Vector3().subVectors(rEnd, rStart).normalize();
            capMesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
            roofGroup.add(capMesh);
          }
        }

        // 4. Razor-Sharp Edges Geometry (28 deg threshold eliminates planar triangle clutter)
        const edges = new THREE.EdgesGeometry(geometry, 28);
        const edgeColor = isSelected ? 0x00f0ff : 0x475569;
        const edgeMat = new THREE.LineBasicMaterial({
          color: edgeColor,
          linewidth: isSelected ? 3 : 1.2,
          transparent: true,
          opacity: isSelected ? 1.0 : 0.70,
        });
        roofGroup.add(new THREE.LineSegments(edges, edgeMat));

        scene.add(roofGroup);
        meshesByGuidRef.current.set(guid, roofGroup);
        bounds.expandByObject(roofGroup);

        if (isSelected) {
          selectedMeshRef = roofGroup;
        }
      });
    }

    if (selectedMeshRef && viewMode === "3D") {
      const boxHelper = new THREE.BoxHelper(selectedMeshRef, 0x00f0ff);
      scene.add(boxHelper);
      highlightBoxRef.current = boxHelper;
    }

    if (!bounds.isEmpty()) {
      boundsCenterRef.current = bounds.getCenter(new THREE.Vector3());
      boundsSizeRef.current = bounds.getSize(new THREE.Vector3());
    }
  }, [displayWalls, flooringElements, roofs, selectedTrade, selectedWallGuid, selectedStorey, hiddenCategories, renderStyle, viewMode]);

  // Center 2D view smoothly on selected wall
  useEffect(() => {
    if ((viewMode === "2D" || viewMode === "SPLIT") && selectedWallGuid) {
      const targetWall = walls.find((w) => w.ifc_guid === selectedWallGuid);
      if (targetWall) {
        const sx = targetWall.start_point?.[0] || 0;
        const sy = targetWall.start_point?.[1] || 0;
        const ex = targetWall.end_point?.[0] || sx + (targetWall.length_ft || 10);
        const ey = targetWall.end_point?.[1] || sy;
        const midX = (sx + ex) / 2;
        const midY = (sy + ey) / 2;
        setPan2D({ x: -midX * zoom2D, y: midY * zoom2D });
      }
    }
  }, [selectedWallGuid, viewMode, walls, zoom2D]);

  // =========================================================================
  // 3. ENTERPRISE BIM / TAKEOFF 2D VECTOR ARCHITECTURAL BLUEPRINT ENGINE
  // =========================================================================
  useEffect(() => {
    if (viewMode !== "2D" && viewMode !== "SPLIT") return;
    const canvas = canvas2DRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.parentElement?.clientWidth || 800;
    const height = canvas.parentElement?.clientHeight || 600;
    const dpr = Math.min(window.devicePixelRatio || 2, 2);
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    // Deep Obsidian Blueprint Background
    ctx.fillStyle = "#080e18";
    ctx.fillRect(0, 0, width, height);

    const originX = width / 2 + pan2D.x;
    const originY = height / 2 + pan2D.y;

    // -----------------------------------------------------------------------
    // A. Precision Architectural Grid
    // -----------------------------------------------------------------------
    ctx.strokeStyle = "#101d2e";
    ctx.lineWidth = 0.6;
    const gridSize = zoom2D * 5; // 5-foot major grid
    const startGridX = ((pan2D.x % gridSize) + gridSize) % gridSize;
    const startGridY = ((pan2D.y % gridSize) + gridSize) % gridSize;

    for (let x = startGridX; x < width; x += gridSize) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }
    for (let y = startGridY; y < height; y += gridSize) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(width, y);
      ctx.stroke();
    }

    // -----------------------------------------------------------------------
    // B. Structural Axis Grid Bubbles (A, B, C... / 1, 2, 3...)
    // -----------------------------------------------------------------------
    if (showGridBubbles && displayWalls.length > 0) {
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      displayWalls.forEach((w) => {
        const sx = w.start_point?.[0] || 0, sy = w.start_point?.[1] || 0;
        const ex = w.end_point?.[0] || sx + 10, ey = w.end_point?.[1] || sy;
        minX = Math.min(minX, sx, ex); maxX = Math.max(maxX, sx, ex);
        minY = Math.min(minY, sy, ey); maxY = Math.max(maxY, sy, ey);
      });

      const topY = originY - maxY * zoom2D - 50;
      const leftX = originX + minX * zoom2D - 50;
      const botY = originY - minY * zoom2D + 50;
      const rightX = originX + maxX * zoom2D + 50;

      ctx.strokeStyle = "#1e3a5f";
      ctx.setLineDash([8, 4, 2, 4]); // Dash-dot architectural center line
      ctx.lineWidth = 0.8;

      const cols = ["A", "B", "C", "D", "E", "F"];
      const colStep = (maxX - minX) / (cols.length - 1 || 1);
      cols.forEach((col, idx) => {
        const gx = originX + (minX + idx * colStep) * zoom2D;
        ctx.setLineDash([8, 4, 2, 4]);
        ctx.beginPath();
        ctx.moveTo(gx, topY + 14);
        ctx.lineTo(gx, botY - 14);
        ctx.stroke();

        ctx.setLineDash([]);
        ctx.fillStyle = "#0c1a2e";
        ctx.strokeStyle = "#0284c7";
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.arc(gx, topY, 12, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = "#38bdf8";
        ctx.font = "bold 10px JetBrains Mono, monospace";
        ctx.textAlign = "center";
        ctx.fillText(col, gx, topY + 3.5);
      });

      const rows = ["1", "2", "3", "4", "5"];
      const rowStep = (maxY - minY) / (rows.length - 1 || 1);
      rows.forEach((row, idx) => {
        const gy = originY - (minY + idx * rowStep) * zoom2D;
        ctx.setLineDash([8, 4, 2, 4]);
        ctx.beginPath();
        ctx.moveTo(leftX + 14, gy);
        ctx.lineTo(rightX - 14, gy);
        ctx.stroke();

        ctx.setLineDash([]);
        ctx.fillStyle = "#0c1a2e";
        ctx.strokeStyle = "#0284c7";
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.arc(leftX, gy, 12, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = "#38bdf8";
        ctx.font = "bold 10px JetBrains Mono, monospace";
        ctx.textAlign = "center";
        ctx.fillText(row, leftX, gy + 3.5);
      });
      ctx.textAlign = "left";
      ctx.setLineDash([]);
    }

    // -----------------------------------------------------------------------
    // C. Spaces / Room Footprints & Architectural Room Tags
    // -----------------------------------------------------------------------
    if (showRoomTags && currentSpaces.length > 0) {
      currentSpaces.forEach((sp) => {
        // Room center in 2D coordinates
        const cx = originX + (sp.start_point?.[0] || 0) * zoom2D;
        const cy = originY - (sp.start_point?.[1] || 0) * zoom2D;

        // Never fabricate missing room area
        const explicitArea = Number(sp.net_floor_area_sqft || 0);
        const hasArea = explicitArea > 0;

        const tagTitle = (sp.name || sp.long_name || "ROOM").toUpperCase();
        const tagSubtitle = hasArea
          ? `${explicitArea.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} SF`
          : null;

        ctx.font = "bold 9.5px Inter, sans-serif";
        const tw1 = ctx.measureText(tagTitle).width;
        ctx.font = "bold 8.5px JetBrains Mono, monospace";
        const tw2 = tagSubtitle ? ctx.measureText(tagSubtitle).width : 0;
        const badgeW = Math.max(tw1, tw2, 55) + 16;
        const badgeH = tagSubtitle ? 30 : 20;

        ctx.fillStyle = "#081322f2";
        ctx.strokeStyle = "#1e3a5f";
        ctx.lineWidth = 1.0;
        ctx.beginPath();
        ctx.roundRect(cx - badgeW / 2, cy - badgeH / 2, badgeW, badgeH, 4);
        ctx.fill();
        ctx.stroke();

        ctx.textAlign = "center";
        ctx.fillStyle = "#e2e8f0";
        ctx.font = "bold 9px Inter, sans-serif";
        if (tagSubtitle) {
          ctx.fillText(tagTitle, cx, cy - 3);
          ctx.fillStyle = "#38bdf8";
          ctx.font = "bold 8px JetBrains Mono, monospace";
          ctx.fillText(tagSubtitle, cx, cy + 9);
        } else {
          ctx.fillText(tagTitle, cx, cy + 3);
        }
        ctx.textAlign = "left";
      });
    }

    // -----------------------------------------------------------------------
    // D. Architectural Walls & Openings (Notched Voids, Frames & Swings)
    // -----------------------------------------------------------------------
    displayWalls.forEach((wall) => {
      const isSelected = wall.ifc_guid === selectedWallGuid;
      const isHovered = hoveredWall?.ifc_guid === wall.ifc_guid;
      const classification = wall.wall_classification || "INTERIOR_PARTITION";
      const catConfig = CATEGORY_COLORS[classification] || CATEGORY_COLORS.INTERIOR_PARTITION;

      const sx = originX + (wall.start_point?.[0] || 0) * zoom2D;
      const sy = originY - (wall.start_point?.[1] || 0) * zoom2D;
      const ex = originX + (wall.end_point?.[0] || (wall.start_point?.[0] || 0) + (wall.length_ft || 10)) * zoom2D;
      const ey = originY - (wall.end_point?.[1] || (wall.start_point?.[1] || 0)) * zoom2D;

      const wallLenPx = Math.sqrt((ex - sx) ** 2 + (ey - sy) ** 2);
      if (wallLenPx === 0) return;

      const dx = (ex - sx) / wallLenPx;
      const dy = (ey - sy) / wallLenPx;
      const perpX = -dy;
      const perpY = dx;

      const isExterior = classification === "EXTERIOR_WALL";
      const isCurtain = classification === "CURTAIN_WALL";
      const isConcrete = classification === "STRUCTURAL_CONCRETE";
      const isDemising = classification === "DEMISING_WALL";

      const thicknessPx = Math.max(isCurtain ? 4 : 5.5, ((wall.nominal_thickness_in || 6) / 12) * zoom2D);
      const halfThick = thicknessPx / 2;

      // 1. Calculate Opening Voids along Wall
      const wallOpenings = (wall.openings && Array.isArray(wall.openings)) ? wall.openings : [];
      const openingSegments: Array<{ startFrac: number; endFrac: number; op: any }> = [];

      wallOpenings.forEach((op: any) => {
        const wallLenFt = wall.length_ft || 0;
        // Strict H-03: NEVER fabricate synthetic position via (opIdx + 1) / (N + 1)
        if (op.position_along_wall_ft == null || isNaN(Number(op.position_along_wall_ft)) || wallLenFt <= 0) {
          return;
        }
        const opFrac = Math.max(0.05, Math.min(0.95, Number(op.position_along_wall_ft) / wallLenFt));
        const opWidthPx = Math.min((op.width_ft || 3) * zoom2D, wallLenPx * 0.45);
        const halfWidthFrac = (opWidthPx / 2) / wallLenPx;
        openingSegments.push({
          startFrac: Math.max(0.05, opFrac - halfWidthFrac),
          endFrac: Math.min(0.95, opFrac + halfWidthFrac),
          op,
        });
      });

      // Sort opening intervals
      openingSegments.sort((a, b) => a.startFrac - b.startFrac);

      // 2. Build Solid Wall Segments (Notched between openings)
      const solidIntervals: Array<{ startFrac: number; endFrac: number }> = [];
      let currentFrac = 0.0;
      openingSegments.forEach((opSeg) => {
        if (opSeg.startFrac > currentFrac) {
          solidIntervals.push({ startFrac: currentFrac, endFrac: opSeg.startFrac });
        }
        currentFrac = Math.max(currentFrac, opSeg.endFrac);
      });
      if (currentFrac < 1.0) {
        solidIntervals.push({ startFrac: currentFrac, endFrac: 1.0 });
      }

      // 3. Render Solid Wall Segments
      solidIntervals.forEach((seg) => {
        const segSx = sx + dx * (seg.startFrac * wallLenPx);
        const segSy = sy + dy * (seg.startFrac * wallLenPx);
        const segEx = sx + dx * (seg.endFrac * wallLenPx);
        const segEy = sy + dy * (seg.endFrac * wallLenPx);

        const p1x = segSx + perpX * halfThick, p1y = segSy + perpY * halfThick;
        const p2x = segEx + perpX * halfThick, p2y = segEy + perpY * halfThick;
        const p3x = segEx - perpX * halfThick, p3y = segEy - perpY * halfThick;
        const p4x = segSx - perpX * halfThick, p4y = segSy - perpY * halfThick;

        ctx.beginPath();
        ctx.moveTo(p1x, p1y);
        ctx.lineTo(p2x, p2y);
        ctx.lineTo(p3x, p3y);
        ctx.lineTo(p4x, p4y);
        ctx.closePath();

        // Architectural fill
        if (isSelected) {
          ctx.fillStyle = "#0c2842";
        } else if (isHovered) {
          ctx.fillStyle = "#162840";
        } else if (isExterior) {
          ctx.fillStyle = "#152438";
        } else if (isConcrete) {
          ctx.fillStyle = "#1f1828";
        } else if (isDemising) {
          ctx.fillStyle = "#221730";
        } else {
          ctx.fillStyle = "#131e2e";
        }
        ctx.fill();

        // Architectural Cross Hatching on Concrete / Masonry
        if (showHatches && zoom2D > 15 && (isConcrete || isDemising) && !isSelected) {
          ctx.save();
          ctx.clip();
          ctx.strokeStyle = isConcrete ? "#f43f5e30" : "#d946ef30";
          ctx.lineWidth = 1.0;
          const segLen = (seg.endFrac - seg.startFrac) * wallLenPx;
          for (let d = -thicknessPx; d <= segLen + thicknessPx; d += 6) {
            const hx = segSx + dx * d;
            const hy = segSy + dy * d;
            ctx.beginPath();
            ctx.moveTo(hx - perpX * halfThick - 6, hy - perpY * halfThick - 6);
            ctx.lineTo(hx + perpX * halfThick + 6, hy + perpY * halfThick + 6);
            ctx.stroke();
          }
          ctx.restore();
        }

        // Heavy Section Cut Stroke (ISO/AIA Line Weights)
        ctx.beginPath();
        ctx.moveTo(p1x, p1y);
        ctx.lineTo(p2x, p2y);
        ctx.lineTo(p3x, p3y);
        ctx.lineTo(p4x, p4y);
        ctx.closePath();
        ctx.strokeStyle = isSelected
          ? "#00f0ff"
          : isHovered
          ? "#38bdf8"
          : isExterior
          ? "#cbd5e1"
          : catConfig.stroke || "#94a3b8";
        ctx.lineWidth = isSelected ? 2.4 : isExterior ? 1.8 : 1.4;
        ctx.stroke();

        // Architectural Drywall Board Layer Visualization (Face A vs Face B)
        const hasSideA = wall.drywall_side_a_scope !== false;
        const hasSideB = wall.drywall_side_b_scope === true;

        // Face A Gypsum Board Line (Emerald = Gypsum board active; Grey dashed = raw/exterior)
        ctx.beginPath();
        ctx.moveTo(p1x + perpX * 1.5, p1y + perpY * 1.5);
        ctx.lineTo(p2x + perpX * 1.5, p2y + perpY * 1.5);
        ctx.strokeStyle = isSelected ? "#00f0ff" : hasSideA ? "#10b981" : "#64748b";
        ctx.lineWidth = isSelected ? 2.0 : 1.2;
        if (!hasSideA) ctx.setLineDash([4, 3]);
        ctx.stroke();
        ctx.setLineDash([]);

        // Face B Gypsum Board Line
        ctx.beginPath();
        ctx.moveTo(p4x - perpX * 1.5, p4y - perpY * 1.5);
        ctx.lineTo(p3x - perpX * 1.5, p3y - perpY * 1.5);
        ctx.strokeStyle = isSelected ? "#00f0ff" : hasSideB ? "#10b981" : "#64748b";
        ctx.lineWidth = isSelected ? 2.0 : 1.2;
        if (!hasSideB) ctx.setLineDash([4, 3]);
        ctx.stroke();
        ctx.setLineDash([]);
      });

      // 4. Render Architectural Hosted Openings (Doors & Windows)
      openingSegments.forEach(({ startFrac, endFrac, op }) => {
        const opSx = sx + dx * (startFrac * wallLenPx);
        const opSy = sy + dy * (startFrac * wallLenPx);
        const opEx = sx + dx * (endFrac * wallLenPx);
        const opEy = sy + dy * (endFrac * wallLenPx);
        const opLen = (endFrac - startFrac) * wallLenPx;

        // Draw Jamb Frame End Stops (2"×4" frame blocks)
        const frameW = 2.5;
        ctx.fillStyle = isSelected ? "#00f0ff" : "#475569";
        ctx.beginPath();
        ctx.rect(opSx - perpX * halfThick, opSy - perpY * halfThick, frameW, thicknessPx);
        ctx.rect(opEx - perpX * halfThick, opEy - perpY * halfThick, frameW, thicknessPx);
        ctx.fill();

        if (op.opening_type === "DOOR") {
          // A. Door Swing Leaf (Open at 90°)
          const hingeX = opSx;
          const hingeY = opSy;
          const leafTipX = hingeX + perpX * opLen;
          const leafTipY = hingeY + perpY * opLen;

          // Solid Door Leaf
          ctx.strokeStyle = isSelected ? "#00f0ff" : "#38bdf8";
          ctx.lineWidth = 1.8;
          ctx.beginPath();
          ctx.moveTo(hingeX, hingeY);
          ctx.lineTo(leafTipX, leafTipY);
          ctx.stroke();

          // Door Swing 90° Arc
          ctx.beginPath();
          ctx.setLineDash([3, 2.5]);
          ctx.arc(hingeX, hingeY, opLen, Math.atan2(dy, dx), Math.atan2(perpY, perpX), false);
          ctx.strokeStyle = isSelected ? "#00f0ff80" : "#38bdf880";
          ctx.lineWidth = 1.1;
          ctx.stroke();
          ctx.setLineDash([]);

          // Opening Label (Width × Height)
          if (showDimensions && zoom2D > 16) {
            const midOpX = (opSx + opEx) / 2;
            const midOpY = (opSy + opEy) / 2;
            const opText = `${formatArchitecturalFeet(op.width_ft || 3.0)} × ${formatArchitecturalFeet(op.height_ft || 7.0)}`;
            ctx.font = "bold 8px JetBrains Mono, monospace";
            const tw = ctx.measureText(opText).width;
            ctx.fillStyle = "#080e18";
            ctx.fillRect(midOpX - tw / 2 - 2, midOpY - 5, tw + 4, 10);
            ctx.fillStyle = isSelected ? "#00f0ff" : "#94a3b8";
            ctx.textAlign = "center";
            ctx.fillText(opText, midOpX, midOpY + 3);
            ctx.textAlign = "left";
          }
        } else {
          // B. Window Sill & Glazing Lines (Double Pane with Sill)
          ctx.strokeStyle = isSelected ? "#00f0ff" : "#0284c7";
          ctx.lineWidth = 1.6;

          // Outer Sill Line
          ctx.beginPath();
          ctx.moveTo(opSx + perpX * halfThick, opSy + perpY * halfThick);
          ctx.lineTo(opEx + perpX * halfThick, opEy + perpY * halfThick);
          ctx.stroke();

          // Inner Sill Line
          ctx.beginPath();
          ctx.moveTo(opSx - perpX * halfThick, opSy - perpY * halfThick);
          ctx.lineTo(opEx - perpX * halfThick, opEy - perpY * halfThick);
          ctx.stroke();

          // Center Glazing Pane Line
          ctx.strokeStyle = "#38bdf8";
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          ctx.moveTo(opSx, opSy);
          ctx.lineTo(opEx, opEy);
          ctx.stroke();
        }
      });

      // 5. Dimension Strings with 45° Architectural Tick Marks
      if (showDimensions && (zoom2D > 12 || isSelected)) {
        const offsetDist = halfThick + 18;
        const dimSx = sx + perpX * offsetDist;
        const dimSy = sy + perpY * offsetDist;
        const dimEx = ex + perpX * offsetDist;
        const dimEy = ey + perpY * offsetDist;

        ctx.strokeStyle = isSelected ? "#00f0ff" : "#64748b";
        ctx.lineWidth = isSelected ? 1.4 : 0.9;

        // Witness lines
        ctx.beginPath();
        ctx.moveTo(sx + perpX * (halfThick + 2), sy + perpY * (halfThick + 2));
        ctx.lineTo(dimSx + perpX * 3, dimSy + perpY * 3);
        ctx.moveTo(ex + perpX * (halfThick + 2), ey + perpY * (halfThick + 2));
        ctx.lineTo(dimEx + perpX * 3, dimEy + perpY * 3);
        ctx.stroke();

        // Main dimension line
        ctx.beginPath();
        ctx.moveTo(dimSx, dimSy);
        ctx.lineTo(dimEx, dimEy);
        ctx.stroke();

        // 45° Architectural slash ticks
        const tickSize = 4;
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.moveTo(dimSx - perpX * tickSize - dx * tickSize, dimSy - perpY * tickSize - dy * tickSize);
        ctx.lineTo(dimSx + perpX * tickSize + dx * tickSize, dimSy + perpY * tickSize + dy * tickSize);
        ctx.moveTo(dimEx - perpX * tickSize - dx * tickSize, dimEy - perpY * tickSize - dy * tickSize);
        ctx.lineTo(dimEx + perpX * tickSize + dx * tickSize, dimEy + perpY * tickSize + dy * tickSize);
        ctx.stroke();

        // Dimension text knockout with border for anti-collision
        const mx = (dimSx + dimEx) / 2;
        const my = (dimSy + dimEy) / 2;
        const lenText = `${formatArchitecturalFeet(wall.length_ft || 10)} (${Number(wall.length_ft || 10).toFixed(2)} LF)`;

        ctx.font = "bold 9px JetBrains Mono, monospace";
        const tw = ctx.measureText(lenText).width;
        ctx.fillStyle = "#080e18f8";
        ctx.strokeStyle = "#162840";
        ctx.lineWidth = 1.0;
        ctx.beginPath();
        ctx.rect(mx - tw / 2 - 4, my - 6.5, tw + 8, 13);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = isSelected ? "#00f0ff" : "#cbd5e1";
        ctx.textAlign = "center";
        ctx.fillText(lenText, mx, my + 3.5);
        ctx.textAlign = "left";
      }

      // 6. Selected Element Floating HUD Callout with Anti-Collision & Viewport Clamping
      if (isSelected) {
        const wallMidX = (sx + ex) / 2;
        const wallMidY = (sy + ey) / 2;

        const catInfo = CATEGORY_COLORS[wall.wall_classification] || CATEGORY_COLORS.UNKNOWN;
        const primaryTitle = catInfo?.label || wall.wall_classification?.replace(/_/g, " ") || "Wall Partition";
        const tag1 = primaryTitle;
        const tag2 = wall.name ? `${wall.name}` : `GUID: ${wall.ifc_guid}`;
        const facesStr =
          wall.drywall_side_a_scope && wall.drywall_side_b_scope
            ? "2-FACES"
            : wall.drywall_side_a_scope
            ? "1-FACE"
            : "NO-DRYWALL";
        const tag3 = `L: ${Number(wall.length_ft || 0).toFixed(2)}' · H: ${Number(
          wall.drywall_finish_height_ft || 10
        ).toFixed(1)}' · ${facesStr}`;

        ctx.font = "bold 9.5px Inter, sans-serif";
        const tw1 = ctx.measureText(tag1).width;
        ctx.font = "bold 8px JetBrains Mono, monospace";
        const tw2 = ctx.measureText(tag2).width;
        const tw3 = ctx.measureText(tag3).width;

        const cardW = Math.max(tw1, tw2, tw3, 140) + 20;
        const cardH = 46;

        // Intelligent Positioning: Flip below if wall is near top boundary
        const preferAbove = wallMidY - halfThick - cardH - 12 > 65;
        const rawCalloutY = preferAbove
          ? wallMidY - halfThick - cardH / 2 - 14
          : wallMidY + halfThick + cardH / 2 + 14;

        // Clamp inside canvas viewable boundaries to prevent clipping
        const calloutX = Math.max(cardW / 2 + 16, Math.min(width - cardW / 2 - 16, wallMidX));
        const calloutY = Math.max(cardH / 2 + 55, Math.min(height - cardH / 2 - 80, rawCalloutY));

        // Subtle anchor leader line to wall center
        ctx.strokeStyle = "#00f0ff80";
        ctx.setLineDash([2, 2]);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(wallMidX, wallMidY);
        ctx.lineTo(calloutX, preferAbove ? calloutY + cardH / 2 : calloutY - cardH / 2);
        ctx.stroke();
        ctx.setLineDash([]);

        // High-contrast clean architectural HUD card
        ctx.fillStyle = "#081322fa";
        ctx.strokeStyle = "#00f0ff";
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.roundRect(calloutX - cardW / 2, calloutY - cardH / 2, cardW, cardH, 5);
        ctx.fill();
        ctx.stroke();

        ctx.textAlign = "center";
        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 9.5px Inter, sans-serif";
        ctx.fillText(tag1, calloutX, calloutY - 10);

        ctx.fillStyle = "#38bdf8";
        ctx.font = "bold 8px JetBrains Mono, monospace";
        ctx.fillText(tag2, calloutX, calloutY + 2);

        ctx.fillStyle = "#10b981";
        ctx.font = "bold 8px JetBrains Mono, monospace";
        ctx.fillText(tag3, calloutX, calloutY + 14);
        ctx.textAlign = "left";
      }
    });

    // -----------------------------------------------------------------------
    // E. Interactive Distance & Area Measurement Tool Overlays
    // -----------------------------------------------------------------------
    if (activeCanvasTool === "measure-distance" && measurePoints.length > 0) {
      const p1 = measurePoints[0];
      const p1ScreenX = originX + p1.x * zoom2D;
      const p1ScreenY = originY - p1.y * zoom2D;
      const p2ScreenX = originX + liveCursorWorld.x * zoom2D;
      const p2ScreenY = originY - liveCursorWorld.y * zoom2D;

      const distFt = Math.hypot(liveCursorWorld.x - p1.x, liveCursorWorld.y - p1.y);
      const deltaX = Math.abs(liveCursorWorld.x - p1.x);
      const deltaY = Math.abs(liveCursorWorld.y - p1.y);

      // Distance Line
      ctx.strokeStyle = "#f59e0b";
      ctx.setLineDash([5, 3]);
      ctx.lineWidth = 2.0;
      ctx.beginPath();
      ctx.moveTo(p1ScreenX, p1ScreenY);
      ctx.lineTo(p2ScreenX, p2ScreenY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Point Nodes
      ctx.fillStyle = "#f59e0b";
      ctx.beginPath();
      ctx.arc(p1ScreenX, p1ScreenY, 4, 0, Math.PI * 2);
      ctx.arc(p2ScreenX, p2ScreenY, 4, 0, Math.PI * 2);
      ctx.fill();

      // Measurement Readout Callout
      const midDistX = (p1ScreenX + p2ScreenX) / 2;
      const midDistY = (p1ScreenX + p2ScreenX) / 2;
      const distLabel = `TAPE: ${formatArchitecturalFeet(distFt)} (${distFt.toFixed(2)} LF) · ΔX: ${deltaX.toFixed(2)}' ΔY: ${deltaY.toFixed(2)}'`;

      ctx.font = "bold 10px JetBrains Mono, monospace";
      const dw = ctx.measureText(distLabel).width;
      ctx.fillStyle = "#0c1a2ef5";
      ctx.strokeStyle = "#f59e0b";
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.roundRect(midDistX - dw / 2 - 4, midDistY - 14, dw + 8, 20, 4);
      ctx.fill();
      ctx.stroke();

      ctx.textAlign = "center";
      ctx.fillStyle = "#fde68a";
      ctx.fillText(distLabel, midDistX, midDistY);
      ctx.textAlign = "left";
    }

    // -----------------------------------------------------------------------
    // F. Architectural Sheet Title Block (Bottom-Left)
    // -----------------------------------------------------------------------
    ctx.fillStyle = "#0c1829f0";
    ctx.strokeStyle = "#1e3a5f";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(16, height - 76, 310, 60, 6);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "#38bdf8";
    ctx.font = "bold 11px Inter, sans-serif";
    ctx.fillText("PROTAKEOFF · CANONICAL BIM TAKEOFF PLAN", 26, height - 54);

    ctx.fillStyle = "#94a3b8";
    ctx.font = "9px JetBrains Mono, monospace";
    ctx.fillText(`LEVEL: ${selectedStorey.toUpperCase()} | SCALE: 1/8" = 1'-0" (1:96)`, 26, height - 38);
    ctx.fillText(
      `CANONICAL TRUTH | ${displayWalls.length} WALLS · ${openingsCount} OPENINGS`,
      26,
      height - 24
    );

    // North Arrow in Bottom-Right
    const naX = width - 40;
    const naY = height - 44;
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(naX, naY, 14, 0, Math.PI * 2);
    ctx.stroke();

    ctx.fillStyle = "#38bdf8";
    ctx.beginPath();
    ctx.moveTo(naX, naY - 11);
    ctx.lineTo(naX - 4, naY + 4);
    ctx.lineTo(naX, naY + 1);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.moveTo(naX, naY - 11);
    ctx.lineTo(naX + 4, naY + 4);
    ctx.lineTo(naX, naY + 1);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 8px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("N", naX, naY - 14);
    ctx.textAlign = "left";

  }, [
    viewMode,
    displayWalls,
    selectedWallGuid,
    hoveredWall,
    hoveredRoom,
    pan2D,
    zoom2D,
    currentSpaces,
    showDimensions,
    showRoomTags,
    showGridBubbles,
    showHatches,
    selectedStorey,
    selectedTrade,
    takeoffFilter,
    activeCanvasTool,
    measurePoints,
    liveCursorWorld,
  ]);

  // -------------------------------------------------------------------------
  // 2D Mouse Dragging, Panning & Interactive Measurement
  // -------------------------------------------------------------------------
  function handleMouseDown2D(e: React.MouseEvent) {
    if (viewMode !== "2D" && viewMode !== "SPLIT") return;

    const canvas = canvas2DRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    const width = canvas.width / Math.min(window.devicePixelRatio || 2, 2);
    const height = canvas.height / Math.min(window.devicePixelRatio || 2, 2);
    const originX = width / 2 + pan2D.x;
    const originY = height / 2 + pan2D.y;
    const worldX = (mouseX - originX) / zoom2D;
    const worldY = (originY - mouseY) / zoom2D;

    if (activeCanvasTool === "measure-distance") {
      if (measurePoints.length === 0) {
        setMeasurePoints([{ x: worldX, y: worldY }]);
      } else {
        setMeasurePoints([]); // Reset after second click
      }
      return;
    }

    if (activeCanvasTool === "pan" || e.button === 1 || e.shiftKey) {
      setIsDragging2D(true);
      dragStart2D.current = { x: e.clientX - pan2D.x, y: e.clientY - pan2D.y };
      return;
    }

    // Default: Select
    setIsDragging2D(true);
    dragStart2D.current = { x: e.clientX - pan2D.x, y: e.clientY - pan2D.y };
  }

  function handleMouseMove2D(e: React.MouseEvent) {
    if (viewMode !== "2D" && viewMode !== "SPLIT") return;

    const canvas = canvas2DRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const width = canvas.width / Math.min(window.devicePixelRatio || 2, 2);
    const height = canvas.height / Math.min(window.devicePixelRatio || 2, 2);
    const originX = width / 2 + pan2D.x;
    const originY = height / 2 + pan2D.y;

    const worldX = (mouseX - originX) / zoom2D;
    const worldY = (originY - mouseY) / zoom2D;
    setLiveCursorWorld({ x: worldX, y: worldY });

    if (isDragging2D && (activeCanvasTool === "pan" || e.buttons === 4 || e.shiftKey)) {
      setPan2D({
        x: e.clientX - dragStart2D.current.x,
        y: e.clientY - dragStart2D.current.y,
      });
    }

    // Wall Hit Detection
    let foundWall: any = null;
    displayWalls.forEach((wall) => {
      const sx = originX + (wall.start_point?.[0] || 0) * zoom2D;
      const sy = originY - (wall.start_point?.[1] || 0) * zoom2D;
      const ex = originX + (wall.end_point?.[0] || (wall.start_point?.[0] || 0) + (wall.length_ft || 10)) * zoom2D;
      const ey = originY - (wall.end_point?.[1] || (wall.start_point?.[1] || 0)) * zoom2D;

      const dx = ex - sx;
      const dy = ey - sy;
      const lenSq = dx * dx + dy * dy;
      if (lenSq === 0) return;

      const t = Math.max(0, Math.min(1, ((mouseX - sx) * dx + (mouseY - sy) * dy) / lenSq));
      const projX = sx + t * dx;
      const projY = sy + t * dy;
      const dist = Math.sqrt((mouseX - projX) ** 2 + (mouseY - projY) ** 2);

      if (dist < 14) {
        foundWall = wall;
      }
    });

    setHoveredWall(foundWall);

    if (activeCanvasTool === "measure-distance") {
      canvas.style.cursor = "crosshair";
    } else if (foundWall) {
      canvas.style.cursor = "pointer";
    } else {
      canvas.style.cursor = activeCanvasTool === "pan" ? (isDragging2D ? "grabbing" : "grab") : "default";
    }
  }

  function handleMouseUp2D() {
    setIsDragging2D(false);
  }

  function handleClick2D() {
    if (activeCanvasTool === "select" && hoveredWall) {
      onSelectWall(hoveredWall.ifc_guid);
    }
  }

  function handleWheel2D(e: React.WheelEvent) {
    if (viewMode !== "2D" && viewMode !== "SPLIT") return;
    const factor = e.deltaY < 0 ? 1.15 : 0.88;
    setZoom2D((prev) => Math.max(4, Math.min(80, prev * factor)));
  }

  function handleFit() {
    if (viewMode === "2D") {
      autoFit2D();
    } else {
      const center = boundsCenterRef.current;
      const size = boundsSizeRef.current;
      const maxDim = Math.max(size.x, size.y, size.z, 25);
      smoothAnimateCamera(
        new THREE.Vector3(center.x + maxDim * 1.15, center.y + maxDim * 0.95, center.z + maxDim * 1.3),
        center
      );
      if (viewMode === "SPLIT") {
        autoFit2D();
      }
    }
  }

  return (
    <div ref={containerRef} className="relative h-full w-full overflow-hidden bg-[#060b14] select-none flex">
      {/* ===================================================================== */}
      {/* 3D WEBGL VIEWPORT PANE                                                */}
      {/* ===================================================================== */}
      <div
        className={`relative h-full overflow-hidden ${
          viewMode === "SPLIT"
            ? "block"
            : viewMode === "2D"
            ? "hidden"
            : "w-full block"
        }`}
        style={{
          width: viewMode === "SPLIT" ? `${splitRatio * 100}%` : viewMode === "3D" ? "100%" : "0%",
        }}
      >
        {/* 3D Viewport Header Bar */}
        <div className="absolute top-3 left-3 right-3 z-10 flex items-center justify-between pointer-events-none">
          <div className="flex items-center space-x-2 bg-[#0a121e]/90 backdrop-blur-md px-2.5 py-1 rounded-md border border-[#162840] shadow-lg pointer-events-auto">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
            <span className="text-[10px] font-mono font-extrabold text-white tracking-wider">
              {selectedTrade === "flooring" ? "FLOORING 3D FINISH MODEL" : selectedTrade === "roofing" ? "ROOFING 3D MODEL" : "3D SPATIAL MODEL"}
            </span>
            <span className="text-[9px] font-mono bg-cyan-950 text-cyan-300 px-1.5 py-0.5 rounded border border-cyan-800 font-bold">
              WEBGL
            </span>
          </div>

        {/* Sleek Floating Hover Inspector in 3D */}
        {hoveredWall && (
          <div className="absolute top-14 left-3 z-20 pointer-events-none bg-[#0a121e]/95 backdrop-blur-md px-3.5 py-2 rounded-lg border border-cyan-500/40 shadow-2xl flex flex-col gap-1 min-w-[210px] animate-fadeIn">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[11px] font-bold text-cyan-300 font-mono flex items-center gap-1.5 truncate max-w-[150px]">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shrink-0" />
                {selectedTrade === "flooring"
                  ? (FLOORING_PALETTE[hoveredWall.flooring_category]?.label || hoveredWall.source_name || "Flooring Finish")
                  : selectedTrade === "roofing"
                  ? (hoveredWall.roof_type || hoveredWall.source_name || "Roof Plane")
                  : (hoveredWall.name || "Wall")}
              </span>
              <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800 shrink-0">
                {hoveredWall.storey_name || hoveredWall.storey || "Level"}
              </span>
            </div>
            {selectedTrade === "flooring" && (
              <div className="flex items-center justify-between text-[10px] font-mono text-gray-400 border-t border-gray-800/80 pt-1 mt-0.5">
                <span>Net Area:</span>
                <span className="font-bold text-cyan-300 font-mono">
                  {hoveredWall.net_area_sqft?.toLocaleString() || hoveredWall.gross_area_sqft?.toLocaleString() || "0"} SF
                </span>
              </div>
            )}
          </div>
        )}

        <div className="flex items-center space-x-2">
            {/* Flooring Estimator Camera Presets & Context Control */}
            {selectedTrade === "flooring" && (
              <div className="flex items-center space-x-1 bg-[#0a121e]/90 backdrop-blur-md p-1 rounded-md border border-[#162840] shadow-lg pointer-events-auto">
                <span className="text-[9px] font-mono text-cyan-400 font-bold px-1.5 uppercase tracking-wider">
                  VIEW:
                </span>
                {(
                  [
                    { id: "ISO", label: "3D ISO" },
                    { id: "TOP", label: "TOP" },
                    { id: "FRONT", label: "FRONT" },
                    { id: "SIDE", label: "SIDE" },
                    { id: "FIT", label: "FIT FLOOR" },
                  ] as const
                ).map((preset) => (
                  <button
                    key={preset.id}
                    onClick={() => {
                      setCameraPreset(preset.id);
                      handleFitToFlooring(selectedWallGuid, preset.id);
                    }}
                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold transition-all cursor-pointer ${
                      cameraPreset === preset.id
                        ? "bg-cyan-600 text-white shadow-sm"
                        : "text-gray-400 hover:text-white hover:bg-gray-800"
                    }`}
                    title={`Align Camera to ${preset.label}`}
                  >
                    {preset.label}
                  </button>
                ))}

                <div className="w-[1px] h-3 bg-gray-700 mx-0.5" />

                {/* Context Toggle: Active Storey vs Full Building Context */}
                <button
                  onClick={() => setShowFullBuildingContext((prev) => !prev)}
                  className={`px-2 py-0.5 rounded text-[9px] font-mono font-bold transition-all cursor-pointer border ${
                    showFullBuildingContext
                      ? "bg-amber-950/80 text-amber-300 border-amber-700/80"
                      : "bg-slate-800/80 text-slate-300 border-slate-700/60 hover:text-white"
                  }`}
                  title="Toggle between Active Storey walls and Full Building context envelope"
                >
                  CONTEXT: {showFullBuildingContext ? "FULL BLDG" : "STOREY"}
                </button>
              </div>
            )}

            <div className="flex items-center space-x-1.5 bg-[#0a121e]/90 backdrop-blur-md p-1 rounded-md border border-[#162840] shadow-lg pointer-events-auto">
            {(
              [
                { id: "solid", label: "SOLID" },
                { id: "glass", label: "X-RAY / GLASS" },
                { id: "wireframe", label: "WIREFRAME" },
              ] as const
            ).map((style) => (
              <button
                key={style.id}
                onClick={() => setRenderStyle(style.id)}
                className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold transition-all cursor-pointer ${
                  renderStyle === style.id
                    ? "bg-cyan-600 text-white shadow-sm"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                {style.label}
              </button>
            ))}
            <div className="w-[1px] h-3 bg-gray-700 mx-0.5" />
            <button
              onClick={() => {
                if (selectedTrade === "flooring") {
                  handleFitToFlooring();
                } else if (selectedTrade === "roofing") {
                  handleFitToRoofing();
                } else {
                  const center = boundsCenterRef.current;
                  const size = boundsSizeRef.current;
                  const maxDim = Math.max(size.x, size.y, size.z, 25);
                  smoothAnimateCamera(
                    new THREE.Vector3(center.x + maxDim * 1.15, center.y + maxDim * 0.95, center.z + maxDim * 1.3),
                    center
                  );
                }
              }}
              className="p-1 rounded hover:bg-gray-800 text-cyan-400 hover:text-white transition-colors cursor-pointer"
              title={
                selectedTrade === "flooring"
                  ? "Fit Camera to Flooring"
                  : selectedTrade === "roofing"
                  ? "Fit Camera to Roofing"
                  : "Fit 3D Camera"
              }
            >
              <Maximize2 size={12} />
            </button>
          </div>
        </div>
      </div>

        {/* 3D WebGL Canvas Mount */}
        <div ref={mountRef} className="h-full w-full block" />

        {/* 3D Bottom Telemetry HUD */}
        <div className="absolute bottom-2.5 left-3 right-3 z-10 flex items-center justify-between text-[9px] font-mono text-gray-400 pointer-events-none">
          <div className="bg-[#0a121e]/90 backdrop-blur-sm px-2 py-0.5 rounded border border-[#162840]">
            CAMERA: ORBIT 3D · LEVEL: {selectedStorey}
          </div>
          {selectedWallGuid && (
            <div className="bg-cyan-950/90 backdrop-blur-sm px-2 py-0.5 rounded border border-cyan-800 text-cyan-300 font-bold truncate max-w-[320px]">
              {(() => {
                if (selectedTrade === "flooring") {
                  const targetFloor = flooringElements.find((f: any) => (f.ifc_guid || f.id) === selectedWallGuid);
                  const label = targetFloor?.flooring_category?.replace(/_/g, " ") || targetFloor?.source_name || "Flooring Surface";
                  return `FLOORING · ${label}`;
                } else if (selectedTrade === "roofing") {
                  const targetRoof = roofs.find((r: any) => (r.ifc_guid || r.id) === selectedWallGuid);
                  const label = targetRoof?.roof_type || targetRoof?.primary_material || "Roof Plane";
                  return `ROOFING · ${label}`;
                } else {
                  const targetWall = walls.find((w: any) => w.ifc_guid === selectedWallGuid);
                  const cat = CATEGORY_COLORS[targetWall?.wall_classification]?.label || "Wall";
                  return `${cat} · GUID: ${selectedWallGuid.slice(0, 16)}…`;
                }
              })()}
            </div>
          )}
        </div>
      </div>

      {/* ===================================================================== */}
      {/* DRAGGABLE RESIZABLE SPLITTER (SPLIT MODE ONLY)                        */}
      {/* ===================================================================== */}
      {viewMode === "SPLIT" && (
        <div
          onMouseDown={handleSplitterMouseDown}
          onDoubleClick={() => setSplitRatio(0.5)}
          className={`group relative z-30 flex-shrink-0 w-2.5 h-full cursor-col-resize select-none flex items-center justify-center transition-all ${
            isDraggingSplitter
              ? "bg-cyan-500 shadow-[0_0_20px_rgba(6,182,212,0.9)]"
              : "bg-[#0e1726] hover:bg-cyan-700/60 border-x border-[#162840]"
          }`}
          title="Drag to resize · Double-click to reset 50:50"
        >
          <div className="w-1 h-10 rounded-full bg-cyan-400/80 group-hover:bg-cyan-200 flex items-center justify-center shadow-md">
            <GripVertical size={10} className="text-black" />
          </div>
        </div>
      )}

      {/* ===================================================================== */}
      {/* 2D VECTOR CAD PLAN VIEWPORT PANE                                      */}
      {/* ===================================================================== */}
      <div
        className={`relative h-full overflow-hidden ${
          viewMode === "SPLIT"
            ? "block"
            : viewMode === "3D"
            ? "hidden"
            : "w-full block"
        }`}
        style={{
          width: viewMode === "SPLIT" ? `${(1 - splitRatio) * 100}%` : viewMode === "2D" ? "100%" : "0%",
        }}
      >
        {selectedTrade === "flooring" ? (
          <BIM2DFlooringPlan
            flooringElements={flooringElements}
            walls={contextWalls.length > 0 ? contextWalls : walls}
            storeys={storeys}
            selectedStorey={selectedStorey}
            onSelectStorey={onSelectStorey}
            selectedFlooringGuid={selectedWallGuid}
            onSelectFlooringGuid={onSelectWall}
          />
        ) : selectedTrade === "roofing" ? (
          <BIM2DRoofPlan
            roofs={roofs}
            walls={contextWalls.length > 0 ? contextWalls : walls}
            storeys={storeys}
            selectedStorey={selectedStorey}
            onSelectStorey={onSelectStorey}
            selectedRoofGuid={selectedWallGuid}
            onSelectRoofGuid={onSelectWall}
          />
        ) : (
          <>
            {/* 2D Viewport Header Bar (CAD Tools + Takeoff Filters + Overlays) */}
            <div className="absolute top-3 left-3 right-3 z-10 flex items-center justify-between pointer-events-none flex-wrap gap-2">
              {/* Active Canvas Mode Selector */}
              <div className="flex items-center space-x-1 bg-[#0a121e]/90 backdrop-blur-md p-1 rounded-md border border-[#162840] shadow-lg pointer-events-auto">
                <button
                  onClick={() => setActiveCanvasTool("select")}
                  className={`p-1.5 rounded flex items-center gap-1 text-[10px] font-mono font-bold transition-all cursor-pointer ${
                    activeCanvasTool === "select"
                      ? "bg-cyan-600 text-white"
                      : "text-gray-400 hover:text-white hover:bg-gray-800"
                  }`}
                  title="Select Element (S)"
                >
                  <MousePointer size={12} />
                  <span>Select</span>
                </button>
                <button
                  onClick={() => setActiveCanvasTool("pan")}
                  className={`p-1.5 rounded flex items-center gap-1 text-[10px] font-mono font-bold transition-all cursor-pointer ${
                    activeCanvasTool === "pan"
                      ? "bg-cyan-600 text-white"
                      : "text-gray-400 hover:text-white hover:bg-gray-800"
                  }`}
                  title="Pan Tool (H / Hand)"
                >
                  <Hand size={12} />
                  <span>Pan</span>
                </button>
                <button
                  onClick={() => {
                    setActiveCanvasTool("measure-distance");
                    setMeasurePoints([]);
                  }}
                  className={`p-1.5 rounded flex items-center gap-1 text-[10px] font-mono font-bold transition-all cursor-pointer ${
                    activeCanvasTool === "measure-distance"
                      ? "bg-amber-600 text-white"
                      : "text-gray-400 hover:text-white hover:bg-gray-800"
                  }`}
                  title="Linear Distance Measurement Tape (M)"
                >
                  <Ruler size={12} />
                  <span>Measure</span>
                </button>
              </div>

              {/* Takeoff Scope Filters */}
              <div className="flex items-center space-x-1 bg-[#0a121e]/90 backdrop-blur-md p-1 rounded-md border border-[#162840] shadow-lg pointer-events-auto text-[10px] font-mono">
                {(
                  [
                    { id: "ALL", label: "ALL" },
                    { id: "ELIGIBLE", label: "ELIGIBLE" },
                    { id: "SINGLE_FACE", label: "1-FACE" },
                    { id: "DOUBLE_FACE", label: "2-FACE" },
                    { id: "REVIEW_REQUIRED", label: "REVIEW" },
                    { id: "BLOCKED", label: "BLOCKED" },
                  ] as const
                ).map((flt) => (
                  <button
                    key={flt.id}
                    onClick={() => setTakeoffFilter(flt.id)}
                    className={`px-2 py-0.5 rounded font-bold transition-all cursor-pointer ${
                      takeoffFilter === flt.id
                        ? "bg-cyan-600 text-white shadow-sm"
                        : "text-gray-400 hover:text-gray-200 hover:bg-gray-800"
                    }`}
                  >
                    {flt.label}
                  </button>
                ))}
              </div>

              {/* Architectural Overlay Toggles & Auto-Fit */}
              <div className="flex items-center space-x-1.5 bg-[#0a121e]/90 backdrop-blur-md p-1 rounded-md border border-[#162840] shadow-lg pointer-events-auto text-xs">
                <button
                  onClick={() => setShowDimensions(!showDimensions)}
                  className={`px-2 py-0.5 rounded text-[10px] font-mono flex items-center gap-1 transition-all cursor-pointer ${
                    showDimensions
                      ? "bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold"
                      : "text-gray-400 hover:text-white"
                  }`}
                  title="Toggle Dimensions"
                >
                  <Ruler size={11} />
                  <span>Dims</span>
                </button>
                <button
                  onClick={() => setShowHatches(!showHatches)}
                  className={`px-2 py-0.5 rounded text-[10px] font-mono flex items-center gap-1 transition-all cursor-pointer ${
                    showHatches
                      ? "bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold"
                      : "text-gray-400 hover:text-white"
                  }`}
                  title="Toggle Hatches"
                >
                  <Layers size={11} />
                  <span>Hatch</span>
                </button>
                <button
                  onClick={() => setShowGridBubbles(!showGridBubbles)}
                  className={`px-2 py-0.5 rounded text-[10px] font-mono flex items-center gap-1 transition-all cursor-pointer ${
                    showGridBubbles
                      ? "bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold"
                      : "text-gray-400 hover:text-white"
                  }`}
                  title="Toggle Grid Bubbles"
                >
                  <Building2 size={11} />
                  <span>Grid</span>
                </button>
                <button
                  onClick={() => setShowRoomTags(!showRoomTags)}
                  className={`px-2 py-0.5 rounded text-[10px] font-mono flex items-center gap-1 transition-all cursor-pointer ${
                    showRoomTags
                      ? "bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold"
                      : "text-gray-400 hover:text-white"
                  }`}
                  title="Toggle Room Space Tags"
                >
                  <Tag size={11} />
                  <span>Rooms</span>
                </button>
                <div className="w-[1px] h-3 bg-gray-700 mx-0.5" />
                <button
                  onClick={autoFit2D}
                  className="p-1 rounded hover:bg-gray-800 text-emerald-400 hover:text-white transition-colors cursor-pointer"
                  title="Auto-Fit 2D Floor Plan"
                >
                  <Maximize2 size={12} />
                </button>
              </div>
            </div>

            {/* 2D Vector CAD Canvas */}
            <canvas
              ref={canvas2DRef}
              onMouseDown={handleMouseDown2D}
              onMouseMove={handleMouseMove2D}
              onMouseUp={handleMouseUp2D}
              onClick={handleClick2D}
              onWheel={handleWheel2D}
              className="h-full w-full block"
            />

            {/* 2D Bottom Telemetry HUD Bar */}
            <div className="absolute bottom-2.5 left-3 right-3 z-10 flex items-center justify-between text-[9px] font-mono text-gray-400 pointer-events-none">
              <div className="bg-[#0a121e]/90 backdrop-blur-sm px-2 py-0.5 rounded border border-[#162840] flex items-center gap-3">
                <span>SCALE: 1/8" = 1'-0" (1:96)</span>
                <span>ZOOM: {(zoom2D * 5).toFixed(0)}%</span>
                <span>CURSOR: ({liveCursorWorld.x.toFixed(2)}', {liveCursorWorld.y.toFixed(2)}')</span>
              </div>
              <div className="bg-[#0a121e]/90 backdrop-blur-sm px-2 py-0.5 rounded border border-[#162840] text-emerald-400 font-bold">
                CANONICAL 2D ↔ 3D SYNC ACTIVE
              </div>
            </div>
          </>
        )}
      </div>

      {/* ===================================================================== */}
      {/* MODE SWITCHER FLOATING PILL (BOTTOM CENTER)                           */}
      {/* ===================================================================== */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 flex items-center space-x-1 bg-[#0a121e]/95 backdrop-blur-md p-1 rounded-lg border border-[#162840] shadow-2xl">
        <button
          id="btn-view-mode-3d"
          onClick={() => setViewMode("3D")}
          className={`px-3 py-1 rounded text-xs font-bold flex items-center gap-1.5 transition-all cursor-pointer ${
            viewMode === "3D"
              ? "bg-[#0284c7] text-white shadow-md shadow-cyan-500/30 font-black"
              : "text-gray-400 hover:text-white hover:bg-gray-800/60"
          }`}
        >
          <Box size={13} />
          <span>3D Only</span>
        </button>
        <button
          id="btn-view-mode-2d"
          onClick={() => setViewMode("2D")}
          className={`px-3 py-1 rounded text-xs font-bold flex items-center gap-1.5 transition-all cursor-pointer ${
            viewMode === "2D"
              ? "bg-emerald-600 text-white shadow-md shadow-emerald-500/30 font-black"
              : "text-gray-400 hover:text-white hover:bg-gray-800/60"
          }`}
        >
          <Square size={13} />
          <span>2D Blueprint</span>
        </button>
        <button
          id="btn-view-mode-split"
          onClick={() => setViewMode("SPLIT")}
          className={`px-3 py-1 rounded text-xs font-bold flex items-center gap-1.5 transition-all cursor-pointer ${
            viewMode === "SPLIT"
              ? "bg-purple-600 text-white shadow-md shadow-purple-500/30 font-black"
              : "text-gray-400 hover:text-white hover:bg-gray-800/60"
          }`}
        >
          <Columns size={13} />
          <span>Synchronized Split</span>
        </button>
      </div>
    </div>
  );
}
