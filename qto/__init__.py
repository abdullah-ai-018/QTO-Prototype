"""
Drywall QTO: Automated Blueprint Processing & Wall Annotation Pipeline.
"""

from qto.geometry import (
    Point,
    Segment,
    BoundingBox,
    point_to_segment_distance,
    angle_diff,
    project_point_to_axis,
    reconstruct_point_from_axis,
    intervals_overlap,
    are_collinear,
    are_parallel,
)
from qto.scale import (
    parse_scale_string,
    detect_scale_from_page,
    pt_to_ft,
    ft_to_pt,
    DEFAULT_SCALE_STR,
    DEFAULT_FT_PER_PT,
)
from qto.tags import (
    TAG_REGEX,
    is_valid_wall_tag,
    discover_tags_from_schedules,
    find_tag_instances_on_page,
    TagInstance,
)
from qto.assemblies import (
    extract_wall_materials,
    parse_assembly_attributes,
    clean_text,
)
from qto.classify.mock import (
    MockClassifier,
    evaluate_with_mock,
)
from qto.classify.jev import (
    load_environment_credentials,
    evaluate_with_jev,
    get_wall_registry,
    PROBABILITY_THRESHOLD,
    REVIEW_THRESHOLD,
)
from qto.segments import (
    extract_page_linework,
    extract_page_segments,
    DoorArc,
    PageLinework,
)
from qto.openings import (
    Opening,
    process_wall_gaps,
    find_matching_door_arc,
)
from qto.trace_walls import (
    find_leader_endpoint,
    find_seed_segment,
    trace_wall_from_seed,
    TracedWall,
)
from qto.dedup import (
    WallRun,
    compute_centerline_spine,
    create_wall_run,
    deduplicate_wall_runs,
)
from qto.annotate import (
    annotate_blueprint_pdf,
    RED_DARK,
    RED_BRIGHT,
    RED_LIGHT_FILL,
)
from qto.pipeline import (
    QTOPipeline,
    run_pipeline,
)

__all__ = [
    "Point",
    "Segment",
    "BoundingBox",
    "point_to_segment_distance",
    "angle_diff",
    "project_point_to_axis",
    "reconstruct_point_from_axis",
    "intervals_overlap",
    "are_collinear",
    "are_parallel",
    "parse_scale_string",
    "detect_scale_from_page",
    "pt_to_ft",
    "ft_to_pt",
    "DEFAULT_SCALE_STR",
    "DEFAULT_FT_PER_PT",
    "TAG_REGEX",
    "is_valid_wall_tag",
    "discover_tags_from_schedules",
    "find_tag_instances_on_page",
    "TagInstance",
    "extract_wall_materials",
    "parse_assembly_attributes",
    "clean_text",
    "MockClassifier",
    "evaluate_with_mock",
    "load_environment_credentials",
    "evaluate_with_jev",
    "get_wall_registry",
    "PROBABILITY_THRESHOLD",
    "REVIEW_THRESHOLD",
    "extract_page_linework",
    "extract_page_segments",
    "DoorArc",
    "PageLinework",
    "Opening",
    "process_wall_gaps",
    "find_matching_door_arc",
    "find_leader_endpoint",
    "find_seed_segment",
    "trace_wall_from_seed",
    "TracedWall",
    "WallRun",
    "compute_centerline_spine",
    "create_wall_run",
    "deduplicate_wall_runs",
    "annotate_blueprint_pdf",
    "RED_DARK",
    "RED_BRIGHT",
    "RED_LIGHT_FILL",
    "QTOPipeline",
    "run_pipeline",
]
