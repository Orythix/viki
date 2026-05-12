from typing import List, Optional
from sqlalchemy import Column, String, Float, Integer, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from viki.domain.entities.learning import Lesson, FailureRecord
from viki.domain.interfaces.learning_repository import ILearningRepository
import json
import time
import hashlib

Base = declarative_base()

class LessonModel(Base):
    __tablename__ = 'lessons'
    id = Column(String, primary_key=True)
    content = Column(Text)
    text_representation = Column(Text)
    embedding = Column(Text)
    created_at = Column(Float)
    last_accessed = Column(Float)
    access_count = Column(Integer, default=1)
    author = Column(String)
    source_task = Column(String)
    reliability = Column(Float)

class FailureModel(Base):
    __tablename__ = 'failures'
    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(Text)
    error = Column(Text)
    context = Column(Text)
    timestamp = Column(Float)

class SqlAlchemyLearningRepository(ILearningRepository):
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def save_lesson(self, lesson: Lesson) -> None:
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
                reliability=lesson.reliability
            )
            session.merge(model)
            session.commit()

    def get_lesson(self, lesson_id: str) -> Optional[Lesson]:
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
                reliability=model.reliability
            )

    def get_relevant_lessons(self, query: str, limit: int = 5) -> List[Lesson]:
        # Note: True semantic search would require an encoder service.
        # This implementation provides a basic recency/lexical fallback for now.
        with self.Session() as session:
            models = session.query(LessonModel).order_by(LessonModel.last_accessed.desc()).limit(limit).all()
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
                    reliability=m.reliability
                ) for m in models
            ]

    def save_failure(self, failure: FailureRecord) -> None:
        with self.Session() as session:
            model = FailureModel(
                action=failure.action,
                error=failure.error,
                context=failure.context,
                timestamp=failure.timestamp or time.time()
            )
            session.add(model)
            session.commit()

    def get_relevant_failures(self, query: str, limit: int = 5) -> List[FailureRecord]:
        with self.Session() as session:
            models = session.query(FailureModel).order_by(FailureModel.timestamp.desc()).limit(limit).all()
            return [
                FailureRecord(
                    id=m.id,
                    action=m.action,
                    error=m.error,
                    context=m.context,
                    timestamp=m.timestamp
                ) for m in models
            ]
