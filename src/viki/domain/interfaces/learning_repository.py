from abc import ABC, abstractmethod

from viki.domain.entities.learning import FailureRecord, Lesson, Relationship


class ILearningRepository(ABC):
    @abstractmethod
    def save_lesson(self, lesson: Lesson) -> None:
        pass

    @abstractmethod
    def get_lesson(self, lesson_id: str) -> Lesson | None:
        pass

    @abstractmethod
    def get_relevant_lessons(self, query: str, limit: int = 5) -> list[Lesson]:
        pass

    @abstractmethod
    def save_failure(self, failure: FailureRecord) -> None:
        pass

    @abstractmethod
    def get_relevant_failures(self, query: str, limit: int = 5) -> list[FailureRecord]:
        pass

    @abstractmethod
    def save_relationship(self, relationship: Relationship) -> None:
        pass

    @abstractmethod
    def get_related_concepts(self, lesson_id: str) -> list[Lesson]:
        pass
