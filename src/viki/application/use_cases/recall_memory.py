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
        
        # 1. Base Semantic Search
        lessons = self.learning_repo.get_relevant_lessons(safe_query, limit=limit)
        
        # 2. Graph Traversal: Find related concepts for the top match
        all_results = list(lessons)
        if lessons:
            top_lesson = lessons[0]
            related = self.learning_repo.get_related_concepts(top_lesson.id)
            # Merge and de-duplicate
            seen_ids = {l.id for l in all_results}
            for r in related:
                if r.id not in seen_ids:
                    all_results.append(r)
                    seen_ids.add(r.id)
        
        return [lesson.text_representation for lesson in all_results[:limit+2]]
