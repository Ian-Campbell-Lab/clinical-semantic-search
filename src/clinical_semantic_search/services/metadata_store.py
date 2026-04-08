"""
Metadata store service -- reference implementation using Google Cloud BigTable.

This module handles:
- Constructing salt-based row keys to avoid hotspotting
- Fetching full note text and metadata by note ID
- Fetching MRNs for a list of note IDs (lightweight lookup)

PORTING NOTE: Replace this module with your metadata store client
(e.g., PostgreSQL, MongoDB).  The key contracts are:

- ``get_notes(note_ids)`` returns ``list[dict]`` where each dict has at
  minimum ``note_id``, ``note_text``, and ``chunk_indices``.
- ``get_mrns(note_ids)`` returns ``list[dict]`` with ``note_id`` and ``mrn``.
- ``build_row_key(note_id)`` is specific to BigTable and can be dropped.
"""

import json
import logging
from typing import Optional

from google.cloud import bigtable
from google.cloud.bigtable import row_filters
from google.cloud.bigtable.row_set import RowSet

from clinical_semantic_search.config import get_settings

logger = logging.getLogger(__name__)

# Cached client singleton
_bigtable_client = None
_bigtable_table = None


def build_row_key(note_id: str, num_salts: int = 100, width: int = 10) -> bytes:
    """Construct a ``<salt>#<reversed_id>`` row key for BigTable.

    The salt distributes writes across tablet servers to avoid hotspotting
    on sequential note IDs.  The reversed ID ensures that recently written
    notes are spread across regions.
    """
    note_id_int = int(note_id)
    salt = f"{note_id_int % num_salts:02d}"
    reversed_part = str(note_id_int).zfill(width)[::-1]
    return f"{salt}#{reversed_part}".encode("ascii")


def _get_table():
    """Return a cached BigTable table object."""
    global _bigtable_client, _bigtable_table
    if _bigtable_client is None:
        settings = get_settings()
        _bigtable_client = bigtable.Client(project=settings.metadata_project, admin=True)
        instance = _bigtable_client.instance(settings.bigtable_instance)
        _bigtable_table = instance.table(settings.bigtable_table)
    return _bigtable_table


def get_notes(note_ids: list[str]) -> list[dict]:
    """Fetch full note text and metadata from BigTable.

    Parameters
    ----------
    note_ids : list[str]
        Epic note IDs as strings.

    Returns
    -------
    list[dict] with keys including ``note_id``, ``note_text``,
    ``chunk_indices`` (list of (start, end) tuples), and all stored
    metadata columns.  Results are returned in the same order as the
    input ``note_ids``.
    """
    table = _get_table()
    row_set = RowSet()
    for note_id in note_ids:
        row_set.add_row_key(build_row_key(note_id))

    rows = table.read_rows(row_set=row_set)
    decoded = [
        {
            col.decode(): cells[0].value.decode()
            for cf, cols in row.cells.items()
            for col, cells in cols.items()
        }
        for row in rows
    ]

    # Parse chunk_indices from JSON string to list of tuples
    for d in decoded:
        if "chunk_indices" in d:
            d["chunk_indices"] = [tuple(t) for t in json.loads(d["chunk_indices"])]

    # Reorder to match input order
    lookup = {d["note_id"]: d for d in decoded}
    return [lookup[n] for n in note_ids if n in lookup]


def get_mrns(note_ids: list[str]) -> list[dict]:
    """Fetch only note_id and MRN from BigTable (lightweight lookup).

    Parameters
    ----------
    note_ids : list[str]
        Epic note IDs as strings.

    Returns
    -------
    list[dict] with keys ``note_id`` and ``mrn``, in input order.
    """
    table = _get_table()
    row_set = RowSet()
    filter_ = row_filters.RowFilterChain(
        filters=[
            row_filters.FamilyNameRegexFilter("meta"),
            row_filters.ColumnQualifierRegexFilter(b"^(note_id|mrn)$"),
            row_filters.CellsColumnLimitFilter(1),
        ]
    )
    for note_id in note_ids:
        row_set.add_row_key(build_row_key(note_id))

    rows = table.read_rows(row_set=row_set, filter_=filter_)
    decoded = [
        {
            col.decode(): cells[0].value.decode()
            for cf, cols in row.cells.items()
            for col, cells in cols.items()
        }
        for row in rows
    ]

    lookup = {d["note_id"]: d for d in decoded}
    return [lookup[n] for n in note_ids if n in lookup]
