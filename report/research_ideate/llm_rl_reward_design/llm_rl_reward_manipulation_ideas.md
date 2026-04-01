# Phase 5 Algorithm Brief

This file summarizes the main algorithms of the 5 selected Phase 5 proposals from [output_en_codex.md](/Users/jerry/projects/ai_apps/applications/llm_research/output_en_codex.md).

The goal here is not paper-style detail. It is to explain, in plain engineering terms, what each algorithm actually does and why it is intuitive.

---

## 1. Submodular Group Coverage in Update Space

**Short idea**

Instead of keeping whatever K sampled responses happen to come out, first generate a larger pool, then keep the subset whose gradients are the most different from each other. The goal is to avoid wasting training on redundant responses that all teach the model the same thing.

**Core intuition**

Think of each response as a direction telling the model how to update itself. If 8 responses all point in almost the same direction, paying for all 8 is wasteful. A better batch is one that spans multiple useful directions.

This is very similar in spirit to:
- diverse mini-batch selection
- active set selection
- picking image samples that cover feature space instead of near-duplicates

**Main algorithm**

1. For one prompt, generate `N` candidate responses, where `N > K`.
2. For each response, compute a compact gradient feature vector.
3. Build a similarity matrix between responses in gradient space.
4. Greedily select `K` responses that maximize group coverage, not individual score.
5. Run normal GRPO training on only those `K` selected responses.

**What makes it different**

The unit of optimization is the whole group, not one response at a time.

The question is not:
"Is this response novel?"

It is:
"Does adding this response increase the diversity of the update directions already in the group?"

**Why it is intuitive**

If you were labeling a vision dataset, you would not want 20 nearly identical crops of the same object pose. You would want examples that cover different angles, lighting, scales, and failure modes. This is the same idea, except the diversity is measured in update space rather than image space.

**Minimal mental model**

Generate many, keep the ones that teach different things.

---

## 2. Geometry-Conditioned Sampling Controller

**Short idea**

Add a small controller that watches the model's gradient geometry during training and adjusts exploration temperature for the next step. Instead of using a fixed schedule, the training loop reacts to the model's current learning state.

**Core intuition**

Training already has signals that tell us whether exploration is too low or too high:
- gradients collapsing into a narrow subspace
- correct and incorrect responses becoming too similar
- diversity shrinking too early

If those signals are visible, we should use them to steer sampling.

This is like:
- adaptive augmentation strength in CV
- a controller that adjusts learning conditions based on feature statistics
- a thermostat: measure state, then act

**Main algorithm**

1. After each training step, compute a few geometry features from the response gradients:
   - effective rank
   - spectral gap
   - alignment between good and bad responses
   - simple trend features over recent steps
2. Feed those features into a small controller network.
3. The controller outputs the sampling temperature for the next rollout step.
4. Generate the next batch using that temperature.
5. Reward the controller based on short-horizon learning progress.
6. Update the controller online.

**What makes it different**

Most methods use geometry only as an analysis tool or as a scalar bonus. This one uses geometry as a control signal.

So the system becomes closed-loop:
- observe geometry
- choose exploration level
- see training outcome
- update controller

**Why it is intuitive**

A fixed temperature schedule assumes training state can be predicted in advance. That is rarely true. In practice, mode collapse, domain shifts, and plateau phases are visible in the gradients before they are obvious in accuracy. The controller tries to exploit that early warning signal.

**Minimal mental model**

Watch the shape of the gradients, then turn exploration up or down.

---

## 3. Hierarchical Step-Span-Token Credit Decomposition

**Short idea**

Assign credit in three stages:
- which reasoning step mattered
- which span inside that step mattered
- which tokens inside that span mattered

Instead of treating the whole response as a flat token list, the algorithm respects reasoning structure.

**Core intuition**

A reasoning answer is not just a sequence of tokens. It has a hierarchy:
- steps
- sub-parts inside steps
- tokens inside those sub-parts

If a solution is correct, not every token deserves equal reward. Boilerplate like "Let us solve this" should not get the same credit as the actual algebraic transformation that made the solution work.

This is similar to:
- coarse-to-fine parsing
- hierarchical attention
- region -> part -> pixel attribution in vision

**Main algorithm**

1. Split each response into reasoning steps.
   - ideally with a PRM
   - otherwise with entropy-drop or heuristics
2. Estimate how important each step is.
   - best version: PRM-based step score
   - alternative: counterfactual continuation check
3. Inside each step, split text into spans such as:
   - key operation
   - intermediate computation
   - boilerplate
4. Give more of the step's credit to the important spans.
5. Inside each span, distribute credit to tokens.
   - uniform or surprisal-weighted
6. Multiply the three levels together to get final token weights.
7. Use those token weights in GRPO instead of uniform token credit.

**What makes it different**

The structure is explicit. A token is important because:
- it belongs to an important span
- inside an important step

That is much more stable than learning each token's weight independently from scratch.

**Why it is intuitive**

In CV terms, it is the difference between:
- giving equal importance to every pixel in an image
- first locating the important object
- then the important part
- then the exact pixels

The hierarchy reduces noise and makes the credit signal more semantically aligned.

**Minimal mental model**

First find the important reasoning step, then zoom in.

---

## 4. Cross-Sample Discriminative Credit Assignment

**Short idea**

Use the GRPO group itself as a local controlled experiment. A token gets credit if it helps distinguish correct responses from incorrect ones within the same group.

**Core intuition**

When the model generates multiple responses to the same question, we already have a comparison set:
- some responses are correct
- some are wrong

So instead of asking:
"Is this token important inside this one response?"

we ask:
"Does this token or span show up more in correct responses than in incorrect ones?"

That is often a much cleaner signal.

This is analogous to:
- discriminative patch mining
- contrastive analysis
- feature selection using class-conditioned frequency

**Main algorithm**

### Level 1: Simple discriminative scoring

1. Generate `K` responses and split them into correct and incorrect sets.
2. Count token frequencies in both sets.
3. For each token, compute a discrimination score:
   - high if common in correct responses
   - low or negative if common in incorrect responses
4. Turn those scores into token weights inside each response.
5. Multiply by the usual sequence-level GRPO advantage.

### Level 2: Stabilize with cross-batch memory

1. Maintain moving-average discrimination statistics across many questions.
2. Mix current-question evidence with global and cluster-level priors.
3. Use the combined posterior score when current group statistics are sparse.

### Higher levels

Move from single-token matching to:
- classifier-based discrimination
- hidden-state probing
- span-level diff/alignment

These variants capture token interactions and semantic equivalence better.

**What makes it different**

The key information source is cross-sample comparison. Existing methods usually work inside one response. This one uses the fact that GRPO naturally provides competing answers to the same problem.

**Why it is intuitive**

If a phrase appears in every response, it probably does not explain success. If a reasoning step appears mainly in the successful responses, it is much more likely to matter.

For a CV analogy: if a visual pattern appears in both positive and negative examples, it is weakly discriminative. If it appears mostly in positives, it becomes a strong feature candidate.

**Minimal mental model**

Reward the parts that make successful answers look different from failed ones.

---

## 5. Gradient-Geometry-Informed Credit Assignment

**Short idea**

Give token credit based on whether that token's gradient points in a direction that actually helps the model improve. In other words, a token is valuable if it pushes the model in the right update direction.

**Core intuition**

A token should not get high credit just because it appears in a correct answer. It should get high credit if learning from that token moves the model toward better behavior.

So this proposal asks:
"What is the beneficial update direction for this problem or batch?"

Then:
"Which tokens are aligned with that direction?"

This is closely related to:
- projection onto a useful subspace
- keeping gradients that align with signal and suppressing orthogonal noise
- in CV terms, rewarding features that point toward the discriminative subspace

**Main algorithm**

### Basic version

1. For each token, compute a compact token gradient.
2. Estimate a beneficial direction from the batch.
   - best simple version: advantage-weighted contrastive mean gradient
   - correct responses pull the direction forward
   - incorrect responses pull it backward
3. For each token, compute alignment between its gradient and that beneficial direction.
4. Use positive alignment as token credit.
5. Normalize and plug into GRPO.

### Stronger version: beneficial subspace

1. Collect gradients from correct responses.
2. Run PCA or SVD.
3. Keep the top principal directions as a beneficial subspace.
4. Score each token by how much of its gradient projects into that subspace.

This handles multiple valid reasoning paths better than a single direction.

### Path-aware version

1. Cluster correct responses by gradient similarity.
2. Compute one beneficial direction per cluster.
3. Give each token credit according to its best-aligned path.

### Cross-over feedback version

1. Summarize the alignment distribution after credit assignment.
2. If alignment is diffuse and uncertain, increase exploration.
3. If alignment is sharp and confident, reduce exploration.
4. Optionally feed the beneficial subspace back into Proposal 1 to guide trajectory selection.

**What makes it different**

This proposal unifies two ideas:
- exploration geometry
- token credit assignment

It says the same geometric object can serve both purposes:
- tell us where learning should go
- tell us which tokens are pushing in that direction

**Why it is intuitive**

Imagine a high-dimensional update space. Some token gradients point toward useful learning, some are sideways noise, and some point in a harmful direction. The algorithm simply tries to keep the first kind and suppress the others.

For a vision analogy, this is like projecting local features onto the class-discriminative subspace rather than rewarding all activated features equally.

**Minimal mental model**

Reward tokens whose gradients point where the model should move.

---

## Comparison Table

| Proposal | Main Question | Main Unit | Main Signal | Simple Intuition |
|---|---|---|---|---|
| 1. Submodular Group Coverage | Which responses should we keep? | Response group | Gradient diversity | Keep responses that teach different things |
| 2. Geometry-Conditioned Controller | How much should we explore next? | Training step | Batch geometry statistics | Use gradient shape to set temperature |
| 3. Hierarchical Credit | Where inside a response should credit go? | Step -> span -> token | Reasoning structure | First find the important step, then zoom in |
| 4. Discriminative Credit | What differentiates correct from incorrect responses? | Token or span across responses | Correct vs. incorrect frequency or representation contrast | Reward what successful answers do differently |
| 5. Geometry-Informed Credit | Which tokens push learning in the right direction? | Token gradient | Alignment with beneficial direction/subspace | Reward tokens whose gradients point the right way |

---

## Recommendation for a Manager-Level Presentation

If the goal is to explain the portfolio clearly in one meeting, present them in this order:

1. **Submodular Group Coverage**
   Reason: easiest to understand and closest to standard diverse-sample selection.
2. **Hierarchical Credit**
   Reason: intuitive structure story, easy to visualize.
3. **Cross-Sample Discriminative Credit**
   Reason: simple and practical, strong engineering appeal.
4. **Geometry-Informed Credit**
   Reason: conceptually strong, but more mathematical.
5. **Geometry-Conditioned Controller**
   Reason: easiest to pitch after the audience already accepts that geometry contains useful training-state information.

If the audience wants a one-line framing:

- Proposal 1 improves **which responses we train on**.
- Proposal 2 improves **how much we explore**.
- Proposal 3 improves **where credit goes inside one response**.
- Proposal 4 improves **credit by comparing responses against each other**.
- Proposal 5 improves **credit by checking whether a token teaches the model the right update direction**.
