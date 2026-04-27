"""Unit tests for the causal-LM answer scorer.

We mock the tokenizer and model so the tests run offline and stay
focused on the scoring logic:

  * score_answer returns the negated model loss,
  * the labels tensor has prompt positions masked with -100 and
    answer positions kept (this is what makes -loss equal the
    length-normalised log-prob of the answer only),
  * rank_answers sorts candidates by score descending,
  * pick_best_answer picks the candidate with the highest score.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import torch

import llm_answer_scorer as mod


# --------------------------------------------------------------------- helpers


class _FakeBatch:
    def __init__(self, ids: torch.Tensor):
        self.input_ids = ids

    def to(self, device):  # mimic the HF BatchEncoding interface we use
        return self


class _FakeTokenizer:
    """Returns a deterministic id tensor of a configured length per input text."""

    def __init__(self, text_to_len: dict[str, int]):
        self._text_to_len = text_to_len

    def __call__(self, text, return_tensors="pt", add_special_tokens=True):
        length = self._text_to_len[text]
        ids = torch.arange(length, dtype=torch.long).unsqueeze(0)
        return _FakeBatch(ids)


class _FakeOutput:
    def __init__(self, loss: float):
        self.loss = torch.tensor(loss)


class _FakeModel:
    """Records the labels it was called with, returns a fixed loss."""

    def __init__(self, loss: float = 0.5):
        self.device = torch.device("cpu")
        self._loss = loss
        self.captured_labels: torch.Tensor | None = None
        self.captured_input_ids: torch.Tensor | None = None

    def __call__(self, input_ids, labels):
        self.captured_input_ids = input_ids.clone()
        self.captured_labels = labels.clone()
        return _FakeOutput(self._loss)


class _FakeModelSequence:
    """Returns a configured sequence of losses across successive calls
    (used to test PMI, which makes two forward passes)."""

    def __init__(self, losses: list[float]):
        self.device = torch.device("cpu")
        self._losses = list(losses)

    def __call__(self, input_ids, labels):
        return _FakeOutput(self._losses.pop(0))


# ---------------------------------------------------------------------- tests


def test_score_answer_returns_negative_loss():
    prompt = mod.build_prompt("q？")
    tok = _FakeTokenizer({prompt: 5, "A": 2})
    model = _FakeModel(loss=0.7)

    score = mod.score_answer(model, tok, "q？", "A")

    assert score == pytest.approx(-0.7)


def test_score_answer_masks_prompt_and_keeps_answer_in_labels():
    prompt = mod.build_prompt("q？")
    prompt_len, answer_len = 5, 3
    tok = _FakeTokenizer({prompt: prompt_len, "ABC": answer_len})
    model = _FakeModel(loss=0.1)

    mod.score_answer(model, tok, "q？", "ABC")

    labels = model.captured_labels
    assert labels.shape == (1, prompt_len + answer_len)
    assert (labels[0, :prompt_len] == -100).all(), "prompt tokens must be masked"
    assert (labels[0, prompt_len:] != -100).all(), "answer tokens must contribute"


def test_score_answer_input_ids_are_prompt_then_answer():
    prompt = mod.build_prompt("q？")
    tok = _FakeTokenizer({prompt: 4, "XY": 2})
    model = _FakeModel()

    mod.score_answer(model, tok, "q？", "XY")

    # Prompt ids are arange(4)=[0,1,2,3]; answer ids are arange(2)=[0,1];
    # concat should be [0,1,2,3,0,1].
    assert model.captured_input_ids.tolist() == [[0, 1, 2, 3, 0, 1]]


def test_rank_answers_sorts_descending_by_score():
    with patch.object(mod, "score_answer", side_effect=[-3.0, -0.5, -1.2]):
        ranked = mod.rank_answers(None, None, "q", ["low", "high", "mid"])

    assert [r.answer for r in ranked] == ["high", "mid", "low"]
    assert [r.score for r in ranked] == [-0.5, -1.2, -3.0]


def test_pick_best_answer_returns_top():
    with patch.object(mod, "score_answer", side_effect=[-2.0, -0.1, -5.0]):
        best = mod.pick_best_answer(None, None, "q", ["a", "b", "c"])

    assert best.answer == "b"
    assert best.score == pytest.approx(-0.1)


def test_score_answer_pmi_subtracts_unconditional_log_prob():
    # Two forward passes: first the conditional call, then the neutral one.
    # Conditional loss 0.3 -> log P(a|q) = -0.3
    # Unconditional loss 0.8 -> log P(a)    = -0.8
    # PMI = (-0.3) - (-0.8) = +0.5
    prompt = mod.build_prompt("q")
    tok = _FakeTokenizer({prompt: 5, mod.NEUTRAL_PROMPT: 2, "A": 3})
    model = _FakeModelSequence([0.3, 0.8])

    pmi = mod.score_answer_pmi(model, tok, "q", "A")

    assert pmi == pytest.approx(0.5)


def test_rank_answers_use_pmi_delegates_to_pmi_scorer():
    with patch.object(mod, "score_answer_pmi", side_effect=[0.1, 0.9, 0.3]) as p:
        ranked = mod.rank_answers(None, None, "q", ["a", "b", "c"], use_pmi=True)

    assert p.call_count == 3
    assert [r.answer for r in ranked] == ["b", "c", "a"]


def test_rank_answers_use_kv_cache_warms_prompt_once_and_scores_each_candidate():
    # With use_kv_cache=True and use_pmi=False:
    #   - _prompt_state called 1x (the question prompt)
    #   - _log_prob_cached called once per candidate
    with patch.object(mod, "_prompt_state", return_value={"fake": "state"}) as p_state, \
         patch.object(mod, "_log_prob_cached", side_effect=[-0.5, -0.1, -0.8]) as p_score:
        ranked = mod.rank_answers(
            None, None, "q", ["a", "b", "c"], use_kv_cache=True
        )

    assert p_state.call_count == 1
    assert p_score.call_count == 3
    assert [r.answer for r in ranked] == ["b", "a", "c"]
    assert [r.score for r in ranked] == [-0.1, -0.5, -0.8]


def test_rank_answers_use_kv_cache_with_pmi_caches_both_prompts():
    # With use_kv_cache=True and use_pmi=True:
    #   - _prompt_state called 2x (question prompt + neutral prompt)
    #   - _log_prob_cached called 2x per candidate (cond + uncond)
    scores = [
        -0.3, -1.0,  # candidate "a": cond, uncond -> PMI = 0.7
        -0.2, -1.5,  # candidate "b": cond, uncond -> PMI = 1.3
        -0.1, -0.5,  # candidate "c": cond, uncond -> PMI = 0.4
    ]
    with patch.object(mod, "_prompt_state", return_value={"fake": "state"}) as p_state, \
         patch.object(mod, "_log_prob_cached", side_effect=scores) as p_score:
        ranked = mod.rank_answers(
            None, None, "q", ["a", "b", "c"], use_pmi=True, use_kv_cache=True
        )

    assert p_state.call_count == 2
    assert p_score.call_count == 6
    assert [r.answer for r in ranked] == ["b", "a", "c"]
    assert [r.score for r in ranked] == pytest.approx([1.3, 0.7, 0.4])


def test_pick_best_answer_forwards_kv_cache_flag():
    with patch.object(mod, "rank_answers") as rank:
        rank.return_value = [mod.ScoredAnswer(answer="x", score=1.0)]
        mod.pick_best_answer(None, None, "q", ["x"], use_pmi=True, use_kv_cache=True)

    rank.assert_called_once()
    kwargs = rank.call_args.kwargs
    assert kwargs["use_pmi"] is True
    assert kwargs["use_kv_cache"] is True
