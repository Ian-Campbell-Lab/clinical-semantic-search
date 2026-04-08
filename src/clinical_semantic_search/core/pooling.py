"""
Pooling strategies for transformer hidden states.

Provides two common approaches for collapsing a sequence of token embeddings
into a single fixed-length vector:

- ``average_pool``: masked mean over non-padding tokens.
- ``last_token_pool``: takes the last non-padding token (used by Qwen3 and
  other causal embedding models with left-padding).
"""

import torch
from torch import Tensor


def average_pool(last_hidden_states: Tensor, attention_mask: Tensor) -> Tensor:
    """Masked mean pooling over token embeddings.

    Zeros out padding positions before computing the mean, so that only
    real tokens contribute to the final vector.
    """
    last_hidden = last_hidden_states.masked_fill(~attention_mask[..., None].bool(), 0.0)
    return last_hidden.sum(dim=1) / attention_mask.sum(dim=1)[..., None]


def last_token_pool(last_hidden_states: Tensor, attention_mask: Tensor) -> Tensor:
    """Pool the embedding of the last non-padding token.

    Handles both left-padded inputs (returns the final column) and
    right-padded inputs (finds the last real token per sequence).
    """
    left_padding = attention_mask[:, -1].sum() == attention_mask.shape[0]
    if left_padding:
        return last_hidden_states[:, -1]
    else:
        sequence_lengths = attention_mask.sum(dim=1) - 1
        batch_size = last_hidden_states.shape[0]
        return last_hidden_states[
            torch.arange(batch_size, device=last_hidden_states.device),
            sequence_lengths,
        ]
