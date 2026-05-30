"""
Temporal Worker entrypoint for the eth-pipeline.

Connects to Temporal Server (localhost:7233, namespace ``default``),
registers the ``event-extraction`` task queue with the workflow and
activity definitions, and runs until a graceful shutdown signal arrives.
"""

from __future__ import annotations

import asyncio
import logging
import signal

import temporalio.client
from temporalio.worker import Worker

from eth_pipeline import activities, workflows

logger = logging.getLogger(__name__)

TARGET_HOST = "localhost:7233"
NAMESPACE = "default"
TASK_QUEUE = "event-extraction"


async def main() -> None:
    """Connect to Temporal Server and run the worker indefinitely."""
    client = await temporalio.client.Client.connect(
        TARGET_HOST,
        namespace=NAMESPACE,
    )

    worker = Worker(
        client=client,
        task_queue=TASK_QUEUE,
        workflows=[workflows.DocumentProcessingWorkflow],
        activities=[
            activities.extract_events_activity,
            activities.update_document_status_activity,
            activities.store_extraction_results_activity,
            activities.resolve_entities_activity,
        ],
    )

    logger.info(
        "Worker starting — target=%s namespace=%s task_queue=%s",
        TARGET_HOST,
        NAMESPACE,
        TASK_QUEUE,
    )
    print(
        f"Worker connected to {TARGET_HOST} (namespace={NAMESPACE}, "
        f"task_queue={TASK_QUEUE})"
    )

    # Graceful shutdown on SIGINT / SIGTERM.
    shutdown_event = asyncio.Event()

    def _on_signal() -> None:
        logger.info("Shutdown signal received, stopping worker…")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal)

    # Run the worker concurrently with the shutdown watcher.
    worker_task = asyncio.create_task(worker.run())

    await shutdown_event.wait()
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    logger.info("Worker stopped cleanly")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
