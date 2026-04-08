"""
Vector export utilities for building index data files.

Converts embedded note chunks into the JSON format expected by
Vertex AI Vector Search for batch index creation.

PORTING NOTE: For other vector databases, modify ``create_point()``
to match your database's expected import format.
"""

import json
from typing import Optional

import pandas as pd


def create_point(row: pd.Series) -> dict:
    """Convert a DataFrame row into a Vertex AI Vector Search point.

    Parameters
    ----------
    row : pd.Series
        Must contain ``vector_id``, ``embedding``, ``mrn``, and metadata
        columns (``note_category``, ``encounter_type``, ``sex``,
        ``department``, ``specialty``, ``author_type``, ``author_name``,
        ``date``, ``utc_epoch_sec``).

    Returns
    -------
    dict with keys ``id``, ``embedding``, ``restricts`` (string filters),
    ``numeric_restricts`` (date filters), and ``crowding_tag`` (MRN).
    """
    restricts = []
    string_fields = [
        ("mrn", row["mrn"]),
        ("note_category", row["note_category"]),
        ("encounter_type", row["encounter_type"]),
        ("sex", row["sex"]),
        ("department", row["department"]),
        ("specialty", row["specialty"]),
        ("author_type", row["author_type"]),
        ("author_name", row["author_name"]),
    ]
    for namespace, value in string_fields:
        if pd.notnull(value):
            restricts.append({"namespace": namespace, "allow": [value]})

    point = {
        "id": row["vector_id"],
        "embedding": row["embedding"],
        "restricts": restricts,
        "numeric_restricts": [
            {"namespace": "year", "value_int": int(row["date"].split("/")[-1])},
            {"namespace": "utc_epoch_sec", "value_int": int(row["utc_epoch_sec"])},
        ],
        "crowding_tag": row["mrn"],
    }
    return point


def export_points_jsonl(df: pd.DataFrame, output_path: str) -> int:
    """Export a DataFrame of embedded chunks to a JSONL file.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain all columns expected by ``create_point()``.
    output_path : str
        Path to write the JSONL file.

    Returns
    -------
    int -- number of points written.
    """
    count = 0
    with open(output_path, "w") as f:
        for _, row in df.iterrows():
            point = create_point(row)
            f.write(json.dumps(point) + "\n")
            count += 1
    return count
