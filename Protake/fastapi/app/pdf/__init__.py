"""PDF Ingestion & Canonical Drawing Subsystem:
Provides deterministic vector extraction, content decoding, coordinate preservation,
topology validation, content-geometry association, and canonical trade QTO.
"""

from app.pdf.models import (
    PDFType,
    PDFPageCapabilities,
    PDFDocumentCapabilities,
    DrawingTextObject,
    DrawingGeometryObject,
    DrawingDimensionObject,
    ScaleEvidence,
    ScaleStatus,
    SemanticContentType,
    GeometryPrimitiveType,
    TransformMetadata,
    CanonicalDrawingDocument,
    CanonicalDrawingPage,
    GeometryValidationReport,
)
from app.pdf.detector import PDFTypeDetector
from app.pdf.content_extractor import PDFContentExtractor
from app.pdf.vector_extractor import PDFVectorExtractor
from app.pdf.scale_validator import ScaleValidator
from app.pdf.roof_classifier import RoofVectorClassifier, ClassifiedRoofVectors
from app.pdf.roof_topology import (
    RoofTopologyReconstructor,
    ReconstructedRoofPlane,
    RoofValidationItem,
    RoofTopologySummary,
)

__all__ = [
    "PDFType",
    "PDFPageCapabilities",
    "PDFDocumentCapabilities",
    "DrawingTextObject",
    "DrawingGeometryObject",
    "DrawingDimensionObject",
    "ScaleEvidence",
    "ScaleStatus",
    "SemanticContentType",
    "GeometryPrimitiveType",
    "TransformMetadata",
    "CanonicalDrawingDocument",
    "CanonicalDrawingPage",
    "GeometryValidationReport",
    "PDFTypeDetector",
    "PDFContentExtractor",
    "PDFVectorExtractor",
    "ScaleValidator",
    "RoofVectorClassifier",
    "ClassifiedRoofVectors",
    "RoofTopologyReconstructor",
    "ReconstructedRoofPlane",
    "RoofValidationItem",
    "RoofTopologySummary",
]
