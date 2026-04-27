"""
LLM Answer Scorer (decoder-only / causal LM)
=============================================

Interview task
--------------
You are given

    question   : a natural-language question, e.g. "世界上最高的山是哪一座山？"
    candidates : a list of candidate answers, e.g.
                 ["珠穆朗瑪峰", "艾佛瑞斯峰", "我覺得是玉山",
                  "我不知道", "去問你媽"]

Using a pretrained decoder-only LLM (a HuggingFace causal LM such as
Qwen2.5), decide which candidate the model is *most likely to produce*
as the answer to the question.

Solution idea
-------------
A causal LM defines a distribution over next tokens, so for any answer
string `a` we can evaluate

    log P(a | q) = sum_t  log P(a_t | q, a_<t)

This is just the sum of the per-token log-probabilities that the model
assigns to the answer tokens *after* the question. We then compare
candidates by this quantity.

There are two subtleties:

1.  Length bias.
    A raw sum-of-log-probs favours short answers (fewer negative terms
    add up to a larger number). We divide by the number of answer
    tokens so the score is the *average per-token log-prob* — a fair
    per-token likelihood that answers of different length can be
    compared on.

2.  Tokenisation at the prompt/answer boundary.
    If we tokenise the prompt and the full text separately, the
    boundary may split differently (BPE can merge across the seam).
    To avoid that we tokenise the prompt once, tokenise the answer
    *without* special tokens, and concatenate the two id tensors.
    This guarantees the first `len(prompt_ids)` tokens of the joined
    sequence are exactly the prompt tokens and can be masked out of
    the loss cleanly.

Implementation trick
--------------------
HuggingFace causal LMs return `output.loss` when we pass `labels`. The
loss is the *mean* cross-entropy over all positions where the label is
not -100. So if we set labels for the prompt positions to -100, then

    -output.loss  ==  (1/|answer|) * sum_t log P(a_t | q, a_<t)

which is exactly the length-normalised log-likelihood we want. One
forward pass per candidate, no manual log-softmax / gather needed.

Picking the best candidate is then just argmax over these scores.

Surface-form prior (why plain log P(a|q) is not enough)
-------------------------------------------------------
If an answer happens to be a *highly coherent* phrase in the training
corpus — e.g. "珠穆朗瑪峰", where once the model sees "珠穆朗" the rest
is almost deterministic — its average per-token log-prob is high
*regardless of the question*. The plain scorer then picks "珠穆朗瑪峰"
even for an unrelated question like "我爸是誰？". This failure mode is
known as surface-form competition (Holtzman et al. 2021).

The fix is to score by pointwise mutual information instead:

    PMI(a, q) = log P(a | q) - log P(a)

We approximate log P(a) by conditioning on a neutral prefix that
carries no question-specific content (``NEUTRAL_PROMPT = "答案："``).
`score_answer_pmi` does this; `rank_answers(..., use_pmi=True)` uses
it. The default remains plain log P(a | q) so the basic algorithm is
easy to read, and the two rankings can be compared side by side.

Note on model choice
--------------------
Any HuggingFace causal LM works, but the scoring method can only
amplify signal that is already in the model's weights — it cannot
invent knowledge. Example with question "台灣最高的山是哪座？":

    Model                 | cond gap (Everest - Yushan) | PMI picks
    ----------------------+-----------------------------+-----------
    Qwen2.5-0.5B (base)   | 3.09 nat (Everest strongly) | Everest ✗
    Qwen2.5-0.5B-Instruct | 2.98 nat                    | Everest ✗
    Qwen2.5-1.5B (base)   | 0.36 nat (nearly tied)      | Yushan  ✓

The 0.5B model just does not encode "Taiwan's tallest mountain →
Yushan" strongly enough; it reflexively completes "tallest mountain
→ Everest". Once the model is large enough that the conditional
log-probs of the correct and distractor answers are within a few
nat of each other, PMI can finish the job. We therefore default to
1.5B — still small enough to run on CPU, but big enough to make the
scoring method actually earn its keep on non-trivial questions.

Optional: KV-cache reuse across candidates
------------------------------------------
Every candidate shares the same prompt, so re-encoding the prompt
for each one is wasted work. With ``use_kv_cache=True``:

1. The prompt is forwarded once with ``use_cache=True``. We keep the
   resulting ``past_key_values`` plus the final-position logits
   (which already predict the first answer token).
2. For each candidate, we only forward the answer tokens, passing
   the cached ``past_key_values``. The model attends over the
   cached prompt through the KV cache instead of recomputing it.
3. The per-token predictions for the answer are assembled from the
   cached last-logits (for a_0) and the answer-pass logits shifted
   by one (for a_1..a_{A-1}). The final length-normalised log-prob
   is numerically identical to the non-cached path.

When ``use_pmi=True``, both the question prompt and the neutral
prompt get cached — so we pay for two prompt passes up front and
each candidate then only pays for its own answer tokens under each
cache.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import List, Tuple

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


DEFAULT_MODEL = "Qwen/Qwen2.5-1.5B"
PROMPT_TEMPLATE = "問題：{question}\n答案："
NEUTRAL_PROMPT = "答案："  # question-free baseline for PMI


@dataclass
class ScoredAnswer:
    answer: str
    score: float  # length-normalised log P(answer | question), or PMI


def build_prompt(question: str) -> str:
    return PROMPT_TEMPLATE.format(question=question)


@torch.no_grad()
def _log_prob(model, tokenizer, prompt: str, answer: str) -> float:
    """Average per-token log P(answer | prompt) under the causal LM.

    Shared helper for both plain conditional scoring and PMI.
    """
    device = model.device

    prompt_ids = tokenizer(prompt, return_tensors="pt").input_ids.to(device)
    answer_ids = tokenizer(
        answer, return_tensors="pt", add_special_tokens=False
    ).input_ids.to(device)

    full_ids = torch.cat([prompt_ids, answer_ids], dim=1)

    # Mask prompt positions so the loss averages over answer tokens only.
    labels = full_ids.clone()
    labels[:, : prompt_ids.shape[1]] = -100

    output = model(input_ids=full_ids, labels=labels)
    return float(-output.loss.item())


def score_answer(model, tokenizer, question: str, answer: str) -> float:
    """Plain length-normalised log P(answer | question). Higher is better.

    Simple and intuitive but prone to surface-form competition — a
    highly coherent answer string can win regardless of the question.
    Use `score_answer_pmi` to correct for that.
    """
    return _log_prob(model, tokenizer, build_prompt(question), answer)


def score_answer_pmi(model, tokenizer, question: str, answer: str) -> float:
    """PMI score: conditional minus unconditional log-prob.

        score = log P(a | q) - log P(a | neutral_prompt)

    Measures how much the question raises the answer's likelihood
    above its baseline, which cancels out surface-form priors.
    """
    cond = _log_prob(model, tokenizer, build_prompt(question), answer)
    uncond = _log_prob(model, tokenizer, NEUTRAL_PROMPT, answer)
    return cond - uncond


@torch.no_grad()
def _prompt_state(model, tokenizer, prompt: str) -> dict:
    """Forward the prompt once with caching enabled.

    Returns the prompt ids, the KV cache it produced, and the
    prompt's last-position logits (which already predict the first
    answer token).
    """
    device = model.device
    prompt_ids = tokenizer(prompt, return_tensors="pt").input_ids.to(device)
    output = model(input_ids=prompt_ids, use_cache=True)
    return {
        "prompt_ids": prompt_ids,
        "past_kv": output.past_key_values,
        "last_logits": output.logits[:, -1:, :].detach(),
    }


@torch.no_grad()
def _log_prob_cached(model, tokenizer, prompt_state: dict, answer: str) -> float:
    """Length-normalised log P(answer | prompt) reusing a cached prompt state.

    Numerically equivalent to `_log_prob(prompt, answer)` but only runs
    the model over the answer tokens.
    """
    device = model.device
    prompt_ids = prompt_state["prompt_ids"]
    last_logits = prompt_state["last_logits"]

    answer_ids = tokenizer(
        answer, return_tensors="pt", add_special_tokens=False
    ).input_ids.to(device)

    prompt_len = prompt_ids.shape[1]
    answer_len = answer_ids.shape[1]
    # Attention mask must cover cached prompt + new answer positions.
    attention_mask = torch.ones(
        1, prompt_len + answer_len, dtype=torch.long, device=device
    )

    # The model extends `past_kv` in place during the forward pass, so
    # each candidate gets its own deep copy of the cached prompt state.
    kv = copy.deepcopy(prompt_state["past_kv"])

    output = model(
        input_ids=answer_ids,
        past_key_values=kv,
        attention_mask=attention_mask,
        use_cache=False,
    )

    # Predict a[0] from prompt's last-position logits; a[i>=1] from
    # the answer pass's logits at position i-1.
    pred_logits = torch.cat([last_logits, output.logits[:, :-1, :]], dim=1)
    log_probs = torch.log_softmax(pred_logits.float(), dim=-1)
    gathered = log_probs.gather(-1, answer_ids.unsqueeze(-1)).squeeze(-1)
    return float(gathered.mean().item())


def rank_answers(
    model,
    tokenizer,
    question: str,
    candidates: List[str],
    *,
    use_pmi: bool = False,
    use_kv_cache: bool = False,
) -> List[ScoredAnswer]:
    if not use_kv_cache:
        scorer = score_answer_pmi if use_pmi else score_answer
        scored = [
            ScoredAnswer(answer=c, score=scorer(model, tokenizer, question, c))
            for c in candidates
        ]
    else:
        q_state = _prompt_state(model, tokenizer, build_prompt(question))
        n_state = _prompt_state(model, tokenizer, NEUTRAL_PROMPT) if use_pmi else None
        scored = []
        for c in candidates:
            cond = _log_prob_cached(model, tokenizer, q_state, c)
            score = cond - _log_prob_cached(model, tokenizer, n_state, c) if use_pmi else cond
            scored.append(ScoredAnswer(answer=c, score=score))

    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def pick_best_answer(
    model,
    tokenizer,
    question: str,
    candidates: List[str],
    *,
    use_pmi: bool = False,
    use_kv_cache: bool = False,
) -> ScoredAnswer:
    return rank_answers(
        model,
        tokenizer,
        question,
        candidates,
        use_pmi=use_pmi,
        use_kv_cache=use_kv_cache,
    )[0]


def load_model(
    model_name: str = DEFAULT_MODEL,
) -> Tuple[AutoModelForCausalLM, AutoTokenizer]:
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name)
    model.eval()
    return model, tokenizer


if __name__ == "__main__":
    import argparse
    import time

    parser = argparse.ArgumentParser(
        description="Rank candidate answers with a HuggingFace causal LM."
    )
    parser.add_argument(
        "--kv-cache",
        action="store_true",
        help="Reuse the prompt's KV cache across candidates.",
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
        use_pmi=args.pmi,
        use_kv_cache=args.kv_cache,
    )
    elapsed = time.perf_counter() - t0

    print(f"[elapsed: {elapsed:.2f}s]")
    for r in ranked:
        print(f"  score={r.score:+.4f}  answer={r.answer}")
    print(f"\nBest: {ranked[0].answer}")
