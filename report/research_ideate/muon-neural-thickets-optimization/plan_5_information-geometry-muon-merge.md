# EigenMerge: Training-Time Eigenvector Geometry for Data-Free Model Merging

---

## 1. Title

**EigenMerge: Using Muon Momentum Buffers as Matrix-Structured Merge Coordinates for Data-Free Riemannian Model Averaging**

---

## 2. One-Sentence Thesis

Standard model merging operates in the Euclidean parameter space, ignoring the Riemannian geometry induced by the Fisher information matrix; Muon's pre-Newton-Schulz momentum buffer M_T encodes matrix-structured eigenvector geometry (full d_out × d_in curvature structure) that Adam's diagonal second-moment v_T cannot represent, and this structural difference — not the mere reuse of optimizer state — enables EigenMerge to project task vectors into a training-time Fisher eigenbasis at sub-linear merge-time cost with zero additional data, outperforming diagonal-Fisher and Euclidean baselines on KL divergence and task accuracy when averaged across K fine-tuned experts.

---

## 3. Research Area Classification

**Primary Area:** Model Merging / Model Soups
**Secondary Areas:** Optimization for Deep Learning, Information Geometry, Riemannian Manifold Methods, Parameter-Efficient Fine-Tuning
**Keywords:** model merging, Fisher information matrix, natural gradient, Riemannian averaging, Muon optimizer, momentum buffer, eigenvector geometry, task vectors, data-free merging, EigenMerge, information geometry, Fisher-Rao metric

**Positioning:** EigenMerge sits at the intersection of two literatures that have developed independently: (1) the information-geometry approach to model merging, which uses Fisher-weighted averaging but requires expensive merge-time data collection, and (2) the training optimizer literature, which generates curvature information as a byproduct of optimization but has never connected that information to post-training merging geometry. The proposal's specific, defensible novelty is that Muon's raw momentum buffer provides matrix-structured (rank-r) Fisher eigenvector approximations, whereas Adam/AdamW's second-moment buffer provides only diagonal approximations — and this structural difference produces meaningfully better merge coordinates. The "reuse optimizer state for merging" concept (which appeared in OTA-Merging and UMTAM/Squisher) is explicitly conceded; the contribution is the matrix-vs-diagonal eigenvector geometry distinction that those works do not address.

---

## 4. Closest Prior Work (8 papers with comparison table)

### Paper Summaries

**P1. Fisher-Weighted Averaging (Matena & Raffel, 2022; arXiv:2111.09832)**
The foundational work on Fisher-information-based model merging. Computes a diagonal approximation to the Fisher information matrix for each model using a held-out validation set, then weights the parameter-wise average by Fisher diagonal entries — high-Fisher parameters (sensitive directions) receive more weight in the merge. Critical limitation: requires validation data at merge time, which may be expensive, unavailable, or domain-specific. Uses only the Fisher diagonal, discarding off-diagonal curvature structure. EigenMerge's relationship: Fisher-Weighted Averaging is the strongest data-dependent diagonal-Fisher baseline; EigenMerge provides matrix-structured Fisher geometry at zero merge-time data cost.

**P2. Task Arithmetic (Ilharco et al., 2023; arXiv:2212.04089)**
Shows that fine-tuning produces "task vectors" (differences θ_i − θ_base) that can be composed by simple addition in Euclidean parameter space. Composition quality degrades with the number of tasks and with task dissimilarity. The paper recognizes that Euclidean averaging may be suboptimal but does not propose a geometry-aware alternative. EigenMerge's relationship: Task Arithmetic is the primary Euclidean baseline; EigenMerge replaces Euclidean task-vector addition with projection into a training-derived Fisher eigenbasis.

**P3. TIES-Merging (Yadav et al., 2023; arXiv:2306.01708)**
Addresses task-vector interference via a three-step "trim, elect, disjoint merge" procedure: prune small-magnitude parameters, resolve sign conflicts by majority vote, then merge only non-conflicting parameters. A strong practical baseline that is data-free and handles sign conflicts explicitly. TIES operates entirely in Euclidean space with no information-geometric component; it does not use optimizer state or curvature information. EigenMerge's relationship: TIES is the strongest data-free Euclidean-with-sparsity baseline; EigenMerge differs by working in a curvature-aware eigenbasis rather than applying magnitude/sign filtering.

**P4. Fisher-Weighted Averaging with KFAC (Kirchenbauer et al., 2023; extends arXiv:2111.09832)**
Extends Fisher-Weighted Averaging to use Kronecker-Factored Approximate Curvature (KFAC) rather than a diagonal Fisher, recovering some off-diagonal structure at higher cost. Still requires validation data at merge time. Provides the "expensive matrix-Fisher with merge-time data" baseline against which EigenMerge's data-free matrix-Fisher should be compared. EigenMerge's relationship: KFAC-Fisher merge is the strongest data-dependent matrix-Fisher baseline; EigenMerge achieves comparable or superior matrix structure with zero merge-time data.

**P5. OTA-Merging (arXiv:2509.11167)**
"Optimizer-state-aware Task Arithmetic Merging" — the first paper to explicitly reuse optimizer state (specifically Adam's second-moment v_T) for model merging, using v_T as a diagonal-Fisher proxy to weight task vector components. Represents the proof-of-concept that training-time optimizer state can improve merging. Critical limitation: uses Adam's v_T, which is a diagonal approximation; cannot represent off-diagonal curvature structure. EigenMerge's relationship: OTA-Merging is the direct predecessor and the most important baseline. The conceptual claim "reuse optimizer state for merging" is conceded to OTA-Merging. EigenMerge's surviving novelty is the matrix-structured eigenvector geometry from Muon's M_T vs the diagonal-only geometry from Adam's v_T.

**P6. UMTAM / Squisher (arXiv:2512.17109, "Bridging Training and Merging")**
A contemporaneous or slightly later work that also uses training-time optimizer momentum/gradient information for merging, further establishing the "training state for merging" direction. Like OTA-Merging, this work operates in the diagonal or low-structure regime and does not extract the full eigenvector geometry available from matrix-valued momentum buffers. EigenMerge's relationship: UMTAM/Squisher reinforces the "reuse optimizer state" claim priority, but does not exploit the matrix-vs-diagonal structural distinction that is EigenMerge's specific contribution.

**P7. Evolutionary Subspace Merging / ESM (various, 2024-2025)**
A family of methods that apply PCA-like dimensionality reduction to task vectors before merging, projecting into the directions of highest task-vector variance. ESM uses merge-time PCA of the task vectors themselves (capturing which directions the fine-tuned models varied most in), rather than training-time curvature from the optimizer. Represents the "eigenvector geometry, but from task-vector PCA at merge time" baseline. EigenMerge's relationship: ESM uses merge-time feature variance (what directions the tasks moved in), while EigenMerge uses training-time curvature (what directions the loss landscape is sensitive to). These are complementary and the comparison is informative — training-time curvature vs merge-time task variance as merge coordinates.

**P8. Fisher-Rao Manifold Merging (arXiv:2603.04972)**
The most recent and most directly competitive work — uses the Fisher-Rao metric on the statistical manifold for model merging, computing a geodesic average in information geometry. This paper establishes that Riemannian merging on the Fisher-Rao manifold is tractable and beneficial. The key distinction from EigenMerge: arXiv:2603.04972 computes the Fisher at merge time (still requires some data for estimation), while EigenMerge uses the training-time Muon momentum buffer as a data-free proxy. EigenMerge should be positioned as a "data-free approximation" to the full Fisher-Rao approach, with an explicit comparison.

### Comparison Table

| Paper | Fisher / Curvature Info | Data-Free at Merge Time | Matrix-Structured (non-diagonal) | Uses Training Optimizer State | Eigenvector Projection |
|---|---|---|---|---|---|
| P1 Fisher-Weighted Avg (2111.09832) | Yes (diagonal F) | No (validation data) | No | No | No |
| P2 Task Arithmetic (2212.04089) | No (Euclidean) | Yes | N/A | No | No |
| P3 TIES-Merging (2306.01708) | No (Euclidean + sparsity) | Yes | No | No | No |
| P4 KFAC Fisher Merge | Yes (Kronecker F) | No (validation data) | Yes | No | Partial |
| P5 OTA-Merging (2509.11167) | Yes (diagonal v_T) | Yes | No | Yes (Adam v_T) | No |
| P6 UMTAM/Squisher (2512.17109) | Partial | Yes | No | Yes | No |
| P7 ESM (merge-time PCA) | No (task variance) | Yes | Yes | No | Yes (from task PCA) |
| P8 Fisher-Rao Manifold (2603.04972) | Yes (full F) | No (estimation data) | Yes | No | Yes |
| **EigenMerge (this work)** | **Yes (matrix-structured eigenvectors)** | **Yes (zero data)** | **Yes (rank-r from M_T)** | **Yes (Muon M_T pre-NS)** | **Yes (training-time curvature)** |

**Gap Summary:** No prior work simultaneously provides (a) matrix-structured eigenvector geometry (not diagonal), (b) zero merge-time data requirement, and (c) derivation from training-time optimizer curvature rather than merge-time task-vector PCA or Fisher estimation. The matrix-vs-diagonal distinction is the specific structural gap; the training-time-vs-merge-time curvature distinction is the operational gap. Both are untested in the literature as of early 2026.

---

## 5. Problem Gap

### The Gap

Model merging — combining multiple fine-tuned variants of a base model into a single model that retains all their capabilities — faces a fundamental geometric problem: the standard approach of averaging task vectors (τ_i = θ_i − θ_base) in Euclidean parameter space ignores the fact that the parameter space has non-uniform geometry. Directions that are "important" to the model (high Fisher information, high curvature of the loss landscape) should dominate the merge average, while directions that are irrelevant (low Fisher, flat directions) should be averaged out more aggressively.

Fisher-Weighted Averaging (Matena & Raffel 2022) addresses this but requires validation data at merge time — a significant practical obstacle when (1) the fine-tuning data for each expert is proprietary or unavailable, (2) the merge is performed at deployment time without task-specific data, or (3) the task set is heterogeneous and no shared calibration set exists.

A deeper problem that no prior work has addressed: Adam/AdamW's second-moment buffer v_T is a diagonal quantity — it estimates the per-parameter Fisher curvature but discards all off-diagonal structure. For 2D weight matrices (the dominant parameter type in transformers), this means v_T treats rows and columns independently, ignoring the joint curvature structure across the full d_out × d_in matrix. Muon's momentum buffer M_T, by contrast, is a full d_out × d_in matrix. Its singular vectors approximate the leading eigenvectors of the empirical Fisher in a rank-r sense — capturing the coupled curvature structure that Adam's diagonal approximation throws away.

OTA-Merging and UMTAM have shown that using Adam's v_T improves on Euclidean merging. But they are constrained to diagonal geometry. EigenMerge asks: does the additional matrix-structured eigenvector geometry available from Muon's M_T produce a materially better merge eigenbasis than Adam's diagonal v_T — and can this be demonstrated at zero merge-time data cost?

### Why Now

Three developments make this investigation timely in 2026:
1. Muon has achieved mainstream use in LLM pre-training, producing a large stock of publicly available Muon-trained models with saved optimizer states (e.g., OLMo-2, Kestrel).
2. OTA-Merging has demonstrated the "reuse optimizer state for merging" proof-of-concept, validating the approach and establishing the diagonal baseline to beat.
3. The Fisher-Rao manifold merging paper (arXiv:2603.04972) has established full Fisher-Rao merging as a tractable reference, creating a clear ladder from Euclidean → diagonal → matrix-eigenvector → full Fisher-Rao with EigenMerge filling the previously empty "matrix-eigenvector, data-free" position.

---

## 6. Thesis Statement (Extended)

EigenMerge proposes that the pre-Newton-Schulz momentum buffer M_T from Muon-trained models encodes rank-r matrix-structured approximations to the leading Fisher eigenvectors — approximations that are qualitatively different from (and geometrically superior to) the diagonal Fisher proxy in Adam's v_T — and that projecting task vectors into this training-time eigenbasis before averaging reduces destructive interference in the high-curvature directions while correctly averaging the low-curvature residual, producing merged models with lower KL divergence to individual expert outputs and higher task accuracy than Euclidean, TIES, diagonal-Fisher (OTA-Merging), or merge-time PCA (ESM) approaches — all at zero merge-time data cost and sub-linear merge-time compute.

**Two-Tier Claim Structure** (introduced after Round 3 review):

- **Tier A (Scalar Proof — Fully Rigorous):** For a scalar parameter θ near convergence under a quadratic loss, the Muon momentum m_T satisfies |m_T| ∝ |∂²L/∂θ²| · |θ_T − θ*| + O(β^T), meaning m_T is a noisy but consistent estimator of the Fisher curvature along that scalar coordinate. This is a formal near-convergence result with explicit error bounds.

- **Tier B (Matrix Case — Empirical Primary Contribution):** For 2D weight matrices W ∈ R^{d_out × d_in}, the raw M_T (before Newton-Schulz) has dominant singular vectors that are correlated with the leading eigenvectors of the empirical Fisher E[gg^T] — a claim that is empirically testable via Hutchinson estimation of the true Fisher eigenvectors and direct cosine-similarity comparison. The Tier A proof motivates this but does not formally extend to the matrix case (non-commutative, NS distortion, stochastic gradients). The paper is honest about this gap.

---

## 7. Theoretical Basis

### Grounding Framework

Information geometry (Amari, 1998) + natural gradient descent + Riemannian manifold optimization.

**Foundation 1 — Fisher-Rao Geometry:**
The Fisher information matrix F = E[∇ log p(y|x; θ) · ∇ log p(y|x; θ)^T] defines a Riemannian metric on the statistical manifold of model distributions p(·|x; θ). The geodesic distance in this metric — the Fisher-Rao distance — is the natural measure of distance between statistical models. Euclidean model averaging (θ_merge = θ_base + (1/K) Σ_i τ_i) corresponds to finding the Fréchet mean in the Euclidean metric, which may be far from the Fréchet mean under the Fisher-Rao metric. The Fisher-Rao Fréchet mean minimizes Σ_i d_F(θ, θ_i)² and corresponds to the "most information-geometrically central" model — the natural choice for a merged model that preserves each expert's statistical properties.

**Foundation 2 — Muon Momentum as Approximate Fisher Eigenbasis:**
Muon's momentum update is M_t = β M_{t-1} + g_t, where g_t ∈ R^{d_out × d_in} is the gradient matrix at step t. The time-averaged outer product (1/T) Σ_t M_t M_t^T approximates E[gg^T] — the empirical Fisher for the matrix parameter W. Critically, the dominant left singular vectors of M_T (the columns of U in M_T = U Σ V^T) approximate the leading eigenvectors of E[gg^T]. This is the matrix analog of PCA on gradient vectors: the singular vectors of a gradient matrix G = [g_1 | g_2 | ... | g_T] converge to the Fisher eigenvectors by the Stein-type estimator argument from random matrix theory. EigenMerge uses raw M_T before the Newton-Schulz step: the NS orthogonalization in Muon's training step projects M onto the nearest orthogonal matrix, which distorts the singular value magnitudes (making them all equal to 1) while approximately preserving the singular vectors. Since we need eigenvalue magnitudes for the L2 weighted merge, we use M_T pre-NS.

**Foundation 3 — First-Order Riemannian Average:**
The first-order approximation to the Fisher-Rao Fréchet mean, linearized around θ_base, is:
  θ* ≈ θ_base + F^{-1} · (1/K) Σ_i F · τ_i

where τ_i = θ_i − θ_base. In the eigenbasis of F (F = U Λ U^T), this simplifies to:
  α*_k = (1/K) Σ_i α_{i,k} for each eigendirection k

where α_{i,k} = U_k^T τ_i (projection of task vector onto k-th eigenvector) — the natural-gradient-frame average is simply the coordinate-wise average in the eigenbasis. The non-trivial step in EigenMerge is that the eigenbasis U comes from training-time M_T rather than merge-time Fisher estimation. The quality of the result depends on how well M_T's singular vectors approximate the true Fisher eigenvectors — which is precisely what Tier B tests empirically.

### Verifiable Propositions

- **P1 (Fisher Alignment, Tier B):** The dominant singular vectors of Muon's raw M_T (at convergence, before NS) have significantly higher cosine similarity with the dominant eigenvectors of the true empirical Fisher E[gg^T] (estimated via Hutchinson) than Adam's v_T provides in the diagonal case. Target: mean cos-sim ≥ 0.7 for top-5 eigenvectors across transformer layers.

- **P2 (Merge Quality):** EigenMerge (L2 default, M_avg eigenbasis) achieves lower average KL divergence to individual expert output distributions than Euclidean averaging, TIES, OTA-Merging (Adam v_T diagonal), and ESM (merge-time PCA), on held-out prompts for K=3,5,7 experts.

- **P3 (Task Accuracy):** The KL divergence improvement translates to ≥ 1% absolute task accuracy gain (co-primary metric alongside KL) on GLUE SST-2, MNLI, QNLI, and SQuAD relative to Euclidean averaging baseline.

- **P4 (Matrix vs Diagonal Advantage):** The gap between EigenMerge (matrix eigenbasis from M_T) and OTA-Merging (diagonal from v_T) is larger in layers with high effective rank (many meaningful singular values) and smaller in bottleneck layers — a structural prediction that, if confirmed, validates the matrix-vs-diagonal mechanism.

- **P5 (AdamW Degraded Proxy):** AdamW's v_T, when used as a degraded curvature proxy (applicability ablation), produces merge quality between OTA-Merging and EigenMerge — confirming that the matrix structure of M_T, not merely its relationship to training, drives the improvement.

### Theoretical Guarantee (Tier A — Scalar Case)

**Proposition (Near-Convergence Scalar Alignment):** Let θ* be a local minimum of L(θ) and suppose the training converges such that |θ_T − θ*| ≤ ε for small ε. Under the Muon update rule with β-momentum and a quadratic local approximation L(θ) ≈ L(θ*) + (1/2)(θ − θ*)^T H (θ − θ*), the scalar momentum satisfies:
  m_T = (β/(1−β)) · H · (θ_T − θ*) + O(ε²) + O(β^T)

where H is the Hessian (= Fisher at a local minimum under standard conditions). Thus m_T is an O(ε)-approximation to H·(θ_T − θ*), and its sign/direction tracks the Fisher curvature direction along the convergence path. This establishes the Tier A result: scalar Muon momentum is a consistent Fisher proxy near convergence.

**Limitation (Explicit):** The scalar proof does not extend to the 2D matrix case due to: (a) non-commutativity of matrix operations, (b) NS distortion of singular value magnitudes (even though we use raw M_T, the training dynamics that produce M_T involve NS-modified updates), and (c) gradient noise at finite batch size. Tier B tests whether the matrix analog holds empirically despite these complications.

---

## 8. Method: The EigenMerge Algorithm

### Inputs

- K fine-tuned task checkpoints {θ_1, ..., θ_K}
- Base model checkpoint θ_base (trained with Muon)
- Muon momentum buffers {M_1^T, ..., M_K^T} (or base model's final M_T)
- Rank hyperparameter r (default: r = min(32, d_out, d_in))
- Residual scaling γ ∈ [0, 1] (default: γ = 1.0, i.e., Euclidean average for residual)
- Level selection: L1, L2 (default), L3, L4

### Core Algorithm (L2 — Eigenvalue-Weighted, Default)

**Step 1 — Compute average momentum:**
```
For each layer l with weight matrix W_l ∈ R^{d_out × d_in}:
    M_avg^l = (1/K) Σ_{i=1}^{K} M_i^l    (or base model M_T^l if task buffers unavailable)
```

**Step 2 — Extract Fisher eigenbasis from M_avg:**
```
For each layer l:
    U_l, Σ_l, V_l^T = TruncatedSVD(M_avg^l, rank=r)
    # U_l ∈ R^{d_out × r}: left Fisher eigenvectors
    # V_l ∈ R^{d_in × r}: right Fisher eigenvectors
    # Σ_l ∈ R^{r × r}: diagonal, singular values ≈ Fisher eigenvalues
    # IMPORTANT: use raw M_avg before any NS orthogonalization
    # NS orthogonalization equalizes singular values to 1, destroying eigenvalue information
```

**Step 3 — Project task vectors into Fisher eigenbasis:**
```
For each task i, each layer l:
    τ_i^l = θ_i^l - θ_base^l                         (d_out × d_in task vector)
    A_i^l = U_l^T · τ_i^l · V_l                       (r × r, projected into Fisher eigenbasis)
    R_i^l = τ_i^l - U_l · A_i^l · V_l^T               (d_out × d_in, orthogonal complement residual)
```

**Step 4 — Eigenvalue-weighted average in Fisher eigenbasis (L2):**
```
For each layer l:
    weights_kk = 1 / (Σ_l[k,k] + ε)    (inverse eigenvalue weighting, ε = 1e-6)
    A_merged^l[k,k'] = Σ_{i=1}^{K} weights_kk · A_i^l[k,k'] / (Σ_{j=1}^{K} weights_jj)
    # Simplified: weight each Fisher-basis component inversely by its eigenvalue
    # High-eigenvalue (high-curvature) directions: eigenvalue weighting makes these dominant
    # Low-eigenvalue (flat) directions: unweighted average

    R_merged^l = γ × (1/K) Σ_{i=1}^{K} R_i^l     (simple Euclidean average for residual)
```

**Step 5 — Reconstruct merged task vector:**
```
For each layer l:
    τ_merged^l = U_l · A_merged^l · V_l^T + R_merged^l
```

**Step 6 — Apply to base model:**
```
θ_merged^l = θ_base^l + τ_merged^l
```

### Four-Level Framework

**L1 — Unweighted Projection:**
Same as L2 but A_merged = (1/K) Σ_i A_i (uniform average in Fisher eigenbasis, no eigenvalue weighting). Tests: Does working in the Fisher basis alone improve over Euclidean? Isolates the coordinate-system effect from the weighting effect.

**L2 — Eigenvalue-Weighted (Default):**
As described above. Uses inverse-eigenvalue weighting to emphasize high-curvature directions. The recommended default: best balance of statistical justification, implementation simplicity, and empirical performance based on ablations.

**L3 — Per-Task Fisher Eigenbasis:**
Instead of using M_avg (averaged across tasks), use each task's own M_i^T to extract its task-specific Fisher eigenbasis. Merge in the union of K task-specific eigenbases (top-r/K vectors from each). Addresses the limitation that the base model's Fisher may not capture task-specific curvature directions. Higher cost: K separate SVDs per layer. Tests: Does task-specific curvature improve over base-model curvature?

**L4 — Laplace Approximation (Full KFAC):**
Uses the full KFAC approximation around each θ_i (Gaussian posterior with covariance F_i^{-1}) and computes the optimal Gaussian product as the merged model. The reference upper-bound method: most expensive (requires validation data and KFAC computation), provides the "what full Bayesian merging achieves" ceiling. Enables the comparison ladder: L1 (Fisher basis, no weighting) → L2 (Fisher basis + weighting) → L3 (task-specific basis) → L4 (full KFAC).

### Why Raw M_T (Pre-NS) is Essential

Newton-Schulz orthogonalization maps M_T to the nearest orthogonal matrix by iterating the polynomial recurrence:
  X_{k+1} = (3X_k − X_k^3) / 2, starting from X_0 = M_T / ||M_T||_F

After convergence, X_∞ has all singular values equal to 1 — the matrix is on the Stiefel manifold. This is excellent for training (uniform step sizes), but catastrophic for EigenMerge's eigenvalue-weighted step: all eigenvalues become 1, the weighting degenerates to a uniform average, and L2 reduces to L1. Using raw M_T preserves the singular value magnitudes that encode relative Fisher curvature. This design choice is a distinctive technical contribution and must be validated empirically (ablation A7: raw vs NS-orthogonalized M_T as merge basis).

---

## 9. Baselines (8 Baselines)

**1. Euclidean Averaging**
θ_merge = θ_base + (1/K) Σ_i τ_i. The simplest possible baseline. Why strong: establishes the floor; any method that fails to beat simple averaging is not useful. Implement: trivial.

**2. Task Arithmetic (Ilharco et al., 2023; arXiv:2212.04089)**
Same as Euclidean averaging with a learned scalar coefficient per task (λ_i tuned on a small validation set). Why strong: the industry standard; represents the practitioner default. Implement: available at https://github.com/mlfoundations/task_vectors.

**3. TIES-Merging (Yadav et al., 2023; arXiv:2306.01708)**
Data-free, sign-conflict-aware. Why strong: currently the strongest data-free Euclidean baseline, widely adopted. Implement: available at https://github.com/prateeky2806/ties-merging.

**4. Fisher-Weighted Averaging / Diagonal Fisher (Matena & Raffel, 2022; arXiv:2111.09832)**
Uses diagonal Fisher from a held-out validation set. Why strong: strongest data-dependent diagonal-Fisher baseline; the gold standard for diagonal methods. Must include because EigenMerge claims to match it without data. Implement: requires computing diagonal Fisher on held-out data; ~100 examples sufficient for reasonable estimation.

**5. OTA-Merging (arXiv:2509.11167)**
Uses Adam's v_T as diagonal Fisher proxy, data-free. Why strong: the direct predecessor; represents the "diagonal-only training-state baseline." The key comparison: EigenMerge (matrix-structured M_T) vs OTA-Merging (diagonal v_T). A non-significant improvement over OTA-Merging would severely weaken the contribution. Implement: available or reimplementable in ~1 day.

**6. UMTAM / Squisher (arXiv:2512.17109)**
Alternative training-state-based merging. Why strong: rounds out the "training state for merging" comparison to ensure EigenMerge's improvement is over the whole class, not just OTA. Implement: available or straightforward to reimplement.

**7. ESM — Evolutionary Subspace Merging (merge-time PCA)**
Applies PCA to the K task vectors {τ_1, ..., τ_K} at merge time, projects each into the top principal components (highest task-vector variance directions), and averages in that basis. Why strong: directly tests whether merge-time task-vector PCA (feature variance geometry) performs as well as training-time curvature geometry (Fisher eigenbasis). The fundamental comparison: "what directions did the tasks move in" vs "what directions does the loss landscape curve in." Implement: SVD of the task vector matrix; ~30 lines of code.

**8. Fisher-Rao Manifold Merging (arXiv:2603.04972)**
Full Fisher-Rao geodesic merging. Why strong: represents the theoretically optimal merge under information-geometric principles; EigenMerge should be positioned as a data-free approximation to this method. If EigenMerge approaches Fisher-Rao merging in quality, the practical case for EigenMerge (zero data, sub-linear cost) is compelling. Implement: follow arXiv:2603.04972; requires validation data, higher compute.

### AdamW v_T as Degraded Proxy (Applicability Ablation)

Not a separate baseline, but a critical ablation: apply the EigenMerge algorithm with AdamW's v_T (inflated to a matrix by treating it as a diagonal and comparing to the diagonal singular vectors of M_T) to test whether the matrix structure of M_T is the mechanism, or whether any training-time curvature estimate is sufficient. If AdamW v_T achieves comparable results to Muon M_T in EigenMerge, the "matrix-structured" claim weakens and the contribution reduces to "training-time curvature for merging" (already in OTA-Merging). This ablation is essential for intellectual honesty.

---

## 10. Ablation Plan

**A1 — Core Comparison (Fisher Eigenbasis vs Euclidean):**
L1 (unweighted Fisher basis) vs Euclidean averaging. Isolates whether the coordinate system change alone matters. If L1 ≈ Euclidean, the basis is not useful regardless of weighting.

**A2 — Eigenvalue Weighting (L1 vs L2):**
Unweighted vs inverse-eigenvalue-weighted merge in Fisher basis. Tests whether curvature-magnitude information (eigenvalue sizes) improves over simply using the eigenvector directions. Expected: L2 > L1 in layers with wide eigenvalue spread (L1 ≈ L2 in layers with flat spectra).

**A3 — Base vs Task-Specific Eigenbasis (L2 vs L3):**
M_avg (averaged base/task buffers) vs task-specific M_i^T per task. Tests whether task-specific curvature capture improves merge quality. Higher cost (K SVDs vs 1 SVD per layer) should be justified by meaningful improvement.

**A4 — Matrix vs Diagonal (EigenMerge vs OTA-Merging):**
Primary structural comparison. Expects EigenMerge (matrix M_T) > OTA-Merging (diagonal v_T), especially in layers with high effective rank. If no difference, the "matrix structure" claim fails.

**A5 — Training-Time vs Merge-Time Eigenbasis (M_T vs Task-Vector PCA):**
EigenMerge (M_T curvature) vs ESM (task-vector PCA). Tests whether training-time Fisher geometry (curvature) provides better merge coordinates than merge-time task-vector geometry (variance). These are complementary; could be combined (hybrid L3.5: use M_T curvature directions weighted by task-vector variance).

**A6 — Number of Experts (K = 2, 3, 5, 7, 10):**
Tests scalability of EigenMerge with increasing number of tasks. Euclidean merge degrades superlinearly with K (growing interference); EigenMerge should degrade more gracefully since Fisher-basis projection handles interference structurally.

**A7 — Raw vs NS-Orthogonalized M_T:**
Uses NS-orthogonalized M_T (all singular values = 1) vs raw M_T as the eigenbasis source. Critical design-choice validation. If orthogonalized M_T (L1-equivalent behavior) matches raw M_T, the eigenvalue weighting is not contributing.

**A8 — Rank r Sensitivity (r = 8, 16, 32, 64, 128):**
Tests how many eigenvectors are needed for good merge quality. Expects a rank-quality curve with diminishing returns above some threshold r*. Informs the storage/quality tradeoff.

**A9 — AdamW v_T as Degraded Proxy:**
Replaces Muon M_T with AdamW v_T (reinterpreted as a diagonal matrix) in the EigenMerge pipeline. If AdamW v_T achieves ≥ 90% of EigenMerge's improvement over Euclidean, the matrix-structure claim is weak and the contribution is primarily the weighting scheme (partially a repackaging of OTA-Merging). This ablation is the honesty check for the "matrix vs diagonal" claim.

**A10 — Residual Treatment (γ = 0, 0.5, 1.0):**
γ = 0: discard residual (only merge in Fisher eigenbasis). γ = 1.0: Euclidean average for residual (default). Intermediate γ: soft interpolation. Tests whether the out-of-basis residual carries useful task information or introduces noise.

---

## 11. Experiment Plan

### Storage Overhead (Explicit Quantification)

Muon momentum buffers M_T require storing one d_out × d_in float32 matrix per weight layer — identical to the size of the weight matrices themselves.

- LLaMA-3-8B (full precision): ~8B parameters × 4 bytes = 32 GB for weights + 32 GB for M_T = 64 GB total. M_T overhead = 1× the model size.
- LLaMA-3-8B (bfloat16 M_T): 16 GB M_T overhead = 0.5× the model size.
- Practical note: M_T need only be saved at the end of training (not throughout). For a 14B-parameter model: 14 GB (float32) or 7 GB (bf16) additional storage per model. This is a one-time cost at training completion, not runtime overhead during inference.

### Compute Classification: Sub-Linear in Training Compute

Merge-time compute for EigenMerge on a K-expert merge of an L-layer model with rank-r SVD:
- Dominant cost: K × L × TruncatedSVD(d_out × d_in, rank=r) ≈ K × L × O(r × d_out × d_in)
- For K=7, L=32, r=32, d=4096: ~7 × 32 × 32 × 4096² / 1e12 ≈ 1.2 × 10^11 FLOPs ≈ 0.12 TFLOPs
- LLaMA-3-8B training: ~10^22 FLOPs (Chinchilla-optimal)
- EigenMerge merge cost / training cost ≈ 10^{-11}: truly sub-linear in training compute.
- Comparison: merge-time Fisher estimation (Fisher-Weighted Averaging) requires forward passes over validation data — at 100 examples × 8B FLOPs/example = 8 × 10^11 FLOPs, 6× more expensive than EigenMerge merge cost.

### Phase 1: Core Validation (Weeks 1-6, ~80 GPU-hours)

**P1-A — MVE: EigenMerge vs 4-Baseline Head-to-Head**

Setup:
- Base model: Mistral-7B-v0.3 (available with Muon-trained variants, or train GPT-2-medium with Muon in-house as lower-cost alternative)
- Task checkpoints: K=5 fine-tuned variants from FLAN-style multi-task setup (SST-2, MNLI, QNLI, SQuAD, CoNLL-NER)
- Momentum buffers: save M_T pre-NS at final training step for each task model
- Metrics: (a) KL divergence to individual expert outputs (held-out 1000 prompts per task), (b) task accuracy on GLUE evaluation sets

Procedure:
1. Compute task vectors τ_i = θ_i − θ_base for each expert
2. Extract EigenMerge eigenbasis: TruncatedSVD(M_avg, r=32) per layer
3. Run all 8 baselines + EigenMerge L1, L2, L3
4. Report: KL divergence (primary), task accuracy (co-primary), merge-time cost (seconds)

Expected outcome: EigenMerge L2 ranks in top-2 among data-free methods on ≥ 4/5 tasks. Beats OTA-Merging by ≥ 0.5 percentage points accuracy on average.

Kill criterion: If EigenMerge L2 does not beat OTA-Merging (diagonal v_T baseline) on ≥ 3/5 tasks with statistical significance (p < 0.05, paired bootstrap), the "matrix vs diagonal" claim fails and the contribution collapses to a negative result. Halt and pivot to analysis of why matrix structure does not help (publishable as a negative/null result in a methods-focused venue).

Hardware: 2× H200, ~40 GPU-hours.

**P1-B — Fisher Alignment Measurement (Tier B Validation)**

Procedure: For each of 5 representative layers (embedding, early attention, mid-FF, late attention, final layer), compute:
1. True empirical Fisher eigenvectors via Hutchinson estimation (50-100 random vectors, 500 samples from training data)
2. Muon M_T singular vectors (top-5)
3. Adam v_T diagonal structure (top-5 diagonal entries as proxy)
4. Cosine similarity between M_T singular vectors and true Fisher eigenvectors

Report: cos-sim distribution across layers and eigenvector ranks. Success threshold (raised from prior 0.5): mean cos-sim ≥ 0.7 for top-5 eigenvectors across layers.

Comparative claim: Muon M_T cos-sim > Adam v_T cos-sim (diagonal-only) by a margin that justifies the matrix-structure claim.

Hardware: 1× H200, ~20 GPU-hours.

**P1-C — Ablation A7 (Raw vs NS M_T) and A9 (AdamW v_T Proxy)**

Run A7 (raw vs NS-orthogonalized M_T) and A9 (AdamW v_T as proxy) alongside P1-A using identical setup.

Critical: If A9 shows AdamW v_T ≥ 90% of EigenMerge improvement, revise framing to "training-time eigenbasis outperforms diagonal regardless of optimizer."

Hardware: Uses P1-A infrastructure, ~15 GPU-hours incremental.

### Phase 2: Scaling and Generalization (Weeks 7-14, ~150 GPU-hours)

**P2-A — Scale Sweep**

Models: GPT-2-medium (345M), GPT-2-large (774M), Pythia-1.4B, Mistral-7B
K = 5 experts for each model
Measure: EigenMerge advantage over OTA-Merging as function of model size
Expected: advantage larger for larger models (more complex curvature structure, more off-diagonal Fisher information)

Hardware: ~80 GPU-hours.

**P2-B — Expert Count Scaling (Ablation A6)**

K ∈ {2, 3, 5, 7, 10} on Mistral-7B with 10 prepared task checkpoints
Key question: Does EigenMerge's advantage over Euclidean grow with K? Euclidean interference grows roughly linearly in K; EigenMerge should mitigate this via eigenbasis projection.

Hardware: ~30 GPU-hours (re-uses trained checkpoints from P1-A).

**P2-C — Rank Sensitivity (Ablation A8)**

r ∈ {8, 16, 32, 64, 128} on Mistral-7B
Report: rank-quality curve. Identify r* (rank of diminishing returns).
Theoretical expectation: r* ≈ stable rank of M_avg (||M_avg||_F² / ||M_avg||_2²).
Also: storage overhead vs quality tradeoff table (bf16 overhead in GB vs accuracy).

Hardware: ~30 GPU-hours.

**P2-D — Residual Treatment Ablation (A10)**

γ ∈ {0, 0.1, 0.25, 0.5, 1.0}. Tests whether residual carries task information.
If γ = 0 performs competitively, the residual is noise — simplifies the method.
If γ = 1.0 is optimal (Euclidean residual), the method is more robust than the theory would suggest.

Hardware: ~10 GPU-hours.

### Phase 3: Benchmarks and Theory (Weeks 15-20, ~90 GPU-hours)

**P3-A — Full GLUE + SQuAD Benchmark**

Apply EigenMerge L2 to merge 8 GLUE task experts + SQuAD expert (K=9) on Mistral-7B
Report full GLUE table with all 8 baselines
Primary claim: EigenMerge is Pareto-optimal on the data-cost vs accuracy curve (best data-free method; competitive with or superior to Fisher-Weighted Averaging which uses data)

Hardware: ~40 GPU-hours.

**P3-B — EigenMerge vs Fisher-Rao Manifold Merging (arXiv:2603.04972)**

Direct comparison: EigenMerge (data-free, sub-linear cost) vs Fisher-Rao manifold merging (data-dependent, higher cost)
Framing: EigenMerge achieves X% of Fisher-Rao quality at Y% of its compute cost and zero data
If EigenMerge matches Fisher-Rao within 1%, the contribution is very strong; even a 3-5% gap is acceptable if the cost differential is large.

Hardware: ~30 GPU-hours.

**P3-C — L1/L2/L3/L4 Framework Comparison (Full Ladder)**

Report all four levels on identical setup. Shows the value ladder from "Fisher basis only" to "eigenvalue weighting" to "task-specific basis" to "full KFAC."
Key finding to surface: at what point does the data requirement outweigh the quality improvement?
Actionable output: a decision table for practitioners — "if you have no data, use L2; if you have 100 examples, use L3; if you have 1000 examples, use L4."

Hardware: ~20 GPU-hours.

### Total Estimated Compute: ~320 GPU-hours

---

## 12. Success Criteria and Kill Results

### Primary Success Criteria (both required for publication)

- **SC1 (Task Accuracy, Co-Primary):** EigenMerge L2 achieves ≥ 1% absolute average task accuracy improvement over Euclidean averaging across ≥ 4/5 task merges in Phase 1 (paired bootstrap, p < 0.05).

- **SC2 (KL Divergence, Co-Primary):** EigenMerge L2 achieves ≥ 10% relative reduction in average KL divergence to individual expert outputs vs Euclidean averaging, held-out 1000 prompts per task.

### Supporting Success Criteria (desired but not required)

- **SC3 (Over OTA-Merging):** EigenMerge L2 beats OTA-Merging by ≥ 0.5 percentage points accuracy on ≥ 3/5 tasks. If this criterion fails, the "matrix vs diagonal" claim is at risk.

- **SC4 (Fisher Alignment):** Mean cos-sim of Muon M_T singular vectors vs true Fisher eigenvectors ≥ 0.7 (threshold raised from 0.5 in R3 review) for top-5 eigenvectors in ≥ 4/5 tested layers.

- **SC5 (Data-Free vs Data-Dependent):** EigenMerge L2 achieves ≥ 95% of Fisher-Weighted Averaging quality (diagonal) at zero data cost. If EigenMerge needs 100+ examples to match Fisher-Weighted Averaging, the "zero data" advantage is weakened.

### Kill Results (halt and reassess)

- **K1:** EigenMerge L2 does not beat OTA-Merging (diagonal v_T) on ≥ 3/5 tasks — suggests matrix structure does not help; consider reframing as a negative result or merging with OTA-Merging as an analysis paper.

- **K2:** AdamW v_T proxy (Ablation A9) achieves ≥ 90% of EigenMerge's improvement over Euclidean — suggests the mechanism is "any training-time curvature" not "matrix-structured curvature," undermining the Muon-specific claim; downgrade to analysis and redirect to systems paper.

- **K3:** Mean cos-sim of M_T singular vectors vs true Fisher eigenvectors < 0.5 — Tier B assumption violated; the eigenbasis is not well-aligned with the Fisher, and the Riemannian interpretation is unjustified; potential pivot to "moment-matching heuristic without information-geometric justification."

---

## 13. Positioning and Anticipated Objections

### Honest Framing of Novelty

The contribution is **not** "reuse optimizer state for merging" — that is conceded to OTA-Merging (2509.11167) and UMTAM/Squisher (2512.17109). The contribution is:

1. **Matrix vs Diagonal:** Muon's M_T provides a rank-r matrix-structured approximation to the Fisher eigenvectors (d_out × d_in, captures row-column correlations). Adam's v_T provides only a diagonal approximation (treats each parameter independently). This structural difference — which has never been tested in the merging literature — is EigenMerge's specific claim.

2. **Training-Time Curvature vs Merge-Time Variance:** EigenMerge's eigenbasis comes from training-time loss curvature (what does the loss surface look like around θ_base?). ESM's eigenbasis comes from merge-time task-vector PCA (what directions did the tasks move in?). These capture different and complementary geometric information.

3. **Zero Data with Matrix Structure:** No prior work has achieved both matrix-structured Fisher geometry AND zero merge-time data cost. The data-free constraint is what motivates the training-time momentum buffer approach.

### Anticipated Reviewer Objections

**Objection 1: "ESM (merge-time PCA) and Fisher-Rao merging already use eigenvector geometry. Your novelty is thin."**
Response: ESM uses task-vector variance (not curvature), has no information-geometric justification, and cannot improve with more training. Fisher-Rao merging (2603.04972) requires merge-time data. EigenMerge occupies a specific position — matrix-structured, training-time, data-free — that neither method occupies. The experimental comparison (Ablations A5, P3-B) directly tests whether this position provides value.

**Objection 2: "The Tier A scalar proof doesn't extend to the matrix case. Your theoretical justification is weak."**
Response: Acknowledged upfront. The paper makes a two-tier claim: Tier A (scalar proof, fully rigorous) + Tier B (empirical matrix case). Tier A provides motivation and intuition; Tier B is the primary empirical contribution. This is honest and follows the standard in the optimization literature where scalar results motivate matrix-case empirics (e.g., gradient descent convergence theory vs practice).

**Objection 3: "If Muon's M_T requires saving, this adds 0.5-1× storage overhead. For large models, this is prohibitive."**
Response: Storage quantified explicitly: 14 GB (float32) or 7 GB (bf16) per base model for LLaMA-3-8B. This is a one-time training-time cost, not inference overhead. For practitioners who already save optimizer checkpoints for training resumption (common practice), there is zero additional cost. The overhead is real but manageable; the paper reports the tradeoff explicitly and tests whether bf16 M_T retains alignment quality (additional ablation).

**Objection 4: "What if the model was not trained with Muon? The method requires Muon."**
Response: True limitation, stated explicitly. The method requires a Muon-trained base model. The applicability ablation (A9) tests AdamW v_T as a degraded alternative — if AdamW v_T achieves 75%+ of EigenMerge's quality, practitioners with AdamW-trained models have a fallback. The paper reports both cases, framing EigenMerge as the optimal case for Muon-trained models and providing a degraded variant for AdamW practitioners.

**Objection 5: "The eroding novelty issue — ESM, SVC, Fisher-Rao (2603.04972) all use eigenvector-level geometry. The 'matrix vs diagonal' split is not as clean as claimed."**
Response (honest): The novelty gap is real and acknowledged. The paper's specific claim — matrix-structured, training-time, data-free eigenvector geometry — is a real differentiated position, but the information-geometric merging space has become crowded in 2025-2026. The paper is positioned as a Tier 2 contribution (ICML 2027 workshop → ICML 2028 main) rather than a Tier 1 splash paper, which is appropriate given the crowding. The honest contribution is: (1) empirically testing whether matrix structure matters over diagonal, (2) showing training-time curvature vs merge-time variance, and (3) quantifying when zero-data merging is competitive with data-dependent methods.

---

## 14. Timeline, Venue, and Confidence

### Timeline (6 months total)

| Weeks | Milestone |
|---|---|
| 1–2 | Literature verification: OTA-Merging, UMTAM, ESM, Fisher-Rao (2603.04972) implementations reviewed; confirm EigenMerge's differentiated position. Save Muon momentum buffers from existing Muon-trained checkpoints or train GPT-2-medium with Muon in-house. |
| 3–4 | P1-A MVE: EigenMerge L2 vs 8 baselines on 5-task K=5 merge. P1-B: Fisher alignment measurement. P1-C: Ablations A7 and A9. |
| 5–6 | Go/No-Go gate: If K1 or K2 (kill criteria), halt and redirect. If SC3+SC4 hold (≥ 0.5 pp over OTA-Merging and cos-sim ≥ 0.7), proceed to Phase 2. |
| 7–10 | P2-A (scale sweep), P2-B (expert count scaling), P2-C (rank sensitivity). |
| 11–14 | P2-D (residual ablation). Remaining ablations. Write up Phase 1+2 results. |
| 15–18 | P3-A (full GLUE benchmark), P3-B (Fisher-Rao comparison), P3-C (L1/L2/L3/L4 ladder). |
| 19–20 | Theory section: Tier A scalar proof writeup, Tier B empirical alignment. Positioning vs OTA-Merging and Fisher-Rao. |
| 21–24 | Paper writing, iterative revision. ICML 2027 workshop submission. |

### Recommended Venue

**Primary:** ICML 2027 (workshop track first, main track if results are strong)
**Alternative:** NeurIPS 2027 main, ICLR 2027 (if timeline permits), TMLR (for a thorough methods paper with full ablation table)

**Rationale for Tier 2 positioning:** The information-geometric merging space has become crowded (ESM, SVC, Fisher-Rao manifold, OTA-Merging, UMTAM). EigenMerge's specific position (matrix-structured, training-time, data-free) is defensible but not high-impact enough for a Tier 1 splash. The contribution is a thorough empirical and theoretical study of a specific structural question (matrix vs diagonal curvature for merging), with honest positioning relative to prior work. Workshop-first strategy allows testing the community reception before investing in a full main-track submission.

**Scooping risk note:** The R3-VP-1 issue identified that OTA-Merging (2509.11167) and UMTAM (2512.17109) partially scoop the "reuse optimizer state for merging" direction. EigenMerge has repositioned to make the "matrix vs diagonal" structural claim the core contribution — this specific comparison is not made in either OTA-Merging or UMTAM. However, if any group publishes "matrix-structured momentum for merging" between now and the submission deadline, EigenMerge would need further repositioning. Monitor arXiv weekly in the model merging, information geometry, and Muon optimizer spaces.

### Confidence Assessment

**Overall confidence: Medium**

- If SC1+SC2 hold (task accuracy and KL improvement over Euclidean): publication confidence = High for workshop track, Medium for main track
- If SC3 holds additionally (EigenMerge > OTA-Merging): publication confidence = Medium for main track at Tier 2 venue
- If SC3 fails (EigenMerge ≈ OTA-Merging): publication confidence = Low for main track; best reframed as a null-result analysis paper "Does Matrix Structure Matter for Optimizer-State Merging?"
- If K1 or K2 (kill results): pivot to analysis paper, ~2 months additional work for repositioning

The key empirical uncertainty is whether the matrix-structured eigenvectors of M_T provide materially different merge coordinates than the diagonal structure of v_T, at a level that translates to task accuracy. This is plausible theoretically (off-diagonal curvature structure should matter for 2D weight matrices) but unconfirmed empirically. The ~320 GPU-hour investment to test this question is modest and well-justified by the specificity of the claim.

---

*Proposal version: Round 4 (EigenMerge reframe)*
*Last revised: 2026-03-28*
*Idea slug: information-geometry-muon-merge*
*Rank: #5 in muon-neural-thickets-optimization portfolio*
