#!/usr/bin/env python3
"""
Latency decomposition benchmark for the semantic search pipeline.

Measures end-to-end query latency decomposed into three phases:

  Phase 1: Query embedding (sequential, matching per-container reality)
  Phase 2: Vector search at varying concurrency levels (MRN-filtered)
  Phase 3: Metadata store lookup (sequential, on real results from Phase 2)

Outputs timestamped CSVs and a combined PNG figure.

Usage:
    python benchmarks/latency_decomposition.py \
        --n-queries 200 \
        --concurrency-levels 1 5 10 20 \
        --out-prefix latency_decomposition
"""

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from google.cloud import aiplatform, bigtable
from google.cloud.bigtable.row_set import RowSet
from matplotlib.gridspec import GridSpec
from transformers import AutoModel, AutoTokenizer

from clinical_semantic_search.config import get_settings
from clinical_semantic_search.core.embedding import embed_query, load_embedding_model
from clinical_semantic_search.services.metadata_store import build_row_key

QUERIES = [
    "What medical problems does this patient have?",
    "Does this patient have a genetic condition?",
    "What was the reason for this patient's hospitalization?",
    "Describe this patient's congenital heart anatomy.",
    "What surgical procedures has this patient undergone?",
    "Has this patient ever had a seizure?",
    "What medications is this patient currently taking?",
    "Does this patient have any allergies?",
    "What immunizations has this patient received?",
    "What is this patient's developmental history?",
]

torch.set_num_threads(8)
torch.set_num_interop_threads(1)


# ── Phase 1: Embedding ───────────────────────────────────────────────
def time_embedding(query: str, model, tokenizer, instruction: str) -> dict:
    """Time a single query embedding on CPU."""
    start = time.perf_counter_ns()
    emb = embed_query(query, model, tokenizer, instruction=instruction)
    elapsed = (time.perf_counter_ns() - start) / 1e6
    return {"query": query, "embedding_ms": elapsed, "embedding": emb}


# ── Phase 2: Vector Search ───────────────────────────────────────────
def run_vs_at_concurrency(
    embeddings, mrn_list, concurrency, endpoint, index_id, num_neighbors=20,
) -> pd.DataFrame:
    """Benchmark vector search at a given concurrency with MRN-filtered queries."""
    Namespace = aiplatform.matching_engine.matching_engine_index_endpoint.Namespace
    results = []

    def job(vec, mrn):
        start = time.perf_counter_ns()
        err = None
        n_returned = 0
        note_chunks = []
        try:
            resp = endpoint.find_neighbors(
                deployed_index_id=index_id,
                queries=[vec],
                filter=[Namespace("mrn", [mrn])],
                num_neighbors=num_neighbors,
            )
            note_chunks = [n.id for n in resp[0]]
            n_returned = len(note_chunks)
        except Exception as e:
            err = repr(e)
        elapsed = (time.perf_counter_ns() - start) / 1e6
        return {
            "vector_search_ms": elapsed,
            "n_results": n_returned,
            "note_chunks": note_chunks,
            "error": err,
        }

    if concurrency == 1:
        for vec, mrn in zip(embeddings, mrn_list):
            r = job(vec, mrn)
            r["concurrency"] = concurrency
            results.append(r)
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futures = {
                ex.submit(job, vec, mrn): i
                for i, (vec, mrn) in enumerate(zip(embeddings, mrn_list))
            }
            for fut in as_completed(futures):
                r = fut.result()
                r["concurrency"] = concurrency
                results.append(r)

    return pd.DataFrame(results)


# ── Phase 3: Metadata Lookup ─────────────────────────────────────────
def time_metadata_lookup(note_chunks: list[str], bt_table) -> dict:
    """Time a BigTable batch read for a set of note IDs."""
    if not note_chunks:
        return {"bigtable_ms": 0.0, "n_notes": 0, "error": None}

    note_ids = list({cid.split("_")[0] for cid in note_chunks})
    start = time.perf_counter_ns()
    err = None
    n_notes = 0
    try:
        row_set = RowSet()
        for nid in note_ids:
            row_set.add_row_key(build_row_key(nid))
        rows = list(bt_table.read_rows(row_set=row_set))
        n_notes = len(rows)
    except Exception as e:
        err = repr(e)
    elapsed = (time.perf_counter_ns() - start) / 1e6
    return {"bigtable_ms": elapsed, "n_notes": n_notes, "error": err}


def run_metadata_benchmark(note_chunks_list, bt_table) -> pd.DataFrame:
    """Benchmark metadata lookups sequentially on a sample of real results."""
    results = [time_metadata_lookup(chunks, bt_table) for chunks in note_chunks_list]
    return pd.DataFrame(results)


# ── Plotting ─────────────────────────────────────────────────────────
def plot_decomposition(df_embed, df_vs, df_bt, out_path):
    concurrency_levels = sorted(df_vs["concurrency"].unique())

    fig = plt.figure(figsize=(12, 8))
    gs = GridSpec(2, 2, height_ratios=[3, 1.2], width_ratios=[1, 2], figure=fig)

    # Left: single-user decomposition
    ax_decomp = fig.add_subplot(gs[0, 0])
    embed_p50 = df_embed["embedding_ms"].quantile(0.50)
    c1 = df_vs[df_vs["concurrency"] == 1]
    vs_p50 = c1["vector_search_ms"].quantile(0.50) if not c1.empty else 0
    bt_p50 = df_bt["bigtable_ms"].quantile(0.50) if not df_bt.empty else 0

    stages = [embed_p50, vs_p50, bt_p50]
    labels = ["Query\nEmbedding", "Vector\nSearch", "Metadata\nLookup"]
    colors = ["#4e79a7", "#f28e2b", "#76b7b2"]

    bars = ax_decomp.bar(labels, stages, color=colors, edgecolor="white", width=0.6)
    for bar, val in zip(bars, stages):
        ax_decomp.text(
            bar.get_x() + bar.get_width() / 2, bar.get_height() + 8,
            f"{val:.0f}", ha="center", va="bottom", fontsize=10, fontweight="bold",
        )
    total = sum(stages)
    ax_decomp.set_title(f"Single-User Latency\n(median total: {total:.0f} ms)")
    ax_decomp.set_ylabel("Median Latency (ms)")
    ax_decomp.grid(axis="y", linestyle=":", alpha=0.4)

    # Right: vector search by concurrency
    ax_conc = fig.add_subplot(gs[0, 1])
    vs_medians = []
    for c in concurrency_levels:
        sub = df_vs[(df_vs["concurrency"] == c) & df_vs["error"].isna()]
        vs_medians.append(sub["vector_search_ms"].quantile(0.50))

    x = np.arange(len(concurrency_levels))
    bars = ax_conc.bar(x, vs_medians, 0.5, color="#f28e2b", edgecolor="white")
    for i, v in enumerate(vs_medians):
        ax_conc.text(i, v + 8, f"{v:.0f}", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax_conc.set_xticks(x)
    ax_conc.set_xticklabels([str(c) for c in concurrency_levels])
    ax_conc.set_xlabel("Concurrent Users (Simulated)")
    ax_conc.set_ylabel("Median Vector Search Latency (ms)")
    ax_conc.set_title("Index Latency Under Concurrent Load")
    ax_conc.grid(axis="y", linestyle=":", alpha=0.4)

    # Bottom: summary table
    ax_table = fig.add_subplot(gs[1, :])
    ax_table.axis("off")

    col_labels = ["Component", "n", "p50 (ms)", "p95 (ms)", "p99 (ms)", "max (ms)"]
    cell_text = []

    emb = df_embed["embedding_ms"]
    cell_text.append([
        "Query Embedding", f"{len(emb)}",
        f"{emb.quantile(.50):.0f}", f"{emb.quantile(.95):.0f}",
        f"{emb.quantile(.99):.0f}", f"{emb.max():.0f}",
    ])

    if not df_bt.empty:
        bt = df_bt["bigtable_ms"]
        cell_text.append([
            "Metadata Lookup", f"{len(bt)}",
            f"{bt.quantile(.50):.0f}", f"{bt.quantile(.95):.0f}",
            f"{bt.quantile(.99):.0f}", f"{bt.max():.0f}",
        ])

    for c in concurrency_levels:
        sub = df_vs[(df_vs["concurrency"] == c) & df_vs["error"].isna()]
        vs = sub["vector_search_ms"]
        errors = df_vs[df_vs["concurrency"] == c]["error"].notna().sum()
        label = f"Vector Search (c={c})"
        if errors > 0:
            label += f" [{errors} err]"
        cell_text.append([
            label, f"{len(sub)}",
            f"{vs.quantile(.50):.0f}", f"{vs.quantile(.95):.0f}",
            f"{vs.quantile(.99):.0f}", f"{vs.max():.0f}",
        ])

    table = ax_table.table(cellText=cell_text, colLabels=col_labels, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.4)

    plt.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote: {out_path}")


# ── MRN sampling ─────────────────────────────────────────────────────
def get_mrn_sample(n: int = 1000) -> list[str]:
    """Get a sample of MRNs from BigQuery for realistic filtered queries.

    NOTE: Replace this SQL with a query appropriate for your institution's
    patient table.
    """
    from google.cloud import bigquery as bq

    settings = get_settings()
    client = bq.Client(settings.metadata_project)
    query = """
        SELECT DISTINCT pat_mrn_id
        FROM YOUR_DATASET.patient PAT
        INNER JOIN YOUR_DATASET.note_info NI ON PAT.pat_id = NI.pat_id
        WHERE PAT.dob >= DATE(2000, 1, 1)
        AND EXTRACT(MONTH FROM dob) = 12
        LIMIT 2000
    """
    df = client.query(query, location="US").result().to_dataframe()
    return df.sample(n=min(n, len(df)), random_state=42).pat_mrn_id.tolist()


# ── CLI ──────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(description="Latency decomposition benchmark.")
    p.add_argument("--n-queries", type=int, default=200)
    p.add_argument("--num-neighbors", type=int, default=20)
    p.add_argument("--concurrency-levels", type=int, nargs="+", default=[1, 5, 10, 20])
    p.add_argument("--warmup-queries", type=int, default=5)
    p.add_argument("--out-prefix", default="latency_decomposition")
    return p.parse_args()


def main():
    args = parse_args()
    settings = get_settings()

    # Init model
    print("Loading embedding model...")
    model, tokenizer = load_embedding_model(settings.embedding_model_path)
    instruction = settings.embedding_instruction

    # Init Vertex AI
    print("Connecting to vector search...")
    aiplatform.init(project=settings.vector_search_project, location=settings.cloud_region)
    endpoint = aiplatform.MatchingEngineIndexEndpoint(
        index_endpoint_name=settings.index_endpoint_path
    )
    if settings.index_psc_ip:
        endpoint.private_service_connect_ip_address = settings.index_psc_ip

    # Init BigTable
    print("Connecting to metadata store...")
    bt_client = bigtable.Client(project=settings.metadata_project, admin=True)
    bt_instance = bt_client.instance(settings.bigtable_instance)
    bt_table = bt_instance.table(settings.bigtable_table)

    # Get MRN sample
    print("Fetching MRN sample...")
    mrn_pool = get_mrn_sample(args.n_queries)
    mrn_list = [mrn_pool[i % len(mrn_pool)] for i in range(args.n_queries)]
    query_list = [QUERIES[i % len(QUERIES)] for i in range(args.n_queries)]

    # Warmup
    print(f"Warming up ({args.warmup_queries} queries)...")
    Namespace = aiplatform.matching_engine.matching_engine_index_endpoint.Namespace
    for i in range(args.warmup_queries):
        q = QUERIES[i % len(QUERIES)]
        emb = embed_query(q, model, tokenizer, instruction=instruction)
        try:
            endpoint.find_neighbors(
                deployed_index_id=settings.deployed_index_id,
                queries=[emb],
                filter=[Namespace("mrn", [mrn_list[i]])],
                num_neighbors=args.num_neighbors,
            )
        except Exception:
            pass
    print("Warmup complete.\n")

    # Phase 1: Embedding
    print(f"Phase 1: Embedding ({args.n_queries} queries, sequential)...")
    embed_results = []
    precomputed = []
    for q in query_list:
        r = time_embedding(q, model, tokenizer, instruction)
        embed_results.append({"query": r["query"], "embedding_ms": r["embedding_ms"]})
        precomputed.append(r["embedding"])
    df_embed = pd.DataFrame(embed_results)
    print(f"  p50={df_embed['embedding_ms'].quantile(.5):.0f}ms  "
          f"p95={df_embed['embedding_ms'].quantile(.95):.0f}ms")

    # Phase 2: Vector search
    all_vs = []
    for c in args.concurrency_levels:
        print(f"\nPhase 2: Vector search at concurrency={c}...")
        t0 = time.perf_counter()
        df_c = run_vs_at_concurrency(
            precomputed, mrn_list, c, endpoint,
            settings.deployed_index_id, args.num_neighbors,
        )
        elapsed = time.perf_counter() - t0
        errors = df_c["error"].notna().sum()
        ok = df_c[df_c["error"].isna()]
        print(f"  Done in {elapsed:.1f}s | errors: {errors}/{len(df_c)}")
        if not ok.empty:
            print(f"  p50={ok['vector_search_ms'].quantile(.5):.0f}ms  "
                  f"p95={ok['vector_search_ms'].quantile(.95):.0f}ms")
        all_vs.append(df_c)
    df_vs = pd.concat(all_vs, ignore_index=True)

    # Phase 3: Metadata lookup
    c1_chunks = df_vs[
        (df_vs["concurrency"] == 1) & df_vs["error"].isna()
    ]["note_chunks"].tolist()
    bt_sample = [c for c in c1_chunks if c][:100]
    print(f"\nPhase 3: Metadata lookup ({len(bt_sample)} lookups, sequential)...")
    df_bt = run_metadata_benchmark(bt_sample, bt_table)
    if not df_bt.empty:
        bt = df_bt["bigtable_ms"]
        print(f"  p50={bt.quantile(.5):.0f}ms  p95={bt.quantile(.95):.0f}ms")

    # Save CSVs
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    for name, df in [("embedding", df_embed), ("vectorsearch", df_vs), ("metadata", df_bt)]:
        path = f"{args.out_prefix}_{ts}_{name}.csv"
        df.to_csv(path, index=False)
        print(f"Wrote: {path}")

    # Plot
    png_path = f"{args.out_prefix}_{ts}.png"
    plot_decomposition(df_embed, df_vs, df_bt, png_path)


if __name__ == "__main__":
    main()
