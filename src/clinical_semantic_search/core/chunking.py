"""
Text chunking utilities for splitting clinical notes into overlapping segments.

Uses LangChain's RecursiveCharacterTextSplitter with a HuggingFace tokenizer
to split notes into chunks of a fixed token length with overlap.  Each chunk
is accompanied by its (start_char, end_char) byte offsets into the original
note text, enabling downstream highlighting and provenance tracking.
"""

from multiprocessing import Pool, cpu_count
from typing import List, Tuple

import pandas as pd
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer

# Module-level global set by each worker process via init_worker().
text_splitter = None


def init_worker(tokenizer_path: str, chunk_size: int = 300, chunk_overlap: int = 50):
    """Initializer for multiprocessing workers.  Loads the tokenizer once per process."""
    global text_splitter
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
    text_splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
        tokenizer,
        separators=["\r\n\r\n", "\n\n", "\r\n", "\n", " "],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        is_separator_regex=False,
    )


def split_note(row_tuple: Tuple[int, str]) -> pd.Series:
    """Split a single note into chunks with character-level offsets.

    Parameters
    ----------
    row_tuple : (index, note_text)
        A tuple of the row index and the raw note text string.

    Returns
    -------
    pd.Series with keys ``chunks`` (List[str]) and ``indices`` (List[Tuple[int, int]]).
    """
    idx, text = row_tuple
    chunks: List[str] = text_splitter.split_text(text)
    indices: List[Tuple[int, int]] = []
    cursor: int = 0
    for chunk in chunks:
        start = text.find(chunk, cursor)
        if start == -1:
            start = text.find(chunk)
            if start == -1:
                raise ValueError("Chunk not found; text may have changed since splitting.")
        end = start + len(chunk)
        indices.append((start, end))
        cursor = start + 1
    return pd.Series({"chunks": chunks, "indices": indices}, name=idx)


def parallel_split_notes(
    notes: pd.DataFrame,
    tokenizer_path: str,
    chunk_size: int = 300,
    chunk_overlap: int = 50,
) -> pd.DataFrame:
    """Split all notes in a DataFrame using multiprocessing.

    Parameters
    ----------
    notes : pd.DataFrame
        Must contain a ``note_text`` column.
    tokenizer_path : str
        Path to a HuggingFace tokenizer (used for token-aware splitting).
    chunk_size : int
        Maximum chunk size in tokens.
    chunk_overlap : int
        Number of overlapping tokens between consecutive chunks.

    Returns
    -------
    pd.DataFrame with ``chunks`` and ``indices`` columns.
    """
    rows = [row for row in notes[["note_text"]].itertuples(index=True, name=None)]
    with Pool(
        processes=cpu_count(),
        initializer=init_worker,
        initargs=(tokenizer_path, chunk_size, chunk_overlap),
    ) as pool:
        results = pool.map(split_note, rows, chunksize=1000)
    return pd.concat(results, axis=1).T.reset_index(drop=True)
