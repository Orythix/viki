import asyncio
from typing import Dict, Any, List
from viki.application.services.safety_service import SafetyService
from viki.domain.interfaces.learning_repository import ILearningRepository
from viki.domain.entities.learning import Lesson

class MemoryRecallUseCase:
    def __init__(self, learning_repo: ILearningRepository, safety_service: SafetyService):
        self.learning_repo = learning_repo
        self.safety_service = safety_service

    async def execute(self, query: str, limit: int = 5) -> List[str]:
        # Application-level logic: sanitize, then query
        safe_query = self.safety_service.sanitize_request(query)
        lessons = self.learning_repo.get_relevant_lessons(safe_query, limit=limit)
        return [lesson.text_representation for lesson in lessons]
