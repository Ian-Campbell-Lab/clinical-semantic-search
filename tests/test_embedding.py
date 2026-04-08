"""Tests for core/embedding.py."""

import pytest

from clinical_semantic_search.core.embedding import format_query


class TestFormatQuery:
    def test_with_instruction(self):
        """Should prepend instruction prefix."""
        result = format_query("What is the diagnosis?", instruction="Find relevant notes")
        assert result == "Instruct: Find relevant notes\nQuery: What is the diagnosis?"

    def test_without_instruction(self):
        """With use_instruction=False, should return raw query."""
        result = format_query("What is the diagnosis?", use_instruction=False)
        assert result == "What is the diagnosis?"

    def test_default_instruction(self):
        """Default instruction should be medical-domain."""
        result = format_query("test query")
        assert "medical query" in result.lower() or "healthcare" in result.lower()
        assert "test query" in result
