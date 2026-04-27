"""Unit tests for the encoder-decoder answer scorer.

The tests mock the tokenizer and seq2seq model to focus on:

  * score_answer returns -loss,
  * padding token ids in the labels are replaced with -100 (so they
    don't contribute to the per-token log-likelihood),
  * the encoder receives the question's ids and the decoder labels
    carry the answer's ids,
  * rank_answers sorts descending,
  * pick_best_answer returns the highest-scoring candidate.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import torch

import encoder_decoder_answer_scorer as mod


# --------------------------------------------------------------------- helpers


class _FakeBatch:
    def __init__(self, input_ids: torch.Tensor):
        self.input_ids = input_ids
        self.attention_mask = torch.ones_like(input_ids)

    def to(self, device):
        return self


class _FakeSeq2SeqTokenizer:
    """Emits configured id sequences; the answer tokenisation can include
    a trailing pad id to exercise the pad-masking branch."""

    def __init__(self, text_to_ids: dict[str, list[int]], pad_token_id: int = 0):
        self._text_to_ids = text_to_ids
        self.pad_token_id = pad_token_id

    def __call__(self, text, return_tensors="pt"):
        ids = torch.tensor([self._text_to_ids[text]], dtype=torch.long)
        return _FakeBatch(ids)


class _FakeOutput:
    def __init__(self, loss: float):
        self.loss = torch.tensor(loss)


class _FakeSeq2SeqModel:
    def __init__(self, loss: float = 0.3):
        self.device = torch.device("cpu")
        self._loss = loss
        self.captured: dict[str, torch.Tensor] = {}

    def __call__(self, input_ids, attention_mask, labels):
        self.captured = {
            "input_ids": input_ids.clone(),
            "attention_mask": attention_mask.clone(),
            "labels": labels.clone(),
        }
        return _FakeOutput(self._loss)


# ---------------------------------------------------------------------- tests


def test_score_answer_returns_negative_loss():
    tok = _FakeSeq2SeqTokenizer({"q": [10, 11, 12], "a": [20, 21]})
    model = _FakeSeq2SeqModel(loss=0.42)

    score = mod.score_answer(model, tok, "q", "a")

    assert score == pytest.approx(-0.42)


def test_pad_tokens_in_labels_are_replaced_with_minus_100():
    # Answer token 0 is the pad id, so it must be masked in labels.
    tok = _FakeSeq2SeqTokenizer(
        {"q": [10, 11], "a": [20, 0, 21, 0]}, pad_token_id=0
    )
    model = _FakeSeq2SeqModel()

    mod.score_answer(model, tok, "q", "a")

    labels = model.captured["labels"]
    assert labels.tolist() == [[20, -100, 21, -100]]


def test_encoder_and_decoder_receive_expected_ids():
    tok = _FakeSeq2SeqTokenizer({"q": [10, 11, 12], "a": [20, 21]})
    model = _FakeSeq2SeqModel()

    mod.score_answer(model, tok, "q", "a")

    assert model.captured["input_ids"].tolist() == [[10, 11, 12]]
    assert model.captured["labels"].tolist() == [[20, 21]]


def test_rank_answers_sorts_descending_by_score():
    with patch.object(mod, "score_answer", side_effect=[-2.5, -0.1, -1.0]):
        ranked = mod.rank_answers(None, None, "q", ["c1", "c2", "c3"])

    assert [r.answer for r in ranked] == ["c2", "c3", "c1"]
    assert [r.score for r in ranked] == [-0.1, -1.0, -2.5]


def test_pick_best_answer_returns_top():
    with patch.object(mod, "score_answer", side_effect=[-1.0, -0.2, -3.0]):
        best = mod.pick_best_answer(None, None, "q", ["a", "b", "c"])

    assert best.answer == "b"
    assert best.score == pytest.approx(-0.2)


def test_rank_answers_use_kv_cache_runs_encoder_once_and_scores_each_candidate():
    with patch.object(mod, "_question_state", return_value={"fake": "state"}) as q_state, \
         patch.object(mod, "_log_prob_cached", side_effect=[-0.5, -0.1, -0.8]) as p_score:
        ranked = mod.rank_answers(
            None, None, "q", ["a", "b", "c"], use_kv_cache=True
        )

    assert q_state.call_count == 1
    assert p_score.call_count == 3
    assert [r.answer for r in ranked] == ["b", "a", "c"]


def test_rank_answers_use_kv_cache_with_pmi_caches_both_encoder_inputs():
    # 2 encoder runs (question + neutral), 2 decoder runs per candidate.
    scores = [
        -0.3, -1.0,  # a: cond, uncond -> 0.7
        -0.2, -1.5,  # b: cond, uncond -> 1.3
        -0.1, -0.5,  # c: cond, uncond -> 0.4
    ]
    with patch.object(mod, "_question_state", return_value={"fake": "state"}) as q_state, \
         patch.object(mod, "_log_prob_cached", side_effect=scores) as p_score:
        ranked = mod.rank_answers(
            None, None, "q", ["a", "b", "c"], use_pimi=True, use_kv_cache=True
        )

    assert q_state.call_count == 2
    assert p_score.call_count == 6
    assert [r.answer for r in ranked] == ["b", "a", "c"]
    assert [r.score for r in ranked] == pytest.approx([1.3, 0.7, 0.4])
