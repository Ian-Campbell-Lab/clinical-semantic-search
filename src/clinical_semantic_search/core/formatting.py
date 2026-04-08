"""
Note metadata formatting for search result display.

Converts raw note dictionaries (as returned by the metadata store) into
human-readable text blocks with structured headers.  This module has no
cloud dependencies and operates purely on ``list[dict]``.
"""

from typing import List, Optional


def format_metadata(
    notes: list[dict],
    include_patient_metadata: bool = True,
) -> list[str]:
    """Format note metadata into readable text blocks.

    Each note is rendered as a markdown-like block with headers for
    note category, encounter type, specialty, department, author, dates,
    age, and the note text itself.

    Parameters
    ----------
    notes : list[dict]
        Note dictionaries as returned by the metadata store.  Expected
        keys include ``note_id``, ``note_category``, ``encounter_type``,
        ``specialty``, ``department``, ``author_name``, ``author_type``,
        ``creation_time``, ``filed_time``, ``age``, ``note_text``, and
        optionally ``first_name``, ``middle_name``, ``last_name``,
        ``mrn``, ``birth_date``.
    include_patient_metadata : bool
        If True, prepend a patient metadata header using fields from the
        first note in the list (name, MRN, date of birth).

    Returns
    -------
    list[str] -- one formatted string per note.
    """
    results: List[str] = []

    if include_patient_metadata and notes:
        first_note = notes[0]
        keys = first_note.keys()
        pat_parts: List[str] = []

        if any(k in keys for k in ("first_name", "middle_name", "last_name")):
            name_elements = []
            for k in ("first_name", "middle_name", "last_name"):
                if k in keys and first_note[k]:
                    name_elements.append(first_note[k])
            if name_elements:
                pat_parts.append(f"##Patient Name\n{' '.join(name_elements)}")

        if "mrn" in keys:
            pat_parts.append(f"##Medical Record Number\n{first_note['mrn']}")
        if "birth_date" in keys:
            pat_parts.append(f"##Date of Birth\n{first_note['birth_date']}")

        results.append("#Patient Metadata\n" + "\n".join(pat_parts) + "\n\n")

    _NOTE_FIELDS = [
        ("note_id", "Note ID"),
        ("note_category", "Note Category"),
        ("encounter_type", "Encounter Type"),
        ("specialty", "Specialty"),
        ("department", "Department"),
        ("author_name", "Author"),
        ("author_type", "Author Role"),
        ("creation_time", "Note Creation Time"),
        ("filed_time", "Note File Time"),
        ("age", "Age"),
    ]

    for note in notes:
        keys = note.keys()
        parts: List[str] = []
        for field, label in _NOTE_FIELDS:
            if field in keys and note[field]:
                parts.append(f"##{label}\n{note[field]}")
        if "note_text" in keys and note["note_text"]:
            parts.append(f"##Note Text\n{note['note_text']}")
            results.append("#Note Metadata\n" + "\n".join(parts) + "\n\n")

    return results
