"""Tests for core/pooling.py."""

import torch
import pytest

from clinical_semantic_search.core.pooling import average_pool, last_token_pool


class TestAveragePool:
    def test_basic(self):
        """Average pooling should compute masked mean."""
        # batch=1, seq=3, hidden=2
        hidden = torch.tensor([[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]])
        mask = torch.tensor([[1, 1, 0]])  # last token is padding

        result = average_pool(hidden, mask)
        # Expected: mean of first two tokens = ([1,2] + [3,4]) / 2 = [2, 3]
        assert result.shape == (1, 2)
        assert torch.allclose(result, torch.tensor([[2.0, 3.0]]))

    def test_all_tokens(self):
        """With no padding, should be a simple mean."""
        hidden = torch.tensor([[[2.0, 4.0], [6.0, 8.0]]])
        mask = torch.tensor([[1, 1]])

        result = average_pool(hidden, mask)
        assert torch.allclose(result, torch.tensor([[4.0, 6.0]]))

    def test_batch(self):
        """Should handle multiple sequences in a batch."""
        hidden = torch.tensor([
            [[1.0, 0.0], [2.0, 0.0], [0.0, 0.0]],
            [[3.0, 0.0], [0.0, 0.0], [0.0, 0.0]],
        ])
        mask = torch.tensor([[1, 1, 0], [1, 0, 0]])

        result = average_pool(hidden, mask)
        assert result.shape == (2, 2)
        assert torch.allclose(result[0], torch.tensor([1.5, 0.0]))
        assert torch.allclose(result[1], torch.tensor([3.0, 0.0]))


class TestLastTokenPool:
    def test_left_padded(self):
        """Left-padded input: last column should be returned."""
        hidden = torch.tensor([[[0.0, 0.0], [1.0, 2.0], [3.0, 4.0]]])
        mask = torch.tensor([[0, 1, 1]])  # left-padded

        result = last_token_pool(hidden, mask)
        assert torch.allclose(result, torch.tensor([[3.0, 4.0]]))

    def test_right_padded(self):
        """Right-padded input: last real token should be returned."""
        hidden = torch.tensor([[[1.0, 2.0], [3.0, 4.0], [0.0, 0.0]]])
        mask = torch.tensor([[1, 1, 0]])

        result = last_token_pool(hidden, mask)
        assert torch.allclose(result, torch.tensor([[3.0, 4.0]]))

    def test_batch_right_padded(self):
        """Batch with varying sequence lengths."""
        hidden = torch.tensor([
            [[1.0, 0.0], [2.0, 0.0], [0.0, 0.0]],
            [[3.0, 0.0], [4.0, 0.0], [5.0, 0.0]],
        ])
        mask = torch.tensor([[1, 1, 0], [1, 1, 1]])

        result = last_token_pool(hidden, mask)
        assert torch.allclose(result[0], torch.tensor([2.0, 0.0]))
        assert torch.allclose(result[1], torch.tensor([5.0, 0.0]))
