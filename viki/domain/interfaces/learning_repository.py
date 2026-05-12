from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from viki.domain.entities.learning import Lesson, FailureRecord

class ILearningRepository(ABC):
    @abstractmethod
    def save_lesson(self, lesson: Lesson) -> None:
        pass

    @abstractmethod
    def get_lesson(self, lesson_id: str) -> Optional[Lesson]:
        pass

    @abstractmethod
    def get_relevant_lessons(self, query: str, limit: int = 5) -> List[Lesson]:
        pass

    @abstractmethod
    def save_failure(self, failure: FailureRecord) -> None:
        pass

    @abstractmethod
    def get_relevant_failures(self, query: str, limit: int = 5) -> List[FailureRecord]:
        pass
