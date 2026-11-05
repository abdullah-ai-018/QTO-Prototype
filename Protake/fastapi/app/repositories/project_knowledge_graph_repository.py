from sqlalchemy import select

from app.models.project_knowledge_graph import ProjectKnowledgeGraphModel
from app.repositories.base import BaseRepository


class ProjectKnowledgeGraphRepository(BaseRepository[ProjectKnowledgeGraphModel]):
    model = ProjectKnowledgeGraphModel

    def for_blueprint(self, blueprint_id: int) -> ProjectKnowledgeGraphModel | None:
        stmt = select(ProjectKnowledgeGraphModel).where(ProjectKnowledgeGraphModel.blueprint_id == blueprint_id)
        return self.db.execute(stmt).scalars().first()
