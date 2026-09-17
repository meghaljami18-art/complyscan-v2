from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import RLock
from typing import Protocol

from sqlalchemy import JSON, DateTime, String, create_engine, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .models import AuditEvent, InspectionRecord, StorageObjectMetadata


class Repository(Protocol):
    kind: str
    ephemeral: bool

    def create_inspection(self, record: InspectionRecord, event: AuditEvent) -> InspectionRecord: ...
    def get_inspection(self, inspection_id: str) -> InspectionRecord | None: ...
    def list_inspections(self, limit: int = 100) -> list[InspectionRecord]: ...
    def save_inspection(self, record: InspectionRecord, event: AuditEvent) -> InspectionRecord: ...
    def list_audit_events(self, limit: int = 200) -> list[AuditEvent]: ...
    def append_audit_event(self, event: AuditEvent) -> None: ...
    def save_storage_object(self, metadata: StorageObjectMetadata, event: AuditEvent) -> StorageObjectMetadata: ...
    def get_storage_objects(self, object_ids: list[str]) -> list[StorageObjectMetadata]: ...
    def healthcheck(self) -> bool: ...


class InMemoryRepository:
    kind = "memory_demo"
    ephemeral = True

    def __init__(self) -> None:
        self._lock = RLock()
        self._inspections: dict[str, InspectionRecord] = {}
        self._storage: dict[str, StorageObjectMetadata] = {}
        self._audits: list[AuditEvent] = []

    def create_inspection(self, record: InspectionRecord, event: AuditEvent) -> InspectionRecord:
        with self._lock:
            if record.id in self._inspections:
                raise ValueError("inspection already exists")
            self._inspections[record.id] = deepcopy(record)
            self._audits.append(deepcopy(event))
            return deepcopy(record)

    def get_inspection(self, inspection_id: str) -> InspectionRecord | None:
        with self._lock:
            record = self._inspections.get(inspection_id)
            return deepcopy(record) if record else None

    def list_inspections(self, limit: int = 100) -> list[InspectionRecord]:
        with self._lock:
            rows = sorted(self._inspections.values(), key=lambda item: item.updated_at, reverse=True)
            return [deepcopy(item) for item in rows[:limit]]

    def save_inspection(self, record: InspectionRecord, event: AuditEvent) -> InspectionRecord:
        with self._lock:
            if record.id not in self._inspections:
                raise KeyError(record.id)
            self._inspections[record.id] = deepcopy(record)
            self._audits.append(deepcopy(event))
            return deepcopy(record)

    def list_audit_events(self, limit: int = 200) -> list[AuditEvent]:
        with self._lock:
            rows = sorted(self._audits, key=lambda item: item.timestamp, reverse=True)
            return [deepcopy(item) for item in rows[:limit]]

    def append_audit_event(self, event: AuditEvent) -> None:
        with self._lock:
            self._audits.append(deepcopy(event))

    def save_storage_object(self, metadata: StorageObjectMetadata, event: AuditEvent) -> StorageObjectMetadata:
        with self._lock:
            if metadata.object_id in self._storage:
                raise ValueError("storage object already exists")
            self._storage[metadata.object_id] = deepcopy(metadata)
            self._audits.append(deepcopy(event))
            return deepcopy(metadata)

    def get_storage_objects(self, object_ids: list[str]) -> list[StorageObjectMetadata]:
        with self._lock:
            return [deepcopy(self._storage[item]) for item in object_ids if item in self._storage]

    def healthcheck(self) -> bool:
        return True


class Base(DeclarativeBase):
    pass


class InspectionRow(Base):
    __tablename__ = "inspections"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_subject: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)


class StorageObjectRow(Base):
    __tablename__ = "storage_objects"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    owner_subject: Mapped[str] = mapped_column(String(255), index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)


class AuditRow(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    actor_subject: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    target_id: Mapped[str] = mapped_column(String(128), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)


class SQLAlchemyRepository:
    kind = "postgresql"
    ephemeral = False

    def __init__(self, database_url: str) -> None:
        if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL")
        self.engine = create_engine(database_url, pool_pre_ping=True, pool_size=3, max_overflow=2, pool_recycle=300)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, class_=Session)

    @staticmethod
    def _audit_row(event: AuditEvent) -> AuditRow:
        return AuditRow(id=event.id, request_id=event.request_id, actor_subject=event.actor_subject, action=event.action, target_id=event.target_id, timestamp=event.timestamp, data=event.model_dump(mode="json"))

    def create_inspection(self, record: InspectionRecord, event: AuditEvent) -> InspectionRecord:
        with self.session_factory.begin() as session:
            session.add(InspectionRow(id=record.id, owner_subject=record.created_by, created_at=record.created_at, updated_at=record.updated_at, data=record.model_dump(mode="json")))
            session.add(self._audit_row(event))
        return record

    def get_inspection(self, inspection_id: str) -> InspectionRecord | None:
        with self.session_factory() as session:
            row = session.get(InspectionRow, inspection_id)
            return InspectionRecord.model_validate(row.data) if row else None

    def list_inspections(self, limit: int = 100) -> list[InspectionRecord]:
        with self.session_factory() as session:
            rows = session.scalars(select(InspectionRow).order_by(InspectionRow.updated_at.desc()).limit(limit)).all()
            return [InspectionRecord.model_validate(row.data) for row in rows]

    def save_inspection(self, record: InspectionRecord, event: AuditEvent) -> InspectionRecord:
        with self.session_factory.begin() as session:
            row = session.get(InspectionRow, record.id, with_for_update=True)
            if row is None:
                raise KeyError(record.id)
            row.updated_at = record.updated_at
            row.data = record.model_dump(mode="json")
            session.add(self._audit_row(event))
        return record

    def list_audit_events(self, limit: int = 200) -> list[AuditEvent]:
        with self.session_factory() as session:
            rows = session.scalars(select(AuditRow).order_by(AuditRow.timestamp.desc()).limit(limit)).all()
            return [AuditEvent.model_validate(row.data) for row in rows]

    def append_audit_event(self, event: AuditEvent) -> None:
        with self.session_factory.begin() as session:
            session.add(self._audit_row(event))

    def save_storage_object(self, metadata: StorageObjectMetadata, event: AuditEvent) -> StorageObjectMetadata:
        with self.session_factory.begin() as session:
            session.add(StorageObjectRow(id=metadata.object_id, owner_subject=metadata.uploaded_by, uploaded_at=metadata.uploaded_at, data=metadata.model_dump(mode="json")))
            session.add(self._audit_row(event))
        return metadata

    def get_storage_objects(self, object_ids: list[str]) -> list[StorageObjectMetadata]:
        if not object_ids:
            return []
        with self.session_factory() as session:
            rows = session.scalars(select(StorageObjectRow).where(StorageObjectRow.id.in_(object_ids))).all()
            by_id = {row.id: StorageObjectMetadata.model_validate(row.data) for row in rows}
            return [by_id[item] for item in object_ids if item in by_id]

    def healthcheck(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False


def create_repository(database_url: str | None, allow_memory_fallback: bool = True) -> Repository:
    if not database_url:
        return InMemoryRepository()
    try:
        return SQLAlchemyRepository(database_url)
    except Exception:
        if not allow_memory_fallback:
            raise
        return InMemoryRepository()
