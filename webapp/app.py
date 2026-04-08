"""
Clinical Semantic Search -- FastAPI web application.

Provides a search interface for querying clinical notes using semantic
vector search with metadata filtering.  The application:

1. Loads an embedding model at startup
2. Accepts search queries with optional metadata filters
3. Embeds queries, searches the vector index, and fetches note text
4. Renders results grouped by patient (MRN) with chunk highlighting
5. Logs all queries for audit purposes

Usage:
    python webapp/app.py \
        --bt_project_id YOUR_PROJECT \
        --bt_instance YOUR_INSTANCE \
        --bt_table_id notes \
        --endpoint_name projects/.../indexEndpoints/... \
        --ip_address 10.0.0.1 \
        --deployed_index YOUR_INDEX_ID \
        --embedding_model_path /path/to/model
"""

import argparse
import asyncio
import base64
import csv
import gc
import json
import logging
import os
import re
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import uvicorn
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from clinical_semantic_search.services import (
    audit_logging as clog,
    vector_search as vs_service,
    metadata_store as bt_service,
    access_control as bq_service,
)
from clinical_semantic_search.core.embedding import (
    embed_query,
    format_query,
    load_embedding_model,
)
from clinical_semantic_search.services.vector_search import (
    build_namespace_filters,
    find_neighbors,
)

BASE_DIR = Path(__file__).resolve().parent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
app_user = None
app_project = None
mem_map = None
mm_index = None
_embedding_model = None
_embedding_tokenizer = None


@app.on_event("startup")
async def startup_event():
    """Initialize models and access control at startup."""
    global app_user, app_project, mem_map, mm_index
    global _embedding_model, _embedding_tokenizer

    try:
        logger.info("Starting app initialization...")
        loop = asyncio.get_running_loop()
        start = loop.time()

        # Load embedding model
        logger.info("Loading embedding model...")

        def _load_model():
            global _embedding_model, _embedding_tokenizer
            _embedding_model, _embedding_tokenizer = load_embedding_model(
                app.state.embedding_model_path
            )

        load_model_task = loop.run_in_executor(None, _load_model)

        # Load filter options
        load_options = loop.run_in_executor(None, get_options)

        # Get user and project
        app_user, app_project = await loop.run_in_executor(
            None, bq_service.get_user_project
        )

        # Build note allowlist
        logger.info("Building note allowlist...")
        access_project = app.state.bt_project_id
        load_note_ids = loop.run_in_executor(
            None, bq_service.build_note_index, access_project
        )

        _, _, (mem_map, mm_index) = await asyncio.gather(
            load_model_task, load_options, load_note_ids
        )

        elapsed = loop.time() - start
        logger.info(f"Startup complete in {elapsed:.2f}s")

    except Exception as e:
        logger.error(f"Failed to initialize: {e}", exc_info=True)
        raise


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def highlight_by_indices(text, selected_indices):
    """Jinja2 filter to highlight matched chunks in note text."""
    if not text:
        return ""
    if not selected_indices:
        return Markup(escape(text))
    out = []
    last = 0
    for s, e in selected_indices:
        out.append(escape(text[last:s]))
        out.append(Markup(f'<span class="highlight">{escape(text[s:e])}</span>'))
        last = e
    out.append(escape(text[last:]))
    return Markup("".join(out))


templates.env.filters["highlight_by_indices"] = highlight_by_indices


@lru_cache(maxsize=20)
def load_json_cached(filename: str):
    """Load filter JSON files with caching."""
    path = BASE_DIR / "filter_data" / filename
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list) and data and isinstance(data[0], str):
                return [{"id": v, "text": v} for v in data]
            return data
    return []


OPTIONS_CACHE = None


def get_options():
    """Load and cache filter dropdown options."""
    global OPTIONS_CACHE
    if OPTIONS_CACHE is None:
        OPTIONS_CACHE = {
            "note_category": load_json_cached("note_categories.json"),
            "encounter_type": load_json_cached("encounter_types.json"),
            "department": load_json_cached("department_names.json"),
            "specialty": load_json_cached("specialties.json"),
            "author_type": load_json_cached("author_types.json"),
            "author_name": load_json_cached("author_names.json"),
        }
    return OPTIONS_CACHE


def embed_static_file(path, mime):
    """Encode a static file as a data URI for embedding in HTML."""
    full_path = Path(path) if Path(path).is_absolute() else BASE_DIR / path
    data = full_path.read_bytes()
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def convert_to_epoch_ts(date_str):
    """Convert a date string to UTC epoch timestamp."""
    dt = pd.to_datetime(date_str, errors="coerce")
    return int(
        dt.tz_localize("America/New_York", ambiguous=False, nonexistent="shift_forward")
        .tz_convert("UTC")
        .timestamp()
    )


def group_chunks_by_mrn_and_distance(chunks):
    """Group notes by MRN, sorted by relevance (max distance)."""
    if not chunks:
        return defaultdict(list)

    groups = defaultdict(list)
    for c in chunks:
        mrn = c.get("mrn")
        if mrn and mrn.lower() != "none":
            groups[mrn].append(c)

    for notes in groups.values():
        notes.sort(key=lambda n: max(n.get("distances", [0.0])), reverse=True)

    sorted_items = sorted(
        groups.items(),
        key=lambda item: max(item[1][0].get("distances", [0.0])) if item[1] else 0.0,
        reverse=True,
    )

    result = defaultdict(list)
    result.update(sorted_items)
    return result


def reorder_chunks(grouped_chunks, mrn_list):
    """Reorder grouped chunks to match user-provided MRN order."""
    placeholder_chunk = [{
        "note_text": "No notes were retrieved for this patient.",
        "mrn": None,
        "note_id": None,
    }]
    ordered = {}
    for mrn in mrn_list:
        ordered[mrn] = grouped_chunks.get(mrn, placeholder_chunk)
    return ordered


async def save_results_to_csv(chunks: list, question: str):
    """Save search results to CSV in the background."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        if not chunks:
            return
        output_dir = Path.home() / "vector_search_results"
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / f"results_{timestamp}.csv"

        def save():
            df = pd.DataFrame([{"mrn": d["mrn"], "note_id": d["note_id"]} for d in chunks])
            df.insert(0, "question", question)
            df.to_csv(filepath, index=False)
            logger.info(f"Results saved to {filepath} ({len(df)} records)")

        await asyncio.get_event_loop().run_in_executor(None, save)
    except Exception as e:
        logger.error(f"Error saving results: {e}")


async def save_cohort_to_csv(include_mrns: list, exclude_mrns: list):
    """Save cohort workspace MRNs to CSV files."""
    try:
        output_dir = Path.home() / "vector_search_results"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        def save():
            for label, mrns in [("include", include_mrns), ("exclude", exclude_mrns)]:
                path = output_dir / f"{label}_{timestamp}.csv"
                with open(path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["MRN"])
                    for mrn in mrns:
                        writer.writerow([mrn])
            return (
                str(output_dir / f"include_{timestamp}.csv"),
                str(output_dir / f"exclude_{timestamp}.csv"),
            )

        return await asyncio.get_event_loop().run_in_executor(None, save)
    except Exception:
        return None, None


def _do_search(query, query_prefix, **filter_kwargs):
    """Synchronous search: embed query, find neighbors, return chunk IDs."""
    global _embedding_model, _embedding_tokenizer

    instruction = "Given a question, retrieve relevant passages that answer the question."
    query_vec = embed_query(
        query,
        _embedding_model,
        _embedding_tokenizer,
        instruction=instruction,
        use_instruction=query_prefix,
    )

    namespace_filters, numeric_filters = build_namespace_filters(**filter_kwargs)
    results = find_neighbors(
        query_vec,
        num_neighbors=filter_kwargs.get("retrieval_limit", 20),
        per_crowding_attribute_neighbor_count=filter_kwargs.get(
            "per_crowding_attribute_neighbor_count"
        ),
        namespace_filters=namespace_filters,
        numeric_filters=numeric_filters,
    )
    return results


@app.get("/", response_class=HTMLResponse)
async def form(
    request: Request,
    background_tasks: BackgroundTasks,
    question: str = "",
    n_notes: str = "",
    crowding_neighbor_count: str = "",
    start_date: str = "",
    end_date: str = "",
    query_prefix: str = "",
    save_results: str = "",
    mrns_exclude: str = "",
    mrns: str = "",
    mrns_user: str = "",
    mrns_exclude_user: str = "",
    save_cohort_action: str = "",
):
    chunks, answer, message, save_message = [], "", "", ""
    options = get_options()
    grouped_chunks = {}
    len_retrieved, len_filtered = 0, 0

    css_data_url = embed_static_file(BASE_DIR / "static" / "style.css", "text/css")
    js_data_url = embed_static_file(BASE_DIR / "static" / "script.js", "application/javascript")

    # Cohort save action (no search)
    if save_cohort_action == "yes":
        include = [m.strip() for m in re.split(r"[,\s]+", mrns) if m.strip()]
        exclude = [m.strip() for m in re.split(r"[,\s]+", mrns_exclude) if m.strip()]
        if include or exclude:
            inc_path, exc_path = await save_cohort_to_csv(include, exclude)
            if inc_path:
                message = f"Cohort saved at {inc_path}"
                save_message = message
        else:
            message = "No MRNs to save"

        return templates.TemplateResponse("index.html", {
            "request": request, "mrns_user": mrns_user,
            "mrns_exclude_user": mrns_exclude_user, "question": question,
            "grouped_chunks": {}, "answer": answer, "message": message,
            "save_message": save_message, "options": options,
            "has_results": False, "style_data": css_data_url, "script_data": js_data_url,
        })

    # Search flow
    if question.strip():
        if mem_map is None and mm_index is None:
            return templates.TemplateResponse("index.html", {
                "request": request, "mrns_user": mrns_user,
                "mrns_exclude_user": mrns_exclude_user, "question": question,
                "grouped_chunks": [], "answer": "",
                "message": "Unable to fetch allowed note IDs for this project",
                "save_message": "", "options": options, "has_results": False,
                "style_data": css_data_url, "script_data": js_data_url,
            })

        combined_mrns = ",".join(filter(None, [mrns, mrns_user]))
        combined_exclude = ",".join(filter(None, [mrns_exclude, mrns_exclude_user]))

        mrn_list = [m.strip() for m in re.split(r"[,\s]+", combined_mrns) if m.strip()]
        mrn_exclude_list = [m.strip() for m in re.split(r"[,\s]+", combined_exclude) if m.strip()]

        mrn_list_allow = [str(m).zfill(8) for m in mrn_list]
        mrn_list_deny = [str(m).zfill(8) for m in mrn_exclude_list]

        try:
            retrieval_limit = int(n_notes) if n_notes.strip() else 3
        except ValueError:
            retrieval_limit = 3

        # Parse metadata filters
        query_params = request.query_params
        filter_kwargs = {}
        if mrn_list_allow:
            filter_kwargs["mrn_list_allow"] = mrn_list_allow
        if mrn_list_deny:
            filter_kwargs["mrn_list_deny"] = mrn_list_deny
        if start_date:
            filter_kwargs["start_date"] = convert_to_epoch_ts(start_date)
        if end_date:
            filter_kwargs["end_date"] = convert_to_epoch_ts(end_date)

        for param_name in [
            "note_category", "encounter_type", "department",
            "specialty", "author_type", "author_name",
        ]:
            for suffix in ("include", "exclude"):
                values = query_params.getlist(f"{param_name}_{suffix}")
                if values:
                    filter_kwargs[f"{param_name}_{suffix}"] = [
                        x.strip() for v in values for x in v.split(";") if x.strip()
                    ]

        if crowding_neighbor_count.strip():
            try:
                filter_kwargs["per_crowding_attribute_neighbor_count"] = int(crowding_neighbor_count)
            except ValueError:
                pass

        filter_kwargs["retrieval_limit"] = retrieval_limit

        try:
            loop = asyncio.get_event_loop()
            chunk_ids = await loop.run_in_executor(
                None,
                lambda: _do_search(question, query_prefix == "yes", **filter_kwargs),
            )

            # Fetch notes from metadata store
            note_map = defaultdict(list)
            for note_id_full, distance in chunk_ids:
                parts = note_id_full.split("_", 1)
                note_id = parts[0]
                chunk_idx = int(parts[1]) if len(parts) > 1 else 0
                note_map[note_id].append((chunk_idx, distance))

            # Filter by access control
            allowed_mask = bq_service.contains_note(mem_map, mm_index, list(note_map.keys()))
            filtered_map = {
                nid: note_map[nid]
                for nid, ok in zip(note_map.keys(), allowed_mask)
                if ok
            }
            len_retrieved = len(note_map)
            len_filtered = len(filtered_map)

            # Fetch from BigTable
            from google.cloud.bigtable.row_set import RowSet
            from clinical_semantic_search.services.metadata_store import build_row_key, _get_table
            import json as _json

            table = _get_table()
            row_set = RowSet()
            for nid in filtered_map:
                row_set.add_row_key(build_row_key(nid))

            rows = table.read_rows(row_set=row_set)
            chunks = []
            for row in rows:
                row_data = {
                    col.decode(): cells[0].value.decode()
                    for cf, cols in row.cells.items()
                    for col, cells in cols.items()
                }
                nid = str(row_data["note_id"])
                if nid not in filtered_map:
                    continue
                try:
                    chunk_indices = _json.loads(row_data["chunk_indices"])
                except (KeyError, _json.JSONDecodeError):
                    continue
                selected = [
                    chunk_indices[ci] for ci, _ in filtered_map[nid]
                    if ci < len(chunk_indices)
                ]
                distances = [
                    d for ci, d in filtered_map[nid]
                    if ci < len(chunk_indices)
                ]
                chunks.append({**row_data, "selected_indices": selected, "distances": distances})

            if save_results == "yes" and chunks:
                background_tasks.add_task(save_results_to_csv, chunks, question)

            grouped_chunks = group_chunks_by_mrn_and_distance(chunks)

            if mrn_list:
                grouped_chunks = reorder_chunks(grouped_chunks, mrn_list)

            # Audit log
            log_params = {"query": question, "retrieval_limit": retrieval_limit}
            log_params.update(filter_kwargs)
            background_tasks.add_task(
                clog.save_user_logs_async, log_params, chunks, app_user, app_project
            )

            del chunks
            gc.collect()

        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            answer = "An error occurred while processing your request."
            grouped_chunks = {}

    has_results = bool(question.strip() and len(grouped_chunks) > 0)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "mrns_user": mrns_user,
        "mrns_exclude_user": mrns_exclude_user,
        "question": question,
        "grouped_chunks": grouped_chunks,
        "count_retrieved_notes": len_retrieved,
        "count_filtered_notes": len_filtered,
        "answer": answer,
        "message": message,
        "save_message": save_message,
        "options": options,
        "has_results": has_results,
        "style_data": css_data_url,
        "script_data": js_data_url,
    })


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bt_project_id", required=True)
    parser.add_argument("--bt_instance", required=True)
    parser.add_argument("--bt_table_id", required=True)
    parser.add_argument("--endpoint_name", required=True)
    parser.add_argument("--ip_address", required=True)
    parser.add_argument("--deployed_index", required=True)
    parser.add_argument("--embedding_model_path", required=True)
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def configure_and_run():
    """Entry point for the web application."""
    args = parse_args()
    app.state.bt_project_id = args.bt_project_id
    app.state.bt_instance = args.bt_instance
    app.state.bt_table_id = args.bt_table_id
    app.state.endpoint_name = args.endpoint_name
    app.state.ip_address = args.ip_address
    app.state.deployed_index = args.deployed_index
    app.state.embedding_model_path = args.embedding_model_path
    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    configure_and_run()
