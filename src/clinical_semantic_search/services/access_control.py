"""
Access control service -- reference implementation using Google BigQuery
allowlists.

This module implements a per-project note allowlist pattern:

1. At startup, query the project's ``note_info`` table to get all note IDs
   the current project is authorized to access.
2. Write them to a sorted memory-mapped file on disk.
3. At query time, use binary search to check whether each returned note ID
   is in the allowlist before returning results to the user.

This design avoids loading millions of note IDs into Python memory and
provides O(log n) lookup per note.

PORTING NOTE: Replace this module with your institution's access control
mechanism.  The key contract is a function that takes a list of note IDs
and returns a list of booleans indicating which ones the current user is
authorized to view.
"""

import getpass
import logging
import os
from typing import Optional

import google.auth
import numpy as np
import pyarrow.compute as pc
from google.cloud import bigquery, bigquery_storage

logger = logging.getLogger(__name__)


def get_user_project() -> tuple[str, str]:
    """Return (username, gcp_project) for the current session."""
    user = os.getenv("USER") or os.getenv("LOGNAME") or getpass.getuser()
    _, project = google.auth.default()
    return user, project


def build_uint64_file(project: str, out_path: str) -> int:
    """Query the project's note_info table and write sorted note IDs to disk.

    Parameters
    ----------
    project : str
        GCP project ID containing the note_info table.
    out_path : str
        Filesystem path for the output binary file.

    Returns
    -------
    int -- the number of note IDs written.
    """
    bq_client = bigquery.Client(project=project)
    bqs_client = bigquery_storage.BigQueryReadClient()

    # REPLACE THIS SQL with your institution's note access query.
    # The query should return a single column of integer note IDs that
    # the current project is authorized to access.
    # Example for an Epic-based data warehouse:
    sql = """
        SELECT DISTINCT SAFE_CAST(epic_note_id AS INT64) AS id
        FROM `YOUR_DATASET.note_info`
        WHERE epic_note_id IS NOT NULL
        ORDER BY id
    """
    job = bq_client.query(sql, location="US")
    rows = job.result()

    count = 0
    with open(out_path, "wb") as f:
        for batch in rows.to_arrow_iterable(bqstorage_client=bqs_client):
            arr = batch.column(0)
            arr_u64 = pc.cast(arr, "uint64")
            chunk = np.asarray(arr_u64)
            chunk.tofile(f)
            count += chunk.size
    return count


def open_allowlist_memmap(path: str, n: int) -> np.memmap:
    """Memory-map the sorted note ID file for fast lookup."""
    return np.memmap(path, dtype=np.uint64, mode="r", shape=(n,))


def build_block_index(mm: np.memmap, block_size: int = 8192) -> np.ndarray:
    """Build a sparse block index over the memory-mapped array for fast search."""
    return np.array(mm[::block_size], dtype=np.uint64)


def contains_note(
    mm: np.memmap,
    idx: np.ndarray,
    probes: list[str],
    block_size: int = 8192,
) -> list[bool]:
    """Test which note IDs are in the allowlist using binary search.

    Parameters
    ----------
    mm : np.memmap
        Memory-mapped sorted array of allowed note IDs.
    idx : np.ndarray
        Block index built by ``build_block_index()``.
    probes : list[str]
        Note IDs to check.
    block_size : int
        Block size used when building the index.

    Returns
    -------
    list[bool] -- True for each probe that is in the allowlist.
    """
    p = np.fromiter((int(x) for x in probes), dtype=np.uint64)
    b = np.searchsorted(idx, p, side="right") - 1
    b = np.clip(b, 0, idx.size - 1)
    out = np.zeros(p.size, dtype=bool)
    for i in range(p.size):
        block = int(b[i])
        lo = block * block_size
        hi = min(lo + block_size, mm.size)
        window = mm[lo:hi]
        j = np.searchsorted(window, p[i])
        out[i] = j < window.size and window[j] == p[i]
    return out.tolist()


def build_note_index(project: str) -> tuple[np.memmap, np.ndarray]:
    """Build the complete note allowlist index.

    Queries the project's note_info table, writes sorted IDs to a temp
    file, and returns a (memmap, block_index) tuple for use with
    ``contains_note()``.
    """
    out_file = "/tmp/project_note_ids.np"
    count = build_uint64_file(project, out_file)
    mem_map = open_allowlist_memmap(out_file, count)
    mm_index = build_block_index(mem_map)
    return mem_map, mm_index
