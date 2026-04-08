# Filter Data

Place your institution's filter JSON files in this directory.
The webapp loads these at startup to populate filter dropdowns.

Expected files (all optional):

- `note_categories.json` -- list of note category strings
- `encounter_types.json` -- list of encounter type strings
- `department_names.json` -- list of department name strings
- `specialties.json` -- list of specialty strings
- `author_types.json` -- list of author type strings (e.g., "Physician", "Nurse")
- `author_names.json` -- list of author name strings

Each file should be a JSON array of strings, e.g.:

```json
["Progress Notes", "Discharge Summary", "H&P", "Consult Note"]
```

These values must match the metadata stored in your vector index
restricts (the values used when building index points in
`etl/vector_export.py`).
