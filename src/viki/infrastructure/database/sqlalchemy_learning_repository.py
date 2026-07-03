import json
import logging
import time
from typing import cast

from sqlalchemy import Float, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import NullPool

from viki.domain.entities.learning import FailureRecord, Lesson, Relationship
from viki.domain.interfaces.learning_repository import ILearningRepository

_log = logging.getLogger("viki.repository")


class Base(DeclarativeBase):
    pass


class LessonModel(Base):
    __tablename__ = "lessons"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    text_representation: Mapped[str] = mapped_column(Text)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float)
    last_accessed: Mapped[float] = mapped_column(Float)
    access_count: Mapped[int] = mapped_column(Integer, default=1)
    author: Mapped[str] = mapped_column(String)
    source_task: Mapped[str] = mapped_column(String)
    reliability: Mapped[float] = mapped_column(Float)


class FailureModel(Base):
    __tablename__ = "failures"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(Text)
    error: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[float] = mapped_column(Float)


class RelationshipModel(Base):
    __tablename__ = "relationships"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String, ForeignKey("lessons.id"))
    target_id: Mapped[str] = mapped_column(String, ForeignKey("lessons.id"))
    type: Mapped[str] = mapped_column(String)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class SqlAlchemyLearningRepository(ILearningRepository):
    def __init__(self, db_url: str):
        self.engine = create_engine(
            db_url,
            poolclass=NullPool,
            connect_args={"check_same_thread": False, "timeout": 15},
        )

        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout = 15000")
            cursor.execute("PRAGMA synchronous = NORMAL")
            cursor.execute("PRAGMA cache_size = -16000")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def _execute(self, fn):
        """Execute a DB operation with retry on locked errors."""
        last_error = None
        for attempt in range(3):
            try:
                return fn()
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if "database is locked" in err_str or "timeout" in err_str:
                    _log.warning("DB lock on attempt %d/3, retrying: %s", attempt + 1, e)
                    time.sleep(0.1 * (attempt + 1))
                    continue
                raise
        assert last_error is not None
        raise last_error

    def save_lesson(self, lesson: Lesson) -> None:
        def _op():
            with self.Session() as session:
                model = LessonModel(
                    id=lesson.id,
                    content=lesson.content,
                    text_representation=lesson.text_representation,
                    embedding=json.dumps(lesson.embedding) if lesson.embedding else None,
                    created_at=lesson.created_at or time.time(),
                    last_accessed=lesson.last_accessed or time.time(),
                    access_count=lesson.access_count,
                    author=lesson.author,
                    source_task=lesson.source_task,
                    reliability=lesson.reliability,
                )
                session.merge(model)
                session.commit()

        self._execute(_op)

    def get_lesson(self, lesson_id: str) -> Lesson | None:
        def _op():
            with self.Session() as session:
                model = session.query(LessonModel).filter_by(id=lesson_id).first()
                if not model:
                    return None
                return Lesson(
                    id=model.id,
                    content=model.content,
                    text_representation=model.text_representation,
                    embedding=json.loads(model.embedding) if model.embedding else None,
                    created_at=model.created_at,
                    last_accessed=model.last_accessed,
                    access_count=model.access_count,
                    author=model.author,
                    source_task=model.source_task,
                    reliability=model.reliability,
                )

        return cast("Lesson | None", self._execute(_op))

    def get_relevant_lessons(self, query: str, limit: int = 5) -> list[Lesson]:
        # Note: True semantic search would require an encoder service.
        # This implementation provides a basic recency/lexical fallback for now.
        def _op():
            with self.Session() as session:
                models = (
                    session.query(LessonModel)
                    .order_by(LessonModel.last_accessed.desc())
                    .limit(limit)
                    .all()
                )
                return [
                    Lesson(
                        id=m.id,
                        content=m.content,
                        text_representation=m.text_representation,
                        embedding=json.loads(m.embedding) if m.embedding else None,
                        created_at=m.created_at,
                        last_accessed=m.last_accessed,
                        access_count=m.access_count,
                        author=m.author,
                        source_task=m.source_task,
                        reliability=m.reliability,
                    )
                    for m in models
                ]

        return cast("list[Lesson]", self._execute(_op))

    def save_failure(self, failure: FailureRecord) -> None:
        def _op():
            with self.Session() as session:
                model = FailureModel(
                    action=failure.action,
                    error=failure.error,
                    context=failure.context,
                    timestamp=failure.timestamp or time.time(),
                )
                session.add(model)
                session.commit()

        self._execute(_op)

    def get_relevant_failures(self, query: str, limit: int = 5) -> list[FailureRecord]:
        def _op():
            with self.Session() as session:
                models = (
                    session.query(FailureModel)
                    .order_by(FailureModel.timestamp.desc())
                    .limit(limit)
                    .all()
                )
                return [
                    FailureRecord(
                        id=m.id,
                        action=m.action,
                        error=m.error,
                        context=m.context,
                        timestamp=m.timestamp,
                    )
                    for m in models
                ]

        return cast("list[FailureRecord]", self._execute(_op))

    def save_relationship(self, relationship: Relationship) -> None:
        def _op():
            with self.Session() as session:
                model = RelationshipModel(
                    source_id=relationship.source_id,
                    target_id=relationship.target_id,
                    type=relationship.type,
                    weight=relationship.weight,
                    metadata_json=json.dumps(relationship.metadata),
                )
                session.add(model)
                session.commit()

        self._execute(_op)

    def get_related_concepts(self, lesson_id: str) -> list[Lesson]:
        def _op():
            with self.Session() as session:
                target_ids = (
                    session.query(RelationshipModel.target_id).filter_by(source_id=lesson_id).all()
                )
                target_ids = [t[0] for t in target_ids]

                models = session.query(LessonModel).filter(LessonModel.id.in_(target_ids)).all()
                return [
                    Lesson(
                        id=m.id,
                        content=m.content,
                        text_representation=m.text_representation,
                        embedding=json.loads(m.embedding) if m.embedding else None,
                        created_at=m.created_at,
                        last_accessed=m.last_accessed,
                        access_count=m.access_count,
                        author=m.author,
                        source_task=m.source_task,
                        reliability=m.reliability,
                    )
                    for m in models
                ]

        return cast("list[Lesson]", self._execute(_op))
