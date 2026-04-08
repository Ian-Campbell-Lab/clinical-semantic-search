# Metadata Store Schema

The metadata store holds clinical note text and associated metadata,
keyed by note ID.  The reference implementation uses Cloud BigTable,
but any key-value or relational store that supports batch reads will work.

## BigTable Schema (Reference)

### Row Key

```
<salt>#<reversed_note_id>
```

- **salt**: `note_id % 100`, zero-padded to 2 digits.  Distributes
  writes across tablet servers to avoid hotspotting.
- **reversed_note_id**: The note ID reversed and zero-padded to 10
  digits.  Prevents sequential write hotspots.

Example: note ID `1234567` → row key `67#7654321000`

### Column Family: `meta`

| Column | Type | Description |
|---|---|---|
| `note_id` | string | Original EHR note identifier |
| `mrn` | string | Patient medical record number |
| `first_name` | string | Patient first name |
| `middle_name` | string | Patient middle name |
| `last_name` | string | Patient last name |
| `birth_date` | string | Date of birth |
| `sex` | string | Patient sex |
| `pat_id` | string | Internal patient identifier |
| `note_text` | string | Full note text |
| `chunk_indices` | JSON string | Array of [start, end] character offsets |
| `note_category` | string | Note type (e.g., "Progress Notes") |
| `encounter_type` | string | Encounter type (e.g., "Office Visit") |
| `department` | string | Department name |
| `specialty` | string | Clinical specialty |
| `author_name` | string | Note author |
| `author_type` | string | Author role (e.g., "Physician") |
| `creation_time` | string | Note creation timestamp |
| `filed_time` | string | Note filed timestamp |
| `age` | string | Patient age at time of note |
| `coalesced_date` | string | Best available note date |

### chunk_indices Format

```json
[[0, 450], [400, 850], [800, 1200]]
```

Each entry is a `[start_char, end_char]` pair corresponding to one
embedding vector in the index.  The vector ID format is
`<note_id>_<chunk_index>`, so vector `1234567_2` corresponds to
characters 800-1200 of note 1234567.

## Relational Alternative

For PostgreSQL or similar:

```sql
CREATE TABLE notes (
    note_id        TEXT PRIMARY KEY,
    mrn            TEXT NOT NULL,
    note_text      TEXT NOT NULL,
    chunk_indices  JSONB NOT NULL,
    note_category  TEXT,
    encounter_type TEXT,
    department     TEXT,
    specialty      TEXT,
    author_name    TEXT,
    author_type    TEXT,
    creation_time  TIMESTAMP,
    filed_time     TIMESTAMP,
    birth_date     DATE,
    age            TEXT,
    first_name     TEXT,
    last_name      TEXT
);

CREATE INDEX idx_notes_mrn ON notes(mrn);
```
