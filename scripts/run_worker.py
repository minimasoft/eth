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
    extract_events_activity,
    store_extraction_results_activity,
    update_document_status_activity,
)
from eth_pipeline.workflows import DocumentProcessingWorkflow


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
        workflows=[DocumentProcessingWorkflow],
        activities=[
            extract_events_activity,
            store_extraction_results_activity,
            update_document_status_activity,
        ],
    )
    print("✅ Worker registered for task_queue 'event-extraction'")
    print("   Workflow: DocumentProcessingWorkflow")
    print("   Activities: extract_events_activity, store_extraction_results_activity, update_document_status_activity")

    # Start the worker (runs until shutdown)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
