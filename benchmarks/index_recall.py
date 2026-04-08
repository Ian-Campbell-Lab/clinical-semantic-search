#!/usr/bin/env python3
"""
Storage-optimized index recall and latency benchmark.

Compares approximate nearest neighbor results from the deployed index
against brute-force reference distances to measure recall quality.
Also measures query latency under concurrent load.

Inputs:
    JSONL with brute-force reference data:
    {"mrn": str, "total_vectors": int, "nearest": float}

Outputs:
    - {out_prefix}_{timestamp}_combined.png (scatter + latency + metrics)
    - Console summary

Usage:
    python benchmarks/index_recall.py \
        --jsonl-path /path/to/vector_counts.jsonl \
        --num-neighbors 20 \
        --concurrency 16 \
        --subsample-n 1000
"""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import List, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from google.cloud import aiplatform
from matplotlib.colors import ListedColormap
from matplotlib.gridspec import GridSpec
from transformers import AutoModel, AutoTokenizer

from clinical_semantic_search.config import get_settings
from clinical_semantic_search.core.embedding import embed_query, load_embedding_model


def load_groups_jsonl(path: str) -> pd.DataFrame:
    """Load brute-force reference data from JSONL."""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    df = df.rename(columns={"total_vectors": "total", "nearest": "nearest"})
    if not {"mrn", "total", "nearest"}.issubset(df.columns):
        raise ValueError(f"{path} must contain 'mrn', 'total_vectors', 'nearest'")
    return df[["mrn", "total", "nearest"]]


def make_endpoint(index_endpoint_name: str, psc_ip: Optional[str] = None):
    """Create a Vertex AI index endpoint connection."""
    ep = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=index_endpoint_name)
    if psc_ip:
        ep.private_service_connect_ip_address = psc_ip
    return ep


def find_neighbors_timed(endpoint, deployed_index_id, mrn, query_vec, num_neighbors):
    """Time a single MRN-filtered nearest neighbor query."""
    Namespace = aiplatform.matching_engine.matching_engine_index_endpoint.Namespace
    start_ns = time.perf_counter_ns()
    err = None
    n_returned = 0
    min_distance = None
    try:
        resp = endpoint.find_neighbors(
            deployed_index_id=deployed_index_id,
            queries=[query_vec],
            filter=[Namespace("mrn", [mrn])],
            num_neighbors=num_neighbors,
        )
        n_returned = len(resp[0])
        if n_returned > 0:
            min_distance = float(max(x.distance for x in resp[0]))
    except Exception as e:
        err = repr(e)

    latency_ms = (time.perf_counter_ns() - start_ns) / 1e6
    return {
        "latency_ms": latency_ms,
        "store_results": int(n_returned),
        "returned_min_distance": min_distance,
        "error": err,
    }


def run_benchmark(df_groups, endpoint, deployed_index_id, query, num_neighbors,
                   subsample_n, subsample_seed, concurrency):
    """Run the recall benchmark across all MRN groups."""
    if subsample_n and 0 < subsample_n < len(df_groups):
        work = df_groups.sample(n=subsample_n, random_state=subsample_seed).copy()
    else:
        work = df_groups

    groups = work["mrn"].tolist()
    results = []

    def job(g):
        return g, find_neighbors_timed(endpoint, deployed_index_id, g, query, num_neighbors)

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = {ex.submit(job, g): g for g in groups}
        for fut in as_completed(futures):
            g, r = fut.result()
            results.append({"mrn": g, **r})

    res = pd.DataFrame(results)
    return work.merge(res, on="mrn", how="left")


def plot_combined(df, target_num, out_path, title, config_lines):
    """Generate combined scatter + histogram + metrics figure."""
    fig = plt.figure(figsize=(12, 8))
    gs = GridSpec(2, 2, height_ratios=[3, 1], figure=fig)

    ax_scatter = fig.add_subplot(gs[0, 0])
    ax_hist = fig.add_subplot(gs[0, 1])
    ax_text = fig.add_subplot(gs[1, :])
    ax_text.axis("off")

    # Scatter
    viridis = plt.cm.get_cmap("viridis", 256)
    newcolors = viridis(np.linspace(0, 1, 256))
    newcolors[0] = np.array([0, 0, 0, 1])
    cmap = ListedColormap(newcolors)

    sc = ax_scatter.scatter(
        df["total"], df["nearest"],
        c=df["store_results"].fillna(0),
        cmap=cmap, vmin=0, vmax=target_num,
        s=60, alpha=0.9, edgecolor="k", linewidth=0.3,
    )
    try:
        ax_scatter.set_xscale("symlog", linthresh=1, linscale=1.0, base=10)
    except TypeError:
        ax_scatter.set_xscale("symlog", linthresh=1, linscale=1.0)
    fig.colorbar(sc, ax=ax_scatter, pad=0.01).set_label(f"Results returned / {target_num}")
    ax_scatter.set_ylabel("Nearest Vector Distance (brute-force)")
    ax_scatter.set_xlabel("Total Vectors for Patient")
    ax_scatter.set_title("Total vs Nearest")
    ax_scatter.grid(True, linestyle=":", alpha=0.4)

    # Histogram
    ok = df[df["error"].isna() & df["latency_ms"].notna()]
    ax_hist.hist(ok["latency_ms"], bins=60)
    ax_hist.set_xlabel("Latency (ms)")
    ax_hist.set_ylabel("Count")
    ax_hist.set_title("Latency Histogram")
    ax_hist.grid(True, linestyle=":", alpha=0.4)

    # Metrics panel
    lines = [
        f"Run Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        f"Groups total        : {len(df):,}",
        f"Groups with results : {(ok['store_results'].fillna(0) > 0).sum():,}",
        f"Errors              : {df['error'].notna().sum():,}",
    ]
    if not ok.empty:
        q = ok["latency_ms"].quantile([0.50, 0.95, 0.99])
        lines.extend([
            "",
            f"Latency: p50={q[0.50]:.1f}ms  p95={q[0.95]:.1f}ms  "
            f"p99={q[0.99]:.1f}ms  max={ok['latency_ms'].max():.1f}ms",
        ])
    if config_lines:
        lines.extend(["", "Config:"] + config_lines)

    ax_text.text(0.01, 0.98, "\n".join(lines), va="top", ha="left", family="monospace", fontsize=10)

    fig.suptitle(title, y=0.995, fontsize=14)
    plt.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def parse_args():
    p = argparse.ArgumentParser(description="Storage-optimized index recall + latency benchmark.")
    p.add_argument("--jsonl-path", required=True, help="Path to brute-force reference JSONL")
    p.add_argument("--query", default=None)
    p.add_argument("--num-neighbors", type=int, default=20)
    p.add_argument("--subsample-n", type=int, default=1000)
    p.add_argument("--subsample-seed", type=int, default=0)
    p.add_argument("--concurrency", type=int, default=16)
    p.add_argument("--out-prefix", default="index_recall")
    p.add_argument("--title", default=None)
    return p.parse_args()


def main():
    args = parse_args()
    settings = get_settings()

    aiplatform.init(project=settings.vector_search_project, location=settings.cloud_region)
    endpoint = make_endpoint(settings.index_endpoint_path, settings.index_psc_ip)

    df_groups = load_groups_jsonl(args.jsonl_path)

    print("Loading embedding model...")
    model, tokenizer = load_embedding_model(settings.embedding_model_path)
    query_text = args.query or "What medical problems does this patient have?"
    query_vec = embed_query(query_text, model, tokenizer, instruction=settings.embedding_instruction)

    print(f"Running benchmark ({args.subsample_n} groups, concurrency={args.concurrency})...")
    result_df = run_benchmark(
        df_groups, endpoint, settings.deployed_index_id,
        query_vec, args.num_neighbors,
        args.subsample_n, args.subsample_seed, args.concurrency,
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    png_path = f"{args.out_prefix}_{ts}_combined.png"
    title = args.title or "Storage-Optimized Index Benchmark"
    config_lines = [
        f"neighbors={args.num_neighbors}",
        f"concurrency={args.concurrency}",
        f"subsample_n={args.subsample_n}",
    ]
    plot_combined(result_df, args.num_neighbors, png_path, title, config_lines)
    print(f"Wrote: {png_path}")

    errs = result_df[result_df["error"].notna()][["mrn", "error"]]
    if not errs.empty:
        print("\nSample errors:")
        print(errs.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
