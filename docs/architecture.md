# System Architecture

## Overview

The clinical semantic search system consists of two major subsystems:
an offline ETL pipeline that builds the vector index, and an online
search service that handles queries.

## Offline: Index Building

```
EHR Database
    │
    ▼
┌─────────────────────┐
│  Data Extract       │  SQL query against EHR tables
│  (BigQuery / SQL)   │  Filters: DOB >= 2000, note_text IS NOT NULL
└─────────┬───────────┘
          │
          ▼
┌───────────────────────┐
│  Preprocessing        │  Column mapping, date parsing, age calculation,
│  (MetadataTransformer)│  note category assembly
└─────────┬─────────────┘
          │
          ▼
┌─────────────────────┐
│  Chunking           │  RecursiveCharacterTextSplitter
│  (300 tokens,       │  Tokenizer-aware, 50-token overlap
│   50 overlap)       │  Records (start_char, end_char) per chunk
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Embedding          │  Data-parallel across 8 TPU cores
│  (Qwen3-0.6B,       │  bfloat16, batch_size=256
│   last-token pool)  │  L2-normalized output
└─────────┬───────────┘
          │
          ▼
┌──────────────────────┐
│  Vector Export       │  JSON points with:
│  (JSONL format)      │  - embedding vector
│                      │  - string restricts (MRN, note_category, ...)
│                      │  - numeric restricts (year, utc_epoch_sec)
│                      │  - crowding_tag (MRN)
└─────────┬────────────┘
          │
          ├──► Vector Index (Vertex AI / pgvector / Qdrant)
          │
          └──► Metadata Store (BigTable / PostgreSQL)
               Stores: note_text, chunk_indices, all metadata columns
```

## Online: Query Processing

```
User Query
    │
    ▼
┌─────────────────────┐
│  Query Embedding    │  CPU inference, ~400ms
│  (instruction +     │  "Instruct: Given a medical query..."
│   last-token pool)  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Vector Search      │  ANN with metadata filters
│  (filtered by MRN,  │  ~240ms at concurrency=1
│   date, category,   │  Returns top-k (chunk_id, distance) pairs
│   department, etc.) │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Access Control     │  Binary search on memory-mapped allowlist
│  (note-level)       │  O(log n) per note ID
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Metadata Lookup    │  Batch read from BigTable, ~5ms
│  (note text +       │  Salt-based row keys avoid hotspotting
│   chunk indices)    │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Result Rendering   │  Group by MRN, sort by distance
│  (chunk highlight,  │  Highlight matched chunks in note text
│   metadata display) │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Audit Logging      │  Log query + returned MRN/note_id pairs
│  (structlog → Cloud │  Never log note text
│   Logging)          │
└─────────────────────┘
```

## Key Design Decisions

### Chunking Strategy

Notes are split into 300-token chunks with 50-token overlap.  The chunk
size balances granularity (finding specific details) against context
(providing enough surrounding text for relevance scoring).  The overlap
ensures that information near chunk boundaries is captured.

Character-level offsets `(start_char, end_char)` are stored alongside
each chunk in the metadata store.  This enables the UI to highlight
exactly which portions of a note matched the query.

### Crowding

Vector search uses a `crowding_tag` set to the patient MRN.  The
`per_crowding_attribute_neighbor_count` parameter limits how many
chunks are returned per patient, preventing a single patient with many
relevant notes from monopolizing all result slots.

### Storage-Optimized vs In-Memory Index

The reference deployment uses the storage-optimized index tier, which
stores vectors on disk (SSD) rather than in RAM.  This reduces costs
significantly at health-system scale, at the expense of slightly higher
per-query latency.  The benchmark tools in this repository can help you
evaluate the latency/cost tradeoff for your deployment.
