"""
eth-pipeline: FastAPI application for document ingestion and entity queries.

The application has been refactored into a package (``api/``).
This file is a thin re-export shim — Python will prefer the
``api/`` package directory over this file for imports.

See ``api/__init__.py`` for the application constructor and
``api/routes/`` for individual endpoint modules.
"""

# Re-export all public names from the api/ package.
# Python resolves ``eth_pipeline.api`` to the package directory,
# so this file is documentation only.  The actual imports in other
# modules (e.g. ``from eth_pipeline.api import app``) resolve to
# ``api/__init__.py``.
from eth_pipeline.api import (  # noqa: E402, F401
    APIInfo,
    DocumentCreated,
    DocumentDeleted,
    DocumentInput,
    DocumentListItem,
    DocumentListResponse,
    DocumentStatus,
    DocumentUploadCreated,
    EntityListItem,
    EntityListResponse,
    EventsCleared,
    GraphQLRequest,
    HealthResponse,
    MergeRequest,
    MergeResponse,
    ProcessingLogListItem,
    ProcessingLogListResponse,
    ReferenceListItem,
    ReferenceListResponse,
    SplitPartition,
    SplitRequest,
    SplitResponse,
    _parse_count,
    app,
)
