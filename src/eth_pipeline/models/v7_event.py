"""SQLAlchemy ORM models for the v7.0 event-centric schema.

These models mirror the DDL from migration ``0001_v7_foundation.py`` and
are used primarily for Alembic ``--autogenerate`` support and future
ORM-based queries.
"""

from __future__ import annotations

import logging

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, relationship

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class EventV2(Base):
    __tablename__ = "event_v2"

    id = Column(String, primary_key=True)
    document_id = Column(String, ForeignKey("document.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    time_start = Column(DateTime(timezone=True), nullable=True)
    time_end = Column(DateTime(timezone=True), nullable=True)
    time_precision = Column(String, nullable=True)
    extraction_confidence = Column(Float, default=1.0)
    provider_id = Column(String, nullable=True)
    model = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    locations = relationship("EventLocation", back_populates="event", cascade="all, delete-orphan")
    participants = relationship("EventParticipantV2", back_populates="event", cascade="all, delete-orphan")
    documents = relationship("EventDocument", back_populates="event", cascade="all, delete-orphan")
    refs = relationship("EventRef", back_populates="event", cascade="all, delete-orphan")


class EventLocation(Base):
    __tablename__ = "event_location"

    id = Column(String, primary_key=True)
    event_id = Column(String, ForeignKey("event_v2.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    location_type = Column(String, nullable=True)
    geom = Column(String, nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    event = relationship("EventV2", back_populates="locations")


class EventParticipantV2(Base):
    __tablename__ = "event_participant_v2"

    id = Column(String, primary_key=True)
    event_id = Column(String, ForeignKey("event_v2.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, default="")
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    event = relationship("EventV2", back_populates="participants")


class EventDocument(Base):
    __tablename__ = "event_document"

    id = Column(String, primary_key=True)
    event_id = Column(String, ForeignKey("event_v2.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(String, ForeignKey("document.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    event = relationship("EventV2", back_populates="documents")


class EventRef(Base):
    __tablename__ = "event_ref"

    id = Column(String, primary_key=True)
    event_id = Column(String, ForeignKey("event_v2.id", ondelete="CASCADE"), nullable=False)
    reference_type = Column(String, nullable=False)
    verbatim_text = Column(Text, nullable=False)
    span_start = Column(Integer, nullable=False)
    span_end = Column(Integer, nullable=False)
    chunk_index = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    event = relationship("EventV2", back_populates="refs")
