"""
Audit logging service -- reference implementation using structlog.

Logs every search query with the user identity, search parameters, and
the note IDs returned (but never the note text).  In the reference
deployment, structlog output is captured by Google Cloud Logging, but the
pattern works with any log aggregator.

PORTING NOTE: This module is already portable.  Replace structlog with
your institution's logging framework if needed, or keep it as-is and
route structlog output to your log aggregator.
"""

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor

import structlog

_executor = ThreadPoolExecutor(max_workers=4)

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()


def _save_user_logs_sync(
    query_input: dict,
    query_output: list[dict],
    user: str,
    project: str,
):
    """Synchronous log writer.

    Logs the query parameters and the MRN/note_id pairs from results.
    Note text is never logged.
    """
    results = [
        {"mrn": c.get("mrn"), "note_id": c.get("note_id")}
        for c in query_output
        if c.get("mrn") or c.get("note_id")
    ]

    logger.info(
        "query returned",
        tag="clinical_semantic_search",
        user=user,
        project=project,
        **query_input,
        results=results,
        request_id=str(uuid.uuid4()),
    )


async def save_user_logs_async(
    query_input: dict,
    query_output: list[dict],
    user: str,
    project: str,
):
    """Async wrapper that offloads logging to a thread pool."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        _executor,
        _save_user_logs_sync,
        query_input,
        query_output,
        user,
        project,
    )
