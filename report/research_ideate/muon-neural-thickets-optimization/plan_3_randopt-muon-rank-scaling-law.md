# Research Proposal: Rank Scaling Law for RandOpt Thicket Density Under Muon Optimization

**Proposal ID**: randopt-muon-rank-scaling-law
**Rank**: #3
**Confidence**: Medium
**Target Venue**: ICLR 2027 / ICML 2027
**Estimated Compute**: ~420 GPU-hours
**Date**: 2026-03-28

---

## 1. Research Question

Does RandOpt thicket density obey a two-parameter power law of the form `density = C × N^α × σ_flat^β`, where N is parameter count and σ_flat is per-model spectral flatness — and does σ_flat carry statistically independent predictive power beyond N alone?

The central hypothesis is that solution-space geometry, as measured by neural thicket density, is jointly determined by model scale and the spectral structure of learned weight matrices. Spectral flatness σ_flat — a continuous summary of how evenly singular values are distributed — is hypothesized to encode optimizer-induced inductive biases that shape the density of good solutions in a neighborhood around a trained checkpoint. If this hypothesis holds, then two models of the same parameter count but trained with different optimizers (Muon vs AdamW) will occupy geometrically different regions of the loss landscape, with Muon-trained models residing in denser, flatter thickets.

The research question is made precise in three parts:

1. **Independence test (primary)**: Within a fixed model size (345M parameters), does varying σ_flat via Muon NS-iteration count and AdamW weight decay produce measurable, statistically significant variation in thicket density? This within-N test must be passed before any joint two-parameter fit is attempted.

2. **Scaling law fit (secondary)**: Across 16 models spanning 70M–1.4B parameters in two architecture families (GPT-2, Pythia), do separate per-family fits of `log(density) = log(C) + α·log(N) + β·log(σ_flat)` yield consistent exponents with LOO-CV R² ≥ 0.80?

3. **Practical utility (tertiary)**: Does the fitted law support a Rank Budget Rule — a practitioner tool that answers "given target density d* and parameter budget N, which NS-iteration count k achieves it?" — with quantified within-family accuracy?

---

## 2. Background and Motivation

### 2.1 Neural Thickets and RandOpt Density

A neural thicket is a neighborhood in weight space around a trained checkpoint in which random perturbations produce models with loss within some epsilon of the original checkpoint's loss. Thicket density is the volumetric measure of this neighborhood, typically estimated by sampling random directions and measuring the radius over which loss stays approximately flat.

Thicket density is practically important for three reasons. First, it predicts robustness to weight perturbation and quantization noise. Second, it correlates with the ease of fine-tuning — checkpoints in denser thickets are more forgiving of hyperparameter choices. Third, it is a geometry-level summary that complements loss-based scaling laws by describing the shape of the loss surface, not just its value.

The RandOpt framework operationalizes thicket density measurement by sampling Gaussian perturbations at a specified radius σ around a checkpoint and measuring the fraction of perturbed models that retain loss within tolerance. This produces a scalar density estimate at any (checkpoint, radius) pair.

### 2.2 Muon Optimizer and Spectral Flatness

Muon (Nesterov-Schulz Momentum) is an optimizer that applies Nesterov momentum in the space of weight matrices followed by Schulz iteration — a Newton-Schulz orthogonalization step that constrains gradient updates to lie near the group of orthogonal transformations. Muon has been reported to produce weight matrices with flatter singular value spectra than AdamW, meaning that the ratio of the largest to smallest singular values is smaller under Muon-trained checkpoints.

Spectral flatness σ_flat is defined here as the epsilon-numerical rank divided by the minimum weight matrix dimension: `σ_flat = rank_ε(W) / min(d_in, d_out)`, where epsilon = 0.01 (so rank_ε counts the number of singular values above 1% of the largest). This normalization ensures σ_flat ∈ (0, 1] regardless of matrix dimensions, with σ_flat = 1 indicating a perfectly flat spectrum (near-orthogonal weight matrix) and σ_flat → 0 indicating a nearly rank-deficient matrix.

The Muon hypothesis is: Muon's orthogonalization step biases weight matrices toward higher σ_flat (flatter spectra), and this spectral flatness independently predicts thicket density beyond what model size alone predicts.

### 2.3 Scaling Law Landscape and Gap

Neural scaling laws — most prominently the Chinchilla law — characterize how loss decreases as a power law in parameter count and training tokens. These laws have transformed how practitioners allocate compute. However, they characterize the value of the loss at a trained checkpoint, not the geometry of the loss surface around it.

No scaling law currently exists for solution-space geometry. If thicket density follows a power law in (N, σ_flat), this fills a gap in the scaling laws toolkit: practitioners designing post-training pipelines (RLHF, fine-tuning, distillation) could predict the geometric robustness of a checkpoint before investing compute in post-training, and could choose optimizer hyperparameters to achieve a target geometry.

### 2.4 Differentiation from Prior Work

This work differs from Henighan et al. (2022) and related spectral analyses (arXiv:2602.07712) in the following ways:

- **Different dependent variable**: Prior spectral work studies how loss or performance scales with rank or spectral properties. This work studies how thicket density (a geometric measure of solution-space shape) scales with N and σ_flat. The matched-loss test in Phase 1 (fitting density at matched loss values for Muon vs AdamW checkpoints) directly falsifies the hypothesis that density is merely a function of loss value: if density = f(loss) were true, matched-loss checkpoints would have equal density regardless of optimizer — but the prediction is that they will not.

- **Optimizer-induced spectral variation as independent variable**: Prior work treats spectral properties as a byproduct of architecture. Here, spectral flatness is actively manipulated as an independent variable (via NS-iteration count and weight decay) within a fixed architecture, enabling causal inference of the σ_flat → density relationship.

- **Unit of analysis**: The unit is 16 model-level observations (one density estimate per model-checkpoint pair), not per-layer statistics. This prevents pseudo-replication and ensures the degrees of freedom count reflects the actual number of independent training runs.

---

## 3. Hypothesis

**Primary hypothesis (H1)**: Spectral flatness σ_flat carries statistically independent predictive power for thicket density beyond model parameter count N alone. Specifically, within a fixed 345M-parameter GPT-2 Medium model, varying σ_flat by changing Muon NS-iteration count k ∈ {1, 3, 5, 10, 20} and AdamW weight decay λ ∈ {0, 1e-4, 1e-3, 1e-2} produces a within-N regression `log(density) = log(C_N) + β·log(σ_flat)` with β significantly positive (permutation p < 0.05, LOO-CV R² > 0.70).

**Secondary hypothesis (H2)**: Across 16 models in two architecture families (GPT-2 and Pythia), the per-family two-parameter law `log(density) = log(C) + α·log(N) + β·log(σ_flat)` achieves LOO-CV R² ≥ 0.80, with exponents α and β having bootstrap 95% CIs that exclude 0 and are consistent across families within overlapping CIs.

**Tertiary hypothesis (H3)**: The β exponent is larger for Muon-trained models than AdamW-trained models (i.e., σ_flat matters more for Muon), reflecting the stronger spectral signature of the Nesterov-Schulz orthogonalization step. This is framed as a hypothesis, not a claimed result, and will be tested by fitting separate (C, β) curves for each optimizer and testing whether β_Muon > β_AdamW at p < 0.05.

**Null hypothesis (H0, to be rejected)**: Thicket density is fully explained by N alone (one-parameter law), and the β term is not significantly different from zero after controlling for N. The F-test against the nested one-parameter model is the primary statistical test of H0.

---

## 4. Technical Approach

### 4.1 Spectral Flatness Computation

For each trained model checkpoint:
1. Extract all weight matrices W from attention (Q, K, V, O projections) and MLP (FC1, FC2) layers.
2. Compute the singular value decomposition of each W.
3. Compute epsilon-numerical rank: `rank_ε(W) = |{σ_i : σ_i ≥ 0.01 × σ_max}|`.
4. Normalize: `σ_flat(W) = rank_ε(W) / min(d_in, d_out)`.
5. Compute per-layer σ_flat for attention and MLP weights separately (for Phase 2 decomposition analysis).
6. Aggregate to per-model σ_flat as the geometric mean of per-layer σ_flat values across all weight matrices.

**Rationale for geometric mean**: The geometric mean is appropriate for multiplicative scale-free quantities. Spectral flatness is a normalized ratio and its log is the mean of log(σ_flat) values — the geometric mean is the natural aggregate.

**Rationale for epsilon = 0.01**: Threshold at 1% of the largest singular value captures meaningful rank while being robust to numerical noise (which produces singular values at machine epsilon, not 1% scale). Sensitivity to epsilon is tested by recomputing σ_flat at epsilon ∈ {0.001, 0.01, 0.05} for a subset of models.

### 4.2 Thicket Density Measurement (RandOpt Protocol)

For each checkpoint:
1. Sample M = 500 random Gaussian perturbation vectors of norm σ (perturbation radius).
2. For each perturbation, evaluate the model loss on a held-out 1,000-batch subsample of OpenWebText.
3. Record the fraction of perturbed models with loss within tolerance ε_loss = 0.05 nats of the unperturbed checkpoint loss.
4. This fraction is the empirical thicket density estimate at radius σ.
5. Primary radius: σ = 0.01 (normalized by weight matrix Frobenius norm).
6. Five radii for Phase 2 sensitivity: σ ∈ {0.005, 0.01, 0.02, 0.05, 0.1}.

**Unit of analysis**: Each model-checkpoint pair produces one density estimate. With 16 models, the regression has n = 16 data points. Layer-level statistics are aggregated to the model level before fitting, preventing pseudo-replication.

### 4.3 Power Law Formulation

The core model is:

```
log(density) = log(C) + α · log(N) + β · log(σ_flat) + ε
```

In its linearized (OLS) form, this is a two-predictor linear regression in log-space. The parameters are:

- `C`: baseline density constant (intercept in log-space)
- `α`: N scaling exponent (expected: α > 0, larger models have denser thickets from sheer capacity)
- `β`: σ_flat exponent (H1 predicts: β > 0, flatter spectra → denser thickets)
- `ε`: residual

The nested one-parameter baseline model is:

```
log(density) = log(C') + α' · log(N) + ε'
```

The F-test comparing these two nested models is the primary test of H0.

### 4.4 Collinearity Control (Phase 0, Mandatory Gate)

Before any joint two-parameter fit, collinearity between log(N) and log(σ_flat) is assessed:

1. **Pearson correlation**: Compute r(log(N), log(σ_flat)) across all data points. If |r| > 0.8, the joint fit is numerically unreliable without additional orthogonal variation.

2. **Variance Inflation Factor**: Compute VIF for each predictor in the joint OLS. VIF > 5 for either predictor triggers mandatory Phase 0 expansion before any joint fit result is reported.

3. **Design matrix condition number**: Report κ([log(N), log(σ_flat)]) as a supplementary diagnostic.

4. **Response if VIF > 5**: Execute the within-fixed-N σ_flat sweep (P0-B) to add orthogonal variation to the design, then recompute VIF on the expanded dataset.

The within-N regression in P0-B (holding N constant at 345M) provides data points where log(N) is exactly constant, creating the orthogonal variation needed to identify β independently of α.

### 4.5 Statistical Rigor Suite

Every fit reported in the paper must include all five of the following:

1. **Adjusted R²**: `R²_adj = 1 − (1−R²)(n−1)/(n−p−1)` where p = number of predictors. Primary threshold: R²_adj ≥ 0.80 for the per-family two-parameter fit.

2. **Permutation test**: Shuffle the σ_flat labels (not the density values) 1,000 times, refit the two-parameter model, and record the null distribution of R². Report: observed R² vs 95th percentile of null distribution. The law is only claimed significant if p_permutation < 0.05 (i.e., observed R² exceeds the 95th percentile of the shuffled null).

3. **F-test for nested model comparison**: `F = [(RSS_1 - RSS_2)/Δp] / [RSS_2/(n-p_2-1)]` where model 1 is the one-parameter baseline and model 2 is the two-parameter law. Two-parameter model must pass F-test at p < 0.05.

4. **Leave-One-Out Cross-Validation (LOO-CV)** as the primary generalization metric: Refit the model n times, each time leaving out one observation, and compute the LOO-CV R² (fraction of variance explained by out-of-sample predictions). All success thresholds (≥ 0.80) apply to LOO-CV R², not in-sample R². LOO-CV is preferred over k-fold CV because with n = 16 observations, leaving out larger fractions creates instability in the small-sample regime.

5. **Bootstrap 95% CIs on α and β**: Resample the (N, σ_flat, density) data 1,000 times with replacement, refit the model each time, and report the 2.5th and 97.5th percentiles of the bootstrap distribution for each exponent. Both CIs must exclude 0 for the law to be claimed.

### 4.6 Per-Family Fitting Strategy

The primary analysis fits separate laws for each architecture family:

- **GPT-2 family**: 6 data points (GPT-2 Small 117M, Medium 345M, Large 774M × Muon, AdamW)
- **Pythia family**: 10 data points (Pythia 70M, 160M, 410M, 1B, 1.4B × Muon, AdamW)

The per-family fits yield family-specific (C_fam, α_fam, β_fam). Cross-family consistency is tested by checking whether the exponent CIs overlap: if [α_GPT2_lo, α_GPT2_hi] ∩ [α_Pythia_lo, α_Pythia_hi] ≠ ∅ and analogously for β, the exponents are declared consistent. Consistency is evidence the law captures architecture-agnostic geometry; inconsistency is reported honestly as a limitation with quantified extrapolation error.

A pooled cross-family fit (combining all 16 points) is reported as a secondary result with explicit caveats: it provides a single summary law for practitioners who lack family-specific data, but its generalization claims are weaker than per-family fits.

---

## 5. Experimental Design

### 5.1 Phase 0: Collinearity Isolation (Weeks 1–3)

Phase 0 is a mandatory prerequisite gate. The joint two-parameter scaling law is not fitted until Phase 0 passes.

**P0-A: Collinearity Diagnostic**

Train 6 base models: GPT-2 Small (117M), Medium (345M), Large (774M) × Muon, AdamW. Pretraining: 8B tokens of OpenWebText, standard training schedule (cosine LR decay, warmup 2000 steps).

Compute:
- Pearson r(log(N), log(σ_flat)) across 6 points
- VIF for each predictor in the joint OLS regression
- Condition number of the [log(N), log(σ_flat)] design matrix

If VIF < 5 for both predictors: proceed to Phase 1 directly.
If VIF ≥ 5 for either predictor: execute P0-B before Phase 1.

**P0-B: Within-Fixed-N σ_flat Sweep (Primary Independence Test)**

This is the lead empirical result of the paper. Hold model size fixed at GPT-2 Medium (345M parameters). Vary:

- Muon NS iterations: k ∈ {1, 3, 5, 10, 20} → 5 checkpoints with distinct σ_flat values at constant N = 345M
- AdamW weight decay: λ ∈ {0, 1e-4, 1e-3, 1e-2} → 4 additional checkpoints

Result: 9 data points with N exactly constant and σ_flat varying continuously across approximately 1.5 decades of range (from low-k Muon near σ_flat ≈ 0.3 to high-k Muon near σ_flat ≈ 0.9, based on prior spectral analyses of Muon).

Fit the one-dimensional within-N regression:
```
log(density) = log(C_N) + β · log(σ_flat)
```

Apply the full statistical rigor suite (adjusted R², permutation test, bootstrap CI on β, LOO-CV).

**Gate criterion**: β significantly positive (permutation p < 0.05) with LOO-CV R² > 0.70 in this within-N regression.

- If gate passes: proceed to Phase 1 joint fit. σ_flat has established independent predictive power.
- If gate fails: pivot to characterizing optimizer effect as categorical (Muon vs AdamW density shift at fixed N) without claiming a continuous σ_flat law. The paper becomes a narrower but honest contribution.

**Training loss as covariate**: In P0-B, include training loss at the end of training as an additional covariate in a 2-predictor model `log(density) = a + β·log(σ_flat) + γ·loss`. Test whether β remains significant after controlling for loss. If β drops to zero after loss is included, σ_flat may be a proxy for training loss rather than an independent geometric property. Include an optimizer indicator variable (Muon = 1, AdamW = 0) as a third predictor to separate optimizer-specific effects from σ_flat effects.

**P0-C: Partial Correlation Analysis**

Hold optimizer fixed at Muon. Compare GPT-2 Small/Medium/Large checkpoints at matched step counts but different NS iterations — producing variation in both N and σ_flat that is partially decoupled.

Compute partial correlation of log(density) with log(σ_flat) after partialing out log(N) via residualization. This is the decisive independence test: if partial r remains significant, σ_flat's predictive contribution is not reducible to its correlation with N.

Report partial r and its 95% CI via bootstrap (1,000 resamples).

**P0 Pass Criteria**: VIF < 5 for both predictors in the joint model, OR (within-fixed-N β significant from P0-B AND partial correlation with log(N) removed is significant from P0-C). If either criterion is met, proceed to Phase 1. If neither, restructure the contribution as a within-architecture categorical law (optimizer × architecture interaction on density, without a continuous σ_flat power law claim).

**Phase 0 Compute**: ~65 GPU-hours (6 base models × ~8h + 9 fixed-N sweep models × ~3.5h)

---

### 5.2 Phase 1: Core Scaling Law Fit with Full Statistical Rigor (Weeks 4–9)

**P1-A: Expanded Data Collection**

Train all 16 primary models:

| Architecture Family | Models | Sizes | Optimizers | Data Points |
|---|---|---|---|---|
| GPT-2 | Small, Medium, Large | 117M, 345M, 774M | Muon, AdamW | 6 |
| Pythia | 70M, 160M, 410M, 1B, 1.4B | 5 sizes | Muon, AdamW | 10 |

Pretraining: 8B tokens of OpenWebText for all models. Standard training: cosine LR decay, warmup 2000 steps, batch size 512, BFloat16 mixed precision.

For each model:
- Compute σ_flat per layer (attention weight groups and MLP weight groups separately)
- Record N (total parameters)
- Compute density at 5 perturbation radii (σ ∈ {0.005, 0.01, 0.02, 0.05, 0.1})
- Record training loss at end of pretraining

Primary density measurement is at σ = 0.01. All other radii are used in Phase 2 robustness analysis.

**Anti-Chinchilla control**: FLOPs are approximately equal across models trained on the same token budget (8B tokens), so the setup is primarily anti-Chinchilla by design — parameter count and FLOPs are not independent when data volume is fixed, but the within-fixed-N P0-B experiment (P0-B models all trained on the same tokens at same N) directly controls for FLOPs. The 3-way regression `log(density) = log(C) + α·log(N) + β·log(σ_flat) + γ·log(FLOPs)` is included as a supplementary analysis with an explicit note that its power is limited given the constrained FLOPs range in the primary dataset.

**P1-B: Per-Family Scaling Law Fits (Primary Analysis)**

Fit separately for GPT-2 family (n = 6) and Pythia family (n = 10):
```
log(density) = log(C_fam) + α_fam · log(N) + β_fam · log(σ_flat)
```

Report for each family:
- (C_fam, α_fam, β_fam) point estimates
- Bootstrap 95% CIs on α_fam and β_fam (1,000 resamples)
- Adjusted R²
- Permutation test p-value (1,000 shuffles of σ_flat labels)
- F-test p-value vs nested one-parameter model
- LOO-CV R² (primary generalization metric)

Cross-family consistency test: Check whether α_GPT2 CI overlaps α_Pythia CI and whether β_GPT2 CI overlaps β_Pythia CI.
- Overlap for both: exponents are architecture-agnostic (strong finding)
- Overlap for neither: families have distinct geometric laws (important limitation, quantify extrapolation error)
- Mixed overlap: report nuanced finding about which exponent transfers and which does not

**P1-C: Statistical Rigor Suite**

The full suite (Section 4.5, items 1–5) is applied to every fit. The rigor table is reproduced in the paper as a mandatory table for all claimed fits, not buried in appendices.

**P1-D: Rank Budget Rule Derivation**

From the per-family fitted law, derive the practitioner design tool. Given target density d* and parameter budget N, the required σ_flat is:

```
σ_flat* = (d* / (C_fam × N^α_fam))^(1/β_fam)
```

The σ_flat*(k) calibration curve maps NS-iteration count k → σ_flat, measured empirically from the P0-B sweep. The Rank Budget Rule then maps (d*, N) → k* as the NS-iteration count closest to σ_flat*.

Report the calibration curve σ_flat(k) with bootstrap CIs on the fit parameters, and the end-to-end prediction accuracy of the Rule on held-out configurations.

**Phase 1 Compute**: ~220 GPU-hours (10 new Pythia models × ~15h + 3 GPT-2 models already trained in P0 × ~25h + density evaluation at 5 radii × ~5h per model × 16 models)

---

### 5.3 Phase 2: Radius Sensitivity and Law Robustness (Weeks 10–14)

**P2-A: Perturbation Radius Sensitivity**

Using all 16 checkpoints from P1-A, refit the two-parameter law separately at each of 5 perturbation radii: σ ∈ {0.005, 0.01, 0.02, 0.05, 0.1}.

Report (α(σ), β(σ)) as a function of σ for each family.

**Stability criterion**: Exponents are declared radius-stable if the shift across σ values is less than 0.5× the bootstrap CI width at the primary radius σ = 0.01. Formally:

```
max_σ |α(σ) - α(0.01)| < 0.5 × (α_hi(0.01) - α_lo(0.01)) / 2
```

and analogously for β.

- If exponents are stable: report this as a robustness finding strengthening the claim. The law is applicable across a range of density measurement protocols.
- If exponents are radius-dependent: report the law as "measurement-protocol-relative" with σ = 0.01 as the reference, and require explicit σ specification in all applications. This is not a failure — it means the geometry has a hierarchical structure where different scales of perturbation probe different aspects.

The paper's primary law is stated at σ = 0.01 (mid-range of the five tested). The full (α(σ), β(σ)) table across all radii appears in the appendix.

**P2-B: Task Generalization**

Measure thicket density on three downstream tasks for 4 representative checkpoints (GPT-2 Medium × {Muon, AdamW} and Pythia 410M × {Muon, AdamW}):

- SST-2 (sentiment classification)
- MNLI (natural language inference)
- SQuAD (question answering)

For each task, fit a restricted model that holds α fixed at the pretraining-fitted value and estimates only (C_task, β_task):
```
log(density_task) = log(C_task) + α_pretrain · log(N) + β_task · log(σ_flat)
```

Test whether C_task and β_task are task-stable (CIs overlapping across tasks). Task-stability of β would indicate that σ_flat's geometric interpretation transfers from pretraining to fine-tuning contexts.

**P2-C: Layer-Type σ_flat Decomposition**

Test whether decomposing σ_flat into attention-specific and MLP-specific components improves the fit:
```
log(density) = log(C) + α·log(N) + β_attn·log(σ_flat_attn) + β_mlp·log(σ_flat_mlp)
```

Compare LOO-CV R² of this three-predictor model to the scalar σ_flat model. If LOO-CV R² improves by more than the LOO-CV standard error, upgrade the law to include layer-type terms. If not, report scalar σ_flat as sufficient — and include this as a parsimony finding.

**P2-D: Architecture Robustness Check (T5 Encoder-Decoder)**

To test whether the law generalizes beyond decoder-only architectures, train T5-Small (60M) and T5-Base (220M) with Muon and AdamW. These encoder-decoder architectures have a fundamentally different parameter distribution (encoder and decoder share vocabulary embeddings, cross-attention introduces additional weight matrices).

Fit the per-family law on T5 family separately (4 data points — limited statistical power, so this is an exploratory robustness check, not a primary claim). Test whether T5-family exponents fall within the bootstrap CI range of GPT-2/Pythia exponents.

**Phase 2 Compute**: ~75 GPU-hours (density evaluation at 4 additional radii × 16 models, task evaluation × 4 models × 3 tasks, T5 training × 4 models)

---

### 5.4 Phase 3: Architecture Extrapolation with Honest Uncertainty (Weeks 15–18)

**P3-A: LLaMA-3-8B Prospective Prediction**

LLaMA-3-8B (8 billion parameters) is outside the training distribution of the fitted laws (maximum training size: 774M for GPT-2, 1.4B for Pythia). This is explicitly an out-of-distribution extrapolation test, not an in-distribution prediction.

Prediction protocol:
1. Compute σ_flat for LLaMA-3-8B at matched NS-iteration counts (k ∈ {1, 5, 10}) using the same spectral analysis pipeline.
2. Apply the Pythia-family law (closer in architecture family than GPT-2 — both are decoder-only with similar design principles) with an explicit out-of-distribution warning.
3. Generate the density prediction with uncertainty: `density_pred = C_Pythia × N^α_Pythia × σ_flat^β_Pythia`, where uncertainty comes from the bootstrap CIs on (α_Pythia, β_Pythia).
4. Measure actual density of LLaMA-3-8B at σ = 0.01.
5. Compute absolute prediction error.

**Success threshold**: Prediction error < 2× the in-family LOO-CV error. This threshold explicitly acknowledges that cross-architecture prediction is harder than within-family prediction. A flat percentage threshold (e.g., < 15%) would conflate in-family and out-of-distribution evaluation, which is scientifically imprecise.

**If prediction succeeds**: Report as supporting evidence that the law captures architecture-agnostic geometry, with the caveat that a single out-of-distribution test is not sufficient to claim general cross-architecture validity.

**If prediction fails (error > 2× LOO-CV)**: Report the magnitude of architecture-transfer error as a quantified finding. This tells practitioners: "The Pythia-family law extrapolates to LLaMA-3-8B with X× the within-family error." This is a useful finding even if the prediction is inaccurate, because it quantifies the cost of cross-architecture transfer.

**P3-B: Rank Budget Rule Validation**

Test 3 practitioner scenarios within each architecture family:
- Scenario 1: Target density d* at a new model size N_new (within family, different from training data)
- Scenario 2: Budget constraint on NS-iterations k_max; predict achievable density
- Scenario 3: Match a reference Muon checkpoint's density with an AdamW checkpoint by choosing weight decay

Report within-family accuracy and cross-family accuracy as distinct numbers. Cross-family accuracy uses the rule from the closer family (Pythia law applied to GPT-2 checkpoints when within-family law is unavailable) and reports the accuracy degradation.

**Phase 3 Compute**: ~60 GPU-hours (LLaMA-3-8B density evaluation × 3 NS-iterations + rule validation experiments)

---

## 6. Baselines

### Baseline 1: Neural Thickets One-Parameter Law (Density vs N Only)

The nested model `log(density) = log(C') + α'·log(N)` without σ_flat. This baseline tests whether N alone is sufficient to predict density. The two-parameter law is compared to this baseline via F-test and adjusted R². The law is only claimed to be an improvement if F-test p < 0.05 and adjusted R² increases by Δ ≥ 0.10.

### Baseline 2: AdamW-Only Scaling Law

Fit the two-parameter law separately using only AdamW checkpoints and compare to the Muon-only law. This tests: (a) whether the law structure is optimizer-specific, and (b) whether C and β differ significantly between optimizers. If β_Muon and β_AdamW are statistically indistinguishable, the σ_flat effect is not optimizer-specific and the hypothesis that Muon uniquely shapes geometry is not supported.

### Baseline 3: FLOPs-Based Scaling Law (Anti-Chinchilla Control)

Fit a three-way model including log(FLOPs) alongside log(N) and log(σ_flat):
```
log(density) = log(C) + α·log(N) + β·log(σ_flat) + γ·log(FLOPs)
```

Test whether β_σ_flat remains significant after controlling for FLOPs. This is the anti-Chinchilla control: it addresses the concern that σ_flat is merely a proxy for effective training compute (flatter spectra → model trained longer → more FLOPs → denser thickets).

- If β_σ_flat remains significant: σ_flat is an independent predictor beyond FLOPs, supporting the geometric interpretation.
- If β_σ_flat drops to zero after FLOPs is included: σ_flat mediates the FLOPs effect. This is still a mechanistic contribution — it identifies the geometric mechanism by which FLOPs affect density — but the claim is revised from "independent predictor" to "mechanistic mediator."

Note: The within-fixed-N P0-B experiment provides the strongest anti-Chinchilla evidence, as it varies σ_flat at exactly matched N (and approximately matched FLOPs, since all P0-B models train on the same token budget). The 3-way regression in Baseline 3 is supplementary to P0-B and has limited statistical power given the constrained FLOPs range in the primary 16-model dataset.

---

## 7. Ablation Study

| What to vary | What to hold constant | Research question | Phase |
|---|---|---|---|
| σ_flat via NS iterations k ∈ {1,3,5,10,20} | Model size (345M), architecture (GPT-2 Medium) | Does σ_flat carry independent signal at fixed N? | P0-B |
| σ_flat via weight decay λ ∈ {0, 1e-4, 1e-3, 1e-2} | Model size (345M), architecture (GPT-2 Medium) | Does non-Muon manipulation of σ_flat shift density? | P0-B |
| Model size N (7 levels: 70M–1.4B) | Optimizer, task, architecture family | Is N^α well-specified within Pythia family? | P1-A |
| Architecture family (GPT-2 vs Pythia) | Optimizer | Are exponents α, β consistent across families? | P1-B |
| Density radius σ (5 values: 0.005–0.1) | Model size, optimizer | Are exponents radius-stable or radius-dependent? | P2-A |
| Task (SST-2, MNLI, SQuAD) | Model size, optimizer | Is the law task-invariant? | P2-B |
| Layer type grouping (attention σ_flat vs MLP σ_flat) | Model size, optimizer | Does layer-type decomposition improve LOO-CV R²? | P2-C |
| Architecture type (decoder-only vs encoder-decoder T5) | Model size range, optimizer | Does the law generalize beyond GPT-style architectures? | P2-D |
| ε threshold in σ_flat computation (0.001, 0.01, 0.05) | Model, optimizer | How sensitive is σ_flat to rank threshold choice? | P1-A sensitivity |
| Training loss as covariate | σ_flat, N, model | Is σ_flat independent of training loss? | P0-B covariate |

---

## 8. Datasets

**Pretraining corpus**: OpenWebText (8B tokens). All models trained on identical data to ensure that FLOPs are approximately matched across models at the same parameter count (modulo batch size differences across model sizes).

**Density evaluation**: RandOpt perturbation evaluation uses a 1,000-batch held-out subset of OpenWebText, not used in training. This is a pretraining-domain density measurement.

**Task generalization evaluation** (Phase 2-B):
- SST-2 (Stanford Sentiment Treebank): Binary sentiment classification, 67k training / 872 validation examples
- MNLI (Multi-Genre NLI): Textual entailment, 433k training / 10k validation examples
- SQuAD v1.1: Extractive question answering, 88k training / 10k validation examples

**Model families and sizes**:
- GPT-2: Small (117M), Medium (345M), Large (774M) — trained from scratch on OpenWebText
- Pythia: 70M, 160M, 410M, 1B, 1.4B — from EleutherAI's Pythia suite (pretrained on The Pile; density measurement uses held-out The Pile or OpenWebText for matched comparison)
- LLaMA-3-8B: Used for extrapolation test only; pretrained weights from Meta (density measured on held-out data, not used in training)
- T5 Small (60M), T5 Base (220M): Architecture robustness check (encoder-decoder)

---

## 9. Metrics and Success Criteria

### Phase 0 Gate Metrics (must be met before Phase 1 is executed)

| Metric | Target / Threshold | Statistical test |
|---|---|---|
| Within-N β significance (P0-B) | β > 0 with permutation p < 0.05 | Permutation test (1,000 shuffles) |
| Within-N LOO-CV R² (P0-B) | ≥ 0.70 | LOO-CV |
| Partial correlation of σ_flat after removing N (P0-C) | Significant at p < 0.05 | Bootstrap CI excludes 0 |
| VIF for joint predictors (P0-A) | < 5 for both | OLS collinearity diagnostic |

### Phase 1 Primary Metrics (law establishment)

| Metric | Target / Threshold | Statistical test |
|---|---|---|
| Per-family LOO-CV R² | ≥ 0.80 for each family separately | LOO-CV |
| Adjusted R² gain (two-parameter vs one-parameter) | Δ ≥ 0.10 | Adjusted R² comparison |
| F-test p-value (nested model comparison) | < 0.05 | F-test |
| Permutation test p-value | < 0.05 | Permutation test (1,000 shuffles) |
| Bootstrap 95% CI on α | Excludes 0 | Bootstrap (1,000 resamples) |
| Bootstrap 95% CI on β | Excludes 0 | Bootstrap (1,000 resamples) |

### Phase 2–3 Secondary Metrics (generalization and robustness)

| Metric | Target / Threshold | Notes |
|---|---|---|
| Exponent stability across σ radii | Shift < 0.5× CI width across 5 radii | Radius-dependent if criterion fails |
| Cross-family exponent consistency | Overlapping CIs for α and β | Report degree of overlap if partial |
| Cross-family prediction error (LLaMA-3-8B) | < 2× in-family LOO-CV error | Out-of-distribution extrapolation test |
| Rank Budget Rule within-family accuracy | ≥ 5/6 correct predictions per family | Practical utility test |
| Task generalization β stability | β_task CIs overlap across SST-2, MNLI, SQuAD | Tests geometry-task decoupling |

### Success Tiers

**Tier 1 (Minimum for publication)**: Phase 0 gate passes (within-N β significant from P0-B), per-family LOO-CV R² ≥ 0.80, F-test and permutation test both significant, bootstrap CIs on α and β both exclude 0.

**Tier 2 (Target for strong paper)**: Tier 1 achieved AND Rank Budget Rule achieves ≥ 5/6 correct predictions within each family AND law holds across 3 tasks with β stable and C varying.

**Tier 3 (Bonus — high uncertainty)**: LLaMA-3-8B prediction error < 2× in-family LOO-CV error AND exponents α, β consistent across GPT-2 and Pythia families within overlapping CIs.

---

## 10. Compute Requirements

| Phase | Activity | Estimated GPU-hours |
|---|---|---|
| P0-A | Train 6 base GPT-2 models (3 sizes × 2 optimizers) | 30h |
| P0-B | Train 9 fixed-N sweep models (345M at varied k, λ) | 25h |
| P0-C | Partial correlation analysis (no additional training) | 0h |
| P1-A | Train 10 Pythia models + density evaluation setup | 180h |
| P1-B | Density evaluation at σ=0.01, 16 models × 500 perturbations | 20h |
| P2-A | Density evaluation at 4 additional radii × 16 models | 30h |
| P2-B | Task evaluation for 4 checkpoints × 3 tasks | 10h |
| P2-C | Layer-type σ_flat decomposition analysis | 5h |
| P2-D | T5 training (4 models) + density evaluation | 30h |
| P3-A | LLaMA-3-8B density evaluation × 3 NS configurations | 50h |
| P3-B | Rank Budget Rule validation experiments | 10h |
| Buffer | Retraining, debugging, reruns | 30h |
| **Total** | | **~420 GPU-hours** |

Hardware assumption: 6× H200 GPUs. Estimated wall-clock time: ~70 hours of actual compute across 18 weeks (intermittent use).

---

## 11. Risk Register

| Risk | Trigger condition | Mitigation / Response |
|---|---|---|
| High collinearity (VIF > 5) | P0-A: VIF ≥ 5 for either predictor | Execute P0-B sweep immediately; report VIF prominently; do not proceed to Phase 1 until P0-B provides orthogonal variation |
| Within-N β not significant (P0-B fails) | β permutation p > 0.05 in fixed-N regression | Pivot to categorical optimizer-effect law: report density shift (Muon vs AdamW) as categorical effect without claiming continuous σ_flat power law; abandon two-parameter claim |
| Radius-dependent exponents (P2-A) | α or β shift > 0.5× CI width across σ radii | Report law as measurement-protocol-relative; require σ specification in all practical applications; σ = 0.01 becomes mandatory reference point |
| Exponents inconsistent across families (P1-B) | CIs of α or β non-overlapping between GPT-2 and Pythia | Publish per-family laws separately as family-specific findings; retract pooled extrapolation claim; quantify between-family exponent gap |
| σ_flat reduces to FLOPs proxy (Baseline 3) | β_σ_flat → 0 after log(FLOPs) included in 3-way regression | Reframe claim: "σ_flat mediates the FLOPs effect on thicket density"; mechanistic contribution retained; independent predictor claim revised to mechanistic mediator |
| σ_flat reduces to training loss proxy (P0-B covariate) | β_σ_flat → 0 after training loss included as covariate | Report density = f(loss) hypothesis not falsified; matched-loss test becomes critical; differentiation from arXiv:2602.07712 requires the matched-loss falsification to hold |
| LLaMA-3-8B prediction fails (P3-A) | Error > 2× in-family LOO-CV error | Report cross-architecture degradation magnitude as quantified finding; abstract revised to: "Law holds within architecture families; cross-family extrapolation degrades by X×" |
| Insufficient σ_flat range in P0-B | σ_flat values cluster in < 0.5 decades despite varying k and λ | Add Muon ablation with modified Schulz iteration count and AdamW combined with L1 penalty to extend σ_flat range |
| Pythia vs OpenWebText distribution mismatch | Pythia density on OpenWebText differs systematically from GPT-2 | Use The Pile for all density evaluations; report separate OpenWebText and Pile density estimates for GPT-2 models to cross-validate |

---

## 12. Related Work and Differentiation

### 12.1 Neural Scaling Laws

Kaplan et al. (2020) established that language model loss follows a power law in model size N, dataset size D, and compute C. Hoffmann et al. (2022) (Chinchilla) refined the compute-optimal ratio of N to D. These laws characterize the minimum achievable loss at a given scale. This proposal addresses a complementary question: given a checkpoint at a certain loss, what is the geometry of the loss surface around it?

### 12.2 Loss Landscape Geometry

Garipov et al. (2018) and Draxler et al. (2018) established mode connectivity — well-trained networks are connected by low-loss paths in weight space. Li et al. (2018) showed that skip connections flatten loss surfaces. These works characterize global landscape topology. Neural thickets are a local characterization: the density of the good-solution neighborhood around a specific checkpoint, not the global topology.

### 12.3 Spectral Analysis of Neural Networks

Arora et al. (2019) studied how singular value distributions of weight matrices relate to compression and generalization. Yang et al. (2022) (arXiv:2602.07712) study how optimizer-dependent spectral properties affect training loss. The critical distinction from the present work: 2602.07712 uses loss as the dependent variable. This work uses thicket density as the dependent variable. The matched-loss test directly falsifies density = f(loss): if true, matched-loss checkpoints would have equal density regardless of optimizer. The prediction is they will not, because optimizer choice shapes geometry beyond what loss captures.

### 12.4 Muon and Orthogonal Optimization

The Muon optimizer (Bernstein et al., 2024) applies Newton-Schulz orthogonalization to gradient matrices. Prior analysis shows Muon produces flatter singular value spectra than AdamW on comparable architectures. This proposal is the first to quantify whether Muon's spectral signature translates into a measurable difference in solution-space geometry (thicket density) that follows a quantitative scaling law.

### 12.5 Rank and Model Compression

LoRA (Hu et al., 2022) and related low-rank adaptation methods implicitly assume that fine-tuning directions lie in a low-rank subspace. If σ_flat → 1 (flat spectrum, all singular values active) implies denser thickets, then Muon-trained checkpoints may be inherently better starting points for full-parameter fine-tuning, while AdamW-trained checkpoints (lower σ_flat, more rank-deficient) may be better starting points for LoRA. This is tested qualitatively in Phase 2-B task generalization experiments.

---

## 13. Expected Contributions

**If Tier 1 is achieved**:
1. First scaling law for neural thicket density, establishing that solution-space geometry obeys quantitative laws analogous to Chinchilla-style performance scaling laws.
2. A rigorous statistical methodology for scaling law validation: collinearity gating (VIF, partial correlation), permutation tests, and LOO-CV as primary generalization metric — a more careful protocol than current practice in empirical scaling law papers.
3. Empirical demonstration that spectral flatness σ_flat carries independent predictive power for thicket density beyond model size at fixed N.

**If Tier 2 is achieved**:
4. Rank Budget Rule: a practical design tool mapping (target density, parameter budget) → NS-iteration count, with quantified within-family accuracy. Immediately applicable to practitioners designing post-training pipelines who want to predict checkpoint robustness before committing to fine-tuning.
5. Cross-task β stability: evidence that spectral geometry transfers from pretraining to downstream tasks, enabling geometry-based prediction of fine-tuning robustness at the pretraining stage.

**If Tier 3 is achieved**:
6. Architecture-agnostic exponents: evidence that (α, β) scaling law exponents are consistent across GPT-2 and Pythia families, suggesting a universal geometric law applicable beyond any single architecture family.
7. Quantified cross-architecture extrapolation error: the first measurement of how much geometry-based laws degrade when applied to out-of-distribution architectures, giving practitioners a calibrated uncertainty budget.

**If any tier fails honestly**:
8. Rigorous negative result: quantified evidence that σ_flat does not carry independent predictive power (if P0-B gate fails), or that geometry-based scaling laws are architecture-family-specific. This is publishable as a statistically rigorous negative result that corrects optimistic priors about the generality of spectral flatness as a geometry predictor.

---

## 14. Paper Storyline

The paper opens by framing the gap: scaling laws predict what loss a model will achieve, but not how robust that model will be to weight perturbation — a property that determines fine-tuning ease, quantization robustness, and post-training stability. We introduce the two-parameter RandOpt thicket density law as the first scaling law for solution-space geometry.

The narrative follows the experimental logic. Before fitting any joint model, we establish that spectral flatness σ_flat carries independent predictive power for thicket density beyond model size alone. Within a fixed 345M-parameter GPT-2 Medium model, varying Muon NS-iteration count (k ∈ {1, 3, 5, 10, 20}) and AdamW weight decay (λ ∈ {0, 1e-4, 1e-3, 1e-2}) produces 9 checkpoints with N exactly constant and σ_flat varying across approximately 1.5 decades. The within-N regression `density ∝ σ_flat^β` achieves LOO-CV R² > 0.70 and permutation p < 0.05. This within-N analysis is the paper's load-bearing empirical foundation — it appears as Section 4, before the joint law fit, not relegated to an ablation appendix.

With σ_flat's independent signal established, we fit separate per-family two-parameter laws for GPT-2 (6 checkpoints, 117M–774M) and Pythia (10 checkpoints, 70M–1.4B) using the full statistical rigor suite: adjusted R², permutation test (1,000 shuffles), F-test against the nested N-only baseline, LOO-CV as primary generalization metric, and bootstrap CIs on all exponents. Per-family LOO-CV R² exceeds 0.80 for both families, and exponents α and β are consistent across families within overlapping bootstrap CIs. The β term is framed as a hypothesis about optimizer choice being an independent predictor of solution-space geometry beyond model size, tested against the nested one-parameter baseline. The matched-loss test (measuring density at matched loss for Muon and AdamW checkpoints) falsifies the hypothesis that density = f(loss) and differentiates this contribution from arXiv:2602.07712.

Exponents are stable across perturbation radii σ ∈ {0.005–0.1} (shifts below 0.5× CI width), providing robustness evidence. The law holds across SST-2, MNLI, and SQuAD with β stable and C varying by task — geometry transfers from pretraining to downstream tasks. Cross-architecture extrapolation to LLaMA-3-8B is assessed against the 2× LOO-CV error threshold, with the result reported honestly regardless of direction.

The paper closes with the Rank Budget Rule: a practitioner tool that maps (target density d*, parameter budget N) to NS-iteration count k*, calibrated from the P0-B sweep. Within-family accuracy and cross-family accuracy degradation are reported separately, giving practitioners an honest, calibrated tool for post-training pipeline design.

Honest limitations are stated explicitly in the conclusion: (1) n = 16 model-level observations limits statistical power; exponent precision is moderate; (2) the anti-Chinchilla claim is strongest from the within-N P0-B experiment — the 3-way regression has limited power given the constrained FLOPs range; (3) cross-architecture universality is supported by one out-of-distribution test and should not be over-extrapolated; (4) the density measurement is protocol-relative at σ = 0.01, and practitioners must use the same protocol for the Rank Budget Rule to apply.

---

*End of Proposal: randopt-muon-rank-scaling-law*
