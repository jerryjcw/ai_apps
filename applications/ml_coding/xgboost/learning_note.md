# XGBoost 考前複習筆記 — Interview Cheat Sheet

> 用途：面試前一天快速複習。先看每節的 **TL;DR**，時間夠再讀細節。
> 英文術語保留，方便聽英文面試時對得上。

---

## 0. 最常被問到的 1 分鐘自介

**What is XGBoost?**
XGBoost = **eXtreme Gradient Boosting**。是一種 **gradient boosted decision trees (GBDT)** 的高效率實作，由陳天奇在 2014 年提出（*XGBoost: A Scalable Tree Boosting System*, KDD 2016）。核心賣點：

1. **Regularized objective** — loss 裡內建 L1/L2 penalty 控制葉子權重。
2. **Second-order Taylor approximation** — 用 gradient + Hessian 同時評分分裂。
3. **Sparsity-aware split finding** — 原生處理 missing values。
4. **Histogram-based split** + **column block + cache-aware** 資料結構 → 快。
5. **Parallel split finding**（節點內平行，不是樹之間平行）。

---

## 1. Gradient Boosting 機制（必考）

### 加法模型 Additive Model

$$\hat{y}_i = \sum_{k=1}^{K} f_k(x_i), \quad f_k \in \mathcal{F} \text{ (space of trees)}$$

每一輪加一棵新樹，擬合的是 **前面所有樹加總後剩下的殘差梯度**。

### 目標函數 Objective Function

$$\text{Obj} = \underbrace{\sum_i L(y_i, \hat{y}_i)}_{\text{training loss}} + \underbrace{\sum_k \Omega(f_k)}_{\text{regularization}}$$

$$\Omega(f) = \gamma T + \tfrac{1}{2}\lambda \|w\|^2$$

- `T` = 葉子數；`w` = 葉子權重向量。
- `γ` (`gamma`) = 每多一片葉子的懲罰 → **剪枝**。
- `λ` (`reg_lambda`) = L2 懲罰 → **壓小葉子權重**。

**This is XGBoost's 主要創新** — 把正則化明確寫進目標函數，讓深樹也能不過擬合。

### Second-order Taylor Expansion

第 `t` 輪要優化：

$$\text{Obj}^{(t)} \approx \sum_i \left[ g_i f_t(x_i) + \tfrac{1}{2} h_i f_t^2(x_i) \right] + \Omega(f_t)$$

其中 `g_i = ∂L/∂ŷ`（一階導），`h_i = ∂²L/∂ŷ²`（二階導）。

**關鍵**：因為用到 Hessian，每個葉子的最佳權重有 closed-form 解：

$$w_j^* = -\frac{\sum_{i \in I_j} g_i}{\sum_{i \in I_j} h_i + \lambda}$$

### Split Gain 公式（考試常出）

$$\text{Gain} = \tfrac{1}{2}\left[ \frac{G_L^2}{H_L+\lambda} + \frac{G_R^2}{H_R+\lambda} - \frac{(G_L+G_R)^2}{H_L+H_R+\lambda} \right] - \gamma$$

Gain < 0 時不分裂（pre-pruning by γ）。這公式讓 XGBoost 能用純加減法快速評估所有候選 split。

---

## 2. 超參數全家桶 (Hyperparameters)

### 最常調的 5 組

| 類別 | 參數 | 作用 | 典型範圍 |
|---|---|---|---|
| **Boosting 結構** | `n_estimators` | 樹的總棵數 | 用 early stopping 決定 |
| | `learning_rate` (`eta`) | Shrinkage，每棵樹的步長 | 0.01–0.3，最後調小 |
| **樹形** | `max_depth` | 單棵樹最大深度 | **3–10**，預設 6 |
| | `min_child_weight` | 葉子最小 Hessian 和 | 1–10 |
| | `gamma` | 分裂最小 gain 閾值 | 0–1 |
| **抽樣** | `subsample` | 每棵樹的列抽樣比例 | 0.6–1.0 |
| | `colsample_bytree` | 每棵樹的欄抽樣比例 | 0.6–1.0 |
| | `colsample_bylevel` | 每層的欄抽樣 | 通常不調 |
| | `colsample_bynode` | 每個節點的欄抽樣 | RF 風格 |
| **正則化** | `reg_lambda` | L2 on leaf weights | 0.1–10 |
| | `reg_alpha` | L1 on leaf weights | 0, 0.001–1 |
| **系統** | `tree_method` | `hist` / `exact` / `approx` / `gpu_hist` | 預設 `hist` |
| | `enable_categorical` | 原生吃 pandas `category` | True 推薦 |
| | `scale_pos_weight` | 類別不平衡權重 | `neg/pos` |

### `max_depth` vs `n_estimators`（我們討論過）

- `max_depth` 控制 **單棵樹的複雜度**。深度 `d` → 最多 `2^d` 片葉子 → 計算量指數成長。
- `n_estimators` 控制 **總共幾棵樹**。和 `learning_rate` 互補：`lr` 小就要多棵樹。
- 實務：**不手動選 `n_estimators`**，用 early stopping。

---

## 3. XGBClassifier vs XGBRFClassifier（我們討論過）

| | `XGBClassifier` | `XGBRFClassifier` |
|---|---|---|
| 算法類型 | **Gradient Boosting**（序列） | **Random Forest**（平行） |
| 樹之間關係 | 有依賴，每棵修正前一棵殘差 | 獨立、bootstrap 抽樣 |
| 最終預測 | `ŷ = f₁ + η·f₂ + ... + η·f_K` | `ŷ = (1/K)·Σ f_k` (平均) |
| `learning_rate` | < 1 (shrinkage) | = 1（無 shrinkage）|
| 典型 `max_depth` | 淺 (~6) | 深 (~10+) |
| 誰建的樹多 | `n_estimators` | `num_parallel_tree` |

XGBRFClassifier 本質是 XGBClassifier 設 `num_parallel_tree=N, n_estimators=1, learning_rate=1`。

**面試要點**：表格資料 99% 情況下 boosting > RF，RF 只當作快速 baseline 或 ensemble 的 base learner。

---

## 4. XGBoost vs LightGBM vs CatBoost（超常考）

| | **XGBoost** | **LightGBM** | **CatBoost** |
|---|---|---|---|
| 作者 | Tianqi Chen (UW, 2014) | Microsoft (2017) | Yandex (2017) |
| **樹生長** | **Level-wise** (按層) | **Leaf-wise** (按葉 best-first) | **Symmetric/oblivious** (對稱樹) |
| 主要調參 | `max_depth` | **`num_leaves`** | `depth` (對稱) |
| 速度 | 中等 | **最快**（GOSS + EFB）| 中等 |
| 類別處理 | 後來加的 (`enable_categorical`) | 原生支援，Fisher 方法 | **最強**，Ordered TS |
| 小資料過擬合 | 不易 | **易**（leaf-wise 貪心） | 不易 |
| 預測速度 | 中 | 中 | **最快**（對稱樹）|
| GPU 支援 | 好 | 好 | 好 |
| 何時用 | 穩健預設、生態系成熟 | 大資料、高維稀疏 | 類別多、預設少調參 |

### LightGBM 的兩個特殊加速

- **GOSS** (Gradient-based One-Side Sampling) — 保留大梯度樣本，隨機丟小梯度樣本。
- **EFB** (Exclusive Feature Bundling) — 把「不同時非零」的稀疏特徵捆成一個。

### CatBoost 的兩個獨特點

- **Ordered Boosting** — 避免 target leakage 的特殊訓練順序。
- **Ordered Target Statistics** — 類別編碼用歷史資料的目標統計。

### 參數命名對照（容易踩坑）

| 概念 | XGBoost | LightGBM | CatBoost |
|---|---|---|---|
| Learning rate | `learning_rate` | `learning_rate` | `learning_rate` |
| 樹形主控 | `max_depth` | **`num_leaves`** | `depth` |
| 葉最小樣本 | `min_child_weight` (Hessian) | `min_child_samples` (count) | `min_data_in_leaf` |
| 列抽樣 | `subsample` | `bagging_fraction` | `subsample` |
| 欄抽樣 | `colsample_bytree` | `feature_fraction` | `rsm` |
| L2 | `reg_lambda` | `lambda_l2` | `l2_leaf_reg` |

---

## 5. 調參策略（我們討論過）

### 順序記憶口訣

```
固定 lr=0.1 + early stopping
  → 調 (max_depth, min_child_weight)    ← 影響最大
  → 調 gamma                             ← 剪枝
  → 調 (subsample, colsample_bytree)     ← 對抗過擬合
  → 調 (reg_alpha, reg_lambda)           ← 微調
  → 最後 lr 調小，n_estimators 放大      ← 收尾
```

### 工具選擇

- **GridSearchCV** — 參數少 (≤3)，網格清楚。
- **RandomizedSearchCV** — sklearn 標配，效率好，建議起手式。
- **Optuna** — 現在業界默認，TPE (Tree-structured Parzen Estimator)，50 次試驗 ≈ 200 次隨機。
- **Hyperopt** — Optuna 的前輩，還活著但新專案多用 Optuna。

### 常見陷阱 (Pitfalls)

1. **用 test set 調參** → test score 會被高估。永遠只有 train+val 做 CV 調參。
2. **不開 early stopping** → 手動挑 `n_estimators` 在浪費時間。
3. **最佳值落在搜索邊界** → 一定要擴大範圍再搜一次。
4. **類別不平衡沒處理** → 二分類記得設 `scale_pos_weight = #neg / #pos`。
5. **CV 沒 stratify** → 小類別樣本在 fold 間分佈不穩。
6. **特徵洩漏 (Target Leakage)** → 用未來資訊、ID、時間洩漏。

---

## 6. 缺失值與類別特徵處理

### Missing Values — Sparsity-Aware Split Finding

每個 split 訓練時 **學一個「預設方向」(default direction)**：缺失值在預測時一律走這個方向。

- **好處**：不用做 imputation；稀疏矩陣 (CSR/CSC) 直接吃。
- **缺點**：如果 NaN 有 informative meaning（例如 `age=NaN` 代表特殊族群），模型會自然學到這個模式。

### Categorical Features

- **早年的做法**：one-hot encoding。高基數類別會爆炸 → curse of dimensionality。
- **XGBoost 1.5+**：`enable_categorical=True` + pandas `category` dtype，底層用 partition-based split。
- **Tip**：類別 > 100 時，優先考慮 LightGBM / CatBoost，或自己做 target encoding（注意 leakage）。

---

## 7. Overfitting 對策清單

當 train score 遠高於 val score 時：

1. **降低 `max_depth`** → 減少單樹複雜度
2. **調高 `min_child_weight`** → 葉子需要更多樣本才能存在
3. **調高 `gamma`** → 分裂門檻更嚴
4. **降低 `subsample` / `colsample_bytree`** → 注入隨機性
5. **調高 `reg_lambda` / `reg_alpha`** → L2 / L1 懲罰
6. **降低 `learning_rate`** + 增加 `n_estimators` + early stopping
7. **更多資料** 或 **特徵工程減少噪音**

當 train score 也不高（underfitting）：相反操作——深度調大、正則放鬆、`n_estimators` 加多。

---

## 8. 類別不平衡 (Class Imbalance)

| 方法 | 做法 |
|---|---|
| `scale_pos_weight` | 設成 `#negatives / #positives`，改每個正例的梯度 |
| `sample_weight` 參數 | `fit(..., sample_weight=w)` |
| Focal Loss | 自訂 objective function |
| 過採樣 (SMOTE) | 在 input 層面做 |
| 閾值調整 (Threshold tuning) | 預測時改 0.5 → 另一個閾值（用 PR curve 找最佳 F1）|

**面試答題要點**：優先用 `scale_pos_weight` 或 class weights，**不要** 在訓練集裡 oversample 然後又 CV，容易資料洩漏。

---

## 9. 評估指標 (Metrics)

### 分類

| 指標 | 何時用 |
|---|---|
| Accuracy | 類別平衡、錯誤代價對稱 |
| **ROC-AUC** | 排序能力，閾值無關；二分類面試首選 |
| **PR-AUC** | 類別嚴重不平衡（正例稀少），比 ROC-AUC 敏感 |
| F1 | 需要單一數字，關心 precision 和 recall 平衡 |
| Log Loss | 關心機率校準 (probability calibration) |
| Brier Score | 機率預測均方誤差 |

**常見陷阱**：類別不平衡時用 accuracy → 全預測多數類也能 95%，騙人指標。

### 迴歸

- RMSE (sensitive to outliers)
- MAE (robust)
- MAPE (相對誤差，但 y 接近 0 時爆炸)
- R² (explained variance)

---

## 10. Feature Importance

XGBoost 提供 5 種，`booster.get_score(importance_type=...)`:

| 類型 | 意義 |
|---|---|
| **gain** | **每次分裂平均 loss 降幅**（面試預設選這個）|
| weight / frequency | 特徵被當 split 用的次數 |
| cover | 平均覆蓋樣本數 (average Hessian) |
| total_gain | 總 loss 降幅（不取平均）|
| total_cover | 總覆蓋 |

**重要提醒**：tree importance 對 **高基數類別 / 連續變數有偏好**，容易誤導。更嚴謹的做法：

- **Permutation Importance**（隨機打亂某特徵，看指標掉多少）
- **SHAP values** — 基於 Shapley value，有 local (per-sample) + global 兩種解釋，`shap.TreeExplainer` 對樹模型有 polynomial-time 精確解。

---

## 11. 什麼時候 **不要** 用 XGBoost

| 情境 | 更好的選擇 |
|---|---|
| 影像 / 音訊 / 原始文字 | CNN / Transformer |
| 時間序列（強趨勢/季節） | Prophet / ARIMA / 深度模型 |
| 特徵間有強空間/順序結構 | CNN / RNN |
| 極小資料 (< 幾百) | 線性模型 + 強特徵工程 |
| 需要線上 (online) 持續學習 | SGD / Vowpal Wabbit |
| 需要絕對可解釋（法規/醫療） | 線性模型 / GAM / 決策樹 |
| 資料太大、記憶體不夠 | LightGBM / Spark ML |

**重點**：XGBoost 的主戰場是 **結構化表格資料 (structured tabular data)**。

---

## 12. 其他高頻面試題

### Q: Random Forest vs Gradient Boosting 差別？

| | Random Forest | Gradient Boosting |
|---|---|---|
| 組合方式 | Bagging（平均）| Boosting（加權序列）|
| 樹建構 | 獨立、平行 | 序列、依賴 |
| 偏差-變異 | 降變異 | 降偏差 |
| 過擬合風險 | 低 | 高（需要正則）|
| 典型樹形 | 深 | 淺 |
| 調參難度 | 簡單 | 難 |
| 結構化資料上的表現 | 中等 | **強**（通常贏）|

### Q: AdaBoost vs Gradient Boosting？

- **AdaBoost**：改變「樣本權重」— 錯分的樣本下一輪權重變大。
- **Gradient Boosting**：用「損失函數的梯度」指導下一棵樹擬合殘差。更通用（任何可微 loss 都行）。

### Q: XGBoost 的平行化在哪？

**不是** 「多棵樹平行」（樹之間有依賴）。而是：

1. **Split 評估平行**：找最佳 split 時，不同特徵的 gain 計算可以平行。
2. **Column block** 資料結構：事先排序特徵值，讓多個節點共用。
3. **分佈式 (distributed XGBoost)**：data-parallel，每個 worker 處理不同樣本的 histogram，Allreduce 合併。

### Q: Histogram 方法原理？

連續特徵分成固定數量 (通常 255) 的 bins，分裂時只考慮 bin 邊界。把 `O(#samples × #features)` 的 split finding 降到 `O(#bins × #features)`。代價：精度略降（但實務上幾乎沒差）。

### Q: XGBoost 的 `early_stopping_rounds` 真的怎麼運作？

訓練時監控 `eval_set` 上的指標。若連續 N 輪沒改善（最好的 epoch 在 N 輪之前），**停止訓練**，保留 `best_iteration` 的模型。面試常問「最佳輪數存在哪？」→ `model.best_iteration` (XGBoost ≥ 2.x)。

### Q: 模型如何儲存 / 部署？

- **JSON / UBJ 格式** (`model.save_model("m.json")`) — 跨語言、跨版本、推薦。
- **Pickle** — 只能同環境，不推薦生產。
- **ONNX** — 要跨框架部署時用。
- **Treelite** — 編譯成 C / shared library，推理極快。

### Q: 為什麼 XGBoost 在 Kaggle 如此成功？

1. **Bias-variance tradeoff 精細**：深樹 + 強正則。
2. **Second-order 導數**：收斂快、split 評分精準。
3. **Regularization 內建**：γ, λ, α, subsample, colsample。
4. **Sparsity-aware + histogram**：速度快、能吃髒資料。
5. **Early stopping + CV + Feature importance** 都是一條龍 API。
6. **可解釋性** (SHAP, tree structure) 比深度模型好。

---

## 13. 常用程式碼片段 (Code Snippets)

### Baseline training with early stopping

```python
import xgboost as xgb

model = xgb.XGBClassifier(
    objective="binary:logistic",
    eval_metric="auc",
    tree_method="hist",
    n_estimators=2000,
    learning_rate=0.05,
    max_depth=6,
    min_child_weight=1,
    subsample=0.9,
    colsample_bytree=0.9,
    reg_lambda=1.0,
    enable_categorical=True,
    random_state=42,
    early_stopping_rounds=50,
)
model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
print("best iteration:", model.best_iteration)
```

### Optuna 搜索

```python
import optuna

def objective(trial):
    params = {
        "max_depth":        trial.suggest_int("max_depth", 3, 10),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
        "gamma":            trial.suggest_float("gamma", 0, 2),
        "subsample":        trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        "reg_lambda":       trial.suggest_float("reg_lambda", 0.1, 10, log=True),
        "learning_rate":    0.1,
        "n_estimators":     2000,
        "early_stopping_rounds": 50,
        "tree_method":      "hist",
        "enable_categorical": True,
        "eval_metric":      "auc",
    }
    m = xgb.XGBClassifier(**params)
    m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    from sklearn.metrics import roc_auc_score
    return roc_auc_score(y_val, m.predict_proba(X_val)[:, 1])

study = optuna.create_study(direction="maximize")
study.optimize(objective, n_trials=50)
```

### SHAP 解釋

```python
import shap
explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)
shap.summary_plot(shap_values, X_test)   # global
shap.force_plot(explainer.expected_value, shap_values[0], X_test.iloc[0])  # local
```

### 類別不平衡

```python
neg = (y_train == 0).sum()
pos = (y_train == 1).sum()
model = xgb.XGBClassifier(scale_pos_weight=neg / pos, ...)
```

### Cross-validation with xgboost.cv

```python
dtrain = xgb.DMatrix(X, label=y, enable_categorical=True)
cv = xgb.cv(
    params={"objective":"binary:logistic", "eval_metric":"auc", "tree_method":"hist"},
    dtrain=dtrain,
    num_boost_round=2000,
    nfold=5,
    stratified=True,
    early_stopping_rounds=50,
    seed=42,
)
print("best AUC:", cv["test-auc-mean"].max())
```

---

## 14. 30 秒能答出的「電梯版」回答模板

**Q: What is XGBoost?**
> XGBoost is a scalable gradient boosting library that builds an additive ensemble of decision trees. Its key innovations are (1) a regularized objective with L1/L2 on leaf weights, (2) second-order Taylor approximation for split gain, (3) sparsity-aware split finding for missing values, and (4) histogram-based parallel split finding for speed. It's the default choice for tabular data and dominated Kaggle for years.

**Q: How do you tune it?**
> I fix `learning_rate=0.1` with early stopping to auto-pick `n_estimators`, then tune `max_depth` and `min_child_weight` first (biggest effect), then `gamma`, then subsampling (`subsample`, `colsample_bytree`), then L1/L2. Finally I lower `learning_rate` to ~0.03 and retrain for the final model. I use Optuna with ~50 trials and stratified 5-fold CV.

**Q: XGBoost vs LightGBM?**
> Same algorithm family (GBDT), different tree-growing strategies: XGBoost grows **level-wise**, LightGBM grows **leaf-wise** which is faster but overfits on small data. LightGBM also has GOSS (gradient-based sampling) and EFB (feature bundling) for speed. LightGBM typically wins on large data; XGBoost is more robust on small data and has a more mature ecosystem. In competitions I'd train both and ensemble them.

---

## 15. 必讀原始資料

- **Chen & Guestrin (2016)** — *XGBoost: A Scalable Tree Boosting System*, KDD — [KDD paper](https://www.kdd.org/kdd2016/papers/files/rfp0697-chenAemb.pdf)
- **Chen & He (2014)** — *Higgs Boson Discovery with Boosted Trees*, JMLR W&CP 42
- **Ke et al. (2017)** — *LightGBM: A Highly Efficient Gradient Boosting Decision Tree*, NIPS
- **Prokhorenkova et al. (2018)** — *CatBoost: unbiased boosting with categorical features*, NeurIPS
- XGBoost docs: https://xgboost.readthedocs.io/en/stable/

---

## 最後一分鐘複習清單 ✅

- [ ] 能寫出 split gain 公式
- [ ] 能解釋 `max_depth` vs `num_leaves` 的差別
- [ ] 能說出 XGBClassifier vs XGBRFClassifier
- [ ] 能比較 XGBoost / LightGBM / CatBoost 三大差別
- [ ] 能說出調參順序口訣
- [ ] 能列出 5 個以上過擬合對策
- [ ] 能解釋 sparsity-aware split（缺失值處理）
- [ ] 知道 `scale_pos_weight` 怎麼算
- [ ] 知道 SHAP 和 permutation importance
- [ ] 知道何時 **不要** 用 XGBoost

Good luck! 🍀
