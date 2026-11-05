"""IFC Validator: Inspects and verifies the structural and geometric integrity of IFC files."""
from __future__ import annotations

import enum
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import ifcopenshell


class ValidationSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class ModelStatus(str, enum.Enum):
    VALID = "VALID"
    VALID_WITH_WARNINGS = "VALID_WITH_WARNINGS"
    INVALID = "INVALID"


@dataclass
class ValidationIssue:
    severity: ValidationSeverity
    code: str
    message: str
    entity_guid: Optional[str] = None
    entity_type: Optional[str] = None
    details: Optional[dict[str, Any]] = None


@dataclass
class ValidationReport:
    status: ModelStatus
    schema: str
    is_valid: bool
    project_name: Optional[str] = None
    building_count: int = 0
    storey_count: int = 0
    wall_count: int = 0
    space_count: int = 0
    door_count: int = 0
    window_count: int = 0
    opening_count: int = 0
    length_unit: str = "METRE"
    unit_scale_to_meters: float = 1.0
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == ValidationSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == ValidationSeverity.WARNING)


class IFCValidator:
    """Validates IFC files for compliance with QTO parsing prerequisites."""

    SUPPORTED_SCHEMAS = {"IFC2X3", "IFC4", "IFC4X3", "IFC4X3_ADD2"}

    def validate_file(self, file_path: str) -> tuple[ValidationReport, Optional[ifcopenshell.file]]:
        """Performs full structural validation on the given IFC file path."""
        issues: list[ValidationIssue] = []

        if not os.path.isfile(file_path):
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="FILE_NOT_FOUND",
                    message=f"IFC file not found at path: {file_path}",
                )
            )
            return (
                ValidationReport(
                    status=ModelStatus.INVALID,
                    schema="UNKNOWN",
                    is_valid=False,
                    issues=issues,
                ),
                None,
            )

        file_size = os.path.getsize(file_path)
        if file_size == 0:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="EMPTY_FILE",
                    message="The uploaded IFC file is empty (0 bytes).",
                )
            )
            return (
                ValidationReport(
                    status=ModelStatus.INVALID,
                    schema="UNKNOWN",
                    is_valid=False,
                    issues=issues,
                ),
                None,
            )

        # Attempt to parse IFC file with IfcOpenShell
        try:
            ifc_file = ifcopenshell.open(file_path)
        except Exception as exc:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="IFC_PARSE_CORRUPT",
                    message=f"Failed to parse IFC file structure: {str(exc)}",
                )
            )
            return (
                ValidationReport(
                    status=ModelStatus.INVALID,
                    schema="UNKNOWN",
                    is_valid=False,
                    issues=issues,
                ),
                None,
            )

        schema = ifc_file.schema.upper()
        if schema not in self.SUPPORTED_SCHEMAS:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code="UNCOMMON_SCHEMA",
                    message=f"IFC schema '{schema}' detected. Expected one of {self.SUPPORTED_SCHEMAS}.",
                )
            )

        # 1. Check IfcProject
        projects = ifc_file.by_type("IfcProject")
        project_name = None
        if not projects:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="MISSING_PROJECT",
                    message="IFC file does not contain an IfcProject root element.",
                )
            )
        else:
            project = projects[0]
            project_name = getattr(project, "Name", None) or getattr(project, "LongName", None) or "Unnamed Project"

        # 2. Check Units & Length Scale
        length_unit_name, scale_to_meters = self._extract_length_unit(ifc_file)

        # 3. Check Spatial Structure: Buildings & Storeys
        buildings = ifc_file.by_type("IfcBuilding")
        if not buildings:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code="NO_BUILDING_ENTITY",
                    message="No IfcBuilding entities found. Falling back to default building hierarchy.",
                )
            )

        storeys = ifc_file.by_type("IfcBuildingStorey")
        if not storeys:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code="NO_STOREYS_FOUND",
                    message="No IfcBuildingStorey levels found in IFC. Elements will be assigned to a default level.",
                )
            )

        # 4. Count Physical & Spatial Elements
        walls = ifc_file.by_type("IfcWall")
        spaces = ifc_file.by_type("IfcSpace")
        doors = ifc_file.by_type("IfcDoor")
        windows = ifc_file.by_type("IfcWindow")
        openings = ifc_file.by_type("IfcOpeningElement")

        if not walls:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code="NO_WALLS_FOUND",
                    message="No IfcWall or IfcWallStandardCase elements found in model.",
                )
            )

        # 5. Check Duplicate GUIDs
        guids_seen: set[str] = set()
        duplicate_guids: list[str] = []
        for element in ifc_file.by_type("IfcProduct"):
            guid = getattr(element, "GlobalId", None)
            if guid:
                if guid in guids_seen:
                    duplicate_guids.append(guid)
                else:
                    guids_seen.add(guid)

        if duplicate_guids:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code="DUPLICATE_GUIDS",
                    message=f"Found {len(duplicate_guids)} duplicate GlobalIds in IFC model.",
                    details={"duplicates": duplicate_guids[:10]},
                )
            )

        # Determine overall status
        has_errors = any(i.severity == ValidationSeverity.ERROR for i in issues)
        has_warnings = any(i.severity == ValidationSeverity.WARNING for i in issues)

        if has_errors:
            status = ModelStatus.INVALID
        elif has_warnings:
            status = ModelStatus.VALID_WITH_WARNINGS
        else:
            status = ModelStatus.VALID

        report = ValidationReport(
            status=status,
            schema=schema,
            is_valid=not has_errors,
            project_name=project_name,
            building_count=len(buildings),
            storey_count=len(storeys),
            wall_count=len(walls),
            space_count=len(spaces),
            door_count=len(doors),
            window_count=len(windows),
            opening_count=len(openings),
            length_unit=length_unit_name,
            unit_scale_to_meters=scale_to_meters,
            issues=issues,
        )

        return report, ifc_file

    def _extract_length_unit(self, ifc_file: ifcopenshell.file) -> tuple[str, float]:
        """Extracts the project length unit and its multiplier to meters."""
        default_unit = ("METRE", 1.0)
        try:
            units = ifc_file.by_type("IfcUnitAssignment")
            if not units:
                return default_unit

            for unit in getattr(units[0], "Units", []):
                if getattr(unit, "UnitType", None) == "LENGTHUNIT":
                    # SiUnit
                    if unit.is_a("IfcSIUnit"):
                        prefix_mult = 1.0
                        prefix = getattr(unit, "Prefix", None)
                        if prefix == "MILLI":
                            prefix_mult = 0.001
                        elif prefix == "CENTI":
                            prefix_mult = 0.01
                        elif prefix == "DECI":
                            prefix_mult = 0.1
                        elif prefix == "KILO":
                            prefix_mult = 1000.0
                        return (getattr(unit, "Name", "METRE"), prefix_mult)

                    # ConversionBasedUnit (e.g. FOOT, INCH)
                    if unit.is_a("IfcConversionBasedUnit"):
                        unit_name = getattr(unit, "Name", "FOOT").upper()
                        conv_factor = getattr(unit, "ConversionFactor", None)
                        if conv_factor:
                            value_comp = getattr(conv_factor, "ValueComponent", None)
                            if value_comp:
                                mult = float(value_comp.wrappedValue)
                                return (unit_name, mult)
        except Exception:
            pass

        return default_unit
