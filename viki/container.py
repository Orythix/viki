from dependency_injector import containers, providers
from viki.infrastructure.database.sqlalchemy_learning_repository import SqlAlchemyLearningRepository
from viki.application.services.safety_service import SafetyService
from viki.application.use_cases.recall_memory import MemoryRecallUseCase

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    # Infrastructure
    learning_repository = providers.Singleton(
        SqlAlchemyLearningRepository,
        db_url="sqlite:///data/viki_knowledge.db"
    )

    # Services
    safety_service = providers.Singleton(
        SafetyService,
        config=config.safety
    )

    # Use Cases
    recall_memory_use_case = providers.Factory(
        MemoryRecallUseCase,
        learning_repo=learning_repository,
        safety_service=safety_service
    )
