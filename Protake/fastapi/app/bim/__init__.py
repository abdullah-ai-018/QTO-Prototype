"""Canonical BIM Abstraction Layer: Platform-agnostic domain models and normalization."""
from app.bim.models import (
    CanonicalBIMModel,
    CanonicalBuilding,
    CanonicalColumn,
    CanonicalDoor,
    CanonicalOpening,
    CanonicalProject,
    CanonicalSlab,
    CanonicalSpace,
    CanonicalStorey,
    CanonicalWall,
    CanonicalWindow,
    MaterialLayer,
    WallAssembly,
)
from app.bim.normalizer import BIMNormalizer
from app.bim.graph import BuildingGraph

__all__ = [
    "CanonicalBIMModel",
    "CanonicalProject",
    "CanonicalBuilding",
    "CanonicalStorey",
    "CanonicalSpace",
    "CanonicalWall",
    "CanonicalOpening",
    "CanonicalDoor",
    "CanonicalWindow",
    "CanonicalSlab",
    "CanonicalColumn",
    "MaterialLayer",
    "WallAssembly",
    "BIMNormalizer",
    "BuildingGraph",
]
