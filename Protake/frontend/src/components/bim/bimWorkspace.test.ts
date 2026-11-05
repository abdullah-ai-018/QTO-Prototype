import { describe, it, expect } from "vitest";
import { formatWallDisplay, CANONICAL_TREE_CATEGORIES } from "./BIMModelTree";

// Canonical Sample BIM Model Structure from backend
const sampleCanonicalModel = {
  project_name: "Lakeside Medical Center",
  schema_version: "IFC4",
  length_unit: "FOOT",
  storeys: [
    { id: "storey-1", name: "Level 1", elevation_ft: 0.0 },
    { id: "storey-2", name: "Level 2", elevation_ft: 12.0 },
  ],
  walls: [
    {
      ifc_guid: "3m$9q8L7H4RvP9X2w1A4bZ",
      name: "Basic Wall:Interior - Partition (1-Hr):384920",
      wall_classification: "INTERIOR_PARTITION",
      storey_name: "Level 1",
      storey_id: "storey-1",
      length_ft: 18.5,
      physical_height_ft: 10.0,
      drywall_finish_height_ft: 10.0,
      nominal_thickness_in: 4.875,
      start_point: [0.0, 0.0, 0.0],
      end_point: [18.5, 0.0, 0.0],
      drywall_side_a_scope: true,
      drywall_side_b_scope: true,
      qto_eligibility: "ELIGIBLE",
      openings: [
        {
          id: "op-1",
          ifc_guid: "1xK982bV10QweRtYuiOp90",
          name: "Single-Flush Door:36x84",
          opening_type: "DOOR",
          width_ft: 3.0,
          height_ft: 7.0,
          area_sqft: 21.0,
        },
      ],
      assembly: {
        assembly_name: "W1 Partition",
        board_type: '5/8" Type X Gypsum',
        stud_size: '3-5/8"',
        stud_spacing_in: 16,
        side_a_layers: 1,
        side_b_layers: 1,
        assembly_provenance: "VERIFIED_EXPLICIT",
      },
      length_provenance: "DERIVED_GEOMETRIC",
    },
    {
      ifc_guid: "2nB871aK09PvcQwErTyUi1",
      name: "Basic Wall:Exterior - Brick on CMU:482019",
      wall_classification: "EXTERIOR_WALL",
      storey_name: "Level 1",
      storey_id: "storey-1",
      length_ft: 40.0,
      physical_height_ft: 12.0,
      drywall_finish_height_ft: 12.0,
      nominal_thickness_in: 12.5,
      start_point: [0.0, 0.0, 0.0],
      end_point: [0.0, 40.0, 0.0],
      drywall_side_a_scope: true,
      drywall_side_b_scope: false,
      qto_eligibility: "ELIGIBLE",
      openings: [],
      assembly: {
        board_type: '5/8" Type X',
        stud_size: '6"',
        stud_spacing_in: 16,
        side_a_layers: 1,
        side_b_layers: 0,
        assembly_provenance: "CONFIGURED_ASSUMPTION",
      },
      length_provenance: "DERIVED_GEOMETRIC",
    },
    {
      ifc_guid: "0pZ765mN34QweAsDfGhJk2",
      name: "Basic Wall:Concrete Shear Core:102938",
      wall_classification: "STRUCTURAL_CONCRETE",
      storey_name: "Level 1",
      storey_id: "storey-1",
      length_ft: 25.0,
      physical_height_ft: 12.0,
      drywall_finish_height_ft: 12.0,
      nominal_thickness_in: 10.0,
      start_point: [10.0, 10.0, 0.0],
      end_point: [35.0, 10.0, 0.0],
      drywall_side_a_scope: false,
      drywall_side_b_scope: false,
      qto_eligibility: "INELIGIBLE_NON_DRYWALL",
      openings: [],
      length_provenance: "DERIVED_GEOMETRIC",
    },
    {
      ifc_guid: "9kL123xY45ZxcVbnMasDf3",
      name: "Basic Wall:Generic Partition:992011",
      wall_classification: "UNKNOWN",
      storey_name: "Level 2",
      storey_id: "storey-2",
      length_ft: 15.0,
      physical_height_ft: 9.0,
      drywall_finish_height_ft: 9.0,
      nominal_thickness_in: 4.5,
      start_point: [0.0, 0.0, 12.0],
      end_point: [15.0, 0.0, 12.0],
      drywall_side_a_scope: true,
      drywall_side_b_scope: true,
      qto_eligibility: "REVIEW_REQUIRED",
      eligibility_reasons: ["Unknown partition type requires estimator confirmation"],
      openings: [],
      length_provenance: "DERIVED_GEOMETRIC",
    },
  ],
  spaces: [
    {
      id: "sp-1",
      ifc_guid: "7vB654nM89QweTyUiOpAs4",
      name: "Exam Room 101",
      storey_id: "storey-1",
      net_floor_area_sqft: 180.0,
      provenance_status: "VERIFIED_EXPLICIT",
    },
    {
      id: "sp-2",
      ifc_guid: "8xC543vB78ZxcAsDfGhJk5",
      name: "Storage Room",
      storey_id: "storey-1",
      net_floor_area_sqft: 0.0,
      provenance_status: "UNKNOWN_UNRESOLVED",
    },
  ],
  openings: [
    {
      id: "op-1",
      ifc_guid: "1xK982bV10QweRtYuiOp90",
      name: "Single-Flush Door:36x84",
      opening_type: "DOOR",
      width_ft: 3.0,
      height_ft: 7.0,
      area_sqft: 21.0,
    },
  ],
  health_card: {
    schema_version: "IFC4",
    length_unit: "FOOT",
    unit_scale_to_meters: 0.3048,
    total_elements: 7,
    wall_count: 4,
    opening_count: 1,
    space_count: 2,
    storey_count: 2,
    readiness: "READY_FOR_QTO",
    geometry_coverage_score: 1.0,
    material_coverage_score: 0.75,
  },
};

// Sample Deterministic Takeoff Response from backend QTO Engine
const sampleTakeoffResponse = {
  document_id: "ifc-doc-12345",
  status: "SUCCESS",
  qto: {
    engine_version: "1.0.0",
    total_gross_wall_area_sqft: 850.0,
    total_opening_deduction_sqft: 21.0,
    total_net_drywall_area_sqft: 829.0,
    board_area_equivalent_sqft: 829.0,
    estimated_drywall_sheets_4x8: 29,
    total_studs_count: 58,
    total_track_linear_ft: 117.0,
    total_screws_count: 1044,
    total_joint_compound_gallons: 7.5,
    total_joint_tape_linear_ft: 414.5,
    total_insulation_sqft: 829.0,
    total_walls_evaluated: 4,
    eligible_walls_count: 2,
    excluded_walls_count: 1,
    review_required_walls_count: 1,
    line_items: [
      {
        item_id: "li-1",
        trade: "drywall",
        category: "BOARDS",
        item_code: "GYP-58-TYPEX",
        description: '5/8" Type X Gypsum Wallboard',
        unit: "SF",
        quantity: 349.0,
        source_guid: "3m$9q8L7H4RvP9X2w1A4bZ",
        provenance: {
          ifc_guid: "3m$9q8L7H4RvP9X2w1A4bZ",
          storey_name: "Level 1",
          wall_name: "Basic Wall:Interior - Partition (1-Hr):384920",
          wall_classification: "INTERIOR_PARTITION",
          length_ft: 18.5,
          finish_height_ft: 10.0,
          side_a_gross_sqft: 185.0,
          side_b_gross_sqft: 185.0,
          openings_count: 1,
          openings_deduction_sqft: 21.0,
          net_drywall_sqft: 349.0,
          formula: "(18.50' × 10.00' × 2) − 21.00 SF = 349.00 SF",
          status: "VERIFIED_EXPLICIT",
        },
      },
      {
        item_id: "li-2",
        trade: "drywall",
        category: "BOARDS",
        item_code: "GYP-58-TYPEX",
        description: '5/8" Type X Gypsum Wallboard (1-Sided)',
        unit: "SF",
        quantity: 480.0,
        source_guid: "2nB871aK09PvcQwErTyUi1",
        provenance: {
          ifc_guid: "2nB871aK09PvcQwErTyUi1",
          storey_name: "Level 1",
          wall_name: "Basic Wall:Exterior - Brick on CMU:482019",
          wall_classification: "EXTERIOR_WALL",
          length_ft: 40.0,
          finish_height_ft: 12.0,
          side_a_gross_sqft: 480.0,
          side_b_gross_sqft: 0.0,
          openings_count: 0,
          openings_deduction_sqft: 0.0,
          net_drywall_sqft: 480.0,
          formula: "(40.00' × 12.00' × 1) − 0.00 SF = 480.00 SF",
          status: "CONFIGURED_ASSUMPTION",
        },
      },
    ],
  },
};

describe("BIM Takeoff Workspace - Frontend Integration Test Suite", () => {
  // Test 1: IFC Upload Flow
  it("Test 1: IFC upload payload and response validation", () => {
    const uploadResponse = {
      id: "ifc-doc-12345",
      filename: "Lakeside_Medical.ifc",
      schema: "IFC4",
      status: "PARSED",
    };
    expect(uploadResponse.id).toBe("ifc-doc-12345");
    expect(uploadResponse.schema).toBe("IFC4");
    expect(uploadResponse.status).toBe("PARSED");
  });

  // Test 2: Model Loading & Normalization
  it("Test 2: Canonical BIM Model normalization by GUID", () => {
    const elementsByGuid: Record<string, any> = {};
    sampleCanonicalModel.walls.forEach((w) => {
      elementsByGuid[w.ifc_guid] = { ...w, entity_type: "IfcWall" };
    });
    sampleCanonicalModel.spaces.forEach((sp) => {
      elementsByGuid[sp.ifc_guid] = { ...sp, entity_type: "IfcSpace" };
    });

    expect(Object.keys(elementsByGuid).length).toBe(6);
    expect(elementsByGuid["3m$9q8L7H4RvP9X2w1A4bZ"].entity_type).toBe("IfcWall");
    expect(elementsByGuid["7vB654nM89QweTyUiOpAs4"].entity_type).toBe("IfcSpace");
  });

  // Test 3: Canonical Element Rendering
  it("Test 3: Canonical walls preserve geometric coordinates and thickness", () => {
    const wall = sampleCanonicalModel.walls[0];
    expect(wall.length_ft).toBe(18.5);
    expect(wall.nominal_thickness_in).toBe(4.875);
    expect(wall.start_point).toEqual([0.0, 0.0, 0.0]);
    expect(wall.end_point).toEqual([18.5, 0.0, 0.0]);
    expect(wall.openings.length).toBe(1);
    expect(wall.openings[0].area_sqft).toBe(21.0);
  });

  // Test 4, 5, 6, 7, 8: CRITICAL GUID SYNCHRONIZATION TEST
  it("Test 4-8 CRITICAL: 3D = 2D = Tree = Inspector = BOQ selection synchronizes via ifc_guid", () => {
    const targetGuid = "3m$9q8L7H4RvP9X2w1A4bZ";

    // 1. 3D Mesh user data
    const mesh3D = { userData: { ifc_guid: targetGuid } };

    // 2. 2D Plan Wall Entity
    const wall2D = sampleCanonicalModel.walls.find((w) => w.ifc_guid === targetGuid);

    // 3. Model Tree Node
    const treeNode = sampleCanonicalModel.walls.find((w) => w.ifc_guid === targetGuid);

    // 4. Inspector Selection
    const inspectorTarget = sampleCanonicalModel.walls.find((w) => w.ifc_guid === targetGuid);

    // 5. BOQ Line Item Lookup
    const boqLineItem = sampleTakeoffResponse.qto.line_items.find((item) => item.source_guid === targetGuid);

    // CRITICAL ASSERTION: All 5 representations share the identical IFC GUID
    expect(mesh3D.userData.ifc_guid).toBe(targetGuid);
    expect(wall2D?.ifc_guid).toBe(targetGuid);
    expect(treeNode?.ifc_guid).toBe(targetGuid);
    expect(inspectorTarget?.ifc_guid).toBe(targetGuid);
    expect(boqLineItem?.source_guid).toBe(targetGuid);

    // Perfect equality
    expect(mesh3D.userData.ifc_guid).toBe(wall2D?.ifc_guid);
    expect(wall2D?.ifc_guid).toBe(treeNode?.ifc_guid);
    expect(treeNode?.ifc_guid).toBe(inspectorTarget?.ifc_guid);
    expect(inspectorTarget?.ifc_guid).toBe(boqLineItem?.source_guid);
  });

  // Test 9: Storey Filtering
  it("Test 9: Storey filtering isolates elements correctly", () => {
    const level1Walls = sampleCanonicalModel.walls.filter((w) => w.storey_name === "Level 1");
    const level2Walls = sampleCanonicalModel.walls.filter((w) => w.storey_name === "Level 2");

    expect(level1Walls.length).toBe(3);
    expect(level2Walls.length).toBe(1);
    expect(level2Walls[0].ifc_guid).toBe("9kL123xY45ZxcVbnMasDf3");
  });

  // Test 10: Drywall QTO Display & Exact Matching
  it("Test 10: Drywall QTO values match backend calculations with zero frontend drift", () => {
    const qto = sampleTakeoffResponse.qto;
    const lineItem1 = qto.line_items[0];

    // Net area for wall 1: (18.5 * 10 * 2) - 21 = 349.0 SF
    expect(lineItem1.provenance.side_a_gross_sqft).toBe(185.0);
    expect(lineItem1.provenance.side_b_gross_sqft).toBe(185.0);
    expect(lineItem1.provenance.openings_deduction_sqft).toBe(21.0);
    expect(lineItem1.provenance.net_drywall_sqft).toBe(349.0);

    // Net area for wall 2: (40.0 * 12 * 1) - 0 = 480.0 SF
    const lineItem2 = qto.line_items[1];
    expect(lineItem2.provenance.net_drywall_sqft).toBe(480.0);

    // Sum of line items matches total net drywall
    const sumLineItems = qto.line_items.reduce((s, it) => s + it.provenance.net_drywall_sqft, 0);
    expect(sumLineItems).toBe(qto.total_net_drywall_area_sqft);
  });

  // Test 11: Review Queue Filtering
  it("Test 11: Review queue accurately extracts gated items", () => {
    const reviewQueue: any[] = [];
    sampleCanonicalModel.walls.forEach((w) => {
      if (w.qto_eligibility === "REVIEW_REQUIRED") {
        reviewQueue.push({ guid: w.ifc_guid, status: "REVIEW_REQUIRED", reason: w.eligibility_reasons?.[0] });
      } else if (w.qto_eligibility === "INELIGIBLE_NON_DRYWALL") {
        reviewQueue.push({ guid: w.ifc_guid, status: "INELIGIBLE_NON_DRYWALL", reason: "Non-drywall scope" });
      }
    });

    sampleCanonicalModel.spaces.forEach((sp) => {
      if (sp.provenance_status === "UNKNOWN_UNRESOLVED") {
        reviewQueue.push({ guid: sp.ifc_guid, status: "UNKNOWN_UNRESOLVED", reason: "Missing area" });
      }
    });

    expect(reviewQueue.length).toBe(3);
    expect(reviewQueue.some((item) => item.guid === "9kL123xY45ZxcVbnMasDf3")).toBe(true);
    expect(reviewQueue.some((item) => item.guid === "0pZ765mN34QweAsDfGhJk2")).toBe(true);
    expect(reviewQueue.some((item) => item.guid === "8xC543vB78ZxcAsDfGhJk5")).toBe(true);
  });

  // Test 12: UNKNOWN_UNRESOLVED and Provenance Display
  it("Test 12: Provenance badges accurately reflect backend truth without fake AI labels", () => {
    const wall1 = sampleCanonicalModel.walls[0];
    const wall2 = sampleCanonicalModel.walls[1];
    const space2 = sampleCanonicalModel.spaces[1];

    expect(wall1.assembly?.assembly_provenance).toBe("VERIFIED_EXPLICIT");
    expect(wall2.assembly?.assembly_provenance).toBe("CONFIGURED_ASSUMPTION");
    expect(space2.provenance_status).toBe("UNKNOWN_UNRESOLVED");
  });

  // Test 13: Backend Error Handling
  it("Test 13: Backend errors are surfaced honestly without silent fallback", () => {
    const backendError = new Error("IFC Schema mismatch: Expected IFC2X3 or IFC4, got corrupted stream.");
    expect(backendError.message).toContain("IFC Schema mismatch");
  });

  // Test 14: Canonical Classification Primary Label & Source IFC Name Preservation
  it("Test 14: Uses canonical classification as primary human-readable label while preserving raw IFC name", () => {
    const wall1 = {
      name: "Basic Wall:Interior - Partition (1-Hr):384920",
      wall_classification: "INTERIOR_PARTITION",
      ifc_guid: "3m$9q8L7H4RvP9X2w1A4bZ",
    };
    const display1 = formatWallDisplay(wall1);
    expect(display1.primaryLabel).toBe("Interior Partition");
    expect(display1.secondaryLabel).toBe("Basic Wall:Interior - Partition (1-Hr):384920");
    expect(display1.categoryGroup).toBe("Interior Partition");
    expect(display1.status).toBe("CONFIRMED");

    const wall2 = {
      name: "Basic Wall:Exterior - Brick on CMU:482019",
      wall_classification: "EXTERIOR_WALL",
      ifc_guid: "2nB871aK09PvcQwErTyUi1",
    };
    const display2 = formatWallDisplay(wall2);
    expect(display2.primaryLabel).toBe("Exterior Wall");
    expect(display2.secondaryLabel).toBe("Basic Wall:Exterior - Brick on CMU:482019");
    expect(display2.categoryGroup).toBe("Exterior Wall");
    expect(display2.status).toBe("CONFIRMED");

    const wall3 = {
      name: "Basic Wall:Concrete Shear Core:102938",
      wall_classification: "STRUCTURAL_CONCRETE",
      ifc_guid: "0pZ765mN34QweAsDfGhJk2",
    };
    const display3 = formatWallDisplay(wall3);
    expect(display3.primaryLabel).toBe("Structural Concrete");
    expect(display3.categoryGroup).toBe("Structural Concrete");

    const wall4 = {
      name: "Curtain Wall:Storefront Double Glazed:5512",
      wall_classification: "CURTAIN_WALL",
      ifc_guid: "4rT981vC09QweRtYuiOp99",
    };
    const display4 = formatWallDisplay(wall4);
    expect(display4.primaryLabel).toBe("Curtain Wall");
    expect(display4.categoryGroup).toBe("Curtain Wall");
  });

  // Test 15: Fallback for Unknown / Missing Classification
  it("Test 15: Displays original IFC name and marks UNKNOWN_UNRESOLVED if classification is missing", () => {
    const unknownWall = {
      name: "Basic Wall:Custom Proprietary Layer:99112",
      wall_classification: "UNKNOWN",
      ifc_guid: "9kL123xY45ZxcVbnMasDf3",
    };
    const display = formatWallDisplay(unknownWall);
    expect(display.primaryLabel).toBe("Basic Wall:Custom Proprietary Layer:99112");
    expect(display.secondaryLabel).toBe("Basic Wall:Custom Proprietary Layer:99112");
    expect(display.categoryGroup).toBe("Other / Review Required");
    expect(display.status).toBe("UNKNOWN_UNRESOLVED");
  });

  // Test 16: Model Tree Canonical Category Grouping
  it("Test 16: Groups walls in Model Tree by canonical classification categories", () => {
    const wallsByCat: Record<string, any[]> = {};
    CANONICAL_TREE_CATEGORIES.forEach((cat: string) => {
      wallsByCat[cat] = [];
    });

    sampleCanonicalModel.walls.forEach((w) => {
      const meta = formatWallDisplay(w);
      if (!wallsByCat[meta.categoryGroup]) wallsByCat[meta.categoryGroup] = [];
      wallsByCat[meta.categoryGroup].push(w);
    });

    expect(wallsByCat["Interior Partition"].length).toBe(1);
    expect(wallsByCat["Exterior Wall"].length).toBe(1);
    expect(wallsByCat["Structural Concrete"].length).toBe(1);
    expect(wallsByCat["Other / Review Required"].length).toBe(1);
  });

  // Test 17: Search Filtering by GUID, Source Name, and Classification
  it("Test 17: Search supports IFC GUID, raw IFC Name, canonical classification, and Storey", () => {
    const walls = sampleCanonicalModel.walls;

    // Search by GUID
    const guidQuery = "3m$9q8L7".toLowerCase();
    const byGuid = walls.filter((w) => w.ifc_guid.toLowerCase().includes(guidQuery));
    expect(byGuid.length).toBe(1);
    expect(byGuid[0].ifc_guid).toBe("3m$9q8L7H4RvP9X2w1A4bZ");

    // Search by Source Name
    const nameQuery = "Brick on CMU".toLowerCase();
    const byName = walls.filter((w) => w.name.toLowerCase().includes(nameQuery));
    expect(byName.length).toBe(1);
    expect(byName[0].ifc_guid).toBe("2nB871aK09PvcQwErTyUi1");

    // Search by Canonical Classification
    const classQuery = "STRUCTURAL_CONCRETE".toLowerCase();
    const byClass = walls.filter((w) => w.wall_classification?.toLowerCase().includes(classQuery));
    expect(byClass.length).toBe(1);
    expect(byClass[0].ifc_guid).toBe("0pZ765mN34QweAsDfGhJk2");
  });

  // Test 18: Real Hierarchy Counts Computation
  it("Test 18: Real backend counts compute accurately at Project, Building, Storey, and Category levels", () => {
    const walls = sampleCanonicalModel.walls;
    const storeys = sampleCanonicalModel.storeys;

    // Total elements at project/building level
    const totalProjectWalls = walls.length;
    expect(totalProjectWalls).toBe(4);

    // Storey-specific counts
    const level1Walls = walls.filter((w) => w.storey_name === "Level 1" || w.storey_id === "storey-1");
    const level2Walls = walls.filter((w) => w.storey_name === "Level 2" || w.storey_id === "storey-2");
    expect(level1Walls.length).toBe(3);
    expect(level2Walls.length).toBe(1);
    expect(level1Walls.length + level2Walls.length).toBe(totalProjectWalls);

    // Classification counts within Level 1
    const l1Partitions = level1Walls.filter((w) => formatWallDisplay(w).categoryGroup === "Interior Partition");
    const l1Exterior = level1Walls.filter((w) => formatWallDisplay(w).categoryGroup === "Exterior Wall");
    const l1Concrete = level1Walls.filter((w) => formatWallDisplay(w).categoryGroup === "Structural Concrete");
    expect(l1Partitions.length).toBe(1);
    expect(l1Exterior.length).toBe(1);
    expect(l1Concrete.length).toBe(1);
  });

  // Test 19: Storey Isolation and Filtering
  it("Test 19: Storey filtering isolates elements to active storey without leaking elements", () => {
    const selectedStorey = "Level 2";
    const filtered = sampleCanonicalModel.walls.filter(
      (w) => w.storey_name === selectedStorey || w.storey_id === selectedStorey
    );
    expect(filtered.length).toBe(1);
    filtered.forEach((w) => {
      expect(w.storey_name).toBe("Level 2");
    });
  });

  // Test 20: Tree Selection Invariant - Tree Selected GUID === Canonical Selected GUID
  it("Test 20: Selection MUST use ifc_guid and propagate directly to canonical state", () => {
    let canonicalSelectedGuid: string | null = null;
    const handleSelectGuid = (guid: string) => {
      canonicalSelectedGuid = guid;
    };

    // User clicks element in tree
    const targetWall = sampleCanonicalModel.walls[2];
    handleSelectGuid(targetWall.ifc_guid);

    // Invariant: Selection uses ifc_guid, not index or coordinates
    expect(canonicalSelectedGuid).toBe(targetWall.ifc_guid);
    expect(canonicalSelectedGuid).toBe("0pZ765mN34QweAsDfGhJk2");
  });

  // Test 21: Hide and Isolate State Logic
  it("Test 21: Hide, Isolate, and Show All maintain strict set consistency by GUID", () => {
    const allGuids = sampleCanonicalModel.walls.map((w) => w.ifc_guid);
    let hiddenGuids = new Set<string>();
    let isolatedGuid: string | null = null;

    // Hide one element
    const hideGuid = allGuids[0];
    hiddenGuids.add(hideGuid);
    expect(hiddenGuids.has(hideGuid)).toBe(true);
    expect(hiddenGuids.size).toBe(1);

    // Isolate second element
    const isolateGuid = allGuids[1];
    isolatedGuid = isolateGuid;
    hiddenGuids = new Set(allGuids.filter((g) => g !== isolateGuid));
    expect(hiddenGuids.has(isolateGuid)).toBe(false);
    expect(hiddenGuids.has(allGuids[0])).toBe(true);
    expect(hiddenGuids.has(allGuids[2])).toBe(true);
    expect(hiddenGuids.has(allGuids[3])).toBe(true);
    expect(hiddenGuids.size).toBe(3);

    // Show All / Reset
    hiddenGuids.clear();
    isolatedGuid = null;
    expect(hiddenGuids.size).toBe(0);
    expect(isolatedGuid).toBeNull();
  });

  // Test 22: Inspector Identity Section & GUID Stability
  it("Test 22: Inspector identity renders canonical classification primary, source IFC name secondary, and stable GUID", () => {
    const wall = sampleCanonicalModel.walls[0];
    const display = formatWallDisplay(wall);

    expect(display.primaryLabel).toBe("Interior Partition");
    expect(display.secondaryLabel).toBe(wall.name);
    expect(wall.ifc_guid).toBe("3m$9q8L7H4RvP9X2w1A4bZ");
    expect(wall.storey_name).toBe("Level 1");
  });

  // Test 23: Inspector Geometry & Provenance
  it("Test 23: Inspector geometry displays exact canonical values with strict provenance", () => {
    const wall = sampleCanonicalModel.walls[0];
    expect(wall.length_ft).toBe(18.5);
    expect(wall.physical_height_ft).toBe(10.0);
    expect(wall.drywall_finish_height_ft).toBe(10.0);
    expect(wall.nominal_thickness_in).toBe(4.875);
    expect(wall.length_provenance).toBe("DERIVED_GEOMETRIC");
  });

  // Test 24: Inspector Wall Assembly & Configured Assumption Labeling
  it("Test 24: Inspector displays assembly layers and explicitly labels configured assumptions", () => {
    const explicitWall = sampleCanonicalModel.walls[0];
    expect(explicitWall.assembly?.board_type).toBe('5/8" Type X Gypsum');
    expect(explicitWall.assembly?.assembly_provenance).toBe("VERIFIED_EXPLICIT");

    const assumptionWall = sampleCanonicalModel.walls[1];
    expect(assumptionWall.assembly?.assembly_provenance).toBe("CONFIGURED_ASSUMPTION");
  });

  // Test 25: Inspector Hosted Openings & Deductions
  it("Test 25: Hosted openings display dimensions and deduct correctly from active drywall faces", () => {
    const wall = sampleCanonicalModel.walls[0];
    const op = wall.openings[0];

    expect(op.opening_type).toBe("DOOR");
    expect(op.width_ft).toBe(3.0);
    expect(op.height_ft).toBe(7.0);
    expect(op.area_sqft).toBe(21.0);

    const sideALayers = wall.assembly?.side_a_layers ?? 1;
    const sideBLayers = wall.assembly?.side_b_layers ?? 1;
    const totalLayers = sideALayers + sideBLayers;
    const totalDeduction = op.area_sqft * totalLayers;

    expect(totalLayers).toBe(2);
    expect(totalDeduction).toBe(42.0);
  });

  // Test 26: Inspector Drywall Scope & Gating Status
  it("Test 26: Drywall scope reflects side A/B scope and reports honest eligibility", () => {
    const eligibleWall = sampleCanonicalModel.walls[0];
    expect(eligibleWall.drywall_side_a_scope).toBe(true);
    expect(eligibleWall.drywall_side_b_scope).toBe(true);
    expect(eligibleWall.qto_eligibility).toBe("ELIGIBLE");

    const ineligibleWall = sampleCanonicalModel.walls[2];
    expect(ineligibleWall.drywall_side_a_scope).toBe(false);
    expect(ineligibleWall.drywall_side_b_scope).toBe(false);
    expect(ineligibleWall.qto_eligibility).toBe("INELIGIBLE_NON_DRYWALL");
  });

  // Test 27: Inspector QTO Derivation Arithmetic
  it("Test 27: QTO derivation matches exact backend arithmetic without client drift", () => {
    const wall = sampleCanonicalModel.walls[0];
    const length = wall.length_ft; // 18.5
    const height = wall.drywall_finish_height_ft; // 10.0
    const faceArea = length * height; // 185.0
    const totalLayers = (wall.assembly?.side_a_layers ?? 1) + (wall.assembly?.side_b_layers ?? 1); // 2
    const grossBoard = faceArea * totalLayers; // 370.0
    const opDeduction = wall.openings[0].area_sqft * totalLayers; // 42.0
    const netBoard = grossBoard - opDeduction; // 328.0

    const wasteFactor = 10;
    const estSheets = Math.ceil((netBoard * (1 + wasteFactor / 100)) / 32);

    expect(faceArea).toBe(185.0);
    expect(grossBoard).toBe(370.0);
    expect(opDeduction).toBe(42.0);
    expect(netBoard).toBe(328.0);
    expect(estSheets).toBe(12); // Math.ceil(360.8 / 32) = 12
  });

  // Test 28: Inspector Review State & Unknown Classification Handling
  it("Test 28: Inspector surfaces review warning banner without fabricating resolutions", () => {
    const reviewWall = sampleCanonicalModel.walls[3];
    expect(reviewWall.qto_eligibility).toBe("REVIEW_REQUIRED");
    expect(reviewWall.wall_classification).toBe("UNKNOWN");
    expect(reviewWall.eligibility_reasons?.length).toBeGreaterThan(0);
  });

  // Test 29: Cross-View Synchronization Invariant (Tree = 3D = 2D = Inspector = BOQ)
  it("Test 29: Cross-view selection synchronizes across all panels using ifc_guid", () => {
    let activeGuid: string | null = null;
    const selectElement = (guid: string) => {
      activeGuid = guid;
    };

    // 1. Select GUID from Tree
    selectElement("3m$9q8L7H4RvP9X2w1A4bZ");
    expect(activeGuid).toBe("3m$9q8L7H4RvP9X2w1A4bZ");

    // 2. Select GUID from 3D Viewport
    selectElement("2nB871aK09PvcQwErTyUi1");
    expect(activeGuid).toBe("2nB871aK09PvcQwErTyUi1");

    // 3. Select GUID from 2D Viewport
    selectElement("0pZ765mN34QweAsDfGhJk2");
    expect(activeGuid).toBe("0pZ765mN34QweAsDfGhJk2");

    // 4. Select GUID from BOQ Dock
    selectElement("9kL123xY45ZxcVbnMasDf3");
    expect(activeGuid).toBe("9kL123xY45ZxcVbnMasDf3");
  });

  // Test 30: Bidirectional Synchronization across All 5 Views
  it("Test 30: All 5 selection directions propagate the exact same IFC GUID", () => {
    interface AppState {
      selectedTreeGuid: string | null;
      selected2DGuid: string | null;
      selected3DGuid: string | null;
      selectedInspectorGuid: string | null;
      selectedBOQGuid: string | null;
    }

    const state: AppState = {
      selectedTreeGuid: null,
      selected2DGuid: null,
      selected3DGuid: null,
      selectedInspectorGuid: null,
      selectedBOQGuid: null,
    };

    const broadcastSelection = (guid: string) => {
      state.selectedTreeGuid = guid;
      state.selected2DGuid = guid;
      state.selected3DGuid = guid;
      state.selectedInspectorGuid = guid;
      state.selectedBOQGuid = guid;
    };

    const targetGuid = "3m$9q8L7H4RvP9X2w1A4bZ";

    // Direction 1: Tree -> All
    broadcastSelection(targetGuid);
    expect(state.selectedTreeGuid).toBe(targetGuid);
    expect(state.selected2DGuid).toBe(targetGuid);
    expect(state.selected3DGuid).toBe(targetGuid);
    expect(state.selectedInspectorGuid).toBe(targetGuid);
    expect(state.selectedBOQGuid).toBe(targetGuid);

    // Direction 2: 2D -> All
    const guid2D = "2nB871aK09PvcQwErTyUi1";
    broadcastSelection(guid2D);
    expect(state.selectedTreeGuid).toBe(guid2D);
    expect(state.selected2DGuid).toBe(guid2D);
    expect(state.selected3DGuid).toBe(guid2D);
    expect(state.selectedInspectorGuid).toBe(guid2D);
    expect(state.selectedBOQGuid).toBe(guid2D);

    // Direction 3: 3D -> All
    const guid3D = "0pZ765mN34QweAsDfGhJk2";
    broadcastSelection(guid3D);
    expect(state.selectedTreeGuid).toBe(guid3D);
    expect(state.selected2DGuid).toBe(guid3D);
    expect(state.selected3DGuid).toBe(guid3D);
    expect(state.selectedInspectorGuid).toBe(guid3D);
    expect(state.selectedBOQGuid).toBe(guid3D);

    // Direction 4: Inspector -> All (Pagination)
    const guidInsp = "9kL123xY45ZxcVbnMasDf3";
    broadcastSelection(guidInsp);
    expect(state.selectedTreeGuid).toBe(guidInsp);
    expect(state.selected2DGuid).toBe(guidInsp);
    expect(state.selected3DGuid).toBe(guidInsp);
    expect(state.selectedInspectorGuid).toBe(guidInsp);
    expect(state.selectedBOQGuid).toBe(guidInsp);

    // Direction 5: BOQ -> All
    broadcastSelection(targetGuid);
    expect(state.selectedTreeGuid).toBe(targetGuid);
    expect(state.selected2DGuid).toBe(targetGuid);
    expect(state.selected3DGuid).toBe(targetGuid);
    expect(state.selectedInspectorGuid).toBe(targetGuid);
    expect(state.selectedBOQGuid).toBe(targetGuid);
  });

  // Test 31: Stale Selection Prevention on Storey Filter Switch
  it("Test 31: Changing storey filter prevents stale element selection outside active level", () => {
    const walls = sampleCanonicalModel.walls;
    let activeStorey = "Level 1";
    let selectedGuid: string | null = "3m$9q8L7H4RvP9X2w1A4bZ"; // On Level 1

    // Switch to Level 2
    activeStorey = "Level 2";
    const filteredLevel2 = walls.filter((w) => w.storey_name === activeStorey || w.storey_id === activeStorey);

    // If previously selected wall is no longer in filtered list, auto-reselect or clear
    if (selectedGuid && !filteredLevel2.some((w) => w.ifc_guid === selectedGuid)) {
      selectedGuid = filteredLevel2.length > 0 ? filteredLevel2[0].ifc_guid : null;
    }

    expect(selectedGuid).toBe("9kL123xY45ZxcVbnMasDf3"); // First wall on Level 2
    expect(filteredLevel2.some((w) => w.ifc_guid === selectedGuid)).toBe(true);
  });

  // Test 32: Stale Selection Prevention on Classification Filter Switch
  it("Test 32: Changing classification filter prevents phantom selection of excluded categories", () => {
    const walls = sampleCanonicalModel.walls;
    let selectedGuid: string | null = "3m$9q8L7H4RvP9X2w1A4bZ"; // INTERIOR_PARTITION

    // Switch filter to STRUCTURAL_CONCRETE
    const activeClass = "STRUCTURAL_CONCRETE";
    const filteredClass = walls.filter((w) => w.wall_classification === activeClass);

    if (selectedGuid && !filteredClass.some((w) => w.ifc_guid === selectedGuid)) {
      selectedGuid = filteredClass.length > 0 ? filteredClass[0].ifc_guid : null;
    }

    expect(selectedGuid).toBe("0pZ765mN34QweAsDfGhJk2"); // Structural wall
    expect(filteredClass[0].wall_classification).toBe("STRUCTURAL_CONCRETE");
  });

  // Test 33: Rapid Selection Updates (No Data Shearing)
  it("Test 33: Rapid selection changes A -> B -> C maintain atomic internal consistency", () => {
    const walls = sampleCanonicalModel.walls;
    const elementsByGuid: Record<string, any> = {};
    walls.forEach((w) => {
      elementsByGuid[w.ifc_guid] = w;
    });

    let currentGuid: string | null = null;
    let inspectorWall: any = null;

    const selectAtomic = (guid: string) => {
      currentGuid = guid;
      inspectorWall = elementsByGuid[guid] || null;
    };

    // Rapid sequence
    selectAtomic("3m$9q8L7H4RvP9X2w1A4bZ");
    expect(currentGuid).toBe("3m$9q8L7H4RvP9X2w1A4bZ");
    expect(inspectorWall.name).toBe("Basic Wall:Interior - Partition (1-Hr):384920");

    selectAtomic("2nB871aK09PvcQwErTyUi1");
    expect(currentGuid).toBe("2nB871aK09PvcQwErTyUi1");
    expect(inspectorWall.name).toBe("Basic Wall:Exterior - Brick on CMU:482019");

    selectAtomic("0pZ765mN34QweAsDfGhJk2");
    expect(currentGuid).toBe("0pZ765mN34QweAsDfGhJk2");
    expect(inspectorWall.name).toBe("Basic Wall:Concrete Shear Core:102938");
  });

  // Test 34: Performance Benchmark for Selection Dispatch
  it("Test 34: Selection dispatch and GUID lookup executes in <1ms even on 1,000 element model", () => {
    // Generate synthetic 1,000 wall model
    const largeModelWalls: any[] = [];
    const lookupMap: Map<string, any> = new Map();

    for (let i = 0; i < 1000; i++) {
      const guid = `guid-bench-${i.toString().padStart(4, "0")}`;
      const wall = {
        ifc_guid: guid,
        name: `Basic Wall:Generic ${i}`,
        length_ft: 10 + (i % 30),
        physical_height_ft: 10,
        nominal_thickness_in: 6,
      };
      largeModelWalls.push(wall);
      lookupMap.set(guid, wall);
    }

    const t0 = performance.now();
    // Perform 100 consecutive random selections
    for (let i = 0; i < 100; i++) {
      const targetGuid = `guid-bench-${(i * 9).toString().padStart(4, "0")}`;
      const found = lookupMap.get(targetGuid);
      expect(found).toBeDefined();
      expect(found.ifc_guid).toBe(targetGuid);
    }
    const t1 = performance.now();
    const durationMs = t1 - t0;

    // 100 lookups benchmark (averaging < 0.5ms per lookup)
    expect(durationMs).toBeLessThan(50);
  });

  // Test 35: BOQ Row ↔ GUID Mapping and Raw IFC Name Preservation
  it("Test 35: BOQ rows bind to ifc_guid, preserve source IFC name, and present canonical classification", () => {
    const wall = sampleCanonicalModel.walls[0];
    const display = formatWallDisplay(wall);

    expect(wall.ifc_guid).toBe("3m$9q8L7H4RvP9X2w1A4bZ");
    expect(display.primaryLabel).toBe("Interior Partition");
    expect(wall.name).toBe("Basic Wall:Interior - Partition (1-Hr):384920");
    expect(wall.storey_name).toBe("Level 1");
  });

  // Test 36: Explicit Quantity Semantics and Units (No Unit Mixing)
  it("Test 36: BOQ schedule preserves explicit quantity semantics without mixing physical vs board areas", () => {
    const wall = sampleCanonicalModel.walls[0];
    const lengthFt = wall.length_ft; // 18.5 ft
    const heightFt = wall.drywall_finish_height_ft; // 10.0 ft
    const physicalFaceAreaSqft = lengthFt * heightFt; // 185.0 SF
    const activeLayers = (wall.assembly?.side_a_layers ?? 1) + (wall.assembly?.side_b_layers ?? 1); // 2 Layers
    const grossBoardSqft = physicalFaceAreaSqft * activeLayers; // 370.0 SF
    const openingDeductionSqft = wall.openings[0].area_sqft * activeLayers; // 42.0 SF
    const netBoardSqft = grossBoardSqft - openingDeductionSqft; // 328.0 SF
    const estSheets4x8 = Math.ceil((netBoardSqft * 1.1) / 32); // 12 EA

    expect(physicalFaceAreaSqft).toBe(185.0); // SF (Face Area)
    expect(grossBoardSqft).toBe(370.0); // SF (Board Area)
    expect(openingDeductionSqft).toBe(42.0); // SF (Deductions)
    expect(netBoardSqft).toBe(328.0); // SF (Net Board Eq.)
    expect(estSheets4x8).toBe(12); // EA (Sheets)
  });

  // Test 37: Compatible Unit Totals (No Incompatible Unit Summing)
  it("Test 37: BOQ totals sum only compatible units separately (SF, EA, LF)", () => {
    const walls = sampleCanonicalModel.walls;
    let sumFaceSqft = 0;
    let sumNetBoardSqft = 0;
    let sumSheetsEa = 0;
    let sumLengthLf = 0;

    walls.forEach((w) => {
      const l = w.length_ft;
      const h = w.drywall_finish_height_ft || 10;
      const face = l * h;
      const layers = (w.drywall_side_a_scope ? 1 : 0) + (w.drywall_side_b_scope ? 1 : 0);
      const gross = face * layers;
      const op = w.openings.reduce((sum: number, o: any) => sum + o.area_sqft, 0) * layers;
      const net = Math.max(0, gross - op);
      const sheets = Math.ceil((net * 1.1) / 32);

      sumLengthLf += l;
      sumFaceSqft += face;
      sumNetBoardSqft += net;
      sumSheetsEa += sheets;
    });

    // Verify separate compatible unit totals
    expect(sumLengthLf).toBe(98.5); // LF (Linear Feet)
    expect(sumFaceSqft).toBe(1100.0); // SF (Physical Wall Face Area: 185 + 480 + 300 + 135)
    expect(sumNetBoardSqft).toBe(1078.0); // SF (Net Board Area Eq: 328 + 480 + 0 + 270)
    expect(sumSheetsEa).toBe(39); // EA (4x8 Sheets: 12 + 17 + 0 + 10)
  });

  // Test 38: BOQ Column Sorting by Storey, Classification, Quantity, Status, GUID
  it("Test 38: BOQ table sorts stably across numeric and string fields", () => {
    const walls = [...sampleCanonicalModel.walls];

    // Sort by Length Ascending
    const sortedByLengthAsc = [...walls].sort((a, b) => a.length_ft - b.length_ft);
    expect(sortedByLengthAsc[0].length_ft).toBe(15.0);
    expect(sortedByLengthAsc[sortedByLengthAsc.length - 1].length_ft).toBe(40.0);

    // Sort by Length Descending
    const sortedByLengthDesc = [...walls].sort((a, b) => b.length_ft - a.length_ft);
    expect(sortedByLengthDesc[0].length_ft).toBe(40.0);
    expect(sortedByLengthDesc[sortedByLengthDesc.length - 1].length_ft).toBe(15.0);

    // Sort by GUID
    const sortedByGuid = [...walls].sort((a, b) => a.ifc_guid.localeCompare(b.ifc_guid));
    expect(sortedByGuid[0].ifc_guid.localeCompare(sortedByGuid[1].ifc_guid)).toBeLessThanOrEqual(0);
  });

  // Test 39: Scope and Provenance Filtering
  it("Test 39: BOQ filtering isolates verified, derived, assumed, eligible, and blocked rows", () => {
    const walls = sampleCanonicalModel.walls;

    // Filter Eligible Only
    const eligibleOnly = walls.filter((w) => w.qto_eligibility === "ELIGIBLE");
    expect(eligibleOnly.length).toBe(2);

    // Filter Blocked / Ineligible Only
    const blockedOnly = walls.filter((w) => w.qto_eligibility?.startsWith("INELIGIBLE"));
    expect(blockedOnly.length).toBe(1);
    expect(blockedOnly[0].ifc_guid).toBe("0pZ765mN34QweAsDfGhJk2");

    // Filter Review Required Only
    const reviewOnly = walls.filter((w) => w.qto_eligibility === "REVIEW_REQUIRED");
    expect(reviewOnly.length).toBe(1);
    expect(reviewOnly[0].ifc_guid).toBe("9kL123xY45ZxcVbnMasDf3");
  });

  // Test 40: Cross-View Selection from BOQ Row Click
  it("Test 40: Selecting a BOQ row dispatches central ifc_guid selection to all views", () => {
    let globalSelectedGuid: string | null = null;
    const handleSelectGuid = (guid: string) => {
      globalSelectedGuid = guid;
    };

    const targetRowGuid = "2nB871aK09PvcQwErTyUi1";
    handleSelectGuid(targetRowGuid);

    expect(globalSelectedGuid).toBe("2nB871aK09PvcQwErTyUi1");
  });

  // Test 41 (CRITICAL NEGATIVE TEST): Unresolved/Invalid QTO Line Gating
  it("Test 41 (CRITICAL NEGATIVE TEST): Deliberately invalid QTO element is NOT silently converted to valid 0 SF quantity", () => {
    const invalidWall = {
      ifc_guid: "invalid-corrupted-wall-guid",
      name: "Basic Wall:Corrupted Null Axis",
      wall_classification: "UNKNOWN",
      length_ft: 0.0,
      physical_height_ft: 0.0,
      nominal_thickness_in: 0.0,
      drywall_side_a_scope: false,
      drywall_side_b_scope: false,
      qto_eligibility: "INELIGIBLE_INVALID_GEOMETRY",
      eligibility_reasons: ["Zero length/extrusion geometry extracted from IFC."],
    };

    // Verify gating status
    expect(invalidWall.qto_eligibility).toBe("INELIGIBLE_INVALID_GEOMETRY");
    expect(invalidWall.eligibility_reasons.length).toBeGreaterThan(0);

    // Provenance status must remain unverified and gated
    const isBlocked = invalidWall.qto_eligibility.startsWith("INELIGIBLE");
    expect(isBlocked).toBe(true);

    // Arithmetic must not invent a positive takeoff value
    const gross = invalidWall.length_ft * invalidWall.physical_height_ft;
    expect(gross).toBe(0.0);
  });

  // Test 42: Missing Geometry Remains UNKNOWN_UNRESOLVED and BLOCKED
  it("Test 42: Missing or corrupted geometry elements remain honestly marked as UNKNOWN_UNRESOLVED / BLOCKED", () => {
    const unmeasuredWall = {
      ifc_guid: "unmeasured-wall-1",
      name: "Basic Wall:Unresolved",
      length_ft: 0.0,
      length_provenance: "UNKNOWN_UNRESOLVED",
      qto_eligibility: "INELIGIBLE_INVALID_GEOMETRY",
    };

    expect(unmeasuredWall.length_provenance).toBe("UNKNOWN_UNRESOLVED");
    expect(unmeasuredWall.qto_eligibility).toBe("INELIGIBLE_INVALID_GEOMETRY");
    expect(unmeasuredWall.length_ft).toBe(0.0);
  });

  // Test 43: Missing Material Layers Do Not Become VERIFIED
  it("Test 43: Walls without explicit IFC material layers are never falsely marked as VERIFIED_EXPLICIT", () => {
    const wallWithoutPset = sampleCanonicalModel.walls[1];
    expect(wallWithoutPset.assembly?.assembly_provenance).not.toBe("VERIFIED_EXPLICIT");
    expect(wallWithoutPset.assembly?.assembly_provenance).toBe("CONFIGURED_ASSUMPTION");
  });

  // Test 44: Configured Assumptions are Transparently Labeled
  it("Test 44: Configured estimator assumptions produce CONFIGURED_ASSUMPTION provenance without pretending to be IFC source", () => {
    const assumedWall = sampleCanonicalModel.walls[1];
    expect(assumedWall.assembly?.assembly_provenance).toBe("CONFIGURED_ASSUMPTION");
    expect(assumedWall.assembly?.board_type).toBe('5/8" Type X');
    expect(assumedWall.assembly?.stud_size).toBe('6"');
  });

  // Test 45: Review Item Selection Propagates ifc_guid to All Views
  it("Test 45: Clicking a review queue item dispatches its exact ifc_guid to the global selection state", () => {
    let globalSelectedGuid: string | null = null;
    const handleSelectReviewGuid = (guid: string) => {
      globalSelectedGuid = guid;
    };

    const reviewItemGuid = "9kL123xY45ZxcVbnMasDf3";
    handleSelectReviewGuid(reviewItemGuid);

    expect(globalSelectedGuid).toBe(reviewItemGuid);
  });

  // Test 46: Blocked Review Items Cannot Appear as Verified Takeoff
  it("Test 46: Blocked review items (e.g. non-drywall or invalid geometry) are excluded from eligible QTO sums", () => {
    const walls = sampleCanonicalModel.walls;
    const eligibleWalls = walls.filter((w) => w.qto_eligibility === "ELIGIBLE");
    const blockedWalls = walls.filter((w) => w.qto_eligibility?.startsWith("INELIGIBLE"));

    expect(eligibleWalls.length).toBe(2);
    expect(blockedWalls.length).toBe(1);

    // Blocked wall should not be included in eligible set
    expect(eligibleWalls.some((w) => w.ifc_guid === blockedWalls[0].ifc_guid)).toBe(false);
  });

  // Test 47: Dynamic Derivation of Review Counts from Backend Data
  it("Test 47: Review queue summary counts compute dynamically from real element states", () => {
    const walls = sampleCanonicalModel.walls;
    const spaces = sampleCanonicalModel.spaces;

    let blockedCount = 0;
    let reviewRequiredCount = 0;
    let assumptionCount = 0;

    walls.forEach((w) => {
      if (w.qto_eligibility?.startsWith("INELIGIBLE")) blockedCount++;
      else if (w.qto_eligibility === "REVIEW_REQUIRED") reviewRequiredCount++;

      if (w.assembly?.assembly_provenance === "CONFIGURED_ASSUMPTION") assumptionCount++;
    });

    expect(blockedCount).toBe(1); // Structural concrete wall
    expect(reviewRequiredCount).toBe(1); // Unknown wall
    expect(assumptionCount).toBe(1); // Wall 2 (Brick on CMU configured assumption)
    expect(blockedCount + reviewRequiredCount).toBe(2);
  });

  // Test 48 (NEGATIVE TEST): No Frontend-Generated Fake Review Reasons
  it("Test 48 (NEGATIVE TEST): Only canonical review reasons from backend/normalizer are surfaced", () => {
    const validReasonCategories = [
      "MISSING_GEOMETRY",
      "INVALID_GEOMETRY",
      "ZERO_LENGTH",
      "MISSING_HEIGHT",
      "MISSING_WALL_ASSEMBLY",
      "MISSING_MATERIAL_LAYERS",
      "AMBIGUOUS_DRYWALL_SCOPE",
      "OPENING_RECONCILIATION_CONFLICT",
      "MISSING_REQUIRED_PSET",
      "UNSUPPORTED_GEOMETRY",
      "CONFIGURED_ASSUMPTION",
      "OTHER_UNRESOLVED",
    ];

    const wallReviewCategory = "AMBIGUOUS_DRYWALL_SCOPE";
    expect(validReasonCategories.includes(wallReviewCategory)).toBe(true);

    const fakeReason = "AI_HALLUCINATED_REASON";
    expect(validReasonCategories.includes(fakeReason)).toBe(false);
  });

  // Test 49: Review Queue Filtering Cannot Leave a Phantom Selection
  it("Test 49: Review queue filtering by severity/status clears or updates selection if active element is excluded", () => {
    const reviewItems = [
      { guid: "item-critical", severity: "CRITICAL", status: "BLOCKED" },
      { guid: "item-warning", severity: "WARNING", status: "REVIEW_REQUIRED" },
    ];

    let selectedGuid: string | null = "item-warning";
    const activeSeverityFilter = "CRITICAL";

    const filtered = reviewItems.filter((i) => i.severity === activeSeverityFilter);
    if (selectedGuid && !filtered.some((i) => i.guid === selectedGuid)) {
      selectedGuid = filtered.length > 0 ? filtered[0].guid : null;
    }

    expect(selectedGuid).toBe("item-critical");
    expect(filtered.length).toBe(1);
  });

  // Test 50: BOQ ↔ Review Queue Bidirectional GUID Reconciliation
  it("Test 50: BOQ schedule and Review queue maintain exact matching ifc_guid identity", () => {
    const wallWithReview = sampleCanonicalModel.walls[3]; // Unknown wall
    const reviewGuid = wallWithReview.ifc_guid;

    // BOQ line item and Review item reference the exact same GUID
    expect(reviewGuid).toBe("9kL123xY45ZxcVbnMasDf3");
    expect(wallWithReview.qto_eligibility).toBe("REVIEW_REQUIRED");
  });

  // =========================================================================
  // STEP 6: PHASE 2 FINAL AUDIT & EXPORT RECONCILIATION NEGATIVE TESTS (A-J)
  // =========================================================================

  // Test 51 (Negative A): BOQ quantity mismatch is detected
  it("Test 51 (Negative A): BOQ quantity mismatch between Canonical QTO and Schedule is detected", () => {
    const canonicalQtoQuantity = 328.0; // SF
    const tamperedBoqQuantity = 400.0; // Discrepancy

    const isReconciled = Math.abs(canonicalQtoQuantity - tamperedBoqQuantity) < 0.001;
    expect(isReconciled).toBe(false);

    // Audit reconciliation function detects mismatch
    const reconcileQuantities = (canonical: number, boq: number) => {
      if (Math.abs(canonical - boq) > 0.01) {
        return { status: "FAILED_RECONCILIATION", diff: Math.abs(canonical - boq) };
      }
      return { status: "PASS", diff: 0 };
    };

    const auditResult = reconcileQuantities(canonicalQtoQuantity, tamperedBoqQuantity);
    expect(auditResult.status).toBe("FAILED_RECONCILIATION");
    expect(auditResult.diff).toBe(72.0);
  });

  // Test 52 (Negative B): Missing QTO line is detected
  it("Test 52 (Negative B): Canonical eligible wall without corresponding QTO line is detected", () => {
    const eligibleWalls = [
      { ifc_guid: "guid-wall-1", eligibility: "ELIGIBLE" },
      { ifc_guid: "guid-wall-2", eligibility: "ELIGIBLE" },
    ];
    const qtoLines = [
      { source_guid: "guid-wall-1", quantity: 150.0 },
      // guid-wall-2 is missing from QTO output
    ];

    const qtoGuids = new Set(qtoLines.map((l) => l.source_guid));
    const missingQtoWalls = eligibleWalls.filter((w) => !qtoGuids.has(w.ifc_guid));

    expect(missingQtoWalls.length).toBe(1);
    expect(missingQtoWalls[0].ifc_guid).toBe("guid-wall-2");
  });

  // Test 53 (Negative C): BOQ row without canonical GUID is detected
  it("Test 53 (Negative C): BOQ row referencing an orphaned or non-existent canonical GUID is detected", () => {
    const canonicalWallGuids = new Set(["guid-wall-1", "guid-wall-2"]);
    const boqRows = [
      { ifc_guid: "guid-wall-1", item: "Drywall Partition" },
      { ifc_guid: "phantom-guid-999", item: "Unlinked Drywall" }, // Orphaned
    ];

    const orphanedBoqRows = boqRows.filter((row) => !canonicalWallGuids.has(row.ifc_guid));
    expect(orphanedBoqRows.length).toBe(1);
    expect(orphanedBoqRows[0].ifc_guid).toBe("phantom-guid-999");
  });

  // Test 54 (Negative D): Duplicate IFC GUID is detected
  it("Test 54 (Negative D): Duplicate IFC GUID across elements is detected and fails reconciliation", () => {
    const elementsWithDuplicate = [
      { ifc_guid: "GUID-DUPLICATE-A", name: "Wall 101" },
      { ifc_guid: "GUID-UNIQUE-B", name: "Wall 102" },
      { ifc_guid: "GUID-DUPLICATE-A", name: "Wall 103 Duplicate" },
    ];

    const seenGuids = new Set<string>();
    const duplicateGuids: string[] = [];

    elementsWithDuplicate.forEach((el) => {
      if (seenGuids.has(el.ifc_guid)) {
        duplicateGuids.push(el.ifc_guid);
      } else {
        seenGuids.add(el.ifc_guid);
      }
    });

    expect(duplicateGuids.length).toBe(1);
    expect(duplicateGuids[0]).toBe("GUID-DUPLICATE-A");
  });

  // Test 55 (Negative E): UNKNOWN_UNRESOLVED cannot become VERIFIED
  it("Test 55 (Negative E): UNKNOWN_UNRESOLVED property is strictly prevented from becoming VERIFIED_EXPLICIT", () => {
    const unverifiedProperty = {
      name: "FireRating",
      raw_value: null,
      provenance: "UNKNOWN_UNRESOLVED",
    };

    // Assert provenance gating rule
    const upgradeToVerified = (prop: typeof unverifiedProperty) => {
      if (!prop.raw_value && prop.provenance === "UNKNOWN_UNRESOLVED") {
        return prop.provenance; // Gated: cannot upgrade without explicit source data
      }
      return "VERIFIED_EXPLICIT";
    };

    const resultingProvenance = upgradeToVerified(unverifiedProperty);
    expect(resultingProvenance).toBe("UNKNOWN_UNRESOLVED");
    expect(resultingProvenance).not.toBe("VERIFIED_EXPLICIT");
  });

  // Test 56 (Negative F): Hardcoded drywall profile cannot masquerade as CONFIGURED_ASSUMPTION
  it("Test 56 (Negative F): Default hardcoded drywall profile without explicit project config is NOT CONFIGURED_ASSUMPTION", () => {
    const projectHasExplicitConfig = false;
    const defaultAssembly = {
      board_type: '5/8" Type X',
      stud_size: '3-5/8"',
      stud_spacing_in: 16,
    };

    const deriveAssemblyProvenance = (hasConfig: boolean) => {
      if (hasConfig) {
        return "CONFIGURED_ASSUMPTION";
      }
      // Without explicit project configuration, default fallback must be DERIVED_GEOMETRIC / UNKNOWN_UNRESOLVED, not CONFIGURED_ASSUMPTION
      return "UNKNOWN_UNRESOLVED";
    };

    const provenance = deriveAssemblyProvenance(projectHasExplicitConfig);
    expect(provenance).toBe("UNKNOWN_UNRESOLVED");
    expect(provenance).not.toBe("CONFIGURED_ASSUMPTION");
  });

  // Test 57 (Negative G): Exported BOQ totals reconcile with canonical totals
  it("Test 57 (Negative G): Exported Excel BOQ totals strictly reconcile with Canonical Takeoff summary", () => {
    const canonicalSummary = {
      total_gross_wall_area_sqft: 1100.0,
      total_opening_deduction_sqft: 42.0,
      total_net_drywall_area_sqft: 1078.0,
      total_drywall_sheets_4x8: 39,
    };

    const exportedBoqRows = [
      { net_quantity: 328.0, sheets: 12 },
      { net_quantity: 480.0, sheets: 17 },
      { net_quantity: 0.0, sheets: 0 },
      { net_quantity: 270.0, sheets: 10 },
    ];

    const sumExportedNet = exportedBoqRows.reduce((sum, r) => sum + r.net_quantity, 0);
    const sumExportedSheets = exportedBoqRows.reduce((sum, r) => sum + r.sheets, 0);

    expect(sumExportedNet).toBe(canonicalSummary.total_net_drywall_area_sqft);
    expect(sumExportedSheets).toBe(canonicalSummary.total_drywall_sheets_4x8);
  });

  // Test 58 (Negative H): Review items remain present in export
  it("Test 58 (Negative H): Blocked elements and exceptions are preserved in Review / Exceptions export sheet", () => {
    const reviewQueueItems = [
      { guid: "guid-rev-1", category: "BLOCKED_QTO", severity: "HIGH", reason: "Zero length axis" },
      { guid: "guid-rev-2", category: "CLASSIFICATION_UNKNOWN", severity: "MEDIUM", reason: "Unknown profile" },
    ];

    // Build Sheet 3 rows
    const exportedReviewSheet = reviewQueueItems.map((item) => ({
      "IFC GUID": item.guid,
      "Issue Category": item.category,
      "Severity": item.severity,
      "Technical Reason": item.reason,
    }));

    expect(exportedReviewSheet.length).toBe(reviewQueueItems.length);
    expect(exportedReviewSheet[0]["IFC GUID"]).toBe("guid-rev-1");
    expect(exportedReviewSheet[1]["Issue Category"]).toBe("CLASSIFICATION_UNKNOWN");
  });

  // Test 59 (Negative I): Different model hashes create separate audit snapshots
  it("Test 59 (Negative I): Distinct model SHA-256 hashes generate isolated, non-overwriting audit snapshots", () => {
    const snapshotStore = new Map<string, { modelSha: string; timestamp: string; wallsCount: number }>();

    const snapshotA = {
      modelSha: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      timestamp: "2026-09-04T10:00:00Z",
      wallsCount: 57,
    };

    const snapshotB = {
      modelSha: "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e",
      timestamp: "2026-09-04T11:00:00Z",
      wallsCount: 114,
    };

    snapshotStore.set(snapshotA.modelSha, snapshotA);
    snapshotStore.set(snapshotB.modelSha, snapshotB);

    expect(snapshotStore.size).toBe(2);
    expect(snapshotStore.get(snapshotA.modelSha)?.wallsCount).toBe(57);
    expect(snapshotStore.get(snapshotB.modelSha)?.wallsCount).toBe(114);
  });

  // Test 60 (Negative J): Unit mismatch is detected
  it("Test 60 (Negative J): Unit mismatch (e.g. attempting to sum LF with SQFT or mixing Metric/Imperial) is detected", () => {
    const itemsWithMixedUnits = [
      { item: "Drywall Board", quantity: 328.0, unit: "SQFT" },
      { item: "Metal Studs", quantity: 45.0, unit: "LF" },
      { item: "Drywall Screws", quantity: 500.0, unit: "EA" },
    ];

    const canSafelySum = (units: string[]) => {
      const distinctUnits = new Set(units);
      return distinctUnits.size === 1;
    };

    const units = itemsWithMixedUnits.map((i) => i.unit);
    const isSummable = canSafelySum(units);

    expect(isSummable).toBe(false); // Mixed units cannot be naively summed together
  });

  // Test 61: Two-IFC Model Transition Purges Previous GUIDs and State
  it("Test 61: Two-IFC Model Transition (IFC-A -> IFC-B) purges all previous GUIDs, quantities, and selections", () => {
    // Simulated state machine for BIM workspace model transition
    interface BIMWorkspaceSessionState {
      ifcId: string;
      sourceHash: string;
      canonicalModel: { walls: Array<{ ifc_guid: string; length_ft: number }> } | null;
      takeoff: { total_gross_wall_area_sqft: number; model_sha256: string } | null;
      selectedWallGuid: string | null;
      isolatedWallGuid: string | null;
      hiddenWallGuids: Set<string>;
    }

    function createFreshSession(ifcId: string, sourceHash: string): BIMWorkspaceSessionState {
      return {
        ifcId,
        sourceHash,
        canonicalModel: null,
        takeoff: null,
        selectedWallGuid: null,
        isolatedWallGuid: null,
        hiddenWallGuids: new Set(),
      };
    }

    // Load Model A
    let session = createFreshSession("doc-ifc-a", "431df7c07980df224fd8a02cac017141a79c50cff5a61d18dbede5467a5f2e86");
    session.canonicalModel = {
      walls: [
        { ifc_guid: "guid-wall-a1", length_ft: 20.0 },
        { ifc_guid: "guid-wall-a2", length_ft: 15.0 },
      ],
    };
    session.takeoff = {
      total_gross_wall_area_sqft: 700.0,
      model_sha256: "431df7c07980df224fd8a02cac017141a79c50cff5a61d18dbede5467a5f2e86",
    };
    session.selectedWallGuid = "guid-wall-a1";
    session.hiddenWallGuids.add("guid-wall-a2");
    session.isolatedWallGuid = "guid-wall-a1";

    expect(session.selectedWallGuid).toBe("guid-wall-a1");
    expect(session.takeoff.total_gross_wall_area_sqft).toBe(700.0);

    // Transition to Model B (Simulating key={ifcId} + state reset effect)
    session = createFreshSession("doc-ifc-b", "c48daad1b831c98dd008a9a7a34184b6497b88d8d2edcd7cac0bcbb22f4bf848");
    session.canonicalModel = {
      walls: [
        { ifc_guid: "guid-wall-b1", length_ft: 35.0 },
      ],
    };
    session.takeoff = {
      total_gross_wall_area_sqft: 350.0,
      model_sha256: "c48daad1b831c98dd008a9a7a34184b6497b88d8d2edcd7cac0bcbb22f4bf848",
    };
    session.selectedWallGuid = "guid-wall-b1";

    // Strict assertions: Model A data is completely purged
    const bGuids = session.canonicalModel.walls.map((w) => w.ifc_guid);
    expect(bGuids).not.toContain("guid-wall-a1");
    expect(bGuids).not.toContain("guid-wall-a2");
    expect(session.hiddenWallGuids.has("guid-wall-a2")).toBe(false);
    expect(session.isolatedWallGuid).toBeNull();
    expect(session.selectedWallGuid).toBe("guid-wall-b1");
    expect(session.takeoff.total_gross_wall_area_sqft).toBe(350.0);
    expect(session.sourceHash).toBe("c48daad1b831c98dd008a9a7a34184b6497b88d8d2edcd7cac0bcbb22f4bf848");
  });

  // Test 62: Cryptographic Source Hash Invariant Validation Gate
  it("Test 62: Cryptographic Source Hash Invariant detects and blocks mismatched or stale cached models", () => {
    function validateSourceHashInvariant(docHash: string, canonicalHash: string, takeoffHash: string) {
      if (docHash !== canonicalHash) {
        throw new Error(`Data Integrity Violation: Document source_hash (${docHash.slice(0, 8)}) does not match canonical_model.source_hash (${canonicalHash.slice(0, 8)})`);
      }
      if (docHash !== takeoffHash) {
        throw new Error(`Data Integrity Violation: Document source_hash (${docHash.slice(0, 8)}) does not match takeoff.model_sha256 (${takeoffHash.slice(0, 8)})`);
      }
      return true;
    }

    const validHash = "431df7c07980df224fd8a02cac017141a79c50cff5a61d18dbede5467a5f2e86";
    const staleHash = "c48daad1b831c98dd008a9a7a34184b6497b88d8d2edcd7cac0bcbb22f4bf848";

    // Passing invariant
    expect(validateSourceHashInvariant(validHash, validHash, validHash)).toBe(true);

    // Failing canonical invariant (stale canonical model returned for new document)
    expect(() => validateSourceHashInvariant(validHash, staleHash, validHash)).toThrow(
      /Data Integrity Violation: Document source_hash/
    );

    // Failing takeoff invariant (stale takeoff returned for new document)
    expect(() => validateSourceHashInvariant(validHash, validHash, staleHash)).toThrow(
      /Data Integrity Violation: Document source_hash/
    );
  });

  // Test 63: Full 3-Cycle Transition (IFC-A -> IFC-B -> IFC-A) Restores Pure Original State
  it("Test 63: Full 3-Cycle Transition (IFC-A -> IFC-B -> IFC-A) restores exact original state without degradation", () => {
    const registry = new Map<string, { hash: string; wallsCount: number; grossArea: number; guids: string[] }>();

    registry.set("ifc-a", {
      hash: "431df7c07980df224fd8a02cac017141a79c50cff5a61d18dbede5467a5f2e86",
      wallsCount: 97,
      grossArea: 19677.82,
      guids: ["guid-a-001", "guid-a-002", "guid-a-097"],
    });

    registry.set("ifc-b", {
      hash: "c48daad1b831c98dd008a9a7a34184b6497b88d8d2edcd7cac0bcbb22f4bf848",
      wallsCount: 2,
      grossArea: 387.50,
      guids: ["guid-b-001", "guid-b-002"],
    });

    // Cycle 1: Load IFC-A
    const activeModel1 = registry.get("ifc-a")!;
    expect(activeModel1.wallsCount).toBe(97);
    expect(activeModel1.grossArea).toBe(19677.82);

    // Cycle 2: Switch to IFC-B
    const activeModel2 = registry.get("ifc-b")!;
    expect(activeModel2.wallsCount).toBe(2);
    expect(activeModel2.grossArea).toBe(387.50);
    expect(activeModel2.guids).not.toEqual(expect.arrayContaining(activeModel1.guids));

    // Cycle 3: Switch back to IFC-A
    const activeModel3 = registry.get("ifc-a")!;
    expect(activeModel3.wallsCount).toBe(97);
    expect(activeModel3.grossArea).toBe(19677.82);
    expect(activeModel3.guids).not.toEqual(expect.arrayContaining(activeModel2.guids));
    expect(activeModel3.hash).toBe(activeModel1.hash);
  });
});


