# Vector Index Setup

This document describes how to create and deploy a vector search index
using the reference GCP implementation (Vertex AI Vector Search).

## Index Configuration

The reference deployment uses a **storage-optimized** index, which
stores vectors on SSD rather than in memory.  This significantly
reduces cost at the expense of slightly higher query latency (~240ms
vs ~50ms for in-memory).

### Key Parameters

| Parameter | Value | Notes |
|---|---|---|
| Dimensions | 1024 | Must match embedding model output |
| Distance Measure | DOT_PRODUCT_DISTANCE | For L2-normalized vectors, equivalent to cosine |
| Shard Size | SHARD_SIZE_LARGE | For indices > 100M vectors |
| Algorithm | SCANN + SOAR | Tree-AH with residual quantization |
| Leaf Node Count | 5000 | Tuned for index size |

### Creating the Index

First, create a metadata JSON file:

```json
{
  "contentsDeltaUri": "gs://YOUR_BUCKET/data/",
  "config": {
    "dimensions": 1024,
    "approximateNeighborsCount": 2000,
    "distanceMeasureType": "DOT_PRODUCT_DISTANCE",
    "shardSize": "SHARD_SIZE_SO_DYNAMIC"
  }
}
```

Note: `SHARD_SIZE_SO_DYNAMIC` is specific to storage-optimized indexes.
For in-memory indexes, use `SHARD_SIZE_LARGE` instead.

Then create the index:

```bash
gcloud ai indexes create \
    --metadata-file=index-config.json \
    --display-name="clinical-notes-storage-optimized" \
    --index-update-method=batch-update \
    --region=us-east4 \
    --project=YOUR_PROJECT
```

### Deploying the Index

The deployment step specifies the storage-optimized tier via the REST
API (the `gcloud` CLI does not expose the `deploymentTier` parameter
directly):

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://REGION-aiplatform.googleapis.com/v1/INDEX_ENDPOINT_RESOURCE_NAME:deployIndex" \
  -d '{
    "deployedIndex": {
      "id": "YOUR_DEPLOYED_INDEX_ID",
      "index": "INDEX_RESOURCE_NAME",
      "displayName": "clinical-notes-storage-optimized",
      "deploymentTier": "STORAGE"
    }
  }'
```

Replace `REGION`, `INDEX_ENDPOINT_RESOURCE_NAME`, and
`INDEX_RESOURCE_NAME` with your values. To deploy as in-memory instead,
omit the `deploymentTier` field (the default is `STANDARD`).

## Data Format

Each vector is stored as a JSON line:

```json
{
    "id": "1234567_3",
    "embedding": [0.012, -0.034, ...],
    "restricts": [
        {"namespace": "mrn", "allow": ["12345678"]},
        {"namespace": "note_category", "allow": ["Progress Notes"]},
        {"namespace": "department", "allow": ["Cardiology"]}
    ],
    "numeric_restricts": [
        {"namespace": "year", "value_int": 2024},
        {"namespace": "utc_epoch_sec", "value_int": 1704067200}
    ],
    "crowding_tag": "12345678"
}
```

- **id**: `<note_id>_<chunk_index>` format
- **restricts**: String filters for metadata-filtered search
- **numeric_restricts**: Numeric filters for date range queries
- **crowding_tag**: Groups vectors by patient (MRN) to limit
  per-patient results. This is a key differentiator of Vertex AI Vector
  Search: the crowding constraint is enforced during graph traversal,
  not as a post-retrieval filter. This means the index returns exactly
  `num_neighbors` results with at most
  `per_crowding_attribute_neighbor_count` per patient, without
  over-fetching and discarding. To our knowledge, no major open-source
  vector database (FAISS, Qdrant, Milvus) or other managed service
  offers an equivalent at-traversal-time diversity constraint.
  Institutions porting to other backends will need to implement
  per-patient limits as a post-retrieval step, which may require
  requesting more candidates than needed and filtering down

## Alternative Vector Databases

### pgvector (PostgreSQL)

```sql
CREATE TABLE note_chunks (
    chunk_id    TEXT PRIMARY KEY,
    note_id     TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    mrn         TEXT NOT NULL,
    embedding   vector(1024) NOT NULL,
    note_category TEXT,
    department  TEXT,
    specialty   TEXT,
    year        INTEGER,
    utc_epoch   BIGINT
);

CREATE INDEX idx_chunks_embedding ON note_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 1000);
CREATE INDEX idx_chunks_mrn ON note_chunks(mrn);
```

### Qdrant

```python
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

client = QdrantClient(host="localhost", port=6333)
client.create_collection(
    collection_name="clinical_notes",
    vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
)
```
