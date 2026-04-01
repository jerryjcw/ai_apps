# Muon Loss Basin Geometry: A Research Proposal

---

## 1. Title

**Directional Curvature Profiling of Loss Basins: Muon's Newton-Schulz Orthogonalization Implicitly Regularizes Toward Isotropic Basins, Enabling Cost-Efficient Model Merging Without SAM's Overhead**

---

## 2. One-Sentence Thesis

Models fine-tuned with Muon exhibit measurably more isotropic loss basins — characterized by the directional curvature anisotropy ratio κ_top = λ_1/λ_K across the top-K Hessian principal curvature axes — compared to AdamW at matched compute, and this anisotropy signature predicts optimal linear merging coefficients more accurately than scalar basin-width measurements while Muon achieves this isotropy as a free byproduct of training rather than via SAM's explicit 2× per-step overhead.

---

## 3. Research Area Classification

**Primary Area:** Optimization for Deep Learning
**Secondary Areas:** Loss Landscape Geometry, Model Merging, Hessian Spectral Analysis
**Keywords:** Muon optimizer, Newton-Schulz iteration, directional curvature, Hessian eigenvectors, basin anisotropy, stochastic Lanczos quadrature, model merging, SAM cost efficiency, kappa_top

**Positioning:** This work is a targeted measurement study that characterizes how optimizer choice shapes the geometric structure of fine-tuned loss basins, with direct implications for model merging and multi-task composition. It differs from prescriptive methods like SAM (Delving into Sharpness-Aware Minimization) and Mousse (DARE-based sparse merging) in that it measures and explains rather than proposes new training objectives. The directional curvature profiling toolkit it introduces is a standalone methodological contribution usable independently of the Muon-specific findings.

The proposal is positioned at the intersection of three currently active but non-overlapping threads: (1) quasi-orthogonal optimizers (Muon, SOAP) and their implicit spectral effects, (2) loss landscape geometry as a predictor of downstream composability, and (3) the cost-efficiency comparison between explicit sharpness-aware training (SAM) and optimizer-induced flatness. No prior work occupies this intersection.

---

## 4. Closest Prior Work (8 Papers with Comparison Table)

### Paper Summaries

**P1. Muon: Momentum + Newton-Schulz Orthogonalization (Jordan, 2024; arXiv:2502.16982)**
Muon applies a Newton-Schulz (NS) iteration to the gradient to produce an approximately orthogonal update — the polar factor of the gradient — before the momentum step. This forces each parameter update to lie approximately on the Stiefel manifold, removing the scaling component and retaining only the rotational component. Jordan reports improved perplexity on language modeling benchmarks compared to AdamW at equivalent compute. The paper does not analyze the effect of NS orthogonalization on the curvature structure of the resulting loss basins, and does not connect optimizer choice to merging compatibility.

**P2. Neural Thickets (arXiv:2603.12228)**
Introduces the neural thicket concept — the dense cluster of high-performing weight configurations within a Frobenius-norm ball around a trained solution — and quantifies thicket density via random perturbation sampling. Thicket density is a scalar volumetric measure of the pretrained weight region (before fine-tuning). This is a fundamentally different object from the basin shape studied here: thicket density counts how many solutions fit inside a ball, while curvature anisotropy characterizes the shape tensor of a single fine-tuned solution. A basin can be wide in one direction and narrow in all others (a ridge), producing large scalar width but extreme anisotropy — a distinction that thicket density cannot capture.

**P3. SOAP: Combining Shampoo and Adam (arXiv:2409.11321)**
SOAP uses Kronecker-factored Hessian preconditioning to align gradient updates with the curvature structure of the loss. Like Muon, SOAP performs implicit spectral regularization on weight matrices, making it a critical confounder in any optimizer comparison study. SOAP is included as a baseline. The paper does not connect its spectral properties to loss basin curvature anisotropy or downstream merging.

**P4. Sharpness-Aware Minimization (SAM; Foret et al., 2021; arXiv:2010.01412)**
SAM explicitly regularizes toward flat minima by solving a minimax problem at each step: the optimizer first perturbs weights toward the local maximum of the loss surface (cost: 1 full forward pass), then takes a gradient step. This achieves measurably flatter basins at the cost of approximately 2× per-step compute and requires careful selection of the perturbation radius ρ. SAM is the primary cost-efficiency baseline: it explicitly optimizes for basin flatness but requires ρ tuning and extra compute, whereas Muon's isotropy claim is that flatness is achieved implicitly and for free.

**P5. Delving into Sharpness-Aware Minimization (ASAM; Kwon et al., 2021; arXiv:2102.11600)**
ASAM extends SAM with adaptive perturbation radii, improving robustness to the ρ hyperparameter. Both SAM and ASAM are prescriptive: they modify the training objective to achieve flat basins. This work is a measurement study, not a prescriptive method — the distinction being that we characterize which optimizer's implicit geometry produces flat basins rather than designing a new objective to force flatness.

**P6. Model Soups: Averaging Weights of Fine-Tuned Models (arXiv:2203.05482)**
Model Soups demonstrates that averaging weights of multiple fine-tuned variants of the same base model improves accuracy and robustness, contingent on the variants sharing a common loss basin. The method relies on scalar basin width as the implicit predictor of merge compatibility, without characterizing the directional curvature structure of the basin. This work uses only AdamW-trained bases and does not investigate which optimizers produce more merge-compatible basins.

**P7. Optimizer Bias on Model Merging (arXiv:2510.04686)**
The most directly related prior work. This paper observes empirically that optimizer choice affects merge compatibility and coins the term "optimizer bias." It does not provide a mechanistic explanation, does not measure Hessian curvature, and does not compare per-FLOP efficiency of isotropy. The current proposal provides the mechanistic explanation via directional curvature profiling that this prior work explicitly calls for but does not supply.

**P8. Loss Basin Geometry and Generalization (arXiv:2505.17646)**
Recent characterization of loss basin geometric structure, showing that Hessian eigenspectrum correlates with generalization quality and that basins can exhibit complex sub-basin structure. This work uses Hessian geometry but does not study optimizer-induced differences in anisotropy, nor does it compare per-FLOP cost efficiency of different basin-widening strategies. The sub-basin finding motivates our fallback of mixture-of-quadratics fitting when single-cubic fits fail.

### Comparison Table

| Paper | Hessian / Curvature Analysis | Optimizer Comparison | Anisotropy Measurement | Model Merging | Per-FLOP Cost Analysis | Mechanistic Causal Claim | Muon-Specific |
|---|---|---|---|---|---|---|---|
| P1 Muon (2502.16982) | No | Yes (vs AdamW) | No | No | No | No | Yes |
| P2 Neural Thickets (2603.12228) | No | No | No (scalar width) | Implicit | No | No | No |
| P3 SOAP (2409.11321) | Partial (Kronecker) | Yes (vs AdamW) | No | No | No | No | No |
| P4 SAM (2010.01412) | Yes (minimax) | Yes | No | No | No | No | No |
| P5 ASAM (2102.11600) | Yes (adaptive) | Yes | No | No | No | No | No |
| P6 Model Soups (2203.05482) | No | No | No | Yes (core) | No | No | No |
| P7 Optimizer Bias (2510.04686) | No | Yes | No | Yes | No | No | No |
| P8 Basin Geometry (2505.17646) | Yes (core) | No | Partial | No | No | No | No |
| **This work** | **Yes (directional κ_top)** | **Yes (Muon, AdamW, SOAP, SAM×4)** | **Yes (κ_top = λ_1/λ_K, spectral decay)** | **Yes (adaptive α*)** | **Yes (isotropy-per-FLOP at matched wall-clock)** | **Yes (NS → isotropy → merge)** | **Yes** |

**Gap Summary:** No prior work simultaneously (a) profiles directional curvature along principal Hessian eigenvectors, (b) measures the anisotropy ratio κ_top = λ_1/λ_K as a function of optimizer, (c) provides a per-FLOP cost comparison between Muon and SAM's isotropy-widening effects, and (d) connects curvature anisotropy to adaptive merge coefficient selection. The measurement-study vs. prescriptive-method distinction is precise: SAM and ASAM modify training to achieve flatness; this work characterizes which optimizer's implicit dynamics produce flatness without modification.

---

## 5. Problem Gap

### The Gap

The model merging literature has established that flat, wide loss basins are the primary geometric predictor of merge quality. However, "flatness" has been operationalized almost exclusively as a scalar width — the average perturbation magnitude that can be absorbed before the loss degrades past a threshold. This scalar conflates two geometrically distinct properties: (1) the average curvature across all directions, and (2) the spread of curvature across directions (anisotropy). A basin that is extremely flat in one direction and extremely steep in all others (a ridge geometry) would register as "flat" under scalar width if the flat direction dominates the average, yet it would fail catastrophically for model merging along the steep directions.

The question of whether Muon's Newton-Schulz orthogonalization produces genuinely isotropic basins — flat in all principal curvature directions simultaneously — or merely wide basins with concentrated flat directions has not been asked, let alone answered. The optimizer literature (including the Muon paper itself) has not characterized basin anisotropy. The merging literature has not compared the per-FLOP cost of isotropy-widening achieved by different methods (SAM vs. Muon). The basin geometry literature has not studied optimizer-induced variation in curvature anisotropy.

### Why This Gap Matters

**Practically:** Practitioners building merging pipelines need to know whether to use SAM (explicit basin widening, 2× compute overhead, ρ hyperparameter) or Muon (implicit basin widening claimed for free). Without a per-FLOP comparison of the anisotropy each achieves, this choice cannot be made principally. Similarly, the choice of merge coefficient α is currently made by scalar interpolation sweep, ignoring the directional curvature information that could identify α* more efficiently.

**Theoretically:** If Muon's NS orthogonalization produces isotropic basins as a free byproduct, this would establish a concrete geometric mechanism for the empirical observation that Muon-trained models merge better. It would also imply that the operative geometric predictor of merge quality is not scalar width but tensor isotropy — a qualitatively different and more informative characterization of the loss landscape.

### Why This Gap Is Tractable Now

Three developments make this specific measurement study tractable at this moment:

1. **Two-track spectral estimation enables coverage at multiple scales.** Track A (Lanczos top-K) provides precise top-K eigenvalues at GPT-2 / LLaMA-345M scale (~500 Hessian-vector products, ~3h per model). Track B (Stochastic Lanczos Quadrature with 100 Rademacher probes) provides bulk spectral density at 774M and 7B scale, with concrete feasibility: 345M in 2h, 774M in 4h, 7B in 100h (3 key checkpoints only).

2. **The kappa_top metric is robust to bottom-eigenvalue noise.** By defining κ_top = λ_1/λ_K within the top-K only (K ∈ {10, 20, 50}), the anisotropy measure avoids the instability of bottom-eigenvalue estimates — λ_K values are unstable in the large-model regime. This is a conceptual advance over the naive κ_max/κ_min ratio.

3. **The SAM ρ sweep provides a natural dose-response control.** By sweeping ρ ∈ {0.01, 0.05, 0.1, 0.2} at matched wall-clock, the proposal can directly measure how much isotropy SAM buys per FLOP as a function of ρ, providing the comparison axis needed to situate Muon's cost efficiency.

---

## 6. Theoretical Basis

### Framework

The theoretical framework characterizes how optimizer dynamics shape the directional curvature structure of fine-tuned loss basins, with a focus on the tensor anisotropy of the Hessian at the trained solution and its implications for interpolation geometry.

**Key Definitions:**

Let W* be the fine-tuned parameter vector (flattened). Let H = ∂²L/∂W² denote the Hessian of the validation loss at W*. Let λ_1 ≥ λ_2 ≥ ... ≥ λ_n be the eigenvalues of H and v_1, ..., v_n the corresponding eigenvectors.

- **Directional curvature:** κ_k = v_k^T H v_k = λ_k. For a directional loss profile L_k(α) = L(W* + α v_k), the curvature at α=0 is d²L_k/dα²|_{α=0} = λ_k.
- **kappa_top (primary metric):** κ_top(K) = λ_1/λ_K, the ratio of the largest to the K-th eigenvalue within the top-K only. K ∈ {10, 20, 50}. A near-isotropic top-K manifold has κ_top ≈ 1; a ridge-dominated manifold has κ_top >> 1.
- **Spectral decay profile:** The sorted sequence λ_1 ≥ ... ≥ λ_K, summarized by the area under the normalized curve (AUC_κ). Flat decay = high AUC_κ = more isotropic.
- **Isotropy-per-FLOP:** κ_top normalized by total training FLOPs consumed, enabling direct comparison between Muon and SAM at matched wall-clock budget.
- **Adaptive merge coefficient:** α* = argmin_{α} L(αW_A + (1−α)W_B), recovered by fitting an 11-point cubic spline to the loss profile along the interpolation path.

### Proposition 1: NS Orthogonalization Biases Fine-Tuning Toward Isotropic Hessian Top-K

**Claim:** Let W*_M be a solution reached by Muon and W*_A be a solution reached by AdamW, both starting from the same pretrained initialization and trained to matched validation loss. Then E[κ_top(W*_M, K)] < E[κ_top(W*_A, K)] for K ∈ {10, 20, 50}.

**Intuition:** Muon's NS iteration approximately produces the polar factor of the gradient: G_update ≈ UG VG^T where G = UG ΣG VG^T is the SVD of the gradient. This orthogonalized update treats all directions in parameter space symmetrically (the singular values of the update are all approximately 1), whereas AdamW's element-wise scaling by 1/√v_t amplifies high-variance gradient directions and suppresses low-variance directions, concentrating update magnitude along a subset of directions. Over the course of fine-tuning, AdamW's directional amplification sharpens the curvature along the directions it preferentially updates, producing a larger κ_top ratio. Muon's symmetric updates distribute curvature more evenly across the top-K directions.

**Verification:** Measure κ_top at matched training loss for Muon vs. AdamW across tasks and scales. Statistical test: Wilcoxon signed-rank p < 0.05 + Cohen's d ≥ 0.5 over matched pairs.

### Proposition 2: κ_top Predicts Merge Interpolation Quality Along Off-Axis Directions

**Claim:** For two models A, B fine-tuned from the same base, the loss barrier along the interpolation path L(αW_A + (1−α)W_B) is a decreasing function of the average isotropy min(κ_top(A), κ_top(B)), holding training loss constant.

**Intuition:** Two models whose top-K principal curvature directions are all low-variance (κ_top ≈ 1) will interpolate well along any direction in the subspace spanned by those eigenvectors. A model pair where both have ridge geometry (κ_top >> 1) will interpolate well only along the flat ridge direction and poorly along the steep directions — but the merge path does not generically align with the flat ridge, so merge quality degrades. This is the precise sense in which isotropy, not scalar width, is the operative predictor of merge compatibility.

**Verification:** Compute Spearman rank correlation between κ_top and loss barrier at α = 0.5 across all model pairs, controlling for training loss difference via partial correlation.

### Proposition 3: Muon Achieves Basin Isotropy as a Zero-Extra-Cost Byproduct

**Claim:** At matched wall-clock compute budget, Muon achieves lower κ_top than AdamW, and comparable or lower κ_top than SAM (ρ=0.05) at half the per-step forward-pass count.

**Intuition:** SAM's perturbation step is an explicit FLOP expenditure targeting flatness. Muon's NS step is an in-place gradient transformation with negligible overhead relative to the backward pass. If both achieve comparable isotropy, Muon's isotropy is effectively free from a compute standpoint. If SAM achieves strictly better isotropy per FLOP (an honest alternative outcome acknowledged in the risk register), the contribution reframes to: Muon achieves comparable isotropy without the ρ hyperparameter, enabling hyperparameter-free merging pipelines.

**Verification:** Plot κ_top vs. cumulative training FLOPs for all five optimizer conditions. SAM ρ sweep {0.01, 0.05, 0.1, 0.2} reveals how sensitive SAM's isotropy is to ρ, while Muon's result is a single curve requiring no ρ selection.

### Causal Chain Summary

NS orthogonalization (Muon) → symmetric per-step updates across parameter directions → Hessian curvature distributed more evenly across top-K eigenvector directions → low κ_top → low interpolation loss barrier along off-axis directions → improved merge quality with adaptive α* → measurable downstream accuracy gain from merged models.

Each link is independently testable. The partial NS ablation (K_NS iterations ∈ {0, 1, 2, 3, 4, 5}) provides causal identification: K_NS = 0 recovers momentum SGD behavior and should remove the isotropy advantage, while K_NS = 5 restores it, isolating the NS step's specific contribution.

---

## 7. Method Sketch

### Overview

The method has two measurement tracks (Lanczos top-K and SLQ bulk) plus a merging evaluation component. All measurements are taken at matched validation loss (not matched steps) to ensure optimizer comparison is not confounded by convergence rate differences.

### Track A: Lanczos Top-K Directional Curvature Profiling

**Applicable scale:** GPT-2 medium (345M), LLaMA-3-1B (approximate 774M scale)
**Tool:** PyHessian (Lanczos iteration, ~500 Hessian-vector products)

```
Algorithm A: Directional Curvature Profile (Track A)

Input: Fine-tuned model W*, validation dataset D_val, K ∈ {10, 20, 50}, ε = 0.01

1. Compute top-K Hessian eigenvectors {v_1, ..., v_K} via Lanczos iteration
   - Convergence criterion: residual ||Hv_k - λ_k v_k|| < 1e-3 for all k ≤ K
   - Record convergence diagnostic (number of Lanczos steps required per K)

2. For each eigenvector v_k (k = 1, ..., K):
   a. Evaluate loss at 11 points: α_j = -ε + 2ε·j/10 for j = 0, ..., 10
      L_k(α_j) = L_val(W* + α_j · v_k / ||v_k||)
   b. Fit cubic spline to {(α_j, L_k(α_j))} using scipy.interpolate.CubicSpline
   c. Compute κ_k = d²L_k/dα²|_{α=0} from the spline's second derivative at α=0

3. Compute κ_top(K) = κ_1 / κ_K = λ_1 / λ_K (within top-K only)

4. Compute spectral decay profile: normalized sequence κ_k / κ_1 for k = 1,...,K
   AUC_κ = (1/K) Σ_k (κ_k / κ_1)   [higher = flatter decay = more isotropic]

5. Flat-direction fraction: fraction of k where κ_k < median(κ_1,...,κ_K)

Output: κ_top(K), spectral decay profile, AUC_κ, flat-direction fraction
```

**K sensitivity sweep:** Run Algorithm A for K ∈ {10, 20, 50}. Report whether κ_top ordering (Muon < AdamW) is stable across K values. If the ordering reverses between K=10 and K=50, this indicates the isotropy advantage is confined to the top eigendirections only (a meaningful finding worth reporting).

### Track B: Stochastic Lanczos Quadrature (SLQ) for Bulk Spectral Density

**Applicable scale:** All scales including LLaMA-3-7B
**Tool:** 100 Rademacher probes, Lanczos tridiagonalization, Gaussian quadrature for spectral density estimation

**Feasibility table (H200 GPU, batch size 32):**

| Model | Parameters | SLQ per checkpoint | Checkpoints | Total SLQ compute |
|---|---|---|---|---|
| GPT-2 medium | 345M | 2h | 4 (all tasks × 2 seeds) | 8h |
| LLaMA-3 ~774M | 774M | 4h | 4 | 16h |
| LLaMA-3-8B | 7B | 100h | 3 (start, mid, end of fine-tuning) | 300h (out-of-scope) |

**Decision rule:** For 7B scale, run SLQ only at 3 checkpoints (step 0, step T/2, step T) using the full budget. Do not compute top-K Lanczos at 7B scale (infeasible). Use Track B output only for bulk spectral mass comparison (fraction of eigenvalue mass in top 5% vs bottom 95%), not for κ_top (which requires precise top-K eigenvalues).

```
Algorithm B: SLQ Bulk Spectral Density (Track B)

Input: Model W*, 100 Rademacher probe vectors {z_1,...,z_100}, m=30 Lanczos steps

1. For each probe vector z_i:
   a. Run m-step Lanczos: produce tridiagonal T_m and Ritz values
   b. Apply Gaussian quadrature to T_m to produce 30 spectral density samples

2. Average spectral density estimates across 100 probes

3. Report:
   - Fraction of eigenvalue mass above median (top-half mass concentration)
   - Estimated trace(H) and trace(H²) (used to bound κ_top from SLQ alone)
   - Comparison of trace(H²)/trace(H)² across optimizers (larger = more anisotropic)

Output: Bulk spectral density histogram, top-half mass fraction, trace moment ratios
```

### Track C: Interpolation Profiling and Adaptive Merge Coefficient

```
Algorithm C: Adaptive Merge Coefficient Recovery

Input: Two fine-tuned models W_A, W_B (same base, different seeds or tasks)
       Validation dataset D_val

1. Evaluate merge loss at 11 points: α_j = j/10 for j = 0,...,10
   L_merge(α_j) = L_val(α_j · W_A + (1 - α_j) · W_B)

2. Fit cubic spline S_cubic to {(α_j, L_merge(α_j))}
   Also fit quadratic Q_5 to the 5 points {α_0, α_2, α_5, α_8, α_10} (subset)

3. α*_cubic = argmin_α S_cubic(α)    [minimizer of cubic spline]
   α*_quad   = argmin_α Q_5(α)       [minimizer of quadratic fit]

4. Compute ground truth: α*_gt = argmin over 21 uniformly spaced α values

5. Report:
   - |α*_cubic - α*_gt|   [target: ≤ 0.02]
   - |α*_quad - α*_gt|    [target: > 0.05 on ≥ 1 condition to justify cubic upgrade]
   - Accuracy of model W_A·α*_cubic + W_B·(1-α*_cubic) vs fixed α=0.5

Output: α*_cubic, accuracy improvement, cubic-vs-quadratic comparison
```

### Causal Identification: Partial NS Ablation

To isolate the NS step's specific contribution to basin isotropy (separate from Muon's momentum schedule), train additional models with K_NS ∈ {0, 1, 2, 3, 4, 5} NS iterations. K_NS=0 reduces Muon to momentum SGD; K_NS=5 is standard Muon. Measure κ_top as a function of K_NS. A monotone decrease in κ_top with K_NS provides direct evidence that NS orthogonalization is the causal driver of isotropy.

---

## 8. Experiment Plan (3 Phases, 12 Weeks)

### Phase 1: Core Validation (Weeks 1–4)

**P1-A: Directional curvature profiling on GPT-2 medium**

- Fine-tune 4 models: Muon, AdamW, SOAP, SAM(ρ=0.05). Model: GPT-2 medium (345M). Task: SST-2.
- All trained to matched validation loss (not matched steps). Adjust training duration per optimizer to equalize final validation loss within ±0.01.
- Apply Algorithm A (Track A, Lanczos top-K) for K ∈ {10, 20, 50} to all 4 models.
- Report per-optimizer: κ_top(10), κ_top(20), κ_top(50), AUC_κ, flat-direction fraction.
- Statistical test: Wilcoxon signed-rank test on κ_top(Muon) vs. κ_top(AdamW) across seeds; Cohen's d. Significance threshold: p < 0.05 + Cohen's d ≥ 0.5.
- Lanczos convergence diagnostic: report residual ||Hv_k - λ_k v_k|| for each k; flag any k where residual > 1e-3 as unreliable.

**P1-B: Interpolation profiling with cubic spline vs. quadratic comparison**

- For each of the 4 fine-tuned models (P1-A), form same-optimizer model pairs (Muon-Muon, AdamW-AdamW, using 2 seeds per optimizer).
- Apply Algorithm C. Report |α*_cubic − α*_gt| and |α*_quad − α*_gt| for all pairs.
- Success criterion for cubic upgrade justification: |α*_quad − α*_gt| > 0.05 on ≥ 1 condition. If neither method exceeds 0.02 error, report 5-point quadratic as sufficient for these symmetric basins.
- Chen et al. sub-basin fallback: if loss profile along interpolation path shows two local minima, switch to mixture-of-quadratics fit and report sub-basin count as additional isotropy descriptor.

**P1-C: Adaptive merge coefficient accuracy**

- Merge Muon-Muon and AdamW-AdamW pairs using (a) α* from cubic spline, (b) fixed α = 0.5.
- Evaluation: SST-2 accuracy, HellaSwag accuracy, Pile perplexity (3 downstream metrics).
- Report accuracy improvement Δacc = acc(α*_cubic) − acc(α=0.5), separately for Muon and AdamW pairs.
- Report whether Muon pairs show larger Δacc than AdamW pairs (testing whether isotropy enables better α* selection).

### Phase 2: SAM Cost-Efficiency Analysis (Weeks 3–6, overlaps Phase 1)

**P2-A: Basin-shape-per-FLOP comparison at matched wall-clock**

- Train 7 models: Muon, AdamW, SOAP, SAM(ρ=0.01), SAM(ρ=0.05), SAM(ρ=0.1), SAM(ρ=0.2). All at matched wall-clock compute (not matched steps, because SAM requires ≈2× forward passes per step due to the perturbation computation).
- Record total training FLOPs consumed by each optimizer (count forward+backward passes precisely; SAM's perturbation step counts as an additional forward pass).
- For each model, compute κ_top(20) via Track A (Algorithm A).
- Primary plot: κ_top(20) vs. cumulative training FLOPs (isotropy-per-FLOP curve for each optimizer).
- Secondary plot: κ_top(20) vs. final task accuracy (isotropy at matched accuracy).

**P2-B: SAM ρ sensitivity and Muon robustness**

- The SAM ρ sweep from P2-A provides the sensitivity data directly.
- Report: standard deviation of κ_top(20) across ρ values for SAM. Compare to Muon's κ_top(20) variance across seeds (no ρ, variance only from random seed).
- Compute sensitivity ratio: std_SAM(κ_top) / std_Muon(κ_top) as a single-number summary of Muon's robustness advantage.
- If SAM achieves strictly lower κ_top per FLOP than Muon at all ρ values: report honestly and reframe as "Muon achieves comparable isotropy without requiring ρ hyperparameter selection, enabling one-click hyperparameter-free merging pipelines."

### Phase 3: Scaling and Multi-Task Generalization (Weeks 7–12)

**P3-A: Model scale extension (345M → 774M → 7B)**

- Repeat P1-A and P2-A at 774M scale using Track A (Lanczos feasible, ~4h per model).
- At 7B scale: use Track B (SLQ, 100 probes) at 3 checkpoints only. Do not attempt full Lanczos at 7B.
- Report: does κ_top ordering (Muon < AdamW) hold at all three scales? Report scale-vs-κ_top plot.
- Feasibility gate: if SLQ at 7B exceeds 100h per checkpoint, restrict 7B experiment to a single fine-tuned model (Muon only) and report a partial scaling result.

**P3-B: Multi-task generalization (SST-2, MNLI, SQuAD)**

- Repeat P1-A at 345M scale for MNLI and SQuAD in addition to SST-2.
- Report: does Muon's κ_top(20) advantage hold across all 3 tasks? Compute per-task effect sizes.
- Generation evaluation: for SQuAD, also report HellaSwag accuracy and Pile perplexity on the fine-tuned models to capture generative quality beyond classification accuracy.

**P3-C: Correlation with spectral flatness (cross-plan linkage)**

- For each fine-tuned model, compute spectral flatness SF(W_l) = geometric_mean(σ_i(W_l)) / arithmetic_mean(σ_i(W_l)) for each linear weight matrix W_l.
- Compute Spearman rank correlation between per-model average κ_top(20) and per-model average SF across layers.
- Expected: moderate correlation (ρ_S ~ 0.5–0.7), confirming basin anisotropy and weight matrix spectral flatness are related but distinct quantities measuring different geometric objects (fine-tuned solution shape vs. pretrained weight structure).

**P3-D: Training trajectory isotropy (cross-plan linkage to checkpoint soups)**

- Along a single Muon fine-tuning trajectory, compute κ_top(20) at checkpoints (step 0, T/4, T/2, 3T/4, T).
- Report: does κ_top decrease monotonically during Muon fine-tuning (basins become more isotropic as training progresses)?
- Compare to AdamW trajectory on the same architecture and task.

**P3-E: Partial NS ablation (causal identification)**

- Train 6 models with K_NS ∈ {0, 1, 2, 3, 4, 5} NS iterations, all other Muon hyperparameters fixed.
- Compute κ_top(20) for each K_NS.
- Fit monotone regression to κ_top vs. K_NS. If the trend is monotone decreasing, this establishes the NS step as the causal driver.

---

## 9. Baselines

1. **AdamW** — standard fine-tuning baseline; used for all comparisons and as the primary contrast.
2. **SOAP** (Vyas et al., 2024; arXiv:2409.11321) — quasi-orthogonal optimizer with Kronecker preconditioning; controls for the confound that any curvature-aware optimizer might produce similar isotropy.
3. **SAM (ρ=0.05)** (Foret et al., 2021; arXiv:2010.01412) — explicit basin-widening baseline at matched wall-clock FLOPs; primary cost-efficiency comparison.
4. **SAM (ρ=0.01), SAM (ρ=0.1), SAM (ρ=0.2)** — three additional SAM conditions for ρ sensitivity sweep; separates SAM's ρ-dependent isotropy from Muon's hyperparameter-free isotropy.

All baselines are evaluated at matched wall-clock compute (not matched steps), because SAM requires ≈2× forward passes per step. All comparisons are made at matched validation loss to avoid conflating convergence rate with basin geometry.

---

## 10. Ablation Table

| What to vary | What to hold constant | Scientific question answered |
|---|---|---|
| Optimizer: Muon, AdamW, SOAP, SAM×4 | Model size (345M), task (SST-2), wall-clock FLOPs | Which optimizer produces most isotropic basins per FLOP? |
| K ∈ {10, 20, 50} in κ_top(K) | Optimizer, model, task | Is isotropy advantage stable across different top-K cutoffs, or concentrated in the very top eigendirections? |
| K_NS ∈ {0,1,2,3,4,5} NS iterations (partial ablation) | All other Muon hyperparameters, model, task | Does NS orthogonalization causally drive the isotropy advantage, isolating it from Muon's other components? |
| Interpolation fit: 5-point quadratic vs 11-point cubic spline | Optimizer, model, task | Does nonlinear basin structure require the cubic upgrade, or is 5-point quadratic sufficient? |
| Model size: 345M, 774M, 7B | Optimizer (Muon vs AdamW), task (SST-2) | Does Muon's anisotropy advantage scale with model size? |
| Task: SST-2, MNLI, SQuAD | Optimizer, model size (345M) | Is basin isotropy advantage task-universal or task-specific? |
| Curvature direction subset: top-K, random-K, bottom-K | Optimizer, model, task | Is the isotropy advantage uniform across the full eigenspectrum or concentrated in top directions? |
| SAM ρ: 0.01, 0.05, 0.1, 0.2 | Model size, task, wall-clock FLOPs | How sensitive is SAM's isotropy per FLOP to ρ selection? |
| Training checkpoint: 0, T/4, T/2, 3T/4, T | Optimizer (Muon, AdamW), model, task | Does isotropy increase monotonically during Muon training? |
| Initialization: shared vs different pretrained checkpoint | Optimizer, task | Does shared initialization amplify or reduce the isotropy difference between optimizers? |

---

## 11. Datasets and Evaluation

### Training / Fine-tuning Datasets

- **SST-2** (67,349 training examples): Binary sentiment classification. Simple, fast to fine-tune; used as the primary Phase 1 development dataset.
- **MNLI** (392,702 training examples): Natural language inference (3-class). More complex label structure tests whether isotropy advantage persists under multi-class fine-tuning.
- **SQuAD v1.1** (87,599 training examples): Extractive question answering. Tests generative (span prediction) rather than classificatory fine-tuning, and enables Pile perplexity evaluation.

### Evaluation Metrics

**Primary (basin geometry):**
- **κ_top(K) = λ_1 / λ_K** (within top-K Hessian eigenvectors). Lower = more isotropic. Reported for K ∈ {10, 20, 50}.
- **Isotropy-per-FLOP:** κ_top(20) normalized by total training FLOPs consumed. Enables direct cross-optimizer cost comparison.

**Secondary (geometry quality):**
- **Spectral decay AUC_κ:** Area under the normalized sorted-κ curve. Higher = flatter decay = more isotropic top-K subspace.
- **Flat-direction fraction:** Fraction of top-K eigendirections with κ_k < median(κ_1,...,κ_K).
- **SLQ trace moment ratio:** trace(H²) / [trace(H)]² from bulk SLQ. Scale-applicable bulk isotropy proxy.

**Secondary (merging quality):**
- **|α*_cubic − α*_gt|:** Cubic spline recovery error relative to 21-point ground truth. Target ≤ 0.02.
- **|α*_quad − α*_gt|:** Quadratic fit error. Target > 0.05 on ≥ 1 condition to justify cubic upgrade.
- **Δacc = acc(α*_cubic) − acc(α=0.5):** Accuracy gain from adaptive vs. fixed merge coefficient.
- **Spearman ρ(κ_top, SF):** Rank correlation between basin anisotropy and weight spectral flatness. Target 0.4–0.75.

**Downstream generation quality:**
- **HellaSwag accuracy** (zero-shot): Tests whether isotropy advantage translates to generative capability.
- **Pile perplexity:** Tests language modeling quality preservation through merging.

### Statistical Tests

- All primary claims use Wilcoxon signed-rank test (matched pairs across seeds, p < 0.05) + Cohen's d (≥ 0.5 required for practical significance).
- The 0.6× threshold (Muon κ_top ≤ 0.6× AdamW κ_top) is a pre-specified effect size threshold, not a p-value threshold.
- Spearman ρ for cross-plan correlation is reported with 95% bootstrap confidence intervals.

---

## 12. Compute Estimate

**Total: ~240 GPU-hours (wall-clock), ~178h active compute**

| Component | Detail | Hours |
|---|---|---|
| Fine-tuning, Phase 1 | 4 optimizers × 3 tasks × 2 seeds × 2h per run | 48h |
| Fine-tuning, Phase 2 (SAM sweep) | SAM ρ×4 + Muon + AdamW = 6 models × 4h | 24h |
| Fine-tuning, Phase 3 (774M scale) | 4 optimizers × 2 seeds × 4h | 32h |
| Track A Lanczos (GPT-2/345M scale) | 4 models × 3 tasks × K_sweep × 1h | 12h |
| Track B SLQ (774M scale) | 4 models × 4h | 16h |
| Track B SLQ (7B, 3 checkpoints only) | 2 models × 3 checkpoints × 12h | 72h |
| Interpolation / merge evaluation | 4 conditions × 3 tasks × 2h | 24h |
| Partial NS ablation (K_NS sweep) | 6 K_NS values × 2h | 12h |
| Training trajectory (checkpoint ISA) | 2 optimizers × 5 checkpoints × 0.5h | 5h |
| Buffer for reruns and ablations | — | ~30h |
| **Total active compute** | | **~178h** |
| **Total wall-clock (with queuing)** | | **~240h** |

**Note on 7B scale:** The 72h SLQ experiment at 7B is optional. If compute budget is constrained, the 7B experiment is the first to cut. The core claim (Muon produces more isotropic basins) is established at 345M and 774M scales.

---

## 13. Success Criteria and Kill Results

### Primary Success Criteria

1. **Isotropy advantage:** Muon κ_top(20) ≤ 0.6× AdamW κ_top(20), measured via Wilcoxon p < 0.05 + Cohen's d ≥ 0.5, across ≥ 3 tasks and ≥ 2 model scales.

2. **Isotropy-per-FLOP advantage:** Muon's isotropy-per-FLOP curve (κ_top vs. cumulative FLOPs) lies at or below SAM's curve at matched wall-clock budget, for at least 2 of 4 SAM ρ values.

3. **Cubic spline justification:** 11-point cubic spline recovers α* within 0.02 of the 21-point ground truth on all conditions. 5-point quadratic deviates by > 0.05 on ≥ 1 condition.

4. **Adaptive merge benefit:** Adaptive α* from cubic spline improves merged model accuracy by ≥ 0.5% vs fixed α = 0.5 on ≥ 1 of the 3 tasks.

5. **Cross-plan correlation:** Spearman ρ between κ_top(20) and weight spectral flatness SF falls in [0.4, 0.75], confirming they are related but non-identical measurements.

### Secondary Success Criteria

- K sensitivity stability: κ_top ordering (Muon < AdamW) holds for all K ∈ {10, 20, 50}, confirming the result is not an artifact of K choice.
- Partial NS ablation: κ_top decreases monotonically with K_NS (ρ_S < 0 with p < 0.05 for Spearman test of κ_top vs. K_NS).
- HellaSwag and Pile perplexity of merged models are at least as good as the best individual fine-tuned model when using adaptive α* from the more isotropic (Muon) fine-tuned pair.

### Kill Results

- **Primary kill:** If Muon and AdamW show equivalent κ_top (< 10% difference) at matched training loss across all tasks and scales, basin anisotropy is not differentiated by optimizer. Pivot: document the measurement toolkit (directional curvature profiling + SLQ pipeline) as the standalone methodological contribution.
- **Interpolation kill:** If cubic spline and quadratic agree to within 0.02 on all tested networks, the cubic upgrade is unnecessary. Report 5-point quadratic as sufficient for these tasks (positive finding, reduces compute overhead for future merge practitioners).
- **Partial kill:** If isotropy advantage holds at 345M but disappears at 774M+, report scale-limited isotropy advantage and characterize the scale at which NS orthogonalization's effect attenuates.

---

## 14. Risk Register, Differentiation, and Standalone Viability

### Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| κ_top advantage < 10% over AdamW at 345M | Medium | High (primary claim fails) | Pivot to toolkit contribution; report null result with full methodology; SLQ pipeline is independently publishable |
| Lanczos convergence failure (residual > 1e-3) for large K | Low | Medium | Use K=10 only (most stable); flag non-converged eigenvectors; fallback to SLQ for all scales |
| SLQ infeasible at 7B within budget | Medium | Low (7B is optional) | Restrict to 345M and 774M; core claim established without 7B |
| SAM achieves strictly better isotropy per FLOP at all ρ | Medium | Medium | Reframe: Muon achieves comparable isotropy without ρ hyperparameter; report sensitivity ratio std_SAM/std_Muon as robustness advantage |
| Cubic spline and quadratic agree everywhere | Low | Low | Report as positive finding (5-point sufficient); no justification needed for upgrade claim; accuracy contribution stands independently |
| Chen et al. sub-basin structure (multiple local minima in merge path) | Medium | Medium | Switch to mixture-of-quadratics fit; report sub-basin count as additional anisotropy descriptor; test whether Muon models show fewer sub-basins |
| κ_top advantage present but Δacc < 0.5% from adaptive α* | Medium | Low | Report geometry contribution decoupled from merge accuracy; geometry claim can stand even if practical accuracy benefit is small |
| SOAP achieves comparable isotropy to Muon | Medium | Low | Report that quasi-orthogonal optimizers as a class produce more isotropic basins than AdamW; strengthens the orthogonalization hypothesis |

### Differentiation from Prior Work

**vs. Delving into Sharpness-Aware Minimization (Foret et al., SAM):** SAM is a prescriptive method that modifies the training objective to target flat minima. This proposal is a measurement study that characterizes which optimizer's implicit dynamics produce isotropy. These are complementary: SAM asks "how do we achieve flatness?" and this work asks "which optimizer already achieves it and at what cost?"

**vs. Mousse / DARE sparse merging:** Mousse targets the model merging outcome via sparse masking. This work characterizes the basin geometry that enables merging, independent of the merging algorithm used. The basin geometry characterization is algorithm-agnostic.

**vs. Optimizer Bias on Merging (arXiv:2510.04686):** That paper observes empirically that optimizers differ in merge compatibility; this paper provides the mechanistic explanation (directional curvature anisotropy) and the per-FLOP cost comparison that the prior work does not attempt.

**vs. Neural Thickets (arXiv:2603.12228):** Thicket density is a scalar volumetric measure of the pretrained weight region. Basin anisotropy is a tensor property of a single fine-tuned solution. Wide basins can be ridges (large scalar width, extreme anisotropy). The anisotropy ratio κ_top is not recoverable from any scalar density measurement. The two quantities are expected to correlate moderately (Spearman ρ ~ 0.5–0.7) but are not equivalent.

### Standalone Viability: SLQ Toolkit Contribution

Independent of the Muon-specific findings, this proposal introduces a complete **SLQ-based directional curvature profiling toolkit** for large language models, including:

- Two-track spectral estimation (Lanczos top-K for ≤ 774M; SLQ bulk for ≤ 7B)
- Automated Lanczos convergence diagnostics (residual < 1e-3 per eigenvector)
- K sensitivity sweep infrastructure
- 11-point cubic spline interpolation with quadratic fallback comparison
- Per-FLOP isotropy normalization utilities
- Feasibility table (2h for 345M, 4h for 774M, 100h per checkpoint for 7B)

This toolkit is a standalone contribution publishable as a systems/methods paper if the Muon isotropy claim does not reach significance. It addresses an acknowledged gap: no standardized toolkit exists for measuring loss basin anisotropy at the scale of modern language models.

---

## Paper Storyline

Prior work on model merging has relied on scalar basin-width as the primary geometric predictor of merging compatibility. However, scalar width conflates two fundamentally different properties: average curvature and directional uniformity of curvature. A basin can be wide in one direction and narrow in all others — a ridge geometry — producing large scalar width but poor merging compatibility along all but one direction. We introduce **directional curvature profiling**, a two-track spectral estimation approach (Lanczos top-K for small models; Stochastic Lanczos Quadrature for large models) that measures the full principal curvature profile of a fine-tuned loss basin. Our primary metric, **κ_top = λ_1/λ_K**, captures the anisotropy of the top-K Hessian eigendirections without incurring the instability of bottom-eigenvalue estimates.

Across three NLP tasks (SST-2, MNLI, SQuAD) and two model scales (GPT-2 medium 345M, LLaMA ~774M), Muon-trained models exhibit 40–60% lower κ_top compared to AdamW at matched validation loss, indicating that Muon's Newton-Schulz orthogonalization implicitly regularizes fine-tuning toward isotropic loss basins. Crucially, Muon achieves this basin isotropy as a free byproduct of training, requiring no additional forward passes and no hyperparameter selection. By contrast, SAM requires approximately 2× forward passes per step and careful ρ selection, and exhibits κ_top values that vary substantially across ρ ∈ {0.01, 0.05, 0.1, 0.2}. A partial Newton-Schulz ablation (K_NS ∈ {0,...,5} iterations) provides causal evidence that the NS step specifically — not Muon's momentum schedule — drives the isotropy advantage.

The directional curvature anisotropy is correlated but non-identical to weight matrix spectral flatness (Spearman ρ ~ 0.5–0.7), confirming it is a distinct measurement rather than a proxy. Using κ_top-informed 11-point cubic spline interpolation to recover adaptive merge coefficients α* improves merged model accuracy by at least 0.5% over fixed α = 0.5, with the improvement concentrated in Muon-fine-tuned model pairs where the isotropic basin structure makes α* selection more informative. These findings suggest that curvature anisotropy, not scalar width, is the operative geometric predictor of optimizer-induced merge compatibility, and that the choice of fine-tuning optimizer is a consequential design decision for practitioners building model merging pipelines.

---

**Target Venues:** AAAI 2027 / EMNLP 2027
**Confidence Level:** Medium
**Total Compute Budget:** ~240 GPU-hours (wall-clock)
**Minimum Viable Experiment:** 21h on 4× H200 (GPT-2 medium, SST-2, Muon vs AdamW κ_top comparison with 11-point cubic spline interpolation profiling)
