# Clinical Semantic Search

A reference implementation for health-system-scale semantic search over
clinical notes.  This system indexes clinical notes as dense embedding
vectors, enabling natural-language queries across an entire health
system's documentation with sub-second latency.

## Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  User Query  │────>│  Embedding Model │────>│  Vector Index   │
│  (natural    │     │  (Qwen3-0.6B,    │     │  (Vertex AI,    │
│   language)  │     │   CPU, ~400ms)   │     │   pgvector,     │
└──────────────┘     └──────────────────┘     │   Qdrant, etc.) │
                                              └────────┬────────┘
                                                       │
                                              ┌────────v────────┐
                                              │  Metadata Store │
                                              │  (BigTable,     │
                                              │   PostgreSQL)   │
                                              └────────┬────────┘
                                                       │
                                              ┌────────v────────┐
                                              │  Search Results │
                                              │  (notes with    │
                                              │   highlighted   │
                                              │   chunks)       │
                                              └─────────────────┘
```

The system has three components:

1. **ETL Pipeline** -- extracts notes from the EHR, chunks them into
   300-token segments, computes embeddings, and loads them into a vector
   index with metadata filters.

2. **Search Service** -- embeds a user's query, searches the vector
   index with optional metadata filters (date range, note category,
   specialty, department, author), and fetches matching note text from
   the metadata store.

3. **Web Application** -- a FastAPI interface for interactive search
   with filter controls, result grouping by patient, and chunk
   highlighting.

## Design Philosophy

This is a **reference implementation**, not an abstract framework.
The code ships with working GCP service implementations (Vertex AI
Vector Search, Cloud BigTable, BigQuery) that you can read, understand,
and replace with your institution's infrastructure.  All
institution-specific values are externalized to environment variables.

See [PORTING_GUIDE.md](PORTING_GUIDE.md) for step-by-step instructions
on adapting this system for your institution.

## Repository Structure

```
src/clinical_semantic_search/
    core/           # Portable: chunking, embedding, pooling, formatting
    services/       # Reference GCP implementations (replace for your infra)
    etl/            # Data loading pipeline
    config.py       # All config from environment variables

webapp/             # FastAPI search interface
benchmarks/         # Latency decomposition, index recall, MCQA evaluation
docs/               # Architecture, deployment, schema documentation
tests/              # Tests for portable core modules
```

## Quick Start

### 1. Install

```bash
pip install -e ".[gcp,webapp]"
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your infrastructure details
```

### 3. Run the web application

```bash
clinical-search \
    --bt_project_id YOUR_PROJECT \
    --bt_instance YOUR_INSTANCE \
    --bt_table_id notes \
    --endpoint_name projects/.../indexEndpoints/... \
    --ip_address YOUR_PSC_IP \
    --deployed_index YOUR_INDEX_ID \
    --embedding_model_path /path/to/model
```

### 4. Run benchmarks

```bash
# Latency decomposition
python benchmarks/latency_decomposition.py --n-queries 200

# Index recall
python benchmarks/index_recall.py --jsonl-path /path/to/reference.jsonl
```

## Key Technical Decisions

- **Embedding model**: Qwen3-Embedding-0.6B (instruction-tuned, 1024-dim,
  last-token pooling).  Small enough for CPU inference (~400ms/query).
- **Chunking**: 300 tokens with 50-token overlap using LangChain's
  `RecursiveCharacterTextSplitter` with a HuggingFace tokenizer.
- **Vector index**: Storage-optimized tier for cost efficiency at scale.
  Supports metadata filtering (string and numeric) and per-patient
  crowding.
- **Access control**: Per-project note allowlists via memory-mapped
  sorted arrays with binary search (O(log n) per lookup).

## Provenance

This repository is a portable, open-source distillation of the
production system deployed at Children's Hospital of Philadelphia. The
original implementation was developed by the authors listed in the
accompanying manuscript, with AI coding assistance (ChatGPT,
Claude Code). This open-source version was restructured and
de-identified from the production codebase using Claude Code (Anthropic)
to remove institution-specific configuration, consolidate duplicated
modules, and generate documentation. All code was reviewed and approved
by the authors prior to release.

## License

CC BY-NC 4.0 (Creative Commons Attribution-NonCommercial 4.0 International)

## Citation

If you use this software in your research, please cite:

> Mutinda FW, et al. (2026). Health-system-scale semantic search over
> clinical notes. [Journal TBD].
