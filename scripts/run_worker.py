#!/usr/bin/env python3
"""Temporal pipeline worker — dispatches eth document LLM extraction pipeline.

Usage:
    uv run python3 scripts/run_worker.py
"""

from __future__ import annotations

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

# Import the workflow and activities from the pipeline package
from eth_pipeline.activities import (
    chunk_document_activity,
    extract_events_v7_activity,
    extract_text_activity,
    get_document_chunks_activity,
    get_document_metadata_activity,
    get_document_text_activity,
    get_prior_events_activity,
    resolve_references_v7_activity,
    store_events_v7_activity,
    update_document_status_activity,
)
from eth_pipeline.workflows import (
    DocumentProcessingV7Workflow,
)


async def main():
    # Connect to Temporal server
    temporal_url = os.environ.get("TEMPORAL_URL", "localhost:7233")
    client = await Client.connect(
        temporal_url,
        namespace="default",
        tls=None,  # Local dev — no TLS
    )
    print("✅ Connected to Temporal server (ns=default)")

    # Register the worker with the workflow and all activities
    worker = Worker(
        client,
        task_queue="event-extraction",
        workflows=[DocumentProcessingV7Workflow],
        activities=[
            chunk_document_activity,
            extract_events_v7_activity,
            extract_text_activity,
            get_document_chunks_activity,
            get_document_metadata_activity,
            get_document_text_activity,
            get_prior_events_activity,
            resolve_references_v7_activity,
            store_events_v7_activity,
            update_document_status_activity,
        ],
    )
    print("✅ Worker registered for task_queue 'event-extraction'")
    print("   Activities: chunk_document_activity, extract_events_v7_activity, extract_text_activity, get_document_chunks_activity, get_document_metadata_activity, get_document_text_activity, get_prior_events_activity, resolve_references_v7_activity, store_events_v7_activity, update_document_status_activity")

    # Start the worker (runs until shutdown)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
