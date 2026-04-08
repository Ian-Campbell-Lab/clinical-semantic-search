# Porting Guide

This guide walks through adapting clinical-semantic-search for your
institution.  The system was developed at a large pediatric health
system on Google Cloud Platform, but the core logic (chunking,
embedding, formatting) is portable.  You need to replace the service
layer and configure the ETL pipeline for your EHR.

## Prerequisites

Before starting, you need:

1. **An embedding model** -- any HuggingFace-compatible model that
   produces dense vectors.  The reference deployment uses
   Qwen3-Embedding-0.6B (1024-dim, instruction-tuned).  Other options
   include e5-large-v2, GTE, or BGE models.

2. **A vector database** -- to store and search embedding vectors.
   The reference uses Vertex AI Vector Search, but any database
   supporting filtered approximate nearest neighbor search will work
   (pgvector, Qdrant, Weaviate, Milvus, Pinecone).

3. **A metadata store** -- to store note text and metadata for retrieval
   after vector search returns matching IDs.  The reference uses Cloud
   BigTable, but PostgreSQL, MongoDB, or any key-value store works.

4. **An EHR data extract** -- clinical notes with metadata (note type,
   author, department, specialty, dates).

## Step 1: Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

If you're not using GCP, you only need `EMBEDDING_MODEL_PATH`.  The
other variables are for the GCP reference services and can be ignored
if you replace the service modules.

## Step 2: EHR Data Model

The key file is `src/clinical_semantic_search/etl/ehr_preprocessing.py`.
The `MetadataTransformer.col_mapper` dictionary maps your EHR's column
names to the internal schema:

| Internal Column | Description | Epic Column (Reference) |
|---|---|---|
| `note_id` | Unique note identifier | `note_id` |
| `pat_mrn_id` | Patient MRN | `pat_mrn_id` |
| `pat_first_name` | Patient first name | `pat_first_name` |
| `pat_last_name` | Patient last name | `pat_last_name` |
| `birth_date` | Date of birth | `birth_date` |
| `sex` | Patient sex | `sex` |
| `note_text` | Full note text | `note_text` |
| `note_type` | Primary note type | `note_type` |
| `note_type_noadd` | Note type without addenda | `note_type_noadd` |
| `ip_note_type` | Inpatient note type | `ip_note_type` |
| `enc_type` | Encounter type | `enc_type` |
| `dept_name` | Department name | `dept_name` |
| `author_prov_name` | Author name | `author_prov_name` |
| `prov_type` | Provider type | `prov_type` |
| `author_service` | Clinical service/specialty | `author_service` |
| `date_of_servic_dttm` | Service date (preferred) | `date_of_servic_dttm` |
| `create_instant_dttm` | Note creation time | `create_instant_dttm` |
| `lst_filed_inst_dttm` | Last filed time | `lst_filed_inst_dttm` |

To adapt for your EHR:
1. Update the **keys** (left side) of `col_mapper` to match your column names
2. Update `datetime_data_dict` with your date format strings
3. If your EHR has a single note type column (not three), simplify `_format_note_category()`

## Step 3: Replace Vector Search

The vector search service is in `src/clinical_semantic_search/services/vector_search.py`.

The key function to replace is `find_neighbors()`.  It must accept:
- `query_embedding` (list of floats)
- `num_neighbors` (int)
- Optional filter parameters

And return: `list[tuple[str, float]]` -- (chunk_id, distance) pairs.

### Example: pgvector (PostgreSQL)

```python
import psycopg2

def find_neighbors(query_embedding, num_neighbors=20, mrn_filter=None, **kwargs):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    sql = """
        SELECT chunk_id, embedding <=> %s::vector AS distance
        FROM note_chunks
        WHERE 1=1
    """
    params = [query_embedding]

    if mrn_filter:
        sql += " AND mrn = ANY(%s)"
        params.append(mrn_filter)

    sql += " ORDER BY distance LIMIT %s"
    params.append(num_neighbors)

    cur.execute(sql, params)
    results = [(row[0], row[1]) for row in cur.fetchall()]
    conn.close()
    return results
```

### Example: Qdrant

```python
from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333)

def find_neighbors(query_embedding, num_neighbors=20, mrn_filter=None, **kwargs):
    filter_condition = None
    if mrn_filter:
        from qdrant_client.models import Filter, FieldCondition, MatchAny
        filter_condition = Filter(
            must=[FieldCondition(key="mrn", match=MatchAny(any=mrn_filter))]
        )

    results = client.search(
        collection_name="clinical_notes",
        query_vector=query_embedding,
        limit=num_neighbors,
        query_filter=filter_condition,
    )
    return [(hit.id, hit.score) for hit in results]
```

## Step 4: Replace Metadata Store

The metadata store is in `src/clinical_semantic_search/services/metadata_store.py`.

The key function is `get_notes(note_ids)`.  It must accept a list of
note ID strings and return `list[dict]` where each dict has at minimum:
- `note_id` (str)
- `note_text` (str)
- `chunk_indices` (list of [start, end] tuples)

Plus any metadata columns you want to display (author, department, etc.).

### Example: PostgreSQL

```python
import psycopg2
import json

def get_notes(note_ids):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute(
        """SELECT note_id, note_text, chunk_indices, mrn, note_category,
                  author_name, department, specialty, creation_time
           FROM notes WHERE note_id = ANY(%s)""",
        [note_ids]
    )
    columns = [desc[0] for desc in cur.description]
    results = []
    for row in cur.fetchall():
        d = dict(zip(columns, row))
        d["chunk_indices"] = json.loads(d["chunk_indices"])
        results.append(d)
    conn.close()

    # Reorder to match input
    lookup = {d["note_id"]: d for d in results}
    return [lookup[nid] for nid in note_ids if nid in lookup]
```

## Step 5: Replace Access Control

The access control module (`services/access_control.py`) implements a
per-project note allowlist.  This is specific to environments where
different research projects have access to different patient populations.

Options for your institution:
- **No filtering needed**: Remove the access control check from the webapp
- **Role-based**: Check the user's role against note sensitivity flags
- **Project-based**: Use the reference implementation pattern with your
  own allowlist source

## Step 6: Index Building Pipeline

The end-to-end pipeline to build the vector index:

```
1. Extract notes from EHR
   └─> etl/ehr_preprocessing.py (MetadataTransformer)

2. Chunk notes into segments
   └─> core/chunking.py (parallel_split_notes)

3. Compute embeddings
   └─> etl/parallel_embedding.py (TPU) or core/embedding.py (CPU)

4. Export to vector index format
   └─> etl/vector_export.py (create_point, export_points_jsonl)

5. Load into vector database
   └─> (database-specific, see docs/vector-index-setup.md)
```

For CPU-based embedding (no TPU), you can use a simple loop:

```python
from clinical_semantic_search.core.embedding import load_embedding_model, embed_query

model, tokenizer = load_embedding_model("/path/to/model")
for chunk in chunks:
    embedding = embed_query(chunk, model, tokenizer, use_instruction=False)
```

## Step 7: Deploying the Web App

The webapp can be deployed as a container:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e ".[gcp,webapp]"
EXPOSE 8000
CMD ["clinical-search", \
     "--bt_project_id", "$BT_PROJECT", \
     "--bt_instance", "$BT_INSTANCE", \
     "--bt_table_id", "notes", \
     "--endpoint_name", "$ENDPOINT", \
     "--ip_address", "$PSC_IP", \
     "--deployed_index", "$INDEX_ID", \
     "--embedding_model_path", "/models/embedding"]
```

## Step 8: Running Benchmarks

After deployment, validate with the benchmark tools:

```bash
# Latency decomposition (requires live infrastructure)
python benchmarks/latency_decomposition.py --n-queries 200

# Index recall (requires brute-force reference JSONL)
python benchmarks/index_recall.py --jsonl-path reference.jsonl

# MCQA evaluation (requires benchmark questions + LLM)
# See benchmarks/mcqa_evaluation.py for the prompt construction utilities
```
