#!/usr/bin/env python3
"""Temporal pipeline worker with workflow support.

Registers extract_events_activity as activity, and also defines
a simple workflow 'extract_single' that just calls the activity.
"""

import asyncio, uuid, json, os, sys
from datetime import datetime, timezone

from temporalio.client import Client
from temporalio.worker import Worker
from temporalio import workflow, activity

# Import the activity
sys.path.insert(0, '/home/u/src/eth/.gsd/worktrees/M001/.gsd/skills/pipeline-pipeline/scripts')
from eth_pipeline.activities import extract_events_activity

# Also check LLM schema
from eth_pipeline.llm import EVENT_EXTRACTION_SCHEMA
import jsonschema
test_obj = {'que_paso': 'test', 'espacio': 'test', 'tiempo': 'test', 'humanos': 'test', 'objetos': 'test', 'references': []}
errors = list(jsonschema.iter_errors(test_obj, EVENT_EXTRACTION_SCHEMA))
if errors:
    print(f"❌ LLM schema validation FAIL: {errors[:3]}")
    sys.exit(1)
else:
    print(f"✅ LLM schema validation PASS")
print(f"✅ extract_events_activity import OK")

# Define a simple workflow that wraps the activity
@workflow.defn(name="extract_single")
class ExtractSingle:
    @workflow.run
    async def run(self, text: str) -> dict:
        result = await extract_events_activity(text)
        return result

async def main():
    # Connect to Temporal server
    client = await Client.connect("localhost:7233", namespace="eth")
    print(f"✅ Connected to Temporal server (ns=eth)")

    # Register the worker with activity + workflow
    worker = Worker(
        client,
        task_queue="pipeline-events",
        activities=[extract_events_activity],
        workflows=[ExtractSingle],
    )
    print(f"✅ Worker registered for 'pipeline-events' (act+workflow)")

    await worker.run()
    print(f"✅ Worker started")

if __name__ == "__main__":
    asyncio.run(main())
