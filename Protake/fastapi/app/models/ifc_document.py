"""IFC Document & BIM Takeoff Database Models."""
from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class IFCDocument(Base):
    __tablename__ = "ifc_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size_bytes = Column(Integer, default=0)
    schema_version = Column(String(32), default="IFC4")
    
    status = Column(String(32), default="UPLOADED", index=True)  # UPLOADED, VALIDATED, PARSED, TAKEOFF_COMPLETED, FAILED
    source_hash = Column(String(64), nullable=True, index=True)  # SHA-256 digest of original uploaded IFC file
    error_message = Column(Text, nullable=True)
    
    # JSON Snapshots
    validation_report = Column(JSON, nullable=True)
    canonical_model = Column(JSON, nullable=True)
    qto_summary = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

    project = relationship("Project", backref="ifc_documents")
