"""SQLAlchemy ORM models for eth-pipeline."""

from __future__ import annotations

import logging

from .v7_event import Base

logger = logging.getLogger(__name__)

__all__ = ["Base"]
