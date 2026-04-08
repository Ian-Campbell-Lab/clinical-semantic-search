"""
Centralized configuration for clinical-semantic-search.

All values are read from environment variables (or a .env file).
No institution-specific defaults are included; every deployment must
provide its own values via .env or the shell environment.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── Vector Search ────────────────────────────────────────────────
    vector_search_project: str = Field(
        ..., description="GCP project ID that hosts the vector search index"
    )
    cloud_region: str = Field(
        ..., description="Cloud region for Vertex AI resources (e.g. us-east4)"
    )
    index_endpoint_path: str = Field(
        ...,
        description=(
            "Full resource name of the Vertex AI index endpoint, e.g. "
            "projects/<number>/locations/<region>/indexEndpoints/<id>"
        ),
    )
    index_psc_ip: Optional[str] = Field(
        None,
        description="Private Service Connect IP for the index endpoint (if applicable)",
    )
    deployed_index_id: str = Field(
        ..., description="ID of the deployed index on the endpoint"
    )

    # ── Metadata Store (BigTable) ────────────────────────────────────
    metadata_project: str = Field(
        ..., description="GCP project ID that hosts the metadata store"
    )
    bigtable_instance: str = Field(
        ..., description="Cloud BigTable instance name"
    )
    bigtable_table: str = Field(
        default="notes", description="BigTable table name for clinical notes"
    )

    # ── Embedding Model ──────────────────────────────────────────────
    embedding_model_path: str = Field(
        ...,
        description="Local filesystem path to the HuggingFace embedding model",
    )
    embedding_instruction: str = Field(
        default="Given a medical query from a healthcare provider, retrieve relevant passages that answer the query",
        description="Instruction prefix for instruction-tuned embedding models",
    )

    # ── Access Control ───────────────────────────────────────────────
    access_control_project: Optional[str] = Field(
        None,
        description="GCP project ID used for BigQuery-based access control (if applicable)",
    )

    # ── Timezone ─────────────────────────────────────────────────────
    timezone: str = Field(
        default="America/New_York",
        description="Timezone for converting date filters to UTC epoch seconds",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
