"""Tests for core/formatting.py."""

import pytest

from clinical_semantic_search.core.formatting import format_metadata


class TestFormatMetadata:
    def test_single_note(self):
        """Should format a single note with metadata headers."""
        notes = [{
            "note_id": "123",
            "mrn": "00012345",
            "first_name": "John",
            "last_name": "Doe",
            "birth_date": "01/15/2010",
            "note_category": "Progress Notes",
            "department": "Cardiology",
            "note_text": "Patient is doing well.",
        }]

        result = format_metadata(notes, include_patient_metadata=True)
        # Should have patient metadata block + note block
        assert len(result) == 2
        assert "John Doe" in result[0]
        assert "00012345" in result[0]
        assert "Progress Notes" in result[1]
        assert "Patient is doing well." in result[1]

    def test_no_patient_metadata(self):
        """With include_patient_metadata=False, should skip patient header."""
        notes = [{
            "note_id": "123",
            "mrn": "00012345",
            "note_text": "Some text.",
        }]

        result = format_metadata(notes, include_patient_metadata=False)
        assert len(result) == 1
        assert "Patient Metadata" not in result[0]

    def test_multiple_notes(self):
        """Should format each note separately."""
        notes = [
            {"note_id": "1", "note_text": "First note.", "mrn": "123"},
            {"note_id": "2", "note_text": "Second note.", "mrn": "123"},
        ]

        result = format_metadata(notes, include_patient_metadata=False)
        assert len(result) == 2
        assert "First note." in result[0]
        assert "Second note." in result[1]

    def test_missing_optional_fields(self):
        """Should handle notes with missing optional metadata."""
        notes = [{"note_id": "1", "note_text": "Minimal note."}]
        result = format_metadata(notes, include_patient_metadata=False)
        assert len(result) == 1
        assert "Minimal note." in result[0]

    def test_empty_list(self):
        """Empty input should return empty output."""
        result = format_metadata([], include_patient_metadata=True)
        assert result == []

    def test_note_without_text_skipped(self):
        """Notes without note_text should not produce output."""
        notes = [{"note_id": "1", "department": "Genetics"}]
        result = format_metadata(notes, include_patient_metadata=False)
        assert result == []

    def test_patient_metadata_uses_first_note(self):
        """Patient metadata should come from the first note only."""
        notes = [
            {"note_id": "1", "mrn": "AAA", "first_name": "Alice", "note_text": "Note 1."},
            {"note_id": "2", "mrn": "BBB", "first_name": "Bob", "note_text": "Note 2."},
        ]
        result = format_metadata(notes, include_patient_metadata=True)
        # Patient header should show Alice, not Bob
        assert "Alice" in result[0]
        assert "Bob" not in result[0]
