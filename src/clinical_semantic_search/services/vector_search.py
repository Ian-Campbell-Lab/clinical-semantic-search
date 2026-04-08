"""
Vector search service -- reference implementation using Google Cloud
Vertex AI Vector Search (Matching Engine).

This module handles:
- Initializing the Vertex AI endpoint connection
- Building namespace (string) and numeric filters for metadata-filtered search
- Executing nearest-neighbor queries against the deployed index

PORTING NOTE: Replace this module with your vector database client
(e.g., pgvector, Qdrant, Weaviate).  The key contract is that
``find_neighbors()`` accepts an embedding vector and returns a list of
``(chunk_id, distance)`` tuples.
"""

import gc
import logging
from typing import List, Optional, Tuple

import torch.nn.functional as F
from google.cloud import aiplatform

from clinical_semantic_search.config import get_settings
from clinical_semantic_search.core.embedding import embed_query, format_query

logger = logging.getLogger(__name__)

# Cached endpoint singleton
_vertex_endpoint = None


def get_vertex_endpoint() -> aiplatform.MatchingEngineIndexEndpoint:
    """Return a cached Vertex AI index endpoint connection."""
    global _vertex_endpoint
    if _vertex_endpoint is None:
        settings = get_settings()
        aiplatform.init(project=settings.vector_search_project, location=settings.cloud_region)
        _vertex_endpoint = aiplatform.MatchingEngineIndexEndpoint(
            index_endpoint_name=settings.index_endpoint_path
        )
        if settings.index_psc_ip:
            _vertex_endpoint.private_service_connect_ip_address = settings.index_psc_ip
    return _vertex_endpoint


def build_namespace_filters(
    mrn_list_allow: Optional[List[str]] = None,
    mrn_list_deny: Optional[List[str]] = None,
    note_category_include: Optional[List[str]] = None,
    note_category_exclude: Optional[List[str]] = None,
    encounter_type_include: Optional[List[str]] = None,
    encounter_type_exclude: Optional[List[str]] = None,
    department_include: Optional[List[str]] = None,
    department_exclude: Optional[List[str]] = None,
    specialty_include: Optional[List[str]] = None,
    specialty_exclude: Optional[List[str]] = None,
    author_type_include: Optional[List[str]] = None,
    author_type_exclude: Optional[List[str]] = None,
    author_name_include: Optional[List[str]] = None,
    author_name_exclude: Optional[List[str]] = None,
    start_date: Optional[int] = None,
    end_date: Optional[int] = None,
) -> Tuple[list, list]:
    """Build Vertex AI namespace and numeric filter objects.

    Returns
    -------
    (namespace_filters, numeric_filters) -- lists to pass to ``find_neighbors()``.
    """
    Namespace = aiplatform.matching_engine.matching_engine_index_endpoint.Namespace
    NumericNamespace = aiplatform.matching_engine.matching_engine_index_endpoint.NumericNamespace

    filters = []
    numeric_filters = []

    filter_configs = [
        ("mrn", mrn_list_allow or [], mrn_list_deny or []),
        ("note_category", note_category_include or [], note_category_exclude or []),
        ("encounter_type", encounter_type_include or [], encounter_type_exclude or []),
        ("department", department_include or [], department_exclude or []),
        ("specialty", specialty_include or [], specialty_exclude or []),
        ("author_type", author_type_include or [], author_type_exclude or []),
        ("author_name", author_name_include or [], author_name_exclude or []),
    ]

    for namespace, allow_list, deny_list in filter_configs:
        if allow_list or deny_list:
            filters.append(Namespace(namespace, allow_list, deny_list))

    if start_date is not None:
        numeric_filters.append(
            NumericNamespace(name="utc_epoch_sec", value_int=start_date, op="GREATER_EQUAL")
        )
    if end_date is not None:
        numeric_filters.append(
            NumericNamespace(name="utc_epoch_sec", value_int=end_date, op="LESS_EQUAL")
        )

    return filters, numeric_filters


def find_neighbors(
    query_embedding: list,
    num_neighbors: int = 20,
    per_crowding_attribute_neighbor_count: Optional[int] = None,
    namespace_filters: Optional[list] = None,
    numeric_filters: Optional[list] = None,
) -> List[Tuple[str, float]]:
    """Execute a nearest-neighbor search against the deployed index.

    Parameters
    ----------
    query_embedding : list
        The query vector.
    num_neighbors : int
        Number of neighbors to retrieve.
    per_crowding_attribute_neighbor_count : int, optional
        Maximum results per crowding attribute (limits results per patient).
    namespace_filters : list, optional
        Vertex AI namespace filter objects.
    numeric_filters : list, optional
        Vertex AI numeric filter objects.

    Returns
    -------
    List of (chunk_id, distance) tuples, sorted by descending similarity.
    """
    settings = get_settings()
    endpoint = get_vertex_endpoint()

    search_params = {
        "deployed_index_id": settings.deployed_index_id,
        "queries": [query_embedding],
        "num_neighbors": num_neighbors,
        "filter": namespace_filters or [],
        "numeric_filter": numeric_filters or [],
    }

    if per_crowding_attribute_neighbor_count:
        search_params["per_crowding_attribute_neighbor_count"] = per_crowding_attribute_neighbor_count

    response = endpoint.find_neighbors(**search_params)
    results = [(n.id, n.distance) for n in response[0]]

    del search_params, response
    gc.collect()

    return results
