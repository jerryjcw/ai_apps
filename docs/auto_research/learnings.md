# Research Ideation Learnings: Human-Agent Iterative Refinement

本文件記錄從 output_zh.md 的迭代改進過程中學到的經驗，涵蓋：(1) 使用者的研究品味與評判標準，(2) 如何透過人機互動將初稿級 idea 提升為成熟研究方案。

---

## 一、使用者的研究評判標準與 Judge 習慣

### 1.1 對「真正理解」的要求

使用者不會接受表面的描述。會直接追問核心機制的具體運作方式：
- 「greedy submodular maximization 具體到底是什麼，要怎麼做？」
- 不滿足於「用 gradient alignment 做 credit」的抽象描述，要求解釋到可以實作的程度。

**啟示：** 研究方案的每個技術元素都必須能被 unpack 到「一個工程師看了可以直接寫 code」的粒度。模糊的技術描述會被立即質疑。

### 1.2 跨領域類比思維

使用者善於從其他領域找到類比，並用類比來檢驗 idea 的深度：
- 「這是不是有點像 recommender system 裡面的 MMR？」
- 「這不就是跑個 Naive Bayes 在 trajectory 上嗎？」

**啟示：**
- 類比是雙刃劍：若 idea 能被一句話歸約到已知方法（如 NB、MMR），說明 novelty 不夠深，需要找到超越類比的地方。
- 但類比也是靈感來源：使用者主動問「RecSys 領域有沒有類似做法可以借鑑」，這開啟了大量有價值的改進。
- 好的 idea 應該能回答：「跟 X 很像，但在 Y 方面有根本不同，因為 Z。」

### 1.3 反事實壓力測試

使用者會立即想到方法的 failure case 並提出質疑：
- 「假設某步驟用到了 (a+b)² = a²+2ab+b²，結果多數 trajectory 失敗了，這就代表這公式爛了沒用了嗎？」
- 「還是說只是這個公式因為前面的地方爛了，所以被誤用了。」

**啟示：** 使用者的 judge 習慣是找具體的反例來攻擊假設。好的研究方案必須：
1. 預見到 reviewer 會想到的 failure case
2. 在方法設計中直接 address 這些 case（而非只在 limitation section 提一句）
3. 將 failure case 轉化為創新點（如 causal discrimination 直接從 spurious correlation 的質疑中誕生）

### 1.4 對 Cross-over / 統一性 claim 的高標準

使用者不接受表面的 cross-over：
- 「IDEA 5 是如何 align 了 Topic 4？Topic 4 不是在找最不一樣的 trajectory 嗎？」

**啟示：** 若 claim 兩個 topic 的 cross-over，必須有 **actionable mechanism** 讓兩邊互相影響，而非只是「共享數學工具」。觀察性的 duality（「alignment 高時 exploration 也高效」）不算 cross-over。Closed-loop feedback 才算。

### 1.5 對理論合理性的直覺式質疑

使用者會直接質疑基本假設的合理性：
- 「你每個 batch 只 compute 出一個 direction 嗎？」
- 「用所有對的 solution 的 token gradient mean 作為正確的方向合理嗎？」

**啟示：** 使用者期望 agent 能：
1. 誠實回答「合理 / 不合理」，而非迴避
2. 若不合理，提出 **可推導的** 替代方案，附上理論依據
3. 不要提出 agent 自己無法 justify 的方法

### 1.6 評判標準總結

| 維度 | 使用者的判斷方式 |
|---|---|
| **Novelty** | 「這跟 X 有什麼不同？」若能被一句話歸約到已知方法 → novelty 不夠 |
| **Soundness** | 找具體反例攻擊核心假設。能不能 survive 反事實壓力測試？ |
| **Depth** | 不接受單層方法。期望看到 spectrum / framework（如 Level 1-4），每層回答一個科學問題 |
| **Cross-over 真實性** | 必須有 closed-loop feedback，不能只是「借用工具」 |
| **Practicality** | 「能不能跨 batch？」「overhead 多少？」直接關心可行性 |
| **理論一致性** | 假設必須可推導、不能 circular。若有 circularity 要承認並修正 |

---

## 二、迭代改進的模式與方法

### 2.1 改進的五個階段

從本次互動中觀察到一個自然的迭代模式：

```
Stage 1: 理解核心機制（使用者要求解釋 greedy submodular maximization）
    ↓
Stage 2: 跨領域類比（「像不像 MMR？」→ 引入 RecSys 文獻）
    ↓
Stage 3: 借鑑與整合（從 EDER, GIST, FlexSubNet 等借鑑技術改進原方案）
    ↓
Stage 4: 反事實攻擊（「公式被誤 penalize 怎麼辦？」→ 發現 spurious discrimination）
    ↓
Stage 5: 基本假設質疑（「一個 direction 夠嗎？」「mean 合理嗎？」→ 重新設計核心機制）
```

每個 stage 都比前一個更深：從理解 → 類比 → 借鑑 → 攻擊 → 重構。

### 2.2 「簡單 heuristic → multi-level framework」的升級路徑

本次互動中最成功的改進模式：

**IDEA 4 的升級路徑：**
1. 原始：frequency-ratio scoring（~NB log-likelihood ratio）
2. 使用者質疑：「這不就是 Naive Bayes？」
3. Agent 承認並分析 NB 的限制（independence assumption、small-K sparsity、surface-level matching）
4. 提出 multi-level framework（NB → Bayesian累積 → Classifier → Representation probing）
5. 使用者提出反例（correct formula wrongly penalized）
6. 從反例中誕生創新點（causal discrimination、temporal discrimination、difficulty-aware calibration）

**學到的 pattern：**
- 不要 defend 原始方法，而是 **承認它是 baseline，然後系統性地去除它的限制**
- 每去除一個限制 = 一個新的 Level
- 每個 Level 的 ablation 回答一個科學問題 → paper 的 scientific contribution 自然浮現
- 反例不是威脅，是創新點的來源

### 2.3 「觀察性 claim → actionable mechanism」的升級路徑

**IDEA 5 的 cross-over 升級：**
1. 原始：「alignment-based credit 自然橋接 exploration 和 credit」（觀察性）
2. 使用者質疑：「Topic 4 不是在找最不一樣的 trajectory 嗎？你哪裡改善了 exploration？」
3. Agent 承認 cross-over claim 太弱
4. 提出 closed-loop feedback（Level E）：alignment statistics → exploration hyperparameter adjustment
5. Cross-over 從「共享數學工具」升級為「genuine closed loop」

**學到的 pattern：**
- 「X 和 Y 可以被統一」是 claim，不是 contribution
- Contribution 需要 actionable mechanism：X 的輸出改善 Y 的輸入
- 若找不到 actionable mechanism → 誠實降級 claim，不要硬撐

### 2.4 Circularity 檢測

**IDEA 5 的 direction estimation：**
1. 原始：d* = mean(correct token gradients)，用 uniform weighting
2. 使用者問：「這合理嗎？」
3. Agent 發現 circularity：用 uniform weighting 算方向 → 用方向算 non-uniform credit → 但 uniform weighting 正是要替換的東西
4. 提出三種解法：advantage-weighted contrastive（不 circular）、EM-style iterative（自我修正）、validation gradient（ground truth）

**學到的 pattern：**
- 檢查任何 bootstrap 估計的 circularity：「估計 X 需要 Y，但 Y 正是 X 的目標」
- 承認 circularity 並提出解法，比隱藏問題更能贏得信任
- 最好的解法往往是「用不同層次的已知資訊」（如用 sequence-level advantage 估計方向 → 用方向算 token-level credit，兩個層次不同所以不 circular）

---

## 三、Agent 端的操作建議

### 3.1 文獻搜索的時機與策略

- **時機：** 使用者提出跨領域類比時（「像不像 RecSys 的 MMR？」），立即搜索該領域的最新進展
- **策略：** 搜索時要 broad — 不只搜相同方法（DPP），也搜相同 problem（diversity in selection）的不同解法（streaming、learned function、adaptive kernel）
- **整合方式：** 不是簡單列出 paper，而是分析每篇可以 **借鑑什麼具體技術** 來改進當前方案

### 3.2 誠實承認弱點

本次互動中，agent 的誠實承認多次推動了改進：
- 「對，這就是 Naive Bayes」→ 引出 multi-level framework
- 「你說得對，cross-over claim 很弱」→ 引出 feedback loop
- 「部分合理，但有根本性弱點」→ 引出 circularity 分析

**原則：** 承認弱點 + 提出解法 > 為弱點辯護

### 3.3 分段更新大文件

- 對大型設計文件（如 output_zh.md）的更新，應 **逐 section 進行**，讓使用者能逐步 review
- 每次 edit 的範圍應足夠小以便 review，但足夠大以保持 coherence
- 更新完後用表格總結改了什麼

### 3.4 從質疑中提取創新點

使用者的每個質疑都可能是一個創新點：

| 使用者質疑 | 提取出的創新點 |
|---|---|
| 「這不就是 NB？」 | Multi-level discrimination framework（從 NB 出發系統性去除限制） |
| 「能不能跨 batch？」 | Hierarchical Bayesian 跨 batch 累積 |
| 「correct formula 被誤 penalize 怎麼辦？」 | Causal discrimination（conditioning on prefix context） |
| 「一個 direction 夠嗎？」 | Multi-dimensional beneficial subspace + per-path clustering |
| 「mean 合理嗎？」 | Advantage-weighted contrastive + EM-style iterative refinement |
| 「哪裡改善了 exploration？」 | Closed-loop feedback mechanism（Level E） |

---

## 四、可復用的研究方案改進 Checklist

基於本次互動，提煉出可復用的 checklist：

### 4.1 初稿檢查
- [ ] 核心方法能被 unpack 到可實作的程度嗎？
- [ ] 能用一句話歸約到已知方法嗎？若能 → novelty 需加深
- [ ] 基本假設是否 circular？
- [ ] Cross-over / 統一性 claim 是否有 actionable mechanism 支撐？

### 4.2 壓力測試
- [ ] 找到 3 個具體的反事實 failure case
- [ ] 每個 failure case 是否在方法設計中被 address（而非只在 limitation 提及）？
- [ ] 最弱的假設是什麼？去掉它方法還能 work 嗎？

### 4.3 深度擴展
- [ ] 能否將 single method 擴展為 multi-level framework？（每個 level 去除一個限制）
- [ ] 有沒有相關領域的最新技術可以借鑑？
- [ ] 跨 batch / 跨問題 / 跨 training stage 的 generalization 如何？
- [ ] 每個 level 的 ablation 是否回答一個獨立的科學問題？

### 4.4 理論一致性
- [ ] 方向估計 / 信號估計是否 circular？
- [ ] 近似（如 last-layer gradient）的 gap 是否被量化？
- [ ] 理論保證（如近似比）是否適用於實際使用場景？
