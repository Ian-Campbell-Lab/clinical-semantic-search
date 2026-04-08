"""Tests for core/chunking.py."""

import pandas as pd
import pytest

from clinical_semantic_search.core.chunking import split_note, init_worker


# Use a small, publicly available tokenizer for testing
TEST_TOKENIZER = "bert-base-uncased"


@pytest.fixture(autouse=True, scope="module")
def _init_splitter():
    """Initialize the global text_splitter for all tests in this module."""
    init_worker(TEST_TOKENIZER, chunk_size=50, chunk_overlap=10)


class TestSplitNote:
    def test_short_text_single_chunk(self):
        """A short text should produce a single chunk."""
        result = split_note((0, "This is a short clinical note."))
        assert len(result["chunks"]) == 1
        assert result["chunks"][0] == "This is a short clinical note."
        assert result["indices"][0] == (0, len("This is a short clinical note."))

    def test_long_text_multiple_chunks(self):
        """A long text should produce multiple chunks with valid offsets."""
        text = "The patient presents with fever. " * 50
        result = split_note((0, text))
        assert len(result["chunks"]) > 1

        # Verify all offsets point to the correct text
        for chunk, (start, end) in zip(result["chunks"], result["indices"]):
            assert text[start:end] == chunk

    def test_indices_are_non_overlapping_starts(self):
        """Chunk start positions should be monotonically increasing."""
        text = "Word " * 200
        result = split_note((0, text))
        starts = [s for s, e in result["indices"]]
        assert starts == sorted(starts)

    def test_preserves_index(self):
        """The returned Series should have the correct name (row index)."""
        result = split_note((42, "A note."))
        assert result.name == 42

    def test_empty_string(self):
        """An empty string should produce an empty chunks list."""
        result = split_note((0, ""))
        assert result["chunks"] == []
        assert result["indices"] == []


class TestParallelSplitNotes:
    def test_basic_parallel(self):
        """parallel_split_notes should produce chunks for each row."""
        from clinical_semantic_search.core.chunking import parallel_split_notes

        df = pd.DataFrame({
            "note_text": [
                "Patient has a cough.",
                "Follow up visit for diabetes management and medication review.",
            ]
        })
        result = parallel_split_notes(df, TEST_TOKENIZER, chunk_size=50, chunk_overlap=10)
        assert "chunks" in result.columns
        assert "indices" in result.columns
        assert len(result) == 2
