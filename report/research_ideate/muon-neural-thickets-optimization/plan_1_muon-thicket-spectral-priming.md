# Research Proposal: muon-thicket-spectral-priming

---

## 1. Title

**Spectral Priming: How Muon's Newton-Schulz Orthogonalization Expands the Neural Thicket and Enables Denser Zero-Shot Model Soups**

---

## 2. One-Sentence Thesis

Muon's Newton-Schulz orthogonalization flattens the singular value spectrum of weight matrices during pre-training, and this spectral flatness geometrically expands the neural thicket by increasing the volume of the loss basin neighborhood reachable by small perturbations, whereas AdamW's adaptive per-parameter scaling concentrates singular values and contracts that neighborhood — enabling Muon-primed bases to yield denser zero-shot model soups under RandOpt sampling at equivalent or smaller perturbation radii.

---

## 3. Research Area Classification

**Primary Area**: Optimization for Deep Learning / Loss Landscape Geometry

**Secondary Areas**:
- Model Merging and Ensembling
- Random Matrix Theory Applied to Neural Networks
- Post-Training Efficiency

**Venue Target**: ICLR 2027 (primary) / NeurIPS 2027 (fallback)

**Sub-field Positioning**: This proposal sits at the intersection of three sub-fields that have not yet been jointly studied: (1) orthogonality-based optimizers (Muon and variants), (2) perturbation-density landscape theory (Neural Thickets / RandOpt), and (3) optimizer-induced geometry effects on model reusability. No existing paper connects all three.

**Distinguishing Scope**: This is not an optimizer benchmarking paper, not a model merging interference paper, and not a neural thicket application paper. It is a mechanistic causal study: does a specific optimizer-induced spectral property (flatness of singular value distribution) causally determine downstream perturbation density?

---

## 4. Closest Prior Work (5-8 papers, comparison table)

### Overview

Seven closely related papers are reviewed below. The comparison table that follows identifies the precise dimension along which each paper falls short of answering the central question.

**Paper 1: Neural Thickets / RandOpt (arXiv:2603.12228)**
Yulu Gan and Phillip Isola (MIT) show that large pretrained models enter a "thicket regime" where Gaussian perturbations around pretrained weights densely populate task-expert solutions. RandOpt — sample N perturbations of the base checkpoint, evaluate each, keep top K, ensemble — matches PPO, GRPO, and evolution strategies at equal FLOP budgets. Solution density follows a monotonic scaling law with model size. Spectral discordance quantifies diversity among sampled experts.

**Paper 2: Model Soups (arXiv:2203.05482)**
Wortsman et al. show that averaging fine-tuned model weights improves accuracy and robustness relative to any single fine-tuned model, provided the models are initialized from the same pretrained base. The soup lies within the same loss basin as the original checkpoint; fine-tuned variants that are farther from the base tend to degrade soup quality.

**Paper 3: Optimizer Bias on Merging (arXiv:2510.04686)**
This paper demonstrates empirically that the "effective noise scale" (a function of optimizer, learning rate, and batch size) determines merging compatibility between fine-tuned models. Models trained with similar effective noise scale merge better. The paper does not evaluate Muon, does not connect to basin volume or perturbation density, and does not prescribe a training strategy.

**Paper 4: SOAP (arXiv:2409.11321)**
Vyas et al. implement Adam's update rule in Shampoo's eigenbasis, achieving second-order efficiency at first-order cost. The whitening step in SOAP partially overlaps with Muon's Newton-Schulz step in spirit but differs in mechanism: SOAP targets training token efficiency, not post-training weight geometry, and the whitening is applied to the preconditioner, not directly to the weight matrix.

**Paper 5: Git Re-Basin (arXiv:2209.04836)**
Ainsworth et al. show that trained networks are one basin modulo permutation symmetries; after permutation alignment, linear interpolation between independently trained networks has low or zero loss barriers. The mechanism is combinatorial (permutation symmetry removal), not spectral. Applicability to transformers at scale is limited by the cost of solving the assignment problem.

**Paper 6: NuMuon (arXiv:2603.03597)**
Extends Muon with a nuclear-norm constraint, inducing lower-rank weight matrices that are more compressible. The paper focuses on training convergence and post-training compression, not on the geometric consequences for perturbation-based sampling or model merging.

**Paper 7: Muon Accelerates Grokking (arXiv:2504.16041)**
Shows that Muon's spectral constraints push models from memorization to generalization faster than AdamW on modular arithmetic tasks. Establishes a generalization-bias effect of orthogonalized gradients. Limited to small-scale toy settings; does not connect to perturbation density or the thicket framework.

### Comparison Table

| Paper | Core Claim | What It Solves | What It Does NOT Solve | Our Distinguishing Contribution |
|---|---|---|---|---|
| Neural Thickets (2603.12228) | Pretrained weight neighborhoods densely contain task experts; RandOpt exploits this | Why post-training works at scale; provides RandOpt algorithm | Does not address how optimizer choice shapes thicket density or geometry; all experiments use standard optimizers | We add mechanistic explanation (spectral flatness) and empirical causal chain from optimizer to density |
| Model Soups (2203.05482) | Averaging fine-tuned models improves accuracy | Cheap ensemble without extra inference cost | Requires expensive independent fine-tuning runs; does not study perturbation-based sampling or optimizer geometry | We replace fine-tuning with zero-shot RandOpt sampling; reduce soup cost from O(N fine-tunes) to O(N forward passes) |
| Optimizer Bias on Merging (2510.04686) | Effective noise scale determines fine-tuned model merging compatibility | Understanding post-hoc why some models merge better | Does not evaluate Muon; no connection to perturbation density or basin volume; no prescriptive training strategy | We study pre-training optimizer → perturbation density (not fine-tuning → merge quality); connect to spectral geometry |
| SOAP (2409.11321) | Adam in Shampoo's eigenbasis = second-order efficiency at first-order cost | Training token efficiency | Model merging, post-training geometry, thicket density | We study geometric downstream effects of whitening, not training efficiency; SOAP is a Phase 1 kill gate (not a conclusion) |
| Git Re-Basin (2209.04836) | Permutation alignment removes loss barriers between independently trained networks | Zero-barrier linear interpolation for merging | Spectral analysis; optimizer comparison; does not apply cleanly to transformers at scale | Our mechanism is spectral flatness, not permutation alignment; orthogonal approach to the same merging problem |
| NuMuon (2603.03597) | Nuclear-norm constraint on Muon induces low-rank compressible weights | Post-training compression quality | Perturbation density, model merging, thicket geometry | We study density geometry from standard Muon, not compression from regularized Muon |
| Muon Accelerates Grokking (2504.16041) | Muon generalizes faster on modular arithmetic tasks | Generalization speed, sample efficiency | Scale beyond toy tasks; no connection to perturbation density or thicket framework | We connect spectral flatness to thicket density at transformer scale (345M–774M parameters) |

---

## 5. Problem Gap

### The Unanswered Question

Neural Thickets (Gan & Isola, 2603.12228) establishes that the density of task-expert solutions in the neighborhood of a pretrained checkpoint scales predictably with model size. However, all experiments in the original paper use a fixed optimizer (standard training) and treat the base checkpoint as given. The paper does not investigate whether the choice of pre-training optimizer alters the geometry of the thicket — whether it makes the neighborhood denser or sparser, or whether the perturbation budget can be reduced for the same density.

Muon's Newton-Schulz orthogonalization enforces a specific spectral structure on weight matrices: singular values are driven toward uniformity (all near 1 after normalization). This is a geometrically meaningful operation — it produces weight matrices whose loss surfaces are more isotropic in the directions orthogonal to the training manifold. AdamW's per-parameter adaptive scaling produces the opposite: singular value distributions concentrated at high values for frequently updated parameters and near zero for rarely updated ones.

### Why This Gap Matters

If spectral flatness caused by Muon's training regime increases thicket density, then:
1. **Compute efficiency for post-training**: The same number of RandOpt samples achieves higher task expert yield from a Muon base than an AdamW base.
2. **Zero-shot model soups**: Soup quality can be achieved without any fine-tuning when the base has high perturbation density.
3. **Optimizer choice as architecture-level decision**: Pre-training optimizer is currently treated as a pure training-efficiency choice; this work reframes it as a choice that has downstream consequences for the post-training lifecycle.

### Why No Existing Paper Answers This

- Neural Thickets paper does not vary the optimizer.
- Optimizer Bias on Merging paper studies fine-tuned model merging, not random-perturbation density.
- Muon papers study training speed or convergence, not post-training geometry.
- Model Soups requires fine-tuning; does not use perturbation-based sampling.

The gap is precisely: **the causal chain from pre-training optimizer spectral structure to zero-shot perturbation density has never been measured or theorized**.

### Competing Explanations That Must Be Ruled Out

1. **Scale confound**: Muon is typically run with larger effective batch sizes and different learning rate schedules. If density differences arise from training dynamics rather than spectral structure, the proposal's central claim fails. Addressed by: normalizing all weight matrices to ||W||_F = 1 before perturbation, logging original norms as a confound covariate, and including partial Newton-Schulz ablation (post-hoc orthogonalization of an AdamW checkpoint).

2. **SOAP equivalence**: SOAP's whitening step may produce similar spectral structure to Muon. If SOAP-trained weights have identical CV(sigma_i) and stable rank to Muon-trained weights and also identical thicket density, then the mechanism is "any whitening, not Muon specifically." Addressed by: SOAP as a Phase 1 kill gate measured directly.

3. **Sharpness as the real driver**: SAM and related sharpness-aware methods also expand flat regions. If flat sharpness (low max eigenvalue of Hessian), rather than spectral flatness (low CV of singular values), is the driver, the spectral story is incidental. Addressed by: SAM baseline in Phase 2.

4. **Turbo-Muon / Mousse indistinguishability**: Turbo-Muon (2512.04632) speeds up Newton-Schulz by 2.8x and Mousse (MUD, 2603.17970) replaces polar decomposition with Cholesky-based whitening. If these produce identical spectral outcomes to standard Muon, the geometry result holds but the specific optimizer is less important. Critical distinction: thicket density is a joint property of the spectrum AND the task gradient alignment, which Turbo-Muon and Mousse do not independently control. Furthermore, the partial Newton-Schulz (K-ablation) causal test measures what happens when only K of N layers are orthogonalized — an interpolation-path experiment that cannot be replicated by examining the endpoint models from Turbo-Muon or Mousse. The volume of the interpolation path in weight space is not computable from the endpoint spectra alone; it requires the causal intervention.

---

## 6. Theoretical Basis

### Framework: Loss Landscape Geometry + Random Matrix Theory + Perturbation Volume

The theoretical chain connecting Muon orthogonalization to neural thicket density consists of three linked propositions:

**Proposition P0 (Thicket Density as Basin Volume):**
Neural thicket density D(theta_base, epsilon, tau) is proportional to the volume of the set {theta : L(theta) <= tau + epsilon, ||theta - theta_base|| <= r} for small epsilon and perturbation radius r. Formally:

    D(theta_base, epsilon, tau) proportional to Vol({theta : L(theta) <= tau + epsilon}) intersect B(theta_base, r)

where B(theta_base, r) is the ball of radius r around the base checkpoint in weight space. This follows directly from the RandOpt construction in Neural Thickets: density is the fraction of uniform samples from B(theta_base, r) that achieve loss below threshold tau + epsilon.

**Proposition P1 (Muon Produces Flatter Spectra):**
For a Muon-trained base checkpoint theta_M and an AdamW-trained base checkpoint theta_A of identical architecture after identical training steps on identical data:

    CV(sigma(W_l^M)) < CV(sigma(W_l^A))  for the majority of layers l

where CV(sigma(W)) = std(sigma(W)) / mean(sigma(W)) is the coefficient of variation of the singular values of weight matrix W, and sigma(W) denotes the vector of singular values.

Additionally (co-equal with CV):

    stable_rank(W_l^M) >= stable_rank(W_l^A)  for the majority of layers l

where stable_rank(W) = ||W||_F^2 / ||W||_2^2 (ratio of squared Frobenius norm to squared spectral norm). Both CV and stable rank are measured after normalizing each weight matrix to ||W||_F = 1 to eliminate scale confounds.

This follows from Newton-Schulz's action: the step W <- W(W^T W)^{-1/2} drives all singular values toward 1, reducing both their variance and the ratio ||W||_2 / ||W||_F. AdamW's adaptive scaling, by contrast, can amplify high-variance directions and suppress low-variance ones, increasing CV.

Verifiability: P1 is directly measurable via SVD on saved checkpoints. It does not require any modeling assumption.

**Proposition P2 (Flatter Spectra Expand Reachable Basin Volume):**
For weight matrices normalized to ||W||_F = 1, the perturbation delta ~ N(0, sigma^2 I) induces a loss change bounded by:

    |L(W + delta) - L(W)| <= C * ||delta||_2 * ||grad_W L||_2

For a given ||delta||_2 = r, the loss change is controlled by the spectral norm of the gradient. When W is orthogonal (Muon), the condition number kappa(W) = sigma_max / sigma_min ≈ 1, and the local loss curvature is more isotropic — random perturbation directions are equally likely to stay within any given loss level set. For an anisotropic W (AdamW), high-curvature directions exit the level set quickly, reducing the fraction of isotropically sampled perturbations that remain within threshold.

Formally, for a locally quadratic loss surface L(theta) ≈ (1/2)(theta - theta*)^T H (theta - theta*) with Hessian H, the volume of the level set {theta : L(theta) <= T} is proportional to det(H)^{-1/2} * T^{d/2} where d is the dimension. More isotropic H (lower condition number, closer to being a multiple of the identity) yields larger volume for the same T. Muon's flatter weight spectra are expected to produce more isotropic local Hessians by reducing parameter-scale heterogeneity.

Partial Guarantee: If P1 holds and the loss surface is locally quadratic within the perturbation radius, then perturbation density for Muon bases is higher by a factor related to the ratio of Hessian condition numbers between the two bases.

**Proposition P3 (Spectral Flatness Predicts Density Independently of Optimizer Label):**
Spectral flatness (quantified by 1/CV or stable rank) of the base checkpoint predicts perturbation density D, regardless of which optimizer produced that checkpoint. This is testable via partial Newton-Schulz ablation: applying Newton-Schulz post-hoc to k% of an AdamW checkpoint's layers (increasing k from 0 to 100%) creates a controlled interpolation between the two spectral geometries, with all other training dynamics held constant. If P3 holds, density increases monotonically with k.

Verifiability: P3 is the causal test. It rules out that optimizer-level confounds (different gradient trajectories, different learning rate schedules) are responsible for the density difference, not spectral structure per se.

### Key Tiebreaker Rule

If stable rank R^2 (across layers, in a regression predicting density) exceeds CV R^2 by more than 0.05 (i.e., stable rank is a strictly better predictor), the primary claim is reframed from "spectral flatness measured by CV drives density" to "stable rank drives density" — and the spectral narrative leads with stable rank while CV is reported as a secondary corroborating predictor.

### Limitations of the Theoretical Guarantees

- No PAC-style bound: the geometry is empirical and the locally-quadratic Hessian assumption may not hold at the perturbation radii used.
- Marchenko-Pastur provides a theoretical prior for isotropic weight matrices but does not directly constrain the loss landscape.
- The connection from spectral flatness of W to isotropy of the loss Hessian is an approximation; the Hessian depends on the full computation graph, not just W.

---

## 7. Method Sketch

### Inputs and Outputs

**Inputs:**
- Pre-training corpus D (OpenWebText or equivalent)
- Architecture A: GPT-2 medium (345M parameters) as primary; GPT-2 large (774M) as second scale point
- Optimizers: Muon (Newton-Schulz orthogonalization), AdamW (control), SOAP (kill gate), Shampoo (Phase 2), SAM (Phase 2)
- RandOpt hyperparameters: N in {1000 default, 2000 at epsilon < 0.05}, K kept experts, perturbation radii epsilon in {0.05, 0.10, 0.20}
- All weight matrices normalized to ||W||_F = 1 per layer before perturbation
- Original Frobenius norms logged as confound covariates

**Outputs:**
- Per-layer spectral flatness metrics: CV(sigma_i), stable rank
- Perturbation density D(theta_base, epsilon, tau) at each radius and threshold
- Regression coefficients: density ~ CV, density ~ stable_rank, density ~ CV + stable_rank
- Dose-response curve: density vs k (fraction of layers orthogonalized in K-ablation)
- Statistical summaries: mean +/- std across minimum 3 seeds, bootstrap 95% CI, Wilcoxon signed-rank test vs AdamW baseline

### Core Algorithm

```
# ============================================================
# STEP 1: Train Base Checkpoints
# ============================================================
for optimizer in [Muon, AdamW, SOAP]:
    theta_base = train(architecture=A, corpus=D, steps=20000,
                       optimizer=optimizer,
                       seed=seed)  # minimum 3 seeds each
    save_checkpoint(theta_base, optimizer, seed)

# ============================================================
# STEP 2: Spectral Flatness Measurement
# (all layers normalized to ||W||_F = 1 first)
# ============================================================
def measure_spectral_flatness(theta):
    metrics = {}
    for layer_name, W in theta.named_2d_matrices():
        W_norm = W / frobenius_norm(W)          # normalize
        U, s, V = svd(W_norm)
        CV = std(s) / mean(s)                   # coefficient of variation
        stable_rank = frobenius_norm(W)**2 / spectral_norm(W)**2
        # Note: stable_rank uses ORIGINAL W (before norm), logged separately
        metrics[layer_name] = {
            'CV': CV,
            'stable_rank': stable_rank,
            'frobenius_norm': frobenius_norm(W),  # confound covariate
            'layer_type': classify_layer(layer_name)  # attention/MLP/embedding
        }
    return metrics

# ============================================================
# STEP 3: Layer-Adaptive Sigma Rule
# ============================================================
def compute_adaptive_sigma(metrics, sigma_base, metric='CV'):
    sigmas = {}
    median_metric = median([m[metric] for m in metrics.values()])
    for layer_name, m in metrics.items():
        ratio = m[metric] / median_metric
        ratio_clipped = clip(ratio, 0.5, 2.0)
        sigmas[layer_name] = sigma_base * ratio_clipped
    return sigmas

# ============================================================
# STEP 4: RandOpt Sampling with Layer-Adaptive Radius
# (50-sample power analysis pilot first)
# ============================================================
def randopt_density(theta_base, sigmas, N, tau, epsilon):
    # Power analysis: 50 samples first
    pilot_scores = []
    for i in range(50):
        delta = {l: normal(0, sigmas[l]) for l in theta_base.layers()}
        theta_i = theta_base + delta
        pilot_scores.append(eval_zero_shot(theta_i, D_val))
    d = cohens_d(pilot_scores, baseline_scores)
    if d < 0.5:
        N = 2000  # escalate at small radii

    # Full sampling
    expert_count = 0
    for i in range(N):
        delta = {l: normal(0, sigmas[l]) for l in theta_base.layers()}
        # Perturbation is on W_normalized; re-scale back to original norm after
        theta_i = theta_base + delta
        score_i = eval_zero_shot(theta_i, D_val)
        if score_i >= tau:
            expert_count += 1

    density = expert_count / N
    return density

# ============================================================
# STEP 5: Density Regression
# ============================================================
# Collect (CV_layer, stable_rank_layer, density_layer) triples
# across all layers, all checkpoints, all seeds

regression_results = {}
for predictor in ['CV', 'stable_rank', 'CV+stable_rank']:
    regression_results[predictor] = linear_regression(
        X=spectral_metrics[predictor],
        y=density_per_layer,
        covariates=['frobenius_norm', 'layer_type', 'model_size']
    )

# Tiebreaker: if stable_rank R^2 > CV R^2 + 0.05, lead narrative with stable_rank
if regression_results['stable_rank'].R2 > regression_results['CV'].R2 + 0.05:
    primary_predictor = 'stable_rank'
else:
    primary_predictor = 'CV'

# ============================================================
# STEP 6: K-Ablation (Partial Newton-Schulz Causal Test)
# ============================================================
# Apply Newton-Schulz post-hoc to k% of AdamW checkpoint's layers
for k in [0, 10, 25, 50, 75, 100]:  # 6 interpolation points
    theta_ablated = partial_newton_schulz(theta_AdamW, fraction=k/100)
    metrics_ablated = measure_spectral_flatness(theta_ablated)
    density_ablated = randopt_density(theta_ablated, ...)
    record(k, metrics_ablated, density_ablated)

# Target: Spearman rho(k, density) > 0.7 as dose-response requirement

# ============================================================
# STEP 7: Statistical Testing
# ============================================================
for result in results_per_seed_per_optimizer:
    compute_mean_std(result)
    bootstrap_95ci(result, n_bootstrap=10000)
    wilcoxon_signed_rank(Muon_densities, AdamW_densities)
```

### Key Properties of the Method

- **Scale invariance**: All perturbations are applied to normalized weight matrices (||W||_F = 1), so density comparisons are not confounded by Muon's known tendency to produce smaller-norm weights.
- **Causal identification**: The K-ablation is a post-hoc intervention that isolates spectral flatness as the causal variable, holding all training dynamics constant.
- **Falsifiability**: Three hard kill gates (Week 2) can stop the entire experiment before Phase 2 begins.

---

## 8. Method Variants (Multi-Level Framework)

### Level 1 — Flat-Rate Priming (Simplest Test)

**Description**: Train a Muon base and an AdamW base. Apply uniform sigma (no layer adaptation). Compare perturbation density at three radii (epsilon = 0.05, 0.10, 0.20).

**Scientific Question**: Does optimizer choice alone (Muon vs. AdamW) produce measurably different thicket density under identical sampling conditions?

**What It Tests**: The pure effect of optimizer choice, controlling for everything else.

**Limitation**: Ignores per-layer spectral heterogeneity. Attention layers, MLP layers, and embedding layers exhibit very different singular value spectra even within the same model. Uniform sigma over-perturbs anisotropic layers and under-explores isotropic ones, reducing density efficiency without changing the fundamental geometry.

**Expected Outcome**: If Muon's spectral flatness hypothesis is correct, Muon base achieves > 5% higher density than AdamW base at epsilon = 0.10 with N = 1000 samples. This level is the minimum viable experiment (MVE) and the only level required to pass the Phase 1 kill gate.

### Level 2 — Layer-Adaptive Radius Schedule

**Description**: Add the layer-adaptive sigma rule: sigma(l) = sigma_base × clip(metric(l) / median_metric, 0.5, 2.0), where metric is the winning predictor from the P1 regression (CV or stable rank). Compare density vs. Level 1 (fixed sigma) for both Muon and AdamW bases.

**Scientific Question**: Does per-layer spectral adaptation increase perturbation budget efficiency, independent of the base optimizer?

**What It Tests**: Whether the information in the per-layer spectral signature can be exploited to improve the yield of the perturbation budget. If Level 2 improves density for AdamW as well as Muon, it demonstrates a general-purpose sampling improvement, not a Muon-specific advantage.

**Layer-Type Stratification**: Results are reported separately for attention (Q/K/V/O projection) layers, MLP (feedforward) layers, and embedding layers. This catches the case where the spectral flatness effect is driven by one layer type only, which would change both the theoretical interpretation and the practical recommendation.

**Limitation**: The adaptive rule uses the winning metric from Phase 1 regression; if metric choice is unstable across seeds, Level 2 requires a pre-registered tie-breaking rule (stable rank wins ties with CV, as specified).

### Level 3 — Partial Orthogonalization Causal Test

**Description**: Take a converged AdamW checkpoint. Apply Newton-Schulz orthogonalization post-hoc to k% of its layers, sweeping k in {0, 10, 25, 50, 75, 100}. For each k, measure spectral flatness and perturbation density. This creates an interpolation from AdamW to Muon geometry holding all training dynamics constant.

**Scientific Question**: Is spectral flatness itself the causal mechanism for increased density, or is it merely correlated with other properties of the Muon training trajectory (e.g., gradient norm trajectory, different implicit regularization)?

**Why This Is the Critical Causal Test**: This is the only experimental manipulation in the literature that holds all training dynamics constant (same optimizer, same training steps, same data) while isolating spectral structure as the independent variable. No prior work has performed this intervention. Turbo-Muon and Mousse reach similar endpoint spectra via different paths, but neither provides a controlled interpolation between AdamW and Muon spectral geometry at the same checkpoint.

**Required Result**: Spearman rho(k, density) > 0.7 across the 6 k values. A monotone dose-response in both CV reduction and density increase with k is required to confirm the causal mechanism. If the dose-response is non-monotone (e.g., density increases up to k=50 then decreases), the causal story requires qualification but the correlation result still stands.

**Limitation**: Post-hoc Newton-Schulz changes the spectral structure but also changes the weight values; it is possible that orthogonalization degrades task performance of the base, reducing density for a different reason. This is controlled by measuring the base model's loss before and after orthogonalization and including loss as a covariate.

### Level 4 — Geometry-Aware Wishart Perturbations

**Description**: Replace isotropic Gaussian perturbations with perturbations drawn from a Wishart distribution parameterized by the empirical Hessian at theta_base. The Hessian is approximated via the Hutchinson trace estimator (100 Hessian-vector products per layer). This aligns the perturbation distribution with the actual loss basin geometry.

**Scientific Question**: Does geometry-aware sampling further amplify the Muon thicket advantage, or does the Gaussian approximation already capture most of the benefit?

**What It Tests**: Whether the theoretical connection between spectral flatness and isotropic Hessians (Proposition P2) is tight enough that geometry-aware sampling provides additional gain beyond the adaptive sigma rule from Level 2.

**Limitation**: Hutchinson Hessian estimation adds approximately 30 GPU-hours of compute per model. Level 4 is only run if Levels 1-3 establish the core result; it is an enrichment, not a gate.

**Expected Outcome**: If P2 is tight (spectral flatness predicts Hessian isotropy well), geometry-aware perturbations should provide minimal additional gain over Level 2. If there is significant additional gain, it suggests the Hessian carries structural information beyond the weight spectrum — an interesting secondary finding.

---

## 9. Implementation Plan

### Timeline Overview (14 Weeks)

| Week | Phase | Task | Compute (GPU-hrs) | Success Criterion |
|---|---|---|---|---|
| 1 | Phase 1 / MVE | Train GPT-2 medium (345M) with Muon, AdamW, SOAP. Collect checkpoints at steps 5K, 10K, 20K. | 45 | Checkpoints saved; SVD computed per layer |
| 2 | Phase 1 / Kill Gate | SOAP vs Muon spectral comparison. Regression: density ~ CV, ~ stable_rank. Power analysis pilot. | 20 | Kill gate decision made; primary predictor identified |
| 3 | Phase 1 | K-ablation: partial Newton-Schulz on AdamW checkpoint (k = 0, 10, 25, 50, 75, 100). Measure CV, stable_rank, density at each k. | 25 | Spearman rho(k, density) measured |
| 4 | Phase 1 | Layer-adaptive sigma pilot using winning metric. Layer-type stratification (attention/MLP/embedding). | 20 | Sigma schedule validated; per-layer-type results collected |
| 5-7 | Phase 2 | Full multi-seed run (3+ seeds per optimizer). Add Shampoo, SAM (3 sharpness radii). GPT-2 medium full density sweep at all epsilons. | 200 | Mean +/- std; Wilcoxon tests computed |
| 8-9 | Phase 2 | SAM ablation: do flat sharpness minima (SAM) produce density gains matching Muon? | 80 | SAM vs Muon density comparison at epsilon = 0.10 |
| 10-11 | Phase 3 | GPT-2 large (774M) scale replication. Confirm density scaling law holds and spectral predictor remains consistent. | 300 | R^2 for spectral predictors at 774M comparable to 345M |
| 12 | Phase 3 | Level 4 (Wishart perturbations) if budget permits. | 30 | Additional density gain from geometry-aware sampling measured |
| 13 | Writing | Paper draft, ablation tables, figures. | — | Draft complete |
| 14 | Revision | Respond to self-review, polish experiments. | Contingency 80 | Final experiment count stable |

**Total Estimated Compute: ~790 GPU-hours** (A100-equivalent)

### Hyperparameter Table

| Optimizer | Learning Rate | Batch Size | LR Schedule | Weight Decay | Optimizer-Specific |
|---|---|---|---|---|---|
| Muon | 0.01 (outer) | 512 | Cosine decay, warmup 1K steps | 0.0 | Newton-Schulz iterations=5, inner Adam lr=0.001 |
| AdamW | 3e-4 | 512 | Cosine decay, warmup 1K steps | 0.1 | beta1=0.9, beta2=0.95, eps=1e-8 |
| SOAP | 3e-4 | 512 | Cosine decay, warmup 1K steps | 0.1 | preconditioner_freq=10, beta2=0.95 |
| Shampoo | 3e-4 | 512 | Cosine decay, warmup 1K steps | 0.1 | update_freq=100, epsilon=1e-6 |
| SAM (rho=0.05) | 3e-4 | 512 | Cosine decay, warmup 1K steps | 0.1 | rho=0.05 |
| SAM (rho=0.10) | 3e-4 | 512 | Cosine decay, warmup 1K steps | 0.1 | rho=0.10 |
| SAM (rho=0.20) | 3e-4 | 512 | Cosine decay, warmup 1K steps | 0.1 | rho=0.20 |

All other hyperparameters held constant across optimizers (same architecture, same data order per seed, same evaluation protocol).

### Failure Modes and Mitigations

| Failure Mode | Probability | Impact | Mitigation |
|---|---|---|---|
| Muon density advantage < 5% (null result at MVE) | 20% | Fatal to central claim | Kill gate at Week 2 triggers early stop; reframe as negative result with spectral measurement methodology contribution |
| SOAP matches Muon spectrally (kill gate triggered) | 15% | Demotes Muon-specific story | Reframe: "any whitening improves density" is a weaker but publishable result; propose SOAP as the practical recommendation |
| SAM achieves same density as Muon | 20% | Demotes spectral flatness story | Report as: sharpness and spectral flatness are correlated; density is driven by basin flatness (which both capture); nuanced conclusion, still publishable |
| K-ablation dose-response non-monotone | 15% | Weakens causal claim | Report correlation result without causal claim; Level 3 becomes descriptive, not causal |
| GPT-2 large (774M) does not replicate | 10% | Limits scaling claim | Limit claims to 345M; flag scaling as open question |
| Seed variance too high for statistical significance | 10% | Entire result unreliable | Escalate to 5 seeds; use bootstrap CI; if variance > signal, report as inconclusive |
| Compute budget overrun | 10% | Delays paper | Drop Level 4 (Wishart); drop Shampoo if SAM already covers second-order territory |

---

## 10. Experimental Plan

### Minimum Viable Experiment (MVE) — Weeks 1-2

**Purpose**: Establish the core empirical claim at minimum cost before committing to full-scale experiments.

**Setup**:
- Architecture: GPT-2 medium (345M parameters)
- Training: OpenWebText, 20K steps
- Optimizers: Muon, AdamW, SOAP
- Checkpoints saved at: 5K, 10K, 20K steps
- Per checkpoint, per layer: compute CV(sigma_i), stable rank, weight Frobenius norm
- All 2D weight matrices normalized to ||W||_F = 1 before perturbation
- RandOpt density: N = 1000 samples at epsilon in {0.05, 0.10, 0.20}
- Power analysis: 50-sample pilot first; if Cohen's d < 0.5, escalate to 2000
- Minimum 3 seeds per optimizer

**MVE Kill Criteria (any one triggers full stop):**
1. Muon vs. AdamW density difference < 5% at epsilon = 0.10 (null result; not worth proceeding)
2. SOAP density within 10% of Muon AND SOAP CV within 10% of Muon (mechanism is "any whitening"; Muon-specific framing unsupported)
3. Stable rank R^2 > CV R^2 + 0.05 AND CV does not independently predict density (NS framing demoted; rewrite around stable rank)

**Cost**: ~45 GPU-hours

### Three-Phase Structure

#### Phase 1 — Mechanistic Characterization (Weeks 1-4, ~110 GPU-hours)

**Week 1: MVE run.** Collect raw singular value spectra. Compute spectral flatness metrics per layer per checkpoint. Run power analysis pilot.

**Week 2: SOAP kill gate + regression.** Three regressions: density ~ CV, density ~ stable_rank, density ~ CV + stable_rank. Log original norms as covariates. If kill gate triggers, stop.

**Week 3: K-ablation (partial Newton-Schulz causal test).** Apply Newton-Schulz post-hoc to k in {0, 10, 25, 50, 75, 100}% of AdamW checkpoint's layers. For each k: measure CV, stable rank, density. Compute Spearman rho(k, density). Require monotone dose-response in both CV reduction and density increase to confirm causal mechanism.

**Week 4: Layer-adaptive sigma pilot.** Use winning metric (CV or stable rank) to compute per-layer sigma. Test against uniform sigma baseline. Report density improvement by layer type (attention / MLP / embedding separately).

#### Phase 2 — Full Statistical Validation (Weeks 5-9, ~280 GPU-hours)

**Baselines:**

| Baseline | Phase | Purpose | Kill/Demote Trigger |
|---|---|---|---|
| AdamW | 1 + 2 | Primary control | Density diff < 5% (kill gate) |
| SOAP | 1 (kill gate) | Spectral mechanism check | SOAP matches Muon (kill gate) |
| Shampoo | 2 | Second-order family benchmark | No kill; contextual comparison |
| SAM (rho=0.05) | 2 | Sharpness-as-density null | Demotes spectral story if SAM matches Muon |
| SAM (rho=0.10) | 2 | Middle sharpness radius | Same |
| SAM (rho=0.20) | 2 | Large sharpness radius | Same |
| Partial Muon (K-ablation) | 1 | Dose-response causal test | No kill; evidence for mechanism |
| Vanilla RandOpt (uniform sigma) | 1 + 2 | Density reference without adaptive schedule | No kill; measures Level 2 improvement |

**Statistical Requirements:**
- Minimum 3 seeds per optimizer (5 if variance is high)
- All results reported as mean +/- std across seeds
- Bootstrap 95% CI with 10,000 resamples
- Primary test: Wilcoxon signed-rank test (Muon density vs. AdamW density, paired by seed and epsilon)
- Secondary test: Spearman rank correlation between spectral flatness index and density across all layers and optimizers

**Ablations:**

| Ablation | Purpose |
|---|---|
| Fixed sigma vs. layer-adaptive sigma | Tests whether radius schedule matters or just base geometry |
| Partial Newton-Schulz (k sweep) | Tests spectral flatness as causal mechanism |
| CV vs. stable rank vs. condition number as flatness index | Tests robustness of measurement |
| Attention vs. MLP vs. embedding stratification | Tests whether effect is layer-type specific |
| Training steps (5K vs. 10K vs. 20K) | Tests whether spectral advantage emerges early or late |

**Datasets:**
- Pre-training: OpenWebText (standard GPT-2 setup)
- Evaluation (zero-shot density): held-out subset of OpenWebText + 3 downstream tasks (HellaSwag, WinoGrande, ARC-Easy) for external validity

**Metrics:**

| Metric | Role | Target |
|---|---|---|
| CV(sigma_i) per layer | Primary spectral predictor (contested by stable rank) | Lower for Muon vs. AdamW in > 70% of layers |
| Stable rank ||W||_F^2 / ||W||_2^2 (original W, not normalized) | Co-equal spectral predictor | Higher for Muon vs. AdamW in > 70% of layers |
| Frobenius norm per layer | Confound covariate | Logged; not a primary metric |
| RandOpt density at epsilon = 0.05, 0.10, 0.20 | Primary outcome | Muon > AdamW by > 5% at epsilon = 0.10 |
| Spearman rho(k, density) in K-ablation | Dose-response causal evidence | > 0.7 |
| R^2 for density ~ CV regression | Predictive validity of spectral flatness | > 0.4 in full dataset |
| R^2 for density ~ stable_rank regression | Predictive validity of stable rank | Compared to CV R^2 for tiebreaker |
| Zero-shot downstream task performance of soups | External validity | Muon-based soups >= AdamW-based soups at same N |

**Success Criteria:**

Tier A (publication-ready at ICLR 2027):
1. Muon density > AdamW density by > 5% at epsilon = 0.10 (p < 0.05, Wilcoxon, Bonferroni-corrected across 3 radii)
2. Spearman rho(k, density) > 0.7 in K-ablation
3. CV or stable rank R^2 > 0.4 in density regression
4. SOAP kill gate not triggered (Muon retains specific advantage over SOAP)
5. Result replicates at GPT-2 large (774M)

Tier B (publishable as workshop paper or negative result):
1. Density difference exists but < 5% OR not statistically significant
2. Spectral flatness predicts density but causal test (K-ablation) fails
3. SOAP matches Muon (reframe as "whitening is the mechanism, not Muon specifically")

#### Phase 3 — Scale Replication (Weeks 10-12, ~330 GPU-hours)

**Scale Point**: GPT-2 large (774M parameters). Same protocol as Phase 2 with 3 seeds per optimizer.

**Purpose**: Establish that the spectral flatness to density relationship holds across model sizes and does not depend on any idiosyncrasy of GPT-2 medium's architecture.

**Minimum Requirement for Scaling Claim**: R^2 for spectral predictor at 774M must be within 0.1 of R^2 at 345M. Density advantage for Muon must persist (> 5%, p < 0.05).

### Risk Register

| Risk | Likelihood | Severity | Mitigation | Contingency |
|---|---|---|---|---|
| Null result at MVE | 20% | Fatal | Kill gate at Week 2 | Publish methodology + negative result; pivot to tool contribution |
| SOAP matches Muon | 15% | High | Kill gate at Week 2 | Reframe: "whitening expands thicket" is still publishable |
| SAM matches Muon | 20% | Moderate | Phase 2 SAM baseline | Include sharpness as co-predictor; write "flatness, not just spectral flatness" story |
| Scale does not replicate | 10% | Moderate | 774M in Phase 3 | Limit claims to 345M; flag scaling as future work |
| Compute overrun | 10% | Low | Budget contingency 80 hrs | Drop Level 4 (Wishart); drop Shampoo |
| Reviewer questions Turbo-Muon/Mousse differentiation | 30% | Moderate | K-ablation is causal test no prior work has | Emphasize: interpolation-path volume not computable from endpoint spectra alone |

---

## 11. Paper Storyline

### Draft Abstract

Large language models trained with the Muon optimizer — which applies Newton-Schulz orthogonalization to weight gradients — exhibit a distinctive spectral geometry: weight matrices cluster near orthogonality, with coefficient of variation (CV) of singular values significantly lower than models trained with AdamW. We show that this spectral flatness geometrically expands the neural thicket: the fraction of zero-shot Gaussian perturbations around a Muon-trained base that land in task-expert solutions (as measured by RandOpt) is consistently higher than for AdamW-trained bases of identical architecture and training budget, across perturbation radii of 0.05, 0.10, and 0.20 (normalized weight norm units). To establish causality, we introduce a partial Newton-Schulz ablation — applying orthogonalization post-hoc to k% of an AdamW checkpoint's layers — and find a monotone dose-response: Spearman rho(k, density) > 0.8 across layer fractions from 0% to 100%. Layer-adaptive perturbation radii (derived from per-layer spectral flatness and clipped to [0.5, 2.0] times baseline) further improve sampling efficiency. Jointly, these results establish that pre-training optimizer choice is not only a training-speed decision but a geometry-shaping decision with downstream consequences for zero-shot model soup quality. Practical implication: Muon-primed bases enable higher-quality zero-shot model soups at the same perturbation budget as AdamW-primed bases, without any fine-tuning.

### Paper Structure Outline

1. **Introduction**: Neural thickets as the mechanism for post-training success. Optimizer choice as a first-class decision for post-training geometry. Preview of spectral flatness hypothesis and main results.

2. **Background**: Muon and Newton-Schulz orthogonalization. Neural Thickets and RandOpt. Spectral properties of weight matrices. Loss landscape geometry.

3. **Hypothesis and Theoretical Framework**: P0 (thicket density as basin volume). P1 (Muon produces flatter spectra). P2 (flatter spectra expand reachable basin volume). P3 (spectral flatness causally predicts density). Limitations.

4. **Methods**: Base training setup. Spectral flatness measurement (CV and stable rank, normalized weights). Layer-adaptive sigma rule. RandOpt density protocol. K-ablation design. Statistical testing protocol.

5. **Results — Phase 1 (MVE and Mechanism)**: Muon vs. AdamW spectral flatness comparison (per-layer, per-layer-type). Density comparison at 3 radii (mean +/- std, 3 seeds, bootstrap CI, Wilcoxon). SOAP comparison (kill gate result). K-ablation dose-response curve. Regression: density ~ CV, density ~ stable_rank, density ~ CV + stable_rank.

6. **Results — Phase 2 (Full Baselines)**: SAM comparison (flat sharpness vs. spectral flatness). Shampoo comparison. Layer-type stratification. Adaptive vs. fixed sigma improvement.

7. **Results — Phase 3 (Scale)**: GPT-2 large (774M) replication. Scaling law for spectral predictor R^2.

8. **Discussion**: What "spectral priming" means for optimizer selection. Implications for post-training pipeline design. Limitations and future work (Level 4 Wishart perturbations, NuMuon nuclear-norm geometry, MoE upcycling from thicket samples).

9. **Conclusion**: Optimizer choice is a geometry-shaping decision. Muon primes the thicket.

---

## 12. Novelty Risk Assessment

### Claim-by-Claim Novelty Analysis

**Claim 1: Muon produces flatter singular value spectra than AdamW.**
Prior work: Muon Accelerates Grokking (2504.16041) notes Muon's spectral constraints but does not measure CV or stable rank per layer in large models. Novelty: The systematic per-layer spectral measurement at transformer scale (345M-774M) with proper normalization is new. Risk: Low. This is a measurement contribution, and even if partially anticipated, the scale and rigor are new.

**Claim 2: Spectral flatness (CV or stable rank) predicts thicket density.**
Prior work: Neural Thickets does not study spectral predictors of density. Optimizer Bias on Merging (2510.04686) studies fine-tuned merging, not perturbation density. Novelty: The regression connecting a spectral property of the base checkpoint to perturbation density is completely new. Risk: Low. No prior paper makes this connection.

**Claim 3: Partial Newton-Schulz ablation establishes causality.**
Prior work: No prior paper performs a post-hoc orthogonalization intervention for causal identification of spectral effects on any downstream property. Novelty: High. This is the most novel methodological contribution. Risk: Very low (it is a controlled experiment; the novelty is the design, not a claim about the world).

**Claim 4: Layer-adaptive sigma rule improves perturbation efficiency.**
Prior work: Neural Thickets uses uniform sigma. No paper derives adaptive radii from per-layer spectral properties. Novelty: Moderate-to-high. The idea is natural once the spectral flatness connection is established, but has not been done. Risk: Low.

**Claim 5: Muon-primed soups achieve higher density than AdamW-primed soups at equivalent budget.**
Prior work: Model Soups uses fine-tuning; does not study base optimizer effects. Novelty: High. This is a new use case for Muon (post-training efficiency, not training efficiency). Risk: Moderate — depends on Claim 2 being confirmed.

### Crowded-Area Risks

- "Muon engineering variants" (Turbo-Muon, MUD, NuMuon): NOT our work. We use Muon as a tool and study its geometric footprint.
- "Model merging interference resolution" (TIES, DARE): NOT our primary contribution. We study perturbation density, not task vector interference.
- "LoRA variants": NOT in scope.
- "Optimizer benchmarking": NOT our work. We do not benchmark Muon for training speed.

### Main Novelty Risk

The primary novelty risk is **SOAP equivalence**: if SOAP produces identical spectral geometry to Muon and identical thicket density, the Muon-specific story collapses to "whitening / orthogonalization helps." This is addressed by the Week 2 kill gate. If SOAP matches Muon, the paper is reframed as "whitening-based optimizers expand the neural thicket" — still publishable, but weaker.

Secondary risk: **SAM matches Muon**. If sharpness-aware training achieves the same density as Muon at the same compute budget, the spectral flatness mechanism is one of several paths to the same outcome. The paper is then "both spectral flatness and loss sharpness predict density; they are correlated but distinct mechanisms." Still publishable.

### Scoop Risk

The Neural Thickets paper (2603.12228) was published March 2026. The optimizer-connection gap was clearly not in scope for that paper. No paper currently in the literature targets this gap. Scoop risk is moderate: once Neural Thickets becomes widely read, the "what does optimizer choice do to the thicket?" question is an obvious follow-up. Estimated 6-12 months before competition appears. Mitigation: The K-ablation causal test is a specific methodological contribution that would be hard to scoop even if others study the basic correlation.

---

## 13. Quality Checklist

| Item | Status | Notes |
|---|---|---|
| Central claim is falsifiable (kill gates defined) | PASS | Three hard kill gates at Week 2 stop experiment before Phase 2 |
| Scale invariance of measurement (||W||_F normalization) | PASS | All perturbations applied to normalized weight matrices; original norms as covariates |
| Co-equal predictors both measured (CV and stable rank) | PASS | Both measured; tiebreaker rule defined (stable rank leads if R^2 > CV R^2 + 0.05) |
| Confound identification and control (Frobenius norm) | PASS | Original norms logged as covariate in all regressions |
| Causal test present (not just correlation) | PASS | K-ablation (partial Newton-Schulz) is the causal intervention |
| SOAP kill gate prevents false Muon-specific claim | PASS | SOAP run in Week 2 as Phase 1 kill gate |
| SAM baseline prevents false spectral-only story | PASS | SAM with 3 sharpness radii in Phase 2 |
| Adequate power analysis | PASS | 50-sample pilot; escalate to 2000 at epsilon < 0.05; Cohen's d threshold |
| Minimum seeds per optimizer (>= 3) | PASS | Minimum 3 seeds; 5 if variance is high |
| Error bars on all results (mean +/- std, bootstrap CI) | PASS | Bootstrap 95% CI with 10,000 resamples; Wilcoxon signed-rank test |
| Layer-type stratification | PASS | Attention / MLP / embedding reported separately |
| Second scale point (GPT-2 large 774M) | PASS | Phase 3 dedicated to 774M replication |
| Full hyperparameter table | PASS | All 7 optimizer configurations fully specified |
| Turbo-Muon / Mousse differentiation addressed | PASS | K-ablation is causal test not replicable from endpoint spectra; interpolation-path volume argument stated |
| Compute budget estimate | PASS | ~790 GPU-hours, itemized by phase |
| Failure modes documented with mitigations | PASS | 7 failure modes with probability, impact, mitigation, and contingency |
| Paper storyline coherent end-to-end | PASS | 9-section paper structure maps to experimental phases |
| Circularity in adaptive sigma addressed | PASS | Fixed-sigma Level 1 ablation; adaptive sigma applied equally to both optimizers using their own SF values |
| Tiebreaker rule for CV vs. stable rank | PASS | Defined: stable rank leads narrative if R^2 > CV R^2 + 0.05 |
| Layer-adaptive sigma clipped to prevent extreme values | PASS | clip(ratio, 0.5, 2.0) prevents degenerate sigma values |

**Summary: 20/20 items PASS.**

---

## 14. Final Verdict

**Recommendation: Proceed to full implementation.**

**Confidence Level: High**

**Rationale:**

This proposal occupies a genuine gap at the intersection of three active sub-fields (Muon optimization, Neural Thickets, optimizer-geometry effects on reusability) that have not been jointly studied. The central claim is mechanistically grounded (Propositions P0-P3), empirically falsifiable (three hard kill gates), and causally testable (K-ablation). The experimental design is statistically rigorous (minimum 3 seeds, bootstrap CI, Wilcoxon tests, power analysis). Key competing explanations are addressed by design (SOAP kill gate, SAM baseline, Frobenius norm covariate, partial Newton-Schulz causal intervention).

**The most important novelty**: the partial Newton-Schulz K-ablation is a clean causal identification strategy that no prior work has deployed for this purpose. Even if the core spectral flatness to density correlation is challenged by reviewers, the causal test provides evidence that goes beyond correlational analysis. Turbo-Muon and Mousse cannot replicate this test because the interpolation-path volume (between AdamW and Muon geometry, measured over 6 k values) is not computable from the endpoint spectra of any existing model.

**Primary Risks and Responses:**
1. SOAP equivalence (15% probability): addressed by Week 2 kill gate; reframe as "whitening hypothesis."
2. SAM equivalence (20% probability): addressed by Phase 2; results in "multiple paths to flat loss basin" conclusion.
3. Null result at MVE (20% probability): addressed by kill gate; pivot to methodology contribution.

**Venue Fit**: ICLR 2027 is appropriate. The paper connects pre-training optimizer choice to post-training geometry, a topic with high relevance to the current state of the field (Muon adoption growing; Neural Thickets paper published March 2026). The experimental rigor (multi-seed, multi-scale, causal test, five baselines) exceeds ICLR standards. NeurIPS 2027 is the fallback if ICLR 2027 is missed.

**Estimated Total Compute**: ~790 GPU-hours (A100-equivalent). This is feasible for a single research group with access to a medium-sized compute cluster.

**Timeline to Submission**: 14 weeks from start to draft-complete; 2 weeks for revision = 16 weeks total. ICLR 2027 deadline is achievable.

---

## Appendix A: Review History

### Round 1 (R1)

**VP Reviewer — 4 Issues:**

R1-VP-1 [SEVERE]: Stable rank was not included as a co-equal predictor alongside CV. CV alone can be confounded by scale (high-magnitude singular values with low variance look "flat" by CV but not by stable rank). Resolution: Added stable rank as a co-equal predictor throughout. Defined tiebreaker rule: if stable rank R^2 > CV R^2 + 0.05, the stable-rank narrative leads.

R1-VP-2 [MAJOR]: Weight matrices were not normalized before perturbation. Muon is known to produce smaller-norm weights than AdamW; higher density for Muon could be a direct artifact of starting closer to the origin in weight space, not spectral flatness. Resolution: All weight matrices normalized to ||W||_F = 1 before perturbation. Original norms logged as confound covariate in all regressions.

R1-VP-3 [MAJOR]: SOAP was originally placed in Phase 2 as a secondary baseline. If SOAP matches Muon, the entire Phase 1-3 effort has been spent on a claim that collapses to "any whitening works." Resolution: SOAP moved to Week 2 of Phase 1 as a kill gate. If SOAP density is within 10% of Muon AND SOAP CV is within 10% of Muon, Phases 2-3 are halted.

R1-VP-4 [MINOR]: Default sample count of 500 was underpowered for small epsilon values where density differences are small. Resolution: Default raised to 1000. Power analysis from 50-sample pilot; escalate to 2000 at radii < 0.05.

**Advisor Reviewer — 1 Issue:**

R1-ADV-1 [MINOR]: No sharpness-aware baseline. SAM produces flat loss minima by construction; if SAM achieves the same density as Muon, the spectral flatness explanation is at best one of several paths to the same outcome. Resolution: SAM added as Phase 2 baseline with 3 sharpness radii (rho = 0.05, 0.10, 0.20).

### Round 2 (R2)

No major issues raised. R1 revisions accepted. Minor wording clarifications incorporated.

### Round 3 (R3)

**Advisor Reviewer — 3 Issues:**

R3-ADV-1 [MAJOR]: Results reported from single seeds only. Without multiple seeds, mean +/- std is unavailable and statistical tests cannot be run. The density advantage could be a random seed artifact. Resolution: Minimum 3 seeds per optimizer added throughout. All results reported as mean +/- std. Bootstrap 95% CI with 10,000 resamples added. Wilcoxon signed-rank test (Muon vs. AdamW, paired by seed) added as primary statistical test.

R3-ADV-2 [MINOR]: Hyperparameters not specified per optimizer. Without a complete table, results are not reproducible. Resolution: Full hyperparameter table added (Section 9): LR, batch size, LR schedule, weight decay, and optimizer-specific parameters for all 7 optimizer configurations.

R3-ADV-3 [MINOR]: All layers aggregated without stratification. If the spectral flatness effect is concentrated in attention layers (which are known to have different spectral properties than MLP layers), the aggregate result may obscure the mechanism. Resolution: Layer-type stratification (attention / MLP / embedding) added throughout. All density and spectral metrics reported separately by layer type.

**VP Reviewer — 2 Issues:**

R3-VP-1 [MINOR]: Only one model scale (345M). A result that does not replicate at a second scale is of limited generality. Resolution: GPT-2 large (774M) added as Phase 3 second scale point. Phase 3 dedicated to replication at this scale with 3 seeds per optimizer.

R3-VP-2 [MINOR]: Layer-adaptive sigma rule used raw metric values; extreme ratios could cause degenerate perturbation radii. Resolution: Sigma rule updated to sigma_base × clip(metric / median_metric, 0.5, 2.0), capping the ratio between 0.5 and 2.0. Median computed over all layers of the checkpoint.

### Round 4 (R4)

**VP Reviewer — 1 Issue:**

R4-VP-1 [MAJOR]: Turbo-Muon (2512.04632) speeds up Newton-Schulz by 2.8x and Mousse/MUD (2603.17970) replaces polar decomposition with Cholesky-based whitening. If these produce the same spectral geometry as standard Muon and the same thicket density, what is specific to the Muon variant chosen? More critically: does the proposal distinguish itself from a hypothetical paper that simply runs Turbo-Muon and measures the same density?

Resolution: Three-part causal-chain argument incorporated throughout:

1. **Density is a spectrum×task joint property**: Thicket density depends not only on the spectral geometry of the weight matrices but also on the alignment between the perturbation directions and the task gradient structure. Turbo-Muon and Mousse reach similar endpoint spectra but traverse different optimization trajectories. Whether these different trajectories produce the same task-gradient alignment is an empirical question this proposal measures directly.

2. **The partial-NS K-ablation is a causal test no prior work has**: The K-ablation measures what happens when only k% of layers are orthogonalized, creating an interpolation from AdamW to Muon geometry. The interpolation-path volume (density at each k value, from k=0 to k=100) is not computable from examining the endpoint spectra of Turbo-Muon or Mousse models. You cannot replicate an interpolation experiment by observing endpoints. This specific causal test is what distinguishes this proposal from any hypothetical variant-comparison paper.

3. **Practical recommendation is optimizer-agnostic**: The paper's practical conclusion is "whitening-style optimization expands the thicket." If Turbo-Muon and Mousse produce the same density as standard Muon, the conclusion becomes "use whichever whitening optimizer is fastest." This strengthens the practical contribution; it does not weaken the science.

---

## Appendix B: Key References

1. **Jordan, K. (2024). Muon optimizer.** No formal arXiv; scalability follow-up at arXiv:2502.16982. Core contribution: Newton-Schulz orthogonalization applied to 2D weight matrices; steepest descent under spectral norm; ~2x compute efficiency vs AdamW on NanoGPT speedrun.

2. **Gan, Y. & Isola, P. (2026). Neural Thickets.** arXiv:2603.12228. Large pretrained models enter a "thicket regime" where Gaussian perturbations densely populate task-expert solutions. RandOpt matches PPO/GRPO/ES at same FLOP budget. Spectral discordance quantifies diversity. Direct predecessor to this proposal.

3. **Wortsman, M. et al. (2022). Model Soups.** arXiv:2203.05482. Averaging fine-tuned variants of the same pretrained model improves accuracy. Establishes the loss basin averaging mechanism. Does not study perturbation-based sampling or optimizer geometry.

4. **Vyas, N. et al. (2024). SOAP: Improving and Stabilizing Shampoo using Adam.** arXiv:2409.11321. Adam in Shampoo's eigenbasis. Second-order efficiency at first-order cost. Kill gate for this proposal: if SOAP matches Muon spectrally and in density, the mechanism is "any whitening."

5. **Ilharco, G. et al. (2022). Editing Models with Task Arithmetic.** arXiv:2212.04089. Task vectors support linear arithmetic for multi-task composition. Background for understanding the post-training weight-space geometry literature.

6. **Ainsworth, S. et al. (2022). Git Re-Basin.** arXiv:2209.04836. Permutation alignment removes loss barriers between independently trained networks. Different mechanism (combinatorial, not spectral) from this proposal's approach.

7. **Yadav, P. et al. (2023). TIES-Merging.** arXiv:2306.01708. Sign conflicts and redundant parameters cause merging interference; trim-elect-merge resolves it. Background for the merging interference literature.

8. **Chen, Z. et al. (2024). Optimizer Bias on Merging.** arXiv:2510.04686. Effective noise scale (optimizer + data) determines merging compatibility. Does not evaluate Muon; does not connect to perturbation density. Most directly adjacent existing work to this proposal.

9. **George, T. et al. (2024). Turbo-Muon.** arXiv:2512.04632. Newton-Schulz iteration sped up by 2.8x via preconditioning. Pure engineering speedup; does not change the asymptotic spectral geometry. Relevant to Problem Gap (Section 5) and Round 4 review response.

10. **MUD / Mousse (2026).** arXiv:2603.17970. Cholesky-based whitening surrogate for Muon's polar decomposition. Faster wall-clock. Same asymptotic spectral target as Muon. Relevant to Round 4 review response; distinguished from this proposal by K-ablation causal test argument.

11. **NuMuon (2026).** arXiv:2603.03597. Nuclear-norm constraint on Muon induces low-rank compressible weights. Different downstream goal (compression, not density). Background for understanding the space of Muon variants.

12. **Liu, Z. et al. (2024). Muon Accelerates Grokking.** arXiv:2504.16041. Muon generalizes faster on modular arithmetic. Establishes spectral-constraint to generalization connection at small scale. Does not measure perturbation density or connect to thicket framework.

13. **Yadav, P. et al. (2024). Model Stock.** arXiv:2403.19522. Two fine-tuned models suffice to approximate weight-space centroid for high-quality soup. Background for the model soup efficiency literature; does not use perturbation-based sampling.

14. **Foret, P. et al. (2021). Sharpness-Aware Minimization (SAM).** arXiv:2010.01412. Seeks parameters in flat loss neighborhoods by perturbing weights in the gradient ascent direction. Phase 2 baseline for this proposal: tests whether flat sharpness and spectral flatness are equivalent predictors of thicket density.

15. **Frankle, J. & Carlin, M. (2019). The Lottery Ticket Hypothesis.** arXiv:1803.03635. Sparse winning subnetworks train as fast as dense networks. Background for understanding the relationship between spectral structure and effective model capacity.

16. **Hu, E. et al. (2021). LoRA.** arXiv:2106.09685. Low-rank adapters for parameter-efficient fine-tuning. Background for the post-training adaptation literature. Not in scope for this proposal but relevant to future work (Level 2 variant: are thicket experts expressible as LoRA deltas?).

17. **Yu, T. et al. (2020). PCGrad.** arXiv:2001.06782. Projecting conflicting task gradients onto normal planes. Background for multi-task gradient conflict literature. Related to the broader question of whether Muon's orthogonality constraints reduce inter-task interference at the gradient level.

18. **Wortsman, M. et al. (2022). Sparse Upcycling.** arXiv:2212.05055. Dense checkpoints expanded into MoE by duplicating FFN weights. Background for the expert-creation literature. Future work: using thicket samples as diverse MoE expert initializations.
