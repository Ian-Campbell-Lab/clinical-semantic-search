#!/usr/bin/env python3
"""
Minimal end-to-end search example.

Demonstrates the core search workflow:
1. Load the embedding model
2. Embed a query
3. Search the vector index
4. Fetch and display matching notes

Requires a populated .env file (see .env.example).
"""

import torch

from clinical_semantic_search.config import get_settings
from clinical_semantic_search.core.embedding import embed_query, load_embedding_model
from clinical_semantic_search.core.formatting import format_metadata
from clinical_semantic_search.services.metadata_store import get_notes
from clinical_semantic_search.services.vector_search import (
    build_namespace_filters,
    find_neighbors,
)

# For CPU inference, set thread count for optimal performance
torch.set_num_threads(8)
torch.set_num_interop_threads(1)


def main():
    settings = get_settings()

    # 1. Load embedding model
    print("Loading embedding model...")
    model, tokenizer = load_embedding_model(settings.embedding_model_path)

    # 2. Embed a query
    query = "Does this patient have a genetic condition?"
    print(f"Query: {query}")
    query_vec = embed_query(
        query, model, tokenizer,
        instruction=settings.embedding_instruction,
    )

    # 3. Search the vector index (optionally filter by MRN)
    #    To filter by patient: build_namespace_filters(mrn_list_allow=["12345678"])
    filters, numeric_filters = build_namespace_filters()
    results = find_neighbors(
        query_vec,
        num_neighbors=5,
        per_crowding_attribute_neighbor_count=1,  # 1 result per patient
        namespace_filters=filters,
        numeric_filters=numeric_filters,
    )

    print(f"\nFound {len(results)} results")

    # 4. Fetch note text from the metadata store
    note_ids = list({chunk_id.split("_")[0] for chunk_id, _ in results})
    notes = get_notes(note_ids)

    # 5. Format and display
    formatted = format_metadata(notes, include_patient_metadata=True)
    for block in formatted:
        print(block)
        print("-" * 60)


if __name__ == "__main__":
    main()
