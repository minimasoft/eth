"""
eth-pipeline: FastAPI application for document ingestion and entity queries.

The application has been refactored into a package (``api/``).
This file is a thin re-export shim — Python will prefer the
``api/`` package directory over this file for imports.

See ``api/__init__.py`` for the application constructor and
``api/routes/`` for individual endpoint modules.
"""

from eth_pipeline.api import (  # noqa: E402, F401
    APIInfo,
    DocumentCreated,
    DocumentDeleted,
    DocumentInput,
    DocumentListItem,
    DocumentListResponse,
    DocumentStatus,
    DocumentUploadCreated,
    HealthResponse,
    ProcessingLogListItem,
    ProcessingLogListResponse,
    app,
)
