from datetime import datetime

from app.models.enums import BlueprintStatus
from app.schemas.common import ORMModel


class BlueprintRead(ORMModel):
    id: int
    project_id: int
    original_filename: str
    file_size_bytes: int
    num_pages: int
    pages_processed: int
    status: BlueprintStatus
    processing_error: str | None
    current_stage: str | None = None
    created_at: datetime


class BlueprintUploadResponse(ORMModel):
    blueprint: BlueprintRead
    message: str
