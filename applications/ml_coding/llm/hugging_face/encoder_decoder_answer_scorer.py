"""
Transformer Encoder-Decoder Answer Scorer (seq2seq)
====================================================

Interview task
--------------
Same as the decoder-only version: given a question and a list of
candidate answers, pick the one the model is most likely to emit.

    question   : "世界上最高的山是哪一座山？"
    candidates : ["珠穆朗瑪峰", "艾佛瑞斯峰", "我覺得是玉山",
                  "我不知道", "去問你媽"]

The difference is that we now use an encoder-decoder Transformer
(e.g. mT5, Flan-T5, BART) where the question goes into the encoder
and the answer goes into the decoder.

Solution idea
-------------
An encoder-decoder model defines

    P(a | q) = prod_t P(a_t | q, a_<t)

just like a causal LM, but conditioning on `q` is done by the encoder
rather than by prepending `q` to the token stream. So we can score
each candidate the same way:

    score(a) = (1/|tokens(a)|) * sum_t log P(a_t | q, a_<t)

and pick the candidate with the largest score. Length-normalising is
again important — otherwise "我不知道" (short) would beat "珠穆朗瑪峰"
(also short but different length) purely on token count.

Implementation trick
--------------------
HuggingFace seq2seq models accept `labels=<answer token ids>` and
return a *mean* cross-entropy loss over target tokens (pad tokens are
ignored if we replace them with -100). They also take care of the
"shift right" step internally: the decoder input is built by prepending
the decoder start id to the labels, so the model at position t predicts
label_t from label_<t. This means

    -output.loss  ==  average per-token log P(answer | question)

exactly the length-normalised log-likelihood we need. One forward pass
per candidate, no manual teacher-forcing code.

Note on model choice
--------------------
``google/mt5-small`` is a good multilingual default and handles the
Chinese example out of the box, but its scores can be noisy because
mT5 was pretrained with span corruption, not natural Q&A. For real
usage, prefer an instruction-tuned seq2seq (e.g. ``google/flan-t5-xl``
for English, or a Chinese-tuned T5). The scoring code is identical.

Runtime dependencies
--------------------
SentencePiece-based tokenisers (T5, mT5, mBART, …) need both
``sentencepiece`` and ``protobuf`` installed; without them the fast-
tokeniser conversion in transformers 5.x falls through to the tiktoken
path and crashes on the SP model file. Install once with::

    pip install sentencepiece protobuf

Optional: encoder-output caching across candidates
---------------------------------------------------
All candidates share the same question, so the encoder only has to
run once. With ``use_kv_cache=True``:

1. The encoder is called once via ``model.get_encoder()`` and its
   ``encoder_outputs`` (last hidden state) is kept.
2. Each candidate's scoring forwards **only** the decoder, passing
   ``encoder_outputs=...`` so the encoder path is skipped entirely.
   Cross-attention still reads the cached encoder hidden states.

This is the seq2seq analogue of "KV cache" in decoder-only models:
amortise the per-question cost across candidates. HuggingFace seq2seq
models accept ``encoder_outputs`` directly, so no manual cache
manipulation is needed. The numerical result matches the non-cached
path exactly (it's the same decoder forward; only the encoder is
skipped).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


DEFAULT_MODEL = "google/mt5-small"
NEUTRAL_PROMPT = ""  # question-free baseline for PMI 

@dataclass
class ScoredAnswer:
    answer: str
    score: float  # length-normalised log P(answer | question)


@torch.no_grad()
def score_answer(model, tokenizer, question: str, answer: str) -> float:
    """Average per-token log-probability that the seq2seq model assigns
    to `answer` when given `question` as the encoder input."""
    device = model.device

    src = tokenizer(question, return_tensors="pt").to(device)
    tgt = tokenizer(answer, return_tensors="pt").to(device)

    # Pad ids must not contribute to the loss.
    labels = tgt.input_ids.clone()
    if tokenizer.pad_token_id is not None:
        labels[labels == tokenizer.pad_token_id] = -100

    output = model(
        input_ids=src.input_ids,
        attention_mask=src.attention_mask,
        labels=labels,
    )
    return float(-output.loss.item())


@torch.no_grad()
def _question_state(model, tokenizer, question: str) -> dict:
    """Run the encoder once and cache its outputs so each candidate's
    scoring only pays for its own decoder forward pass."""
    device = model.device
    src = tokenizer(question, return_tensors="pt").to(device)
    encoder_outputs = model.get_encoder()(
        input_ids=src.input_ids,
        attention_mask=src.attention_mask,
        return_dict=True,
    )
    return {"src": src, "encoder_outputs": encoder_outputs}


@torch.no_grad()
def _log_prob_cached(model, tokenizer, question_state: dict, answer: str) -> float:
    """Length-normalised log P(answer | question) reusing cached encoder
    outputs. Numerically identical to `score_answer`: only the encoder
    forward is skipped."""
    device = model.device
    src = question_state["src"]
    encoder_outputs = question_state["encoder_outputs"]

    tgt = tokenizer(answer, return_tensors="pt").to(device)
    labels = tgt.input_ids.clone()
    if tokenizer.pad_token_id is not None:
        labels[labels == tokenizer.pad_token_id] = -100

    output = model(
        attention_mask=src.attention_mask,
        encoder_outputs=encoder_outputs,
        labels=labels,
    )
    return float(-output.loss.item())


def rank_answers(
    model,
    tokenizer,
    question: str,
    candidates: List[str],
    use_pimi: bool = False,
    use_kv_cache: bool = False,
) -> List[ScoredAnswer]:
    if use_kv_cache:
        q_state = _question_state(model, tokenizer, question)
        n_state = (
            _question_state(model, tokenizer, NEUTRAL_PROMPT) if use_pimi else None
        )

        def score(c: str) -> float:
            cond = _log_prob_cached(model, tokenizer, q_state, c)
            return cond - _log_prob_cached(model, tokenizer, n_state, c) if use_pimi else cond
    else:
        def score(c: str) -> float:
            cond = score_answer(model, tokenizer, question, c)
            return cond - score_answer(model, tokenizer, NEUTRAL_PROMPT, c) if use_pimi else cond

    scored = [ScoredAnswer(answer=c, score=score(c)) for c in candidates]
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def pick_best_answer(
    model,
    tokenizer,
    question: str,
    candidates: List[str],
    use_pimi: bool = False,
    use_kv_cache: bool = False,
) -> ScoredAnswer:
    return rank_answers(
        model,
        tokenizer,
        question,
        candidates,
        use_pimi=use_pimi,
        use_kv_cache=use_kv_cache,
    )[0]


def load_model(
    model_name: str = DEFAULT_MODEL,
) -> Tuple[AutoModelForSeq2SeqLM, AutoTokenizer]:
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
    model.eval()
    return model, tokenizer


if __name__ == "__main__":
    import argparse
    import time

    parser = argparse.ArgumentParser(
        description="Rank candidate answers with a HuggingFace encoder-decoder model."
    )
    parser.add_argument(
        "--kv-cache",
        action="store_true",
        help="Reuse the encoder output across candidates.",
    )
    parser.add_argument(
        "--pmi",
        action="store_true",
        help="Use PMI scoring: log P(a|q) - log P(a|neutral).",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="HF model id to load.")
    parser.add_argument("--question", default="希特勒是好人嗎", help="The question to ask.")
    args = parser.parse_args()

    candidates = [
        "珠穆朗瑪峰",
        "艾佛瑞斯峰",
        "我覺得是玉山",
        "我不知道",
        "去問你媽",
        "他是壞人喔！",
        "周杰倫的黑色幽默是他的暢銷曲",
        "黑色柳丁",
        "China airlines is a safe airline",
        "Adolf Hitler is a great leader, saving Germany from hell.",
    ]

    model, tokenizer = load_model(args.model)

    print(f"Question: {args.question}")
    print(
        f"Config:   model={args.model}  "
        f"pmi={'on' if args.pmi else 'off'}  "
        f"kv-cache={'on' if args.kv_cache else 'off'}\n"
    )

    t0 = time.perf_counter()
    ranked = rank_answers(
        model,
        tokenizer,
        args.question,
        candidates,
        use_pimi=args.pmi,
        use_kv_cache=args.kv_cache,
    )
    elapsed = time.perf_counter() - t0

    print(f"[elapsed: {elapsed:.2f}s]")
    for r in ranked:
        print(f"  score={r.score:+.4f}  answer={r.answer}")
    print(f"\nBest: {ranked[0].answer}")
