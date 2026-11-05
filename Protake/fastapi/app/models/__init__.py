"""Import every ORM model here so `Base.metadata` (and Alembic
autogenerate) can discover the full schema from a single import.
"""

from app.models.architectural_wall import ArchitecturalWallModel
from app.models.audit_log import AuditLog
from app.models.blueprint import Blueprint
from app.models.detection import Detection
from app.models.drywall import DrywallClassification, DrywallItem, DrywallTakeoff
from app.models.estimate import Estimate, EstimateItem
from app.models.flooring import FlooringClassification, FlooringItem, FlooringTakeoff
from app.models.ground_truth import GroundTruthReference
from app.models.ifc_document import IFCDocument
from app.models.measurement import Measurement
from app.models.page import Page
from app.models.painting import PaintingClassification, PaintingItem, PaintingTakeoff
from app.models.pdf_document import PDFDocument
from app.models.project import Project
from app.models.project_knowledge_graph import ProjectKnowledgeGraphModel
from app.models.qc_signoff import QcSignoff
from app.models.room import Room
from app.models.roofing_takeoff import RoofingClassification, RoofingItem, RoofingTakeoff
from app.models.schedule_item import ScheduleItem
from app.models.trade import TradeConfig
from app.models.user import User
from app.models.wall import Wall

# Not imported here: app.models.roof — it only gets registered on
# Base.metadata because app/api/v1/endpoints/roofing.py imports it at
# startup. Kept as-is (out of scope for this change) but worth knowing
# about before assuming autogenerate sees every table.

__all__ = [
    "ArchitecturalWallModel",
    "AuditLog",
    "Blueprint",
    "Detection",
    "DrywallClassification",
    "DrywallItem",
    "DrywallTakeoff",
    "Estimate",
    "EstimateItem",
    "FlooringClassification",
    "FlooringItem",
    "FlooringTakeoff",
    "GroundTruthReference",
    "Measurement",
    "Page",
    "PaintingClassification",
    "PaintingItem",
    "PaintingTakeoff",
    "PDFDocument",
    "Project",
    "ProjectKnowledgeGraphModel",
    "QcSignoff",
    "Room",
    "RoofingClassification",
    "RoofingItem",
    "RoofingTakeoff",
    "ScheduleItem",
    "TradeConfig",
    "User",
    "Wall",
]

