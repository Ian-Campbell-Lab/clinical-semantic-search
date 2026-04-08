"""
Query embedding utilities.

Provides functions for loading an embedding model and computing a query
embedding on CPU.  The instruction prefix is configurable and defaults to
a medical-domain retrieval instruction.

This module consolidates embedding logic that was previously scattered
across multiple scripts into a single canonical implementation.
"""

import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer

from clinical_semantic_search.core.pooling import last_token_pool


def load_embedding_model(
    model_path: str,
    device: str = "cpu",
    dtype=torch.float32,
):
    """Load an embedding model and tokenizer from a local directory.

    Parameters
    ----------
    model_path : str
        Local filesystem path to a HuggingFace model directory.
    device : str
        Device to load the model onto (``"cpu"``, ``"cuda"``, etc.).
    dtype : torch.dtype
        Data type for model weights.  Use ``torch.float32`` for CPUs that
        lack hardware bfloat16 support.

    Returns
    -------
    (model, tokenizer) tuple.
    """
    model = AutoModel.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=True,
        torch_dtype=dtype,
    ).to(device).eval()

    tokenizer = AutoTokenizer.from_pretrained(model_path, padding_side="left")
    return model, tokenizer


def format_query(
    query: str,
    instruction: str = "Given a medical query from a healthcare provider, retrieve relevant passages that answer the query",
    use_instruction: bool = True,
) -> str:
    """Wrap a query string with an instruction prefix.

    Parameters
    ----------
    query : str
        The raw query text.
    instruction : str
        Task instruction for instruction-tuned embedding models.
    use_instruction : bool
        If False, return the query unchanged.
    """
    if use_instruction:
        return f"Instruct: {instruction}\nQuery: {query}"
    return query


@torch.no_grad()
def embed_query(
    query: str,
    model: AutoModel,
    tokenizer: AutoTokenizer,
    instruction: str = "Given a medical query from a healthcare provider, retrieve relevant passages that answer the query",
    use_instruction: bool = True,
) -> list:
    """Compute an L2-normalized embedding for a single query on CPU.

    Parameters
    ----------
    query : str
        Raw query text.
    model : AutoModel
        A loaded HuggingFace embedding model.
    tokenizer : AutoTokenizer
        The corresponding tokenizer.
    instruction : str
        Task instruction for instruction-tuned models.
    use_instruction : bool
        Whether to prepend the instruction prefix.

    Returns
    -------
    List[float] -- a single embedding vector as a Python list.
    """
    formatted = format_query(query, instruction, use_instruction)
    tok = tokenizer(formatted, padding="longest", truncation=True, return_tensors="pt")
    out = model(**{k: v for k, v in tok.items()})
    emb = last_token_pool(out.last_hidden_state, tok["attention_mask"])
    emb = F.normalize(emb, p=2, dim=1)
    return emb.tolist()[0]
