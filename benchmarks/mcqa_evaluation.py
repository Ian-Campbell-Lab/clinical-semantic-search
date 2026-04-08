#!/usr/bin/env python3
"""
MCQA evaluation utilities for benchmarking retrieval quality.

This module provides functions for:
- Preprocessing MCQA benchmark datasets
- Constructing RAG prompts with retrieved note context
- Computing accuracy metrics

These utilities are used to evaluate the end-to-end pipeline
(retrieval + LLM reasoning) on physician-authored multiple-choice
questions about specific patients.

Usage as a library:
    from benchmarks.mcqa_evaluation import create_rag_prompt, preprocess_mcqa
"""

import json
import random
from typing import Optional


def create_rag_prompt(
    question: str,
    choices: dict,
    retrieved_texts: list[str],
    instruction: str = (
        "You are a medical assistant. Using the provided clinical notes, "
        "answer the multiple choice question. Respond with ONLY a JSON "
        'object: {"answer": "<letter>"}'
    ),
) -> str:
    """Build a RAG prompt combining retrieved notes with an MCQA question.

    Parameters
    ----------
    question : str
        The clinical question text.
    choices : dict
        Mapping of choice letters to answer text, e.g. {"A": "...", "B": "..."}.
    retrieved_texts : list[str]
        Formatted note text blocks from the retrieval system.
    instruction : str
        System instruction for the LLM.

    Returns
    -------
    str -- the complete prompt ready for LLM inference.
    """
    # Shuffle choice order to reduce position bias
    items = list(choices.items())
    random.shuffle(items)

    context = "\n\n---\n\n".join(retrieved_texts)
    choices_text = "\n".join(f"{letter}. {text}" for letter, text in items)

    prompt = (
        f"{instruction}\n\n"
        f"## Clinical Notes\n{context}\n\n"
        f"## Question\n{question}\n\n"
        f"## Choices\n{choices_text}\n\n"
        "Respond with ONLY a JSON object containing your answer."
    )
    return prompt


def preprocess_mcqa(
    mcqa_path: str,
    predictions_path: Optional[str] = None,
    k: int = 20,
) -> list[dict]:
    """Load and preprocess an MCQA benchmark dataset.

    Parameters
    ----------
    mcqa_path : str
        Path to the MCQA JSONL file.
    predictions_path : str, optional
        Path to a predictions file containing retrieved_texts per question.
    k : int
        Number of retrieved texts to include (truncates to top-k).

    Returns
    -------
    list[dict] with keys: question, choices, correct_answer, mrn,
    retrieved_texts (if predictions_path provided), prompt_RAG.
    """
    questions = []
    with open(mcqa_path, "r") as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))

    if predictions_path:
        with open(predictions_path, "r") as f:
            predictions = json.load(f)

        # Merge retrieved texts into questions
        pred_lookup = {p.get("question_id", p.get("mrn", i)): p for i, p in enumerate(predictions)}
        for q in questions:
            qid = q.get("question_id", q.get("mrn"))
            if qid in pred_lookup:
                texts = pred_lookup[qid].get("retrieved_texts", [])
                q["retrieved_texts"] = texts[:k]

    # Build RAG prompts
    for q in questions:
        if "retrieved_texts" in q:
            q["prompt_RAG"] = create_rag_prompt(
                q["question"], q["choices"], q["retrieved_texts"]
            )

    return questions


def compute_accuracy(predictions: list[dict], answer_key: str = "correct_answer") -> dict:
    """Compute accuracy and per-category breakdown.

    Parameters
    ----------
    predictions : list[dict]
        Each must have ``predicted_answer`` and the ``answer_key`` field.
    answer_key : str
        Key for the correct answer in each dict.

    Returns
    -------
    dict with ``accuracy``, ``correct``, ``total``, and optionally
    ``by_category`` if a ``category`` field is present.
    """
    correct = sum(1 for p in predictions if p.get("predicted_answer") == p.get(answer_key))
    total = len(predictions)

    result = {
        "accuracy": correct / total if total > 0 else 0.0,
        "correct": correct,
        "total": total,
    }

    # Per-category breakdown if available
    categories = set(p.get("category") for p in predictions if p.get("category"))
    if categories:
        by_cat = {}
        for cat in categories:
            cat_preds = [p for p in predictions if p.get("category") == cat]
            cat_correct = sum(1 for p in cat_preds if p.get("predicted_answer") == p.get(answer_key))
            by_cat[cat] = {"accuracy": cat_correct / len(cat_preds), "n": len(cat_preds)}
        result["by_category"] = by_cat

    return result
