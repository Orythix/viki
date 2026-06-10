from typing import List, Optional
from sqlalchemy import Column, String, Float, Integer, Text, create_engine, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship as sqlalchemy_relationship
from domain.entities.learning import Lesson, FailureRecord, Relationship
from domain.interfaces.learning_repository import ILearningRepository
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

class RelationshipModel(Base):
    __tablename__ = 'relationships'
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String, ForeignKey('lessons.id'))
    target_id = Column(String, ForeignKey('lessons.id'))
    type = Column(String)
    weight = Column(Float, default=1.0)
    metadata_json = Column(Text)

from sqlalchemy import event

class SqlAlchemyLearningRepository(ILearningRepository):
    def __init__(self, db_url: str):
        self.engine = create_engine(
            db_url, 
            connect_args={"check_same_thread": False}
        )
        
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
            
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

    def save_relationship(self, relationship: Relationship) -> None:
        with self.Session() as session:
            model = RelationshipModel(
                source_id=relationship.source_id,
                target_id=relationship.target_id,
                type=relationship.type,
                weight=relationship.weight,
                metadata_json=json.dumps(relationship.metadata)
            )
            session.add(model)
            session.commit()

    def get_related_concepts(self, lesson_id: str) -> List[Lesson]:
        with self.Session() as session:
            # Find lessons targeted by relationships from the source lesson
            target_ids = session.query(RelationshipModel.target_id).filter_by(source_id=lesson_id).all()
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
                    reliability=m.reliability
                ) for m in models
            ]
