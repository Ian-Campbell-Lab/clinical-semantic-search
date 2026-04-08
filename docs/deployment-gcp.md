# GCP Reference Deployment

This document describes the Google Cloud Platform deployment used in the
reference implementation.  Use it as a guide for replicating the
architecture or as context for understanding the codebase.

## Infrastructure Components

| Component | GCP Service | Purpose |
|---|---|---|
| Vector Index | Vertex AI Vector Search | ANN search with metadata filtering |
| Metadata Store | Cloud BigTable | Note text and metadata retrieval by ID |
| Access Control | BigQuery | Per-project note allowlist queries |
| Audit Logging | Cloud Logging | Query audit trail via structlog |
| Embedding Compute | Cloud TPU (v4-8) | Bulk embedding for index building |
| Web Hosting | Cloud Run / GKE | Per-project containerized deployments |

## Network Architecture

The vector search index is accessed via Private Service Connect (PSC),
which provides a private IP address within the VPC for low-latency
access without traversing the public internet.

Each research project gets its own container deployment with:
- Its own BigQuery-derived note allowlist
- The shared vector search endpoint (read-only)
- The shared BigTable instance (read-only)
- Its own audit log stream

## Index Creation

See [vector-index-setup.md](vector-index-setup.md) for index creation
and deployment commands.

## Cost Structure

The major cost components are:

1. **Vector Search** -- billed per capacity unit per hour.  The
   storage-optimized tier is substantially cheaper than in-memory.
2. **BigTable** -- billed per node-hour plus storage.  A single node
   handles the read load for typical usage.
3. **Embedding Compute** -- one-time cost for index building.  TPUs
   are cost-effective for large-scale embedding computation.
4. **Cloud Run / GKE** -- per-container costs for the web application.

See the manuscript for detailed cost figures.
