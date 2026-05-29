#!/usr/bin/env python3
"""Entrypoint for the eth-pipeline FastAPI application.

Run with::

    uv run python scripts/run_api.py

The server listens on all interfaces at port 8001.
"""

from __future__ import annotations

import logging
import sys

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

if __name__ == "__main__":
    uvicorn.run(
        "eth_pipeline.api:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
    )
