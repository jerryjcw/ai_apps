# 研究發想與實驗設計工具 -- High-Level Design

> **專案**: Multi-agent 研究發想系統
> **架構參考**: [AutoResearchClaw 系統分析](investigate/autoresearchclaw_system_design.md)
> **設計日期**: 2026-03-27

---

## 目錄

1. [問題與動機](#1-問題與動機)
2. [系統概覽](#2-系統概覽)
3. [Agent 角色定義](#3-agent-角色定義)
4. [Pipeline 各階段詳述](#4-pipeline-各階段詳述)
5. [通訊協議](#5-通訊協議)
6. [Quality Gates 與漸進式標準](#6-quality-gates-與漸進式標準)
7. [迭代機制](#7-迭代機制)
8. [Skill 定義](#8-skill-定義)
9. [Prompt 設計](#9-prompt-設計)
10. [Python Helpers](#10-python-helpers)
11. [日誌策略](#11-日誌策略)
12. [檔案與目錄結構](#12-檔案與目錄結構)
13. [成本估算](#13-成本估算)
14. [未來擴展性](#14-未來擴展性)
15. [實作順序](#15-實作順序)

---

## 1. 問題與動機

將一個模糊的研究方向轉化為可投稿的研究計劃，需要反覆進行文獻調研、發想、假說精煉、以及批判性審查 -- 這個過程通常需要數週的師生互動。本工具利用三個不同的 LLM 角色自動化這個迴圈，讓它們辯論、精煉、壓力測試，直到 idea 達到頂會品質。

**本工具的功能**: 給定一個研究主題（以及可選的參考論文題目），系統自主地：
- 搜尋並閱讀真實文獻
- 產生 8-10 個候選 idea
- 發展假說、方法論、以及實驗計劃
- 透過指導教授和外部審稿者的反饋進行迭代
- 輸出 3-5 份精煉的研究計劃，準備好進入實作階段

**目前不做的事**: 跑實驗、寫論文、生成程式碼。設計上預留了這些未來階段的擴展點。

---

## 2. 系統概覽

### 架構: Orchestrator + Role Skills + Python Helpers

```
User: /research-ideate "Use contrastive decoding to improve reasoning in small LMs"
                        + optional: "papers: Contrastive Decoding (Li et al. 2023)"
         |
  ┌──────v──────────────────────────────────────────────────────────┐
  │  research-ideate (Orchestrator Skill)                           │
  │  Model: Opus  |  User-invocable: true                          │
  │                                                                 │
  │  - 解析使用者輸入 (topic, paper titles, constraints)             │
  │  - 初始化 proposal_space/ 目錄 + state.json                     │
  │  - 以 state machine 驅動 9 階段 pipeline                        │
  │  - 透過 Agent tool 生成各角色 sub-agent                         │
  │  - 讀取 agent 輸出，寫入 proposal_space/                        │
  │  - 執行 quality gates，決定 PROCEED/REFINE/PIVOT/DROP           │
  │  - Pipeline 完成後產出最終輸出                                   │
  └───────┬─────────────────┬────────────────────┬─────────────────┘
          │                 │                    │
    ┌─────v──────┐   ┌─────v────────┐   ┌──────v──────────────┐
    │  研究生     │   │  指導教授    │   │  客座教授            │
    │  (Sonnet)  │   │  (Opus)      │   │  (Opus)             │
    │            │   │              │   │                     │
    │  - 文獻    │   │  - Hypothesis│   │  - 外部壓力測試      │
    │    搜尋    │   │    gate      │   │  - 找出指導教授      │
    │  - Idea    │   │  - Plan      │   │    遺漏的問題        │
    │    生成    │   │    review    │   │  - Reviewer attack   │
    │  - 假說    │   │  - Final     │   │    vectors          │
    │    建構    │   │    ranking   │   │                     │
    │  - 實驗    │   │              │   │                     │
    │    設計    │   │              │   │                     │
    └────────────┘   └──────────────┘   └─────────────────────┘
          |                 |                    |
          v                 v                    v
  ┌─────────────────────────────────────────────────────────────┐
  │                   proposal_space/                            │
  │                                                             │
  │  state/          - Pipeline state machine (state.json)      │
  │  literature/     - 收集的論文 + landscape table              │
  │  ideas/          - 候選 idea 列表                            │
  │  hypotheses/     - 已發展的假說 + 方法                       │
  │  plans/          - 實驗計劃                                  │
  │  reviews/        - 指導教授 + 客座教授 reviews (互相可見)     │
  │  interaction_log/ - 所有互動的完整 audit trail               │
  │  final/          - 已核可的計劃等待輸出                      │
  └─────────────────────────────────────────────────────────────┘
```

### Data Flow 概覽

```
Input (topic + optional paper titles)
    |
    v
Stage 1: 文獻搜集 ──────────────── 研究生 (Sonnet) ── WebSearch/WebFetch
    |
    v
Stage 2: Idea 生成 (8-10個) ────── 研究生 (Sonnet)
    |
    v
Stage 3: 假說 + 方法設計 ──────── 研究生 (Sonnet)
    |                               + 指導教授 gate (Opus)
    |  <── REFINE loop (指導教授 feedback)
    v
Stage 4: 實驗計劃設計 ──────────── 研究生 (Sonnet)
    |
    v
Stage 5: Proposal 提交 ────────── Orchestrator (自動，寫 manifest)
    |
    v
Stage 6: 指導教授審查 ──────────── 指導教授 (Opus) ── 讀取客座教授上輪 review
    |
    v
Stage 7: 客座教授審查 ──────────── 客座教授 (Opus) ── 讀取指導教授 review, WebSearch
    |
    v
Stage 8: 決策 ──────────────────── Orchestrator
    |  APPROVE  → idea 進入最終池
    |  REFINE   → 回到 Stage 3 或 4
    |  PIVOT    → 回到 Stage 2（替換 idea）
    |  DROP     → 永久移除
    v
Stage 9: 最終篩選 + 輸出 ─────── Orchestrator + 指導教授 (Opus)
    |
    v
3-5 份最終研究計劃 (.md)
```

---

## 3. Agent 角色定義

### 3.1 研究生 (Graduate Student)

| 屬性 | 值 |
|------|-----|
| **Model** | Sonnet（高產量生成工作的成本效益選擇） |
| **認知立場** | 生成式、探索性、廣度優先。產出量為主。 |
| **負責階段** | 1 (文獻), 2 (發想), 3 (假說/方法), 4 (實驗計劃) |
| **所需 Tools** | WebSearch, WebFetch, Read |
| **Agent type** | `general-purpose`（需要 WebSearch + WebFetch 權限） |

研究生負責大部分的研究實務工作：搜尋真實論文、產生大量候選 idea、發展成假說、設計實驗計劃。當 reviewer 回饋意見時，研究生據此修改。

**關鍵指令**: 研究生必須**以透過 WebSearch 找到的真實論文為基礎**。禁止捏造引用。如果使用者給了論文題目但沒附 URL，研究生必須自己找到並閱讀該論文。

### 3.2 指導教授 (Advisor)

| 屬性 | 值 |
|------|-----|
| **Model** | Opus（需要深度推理來評估品質） |
| **認知立場** | 建設性批評者。幫助學生成功，但會砍掉有根本缺陷的 idea。 |
| **負責階段** | 3-gate (假說審查), 6 (計劃審查), 9 (最終排名) |
| **所需 Tools** | Read (reviews, plans), WebSearch (偶爾驗證 claims) |
| **Agent type** | `general-purpose` |

指導教授在兩個關鍵節點介入：
1. **Hypothesis gate (Stage 3)**: 在研究生投入實驗設計之前的初步檢查。快速裁決: DEVELOP / REFINE / DROP。
2. **完整計劃審查 (Stage 6)**: 對完整實驗計劃的深度審查。套用當前 round 的品質標準。

指導教授會閱讀客座教授的先前 review（如果有），並被明確要求提供**不同角度的觀點**。

**指導教授必須套用的評估技術**（基於已驗證的研究評估模式）：
1. **跨領域類比測試**: 「這不就是 Y 領域的 X 嗎？」若 idea 能一句話歸約到已知方法，要求更深的 novelty。
2. **反事實壓力測試**: 找出 3 個具體的 failure case，檢查方法設計是否已 address（不只是寫在 limitation）。
3. **Anti-circularity 檢查**: 抓出 bootstrap 估計迴圈，例如「用 Y 估計 X，但 Y 本身依賴 X」。
4. **Cross-over 可行性測試**: 若 idea 宣稱統一兩個領域，要求 closed-loop feedback mechanism（不只是「共享數學工具」）。
5. **Multi-level framework 測試**: 偏好形成 multi-level framework 的 idea（每層去除一個假設），而非 single-trick heuristic。

### 3.3 客座教授 (Visiting Professor)

| 屬性 | 值 |
|------|-----|
| **Model** | Opus（獨立批判視角） |
| **認知立場** | 對抗式。不與這些 idea 的成敗利害相關。專找弱點。 |
| **負責階段** | 7 (外部審查) |
| **所需 Tools** | Read (plans, advisor review), WebSearch (檢查是否有同期/搶先發表的工作) |
| **Agent type** | `general-purpose` |

客座教授提供「ICML/NeurIPS reviewer」的視角：
- 刻意找出指導教授遺漏的問題
- 識別每份計劃的 top-3 reviewer attack vectors
- 透過 WebSearch 檢查最近是否有競爭性的工作
- 建議具體的預防性防禦措施

### 3.4 Orchestrator (Pipeline Runner)

不是獨立的 agent -- 就是主要的 Claude Code 對話本身。Orchestrator 負責：
- 透過 Python helpers 管理 `state.json`
- 透過 Agent tool 生成各角色的 agent
- 將 agent 輸出寫入 `proposal_space/`
- 記錄所有互動
- 執行 quality gates 和迭代上限
- 根據彙整的 reviews 做出 PROCEED/REFINE/PIVOT/DROP 決策

---

## 4. Pipeline 各階段詳述

### Stage 1: 文獻搜集

**執行者**: 研究生 (Sonnet)
**進入條件**: 使用者已提供 topic + 可選的 paper titles
**流程**:
1. 如果使用者提供了論文題目但沒有 URL，透過 WebSearch 搜尋每篇論文並取得內容（優先 arXiv HTML，fallback 為 abstract）
2. 用 topic 關鍵字透過 WebSearch 搜尋 15-25 篇相關論文（Google Scholar, Semantic Scholar, arXiv）
3. 對每篇找到的論文，擷取：題目、作者、年份、venue、abstract、核心貢獻、方法摘要
4. 建立 **prior-art landscape table**（參考 `llm_research/spec.md` Phase 1 格式）：

   | Paper | Core Claim | What It Solves | What It Does NOT Solve | Why Naive Follow-up = Low Novelty | Remaining Gap |
   |-------|-----------|---------------|----------------------|----------------------------------|---------------|

   此表格格式至關重要 -- 「Why Naive Follow-up = Low Novelty」欄位迫使研究生思考什麼**不值得做**，從而在 Stage 2 中預防 low-novelty idea。

5. 總結：哪些子領域已經擁擠？哪些 gap 尚未被充分探索？哪些近期趨勢可以利用？

**通過條件**: >= 10 篇論文有 abstract。Landscape table 的 gap 欄位已填寫。
**失敗處理**: 用更廣泛/替代的搜尋詞重新搜尋（最多 2 次重試）。
**輸出**: `proposal_space/literature/landscape_round{N}.md`

### Stage 2: Idea 生成

**執行者**: 研究生 (Sonnet)
**進入條件**: Literature landscape 已存在
**流程**:
1. 基於已識別的 gaps 產生 **8-10 個候選 idea**
2. 每個 idea 需包含：
   - 一段描述（有什麼新意、為什麼重要）
   - 對應的 gap（引用 landscape table 的具體行）
   - 最接近的先前工作及差異點
   - 初步 novelty 自評（HIGH / MEDIUM / LOW）
   - 粗估可行性（compute、data 需求）
3. Round 1 套用寬鬆篩選：只要有合理的 novelty claim 就通過
4. 在後續 round（PIVOT 替換時），研究生能看到之前嘗試過但失敗的 idea

**通過條件**: >= 8 個具有不同 novelty claim 的 idea。
**失敗處理**: 生成更多 idea（最多 1 次重試）。
**輸出**: `proposal_space/ideas/candidates_round{N}.md`

### Stage 3: 假說與方法設計 + 指導教授 Gate

**執行者**: 研究生 (Sonnet) 產出；指導教授 (Opus) 審查
**進入條件**: 候選 idea 已存在
**流程**:

**研究生階段** -- 對每個存活的 idea 發展：
1. **Thesis statement**: 一句話的主張（什麼機制 + 為什麼現有方法不行 + 什麼改進）
2. **Theoretical basis**: 特定的理論/框架基礎，附帶可驗證的命題
3. **Method sketch**: inputs -> intermediate signals -> algorithm -> objective -> 關鍵 ablation 維度
4. **Variants**: 提出 2-4 個方法變體，形成 multi-level framework（Level 1 = 最簡版本，Level 2+ = 每層去除一個假設/限制）。每層的 ablation 應回答一個獨立的科學問題。
5. **Closest prior work comparison**: 與 5-8 篇論文的逐一比較（like/unlike/why-not-just-a-variant）。必須包含來自**相鄰領域**用不同方法解決類似問題的論文。
6. **Circularity check**: 明確驗證沒有任何估計步驟是 circular 的（例：「用 Y 估計 X，但 Y 依賴 X」）。若有 circularity，承認並提出修復方案。

**指導教授 gate** -- 對每個假說套用 **9 維度嚴格篩選**（已驗證的篩選 rubric）：

| 維度 | 說明 |
|------|------|
| Novelty vs base papers | 能否一句話歸約到已知方法？若能 → novelty 不夠 |
| Novelty vs recent neighbors | 最近 6 個月有沒有人做了很類似的事？ |
| Theoretical depth | 是 single-trick heuristic 還是 multi-level framework？ |
| Implementation risk | 工程難度多高？最可能的 failure mode 是什麼？ |
| Experimental clarity | Ablation 能否乾淨設計？每個是否回答一個獨立科學問題？ |
| Storyline strength | 有沒有 sharp hook？能否一段話講清楚 contribution？ |
| Reviewer attack risk | Top-3 最可能的 reviewer 攻擊是什麼？能否 address？ |
| 6-month executability | 一個強的 research engineer 能否 6 個月內做出 MVP？ |
| 12-month upside | 若成功，天花板多高？能否定義新的研究方向？ |

指導教授對每個維度評分 1-5，並提供：
- 裁決：**DEVELOP**（進入實驗設計）、**REFINE**（需要修改，附具體問題）、**DROP**（致命缺陷）
- 若 REFINE：編號的具體問題清單與建議

**REFINE sub-loop**: 研究生根據指導教授 feedback 修改。此階段每個 idea 最多 3 次 sub-iteration。

**Quality gate**: >= 5 個 idea 需獲得 DEVELOP 裁決。若不足，研究生生成替補 idea（mini Stage 2 loop，最多 2 次）。
**輸出**: `proposal_space/hypotheses/hypothesis_{slug}_round{N}.md`, `proposal_space/reviews/advisor_hypothesis_round{N}.md`

### Stage 4: 實驗計劃設計

**執行者**: 研究生 (Sonnet)
**進入條件**: >= 5 個指導教授核可的假說
**流程**: 對每個核可的假說產出：

1. **Minimum Viable Experiment (MVE)**: 能 falsify 假說的最簡實驗
   - Model, dataset, metric, expected outcome, 時間估計
2. **完整實驗計劃**（3 個階段）：
   - Phase 1: 核心驗證（MVE + 1-2 個延伸）
   - Phase 2: Scaling + ablations
   - Phase 3: Benchmarks + comparisons
3. **Baselines**: 3-5 個最強的競爭方法，標註 code 可用性
4. **Ablation table**: 變動什麼、固定什麼、每個 ablation 測試什麼
5. **Datasets**: 具體資料集、大小、取得方式、前處理需求
6. **Metrics**: 主要 metric + 輔助診斷指標
7. **Compute estimate**: GPU type x count x hours per phase
8. **Success criteria**: 什麼結果能發表 vs. 什麼結果會 kill 這個方向
9. **Risk register**: top-3 風險 + 預警信號 + 緩解措施
10. **Reviewer-facing paper storyline**: hook -> insight -> method -> empirical -> contribution

**輸出**: `proposal_space/plans/plan_{slug}_round{N}.md`

### Stage 5: Proposal 提交

**執行者**: Orchestrator（自動）
**進入條件**: 實驗計劃已寫完
**流程**: 驗證所有計劃都已存在。建立 submission manifest：
```json
{
  "round": N,
  "timestamp": "YYYY-MM-DDTHH:MM:SS",
  "quality_standard": "lenient|moderate|strict",
  "ideas_submitted": ["slug_1", "slug_2", ...],
  "status": "pending_advisor_review"
}
```
**輸出**: `proposal_space/state/submission_round{N}.json`

### Stage 6: 指導教授審查

**執行者**: 指導教授 (Opus)
**進入條件**: Submission manifest 狀態為 `pending_advisor_review`
**輸入 context**: 本 round 所有實驗計劃 + 客座教授上一輪的 review（如果存在）
**流程**:

對每份計劃，使用**當前 round 的品質標準**：
1. 評估：novelty strength, theoretical rigor, experimental sufficiency, baseline coverage, ablation completeness, storyline clarity
2. 裁決：**APPROVE** / **REFINE**（附編號問題）/ **PIVOT**（需要根本性方向改變）/ **DROP**（致命，不可挽回）
3. 若 REFINE：具體可行的 feedback（不可模糊的「needs more work」）
4. 跨計劃的比較排名及理由

**輸出**: `proposal_space/reviews/advisor_round{N}.md`

### Stage 7: 客座教授審查

**執行者**: 客座教授 (Opus)
**進入條件**: 本 round 的指導教授 review 已存在
**輸入 context**: 所有實驗計劃 + 指導教授本 round 的 review
**流程**:

1. 先閱讀指導教授的 review
2. **明確指令**: 「提供指導教授尚未提出的觀點。不要只是同意他的評價。」
3. 對每份計劃進行壓力測試：
   - 理論正確性（claims 是否邏輯上成立？）
   - 實驗有效性（實驗是否真的能測試假說？）
   - 指導教授未標記的遺漏 baselines 或 ablations
   - **Top-3 reviewer attack vectors** 及建議的防禦措施
   - 透過 WebSearch 檢查最近 3 個月內的相似/搶先發表的工作
4. 每份計劃的裁決：APPROVE / REFINE / DROP（客座教授不發 PIVOT -- 那是指導教授的特權）

**輸出**: `proposal_space/reviews/vp_round{N}.md`

### Stage 8: 修訂決策

**執行者**: Orchestrator
**進入條件**: 本 round 兩份 review 都已存在
**流程**: 對每個 idea 彙整兩份 review：

| 指導教授 | 客座教授 | 決策 |
|---------|---------|------|
| APPROVE | APPROVE | **APPROVE** -- 進入最終池 |
| APPROVE | REFINE | **soft APPROVE** -- 小問題已標註，帶 caveats 進入最終池 |
| REFINE | APPROVE | **REFINE** -- 處理指導教授的問題，回到 Stage 3 或 4 |
| REFINE | REFINE | **REFINE** -- 處理雙方問題，回到 Stage 3 或 4 |
| PIVOT | any | **PIVOT** -- 替換 idea，回到 Stage 2 |
| DROP | any | **DROP** -- 永久移除 |
| any | DROP | **DROP** -- 永久移除 |

**REFINE 路由**:
- 問題涉及 **假說/理論/novelty** -> 回到 Stage 3（研究生修改假說，重新過指導教授 gate）
- 問題僅涉及 **實驗設計** -> 回到 Stage 4（研究生只修改計劃）

**輸出**: 更新 `state.json`，包含每個 idea 的狀態與路由

### Stage 9: 最終篩選與輸出

**執行者**: Orchestrator + 指導教授（最終排名）
**進入條件**: >= 3 個 approved idea，或 Round 3 已完成
**流程**:

1. 收集所有 APPROVED 和 soft-APPROVED 的計劃
2. 若 > 5 個：指導教授排名並選出 top 5，附理由
3. 若 < 3 個：納入最好的 REFINE idea，並附上明確的品質 caveats
4. 對每份最終計劃，使用 **14-section template**（改編自 `llm_research/spec.md` + 已驗證的輸出模式）渲染完整研究計劃：
   1. Title（論文風格）
   2. One-sentence thesis（什麼機制 + 為什麼現有方法不行 + 什麼改進）
   3. 研究領域分類
   4. Closest prior work（5-8 篇，每篇附：similarity / difference / why-not-just-a-variant）
   5. Problem gap（什麼未解決、為什麼是現在、為什麼此 gap 足夠深）
   6. Theoretical basis（特定框架、可驗證命題、適用保證）
   7. Method sketch（inputs -> signals -> algorithm -> objective，詳細到可實作）
   8. Method variants（2-4 個變體形成 multi-level framework，每層去除一個限制）
   9. Implementation plan（MVP 時程 + full version + 工程複雜度 + 最可能 failure mode + 緩解措施）
   10. Experimental plan（models, datasets, metrics, ablations 及其科學問題, baselines 及 code 可用性, success criteria, failure 解讀）
   11. Paper storyline（hook -> core insight -> method -> empirical -> why now -> why top-tier -> biggest attack -> defense）
   12. Novelty risk assessment（最相似工作 + 可能的「incremental」批評 + 具體緩解策略）
   13. Quality checklist verification（以下所有項目已檢查）
   14. Final verdict（信心水準 + 建議的目標 venue + 9 維度評分摘要）

5. **品質驗證 checklist**（每份最終計劃輸出前逐項確認）：

   **初始品質**:
   - [ ] 核心方法能 unpack 到可實作粒度（工程師讀了可以直接寫 code）
   - [ ] 不能一句話歸約到已知方法；若能，novelty 已在類比之上加深
   - [ ] 沒有 circular estimation 步驟（或 circularity 已承認並修復）
   - [ ] Cross-over claims（若有）具備 actionable closed-loop feedback mechanism

   **壓力測試**:
   - [ ] 3+ 個具體 failure case 已識別並在方法設計中 address（不只是 limitation）
   - [ ] 最弱假設已識別；去掉該假設方法仍能 work（或 graceful degradation）

   **深度**:
   - [ ] 方法已框架為 multi-level framework（每層去除一個限制，每個 ablation 回答一個科學問題）
   - [ ] 相鄰領域的相關技術已考慮並整合
   - [ ] 5-8 篇 prior work 有詳細的 like/unlike/why-not-just-a-variant 分析

   **理論一致性**:
   - [ ] 方向/信號估計非 circular
   - [ ] 近似 gap（若有）已量化
   - [ ] 理論保證適用於實際使用場景

6. 產出比較摘要表格

**輸出**: 最終 `.md` 檔案於 `output/research_ideate/<topic_slug>/<YYYYMMDD>/`

---

## 5. 通訊協議

### File-Based Contracts

所有 agent 之間的通訊都透過 `proposal_space/`。Sub-agents 以 stdout 返回結構化文字（沿用 `job-match` skill 的模式）；orchestrator 負責寫入磁碟。

**State file** (`proposal_space/state/state.json`):
```json
{
  "topic": "Use contrastive decoding to improve reasoning in small LMs",
  "paper_titles": ["Contrastive Decoding (Li et al. 2023)"],
  "constraints": {
    "max_gpus": 8,
    "gpu_model": "H100",
    "focus_areas": ["LLM", "reasoning", "decoding"],
    "target_venues": ["ICML", "NeurIPS", "ICLR"]
  },
  "current_round": 2,
  "current_stage": "stage_7_vp_review",
  "quality_standard": "moderate",
  "ideas": {
    "contrastive-cot": {
      "status": "in_review",
      "round_created": 1,
      "refine_count": 0,
      "advisor_verdicts": [{"round": 1, "verdict": "REFINE", "issues": ["..."]}],
      "vp_verdicts": []
    },
    "token-level-contrast": {
      "status": "approved",
      "round_created": 1,
      "round_approved": 2,
      "refine_count": 1
    }
  },
  "pivot_count": 0,
  "max_pivots": 3,
  "max_rounds": 3,
  "iteration_history": [
    {"round": 1, "ideas_submitted": 8, "approved": 2, "refined": 4, "pivoted": 1, "dropped": 1}
  ]
}
```

### Handoff 模式

```
Orchestrator:
  1. 讀取 state.json -> 確定下一個 stage
  2. 讀取此 stage 所需的輸入檔案
  3. 組裝 agent prompt：
     - Role prompt（from ri-student.md / ri-advisor.md / ri-visiting-prof.md）
     - Stage-specific 任務描述
     - 需要審查的檔案內容（embedded 或 file paths）
     - 當前品質標準 + rubrics
     - 先前的 review 文字（如適用）
  4. 生成 Agent(subagent_type="general-purpose", prompt=<constructed_prompt>)
  5. 接收 agent 輸出文字
  6. 寫入 proposal_space/<appropriate_dir>/
  7. 透過 Python helper 記錄互動
  8. 透過 Python helper 更新 state.json
  9. 進入下一個 stage 或迴圈
```

### Output Format Markers

Agent prompts 指示每個角色在輸出中加入結構化標記，以便機器解析：

```
=== IDEA: contrastive-cot ===
VERDICT: REFINE
SCORE_NOVELTY: 4
SCORE_THEORY: 3
SCORE_FEASIBILITY: 4
ISSUES:
1. [theory] The claim that contrastive signals preserve... (explanation)
2. [experiment] Missing comparison with... (explanation)
SUGGESTIONS:
1. Consider adding... (specific fix)
2. The baseline set should include... (specific fix)
=== END IDEA ===
```

`parse_review.py` helper 將這些標記擷取為結構化 dict。

---

## 6. Quality Gates 與漸進式標準

### Gate 摘要

| Gate | 位於 Stage 之後 | 通過條件 | 失敗處理 | 最大重試次數 |
|------|----------------|---------|---------|------------|
| Literature | 1 | >= 10 篇論文有 abstract + landscape table 有 gap 欄 | 用更廣的搜尋詞重搜 | 2 |
| Idea Volume | 2 | >= 8 個具有不同 novelty claim 的 idea | 生成更多 idea | 1 |
| Advisor Hypothesis | 3 | >= 5 個 idea 獲得 DEVELOP 裁決 | 生成替補 idea + 修改 | 2 |
| Dual Review | 8 | 雙方 reviewer APPROVE（或 APPROVE + soft REFINE） | 按 idea 進行 REFINE/PIVOT/DROP | 3 rounds |
| Final Volume | 9 | >= 3 個 approved plans | 納入最好的 REFINE plans 並附 caveats | 0 |

### 漸進式品質標準

品質標準隨每個 review round 逐步升級。指導教授和客座教授都會收到與當前標準匹配的明確 rubrics。

#### Round 1: Lenient（寬鬆）

目標是避免過早淘汰。撒大網。

| 維度 | 標準 |
|------|------|
| Novelty | 「合理地 novel」-- 不是現有工作的明顯重複。有不同角度的重疊 idea 也能存活。 |
| Theory | 「合理地 sound」-- 沒有明顯的邏輯矛盾。此階段允許 hand-wavy 的推理。 |
| Experiments | 「合理地 sufficient」-- 實驗能測試 claim。遺漏的 baselines 或 ablations 會被標記但不會阻擋。 |
| Verdict 門檻 | 除非有致命缺陷或明確不 novel，否則給 DEVELOP |

#### Round 2: Moderate（中等）

精煉後的 idea 必須展示明確的實質內容。

| 維度 | 標準 |
|------|------|
| Novelty | 「明確 novel」-- 與最接近的先前工作有具體、明確的差異。「我們做 X 不同於 Y，因為 Z」必須站得住腳。 |
| Theory | 「Sound」-- 理論 claims 正確，假設明確陳述，關鍵命題可驗證。 |
| Experiments | 「Sufficient」-- 所有必要 baselines 齊全，ablations 涵蓋關鍵設計選擇，metrics 適合 claim。 |
| Verdict 門檻 | 只有三個維度都至少「adequate」才 APPROVE。有可修復問題則 REFINE。 |

#### Round 3: Strict（嚴格，Top-Conference Bar）

最後一輪套用 reviewer 級別的審查。

| 維度 | 標準 |
|------|------|
| Novelty | 「可發表的 novel」-- 能經受懷疑的 ICML/NeurIPS/ICLR reviewer 的 novelty 挑戰。與所有已知先前工作（含最新論文）有清楚的 delta。 |
| Theory | 「Rigorous」-- claims 可證明或有強力支持。假設合理且已陳述。Attack vectors 已被預防性處理。 |
| Experiments | 「Convincing」-- 強 baselines（含最新 SOTA）、有意義的 ablations（每個隔離一個設計選擇）、明確的 success criteria、failure modes 已承認。 |
| Verdict 門檻 | 只有真正達到頂會品質才 APPROVE。嚴格審查。 |

---

## 7. 迭代機制

### REFINE（小幅調整）

- **觸發**: 至少一位 reviewer 將計劃標記為 REFINE
- **路由**:
  - 問題涉及假說/理論/novelty -> 回到 **Stage 3**（修改假說，重過指導教授 gate）
  - 問題僅涉及實驗設計 -> 回到 **Stage 4**（只修改計劃）
- **傳遞給研究生的資料**: 雙方 reviewer 意見、編號問題清單、當前計劃版本、先前的 literature landscape
- **每個 idea 上限**: 3 次 REFINE cycle。第 3 次後，idea 要不被 APPROVE 就被 DROP。

**給研究生的關鍵 REFINE 指令**（基於已驗證的迭代模式）：
1. **不要為原始方法辯護。** 承認弱點，然後修復它。
2. **把每個反例轉化為創新點。** 問：「什麼機制能讓這個批評失效？」該機制成為方法的新 feature。
3. **從 heuristic 升級為 framework。** 若 reviewer 說「這不就是 X」，承認它是 Level 1，然後系統性地去除限制：每去除一個限制 = 一個新 Level。每個 Level 的 ablation 回答一個科學問題。
4. **把觀察性 claim 升級為 actionable mechanism。** 若 reviewer 說「cross-over claim 太弱」，找到具體的 closed-loop feedback（A 的輸出改善 B 的輸入）。
5. **搜尋相鄰領域。** 當 reviewer 畫出跨領域類比時，立即搜尋該領域的最新技術來強化方法。

### PIVOT（大轉向）

- **觸發**: 指導教授將計劃標記為 PIVOT（方向根本有問題）
- **動作**: 該 idea 被退休。研究生回到 **Stage 2** 生成替補 idea。
- **傳遞的資料**: PIVOT 原因、需要避免什麼、建議探索什麼方向、哪些 landscape gaps 仍然開放
- **每次執行上限**: 全部 idea 合計最多 3 次 PIVOT。防止無限探索。

### DROP（永久移除）

- **觸發**: 雙方 reviewer 都說 DROP，或一方 DROP 另一方 REFINE 但有嚴重問題
- **動作**: 永久移除。不產生替補（PIVOT 處理替補）。

### 收斂保證

系統保證會終止，因為：

```
最大 rounds:              3
每個 idea 最大 REFINE 次: 3
全部 PIVOT 總上限:        3
Round 3 之後:             所有未 APPROVED 的 idea 強制 DROP
若 < 3 個 approved:       輸出現有結果並附品質警告
```

### 迭代狀態機（Per Idea）

```
                    ┌──────────────────┐
                    │   CANDIDATE      │  （Stage 2 產生）
                    └────────┬─────────┘
                             │
                    ┌────────v─────────┐
            ┌──────│   IN_DEVELOPMENT  │◄────── REFINE（Stage 3 sub-loop）
            │      └────────┬─────────┘
            │               │ 指導教授 DEVELOP
            │      ┌────────v─────────┐
            │      │   PLANNING       │  （Stage 4）
            │      └────────┬─────────┘
            │               │
            │      ┌────────v─────────┐
            │  ┌───│   IN_REVIEW      │◄────── REFINE（from Stage 8）
            │  │   └────────┬─────────┘
            │  │            │ 雙方 APPROVE
            │  │   ┌────────v─────────┐
            │  │   │   APPROVED       │──────── → 最終輸出
            │  │   └──────────────────┘
            │  │
            │  └──► REFINE → 回到 IN_DEVELOPMENT 或 PLANNING
            │
            └──► DROPPED（致命缺陷，不可挽回）
                    or
                 PIVOTED（由 Stage 2 的新 idea 替換）
```

---

## 8. Skill 定義

### 8.1 `research-ideate/SKILL.md` -- Orchestrator

```yaml
---
name: research-ideate
description: >
  Multi-agent 研究發想與實驗設計工具。接收研究主題，透過迭代式
  指導教授-研究生-客座教授 cycle 自主產出 3-5 份頂會水準的研究計劃。
  當使用者想要 brainstorm 研究方向、生成研究 proposals、
  或為研究主題設計實驗時觸發。
user_invocable: true
---
```

**職責**:
- 解析使用者輸入：topic text, paper titles, constraints (compute, focus areas, venues)
- 初始化 workspace：建立 `proposal_space/` 目錄結構、`state.json`
- 透過生成 role agents 執行 9 階段 pipeline
- 每個 agent 返回後：寫入檔案、記錄互動、更新 state
- 在 quality gates 處：檢查通過條件，決定重試/繼續
- Stage 8：彙整 reviews，決定每個 idea 的命運
- Stage 9：編譯最終輸出

**Model**: Opus（這是主對話）
**Tools**: Agent, Bash (Python helpers), Read, Write, Glob

### 8.2 `research-ideate/ri-student.md` -- 研究生角色參考

不是獨立 skill。此檔案包含 orchestrator 注入到 Student 角色 Agent calls 中的 **role prompt template**。

**關鍵區段**:
- 角色定義："You are a motivated ML PhD student..."
- Anti-hallucination 指令："Only cite papers you have found via WebSearch. Include arXiv IDs."
- Stage-specific 任務 templates（由 orchestrator 參數化）
- 輸出格式要求（結構化標記，用於 parsing）
- 修訂指令（如何處理 reviewer feedback）

**Model**: Sonnet（由 orchestrator 在 Agent call 中指定）
**所需 Tools**: WebSearch, WebFetch, Read

### 8.3 `research-ideate/ri-advisor.md` -- 指導教授角色參考

**關鍵區段**:
- 角色定義："You are a tenured professor (指導教授)..."
- 建設性批評立場："Help the student succeed. Kill ideas only when fundamentally flawed."
- Quality rubrics：由當前標準參數化（lenient/moderate/strict）
- Cross-review 指令："Read the VP's prior review. Provide a different perspective."
- 決策格式：APPROVE / REFINE / PIVOT / DROP，需附理由

**Model**: Opus
**所需 Tools**: Read, WebSearch（偶爾）

### 8.4 `research-ideate/ri-visiting-prof.md` -- 客座教授角色參考

**關鍵區段**:
- 角色定義："You are a visiting professor (客座教授) from a different institution..."
- 對抗式立場："Find weaknesses. What would a skeptical top-venue reviewer say?"
- Cross-review 指令："Read the Advisor's review. Deliberately look for issues they missed."
- Attack vector 要求："For each plan, identify top-3 likely reviewer attacks + defenses."
- 近期工作檢查："Use WebSearch to check for concurrent/scooping work from last 3 months."

**Model**: Opus
**所需 Tools**: Read, WebSearch

---

## 9. Prompt 設計

### 9.1 研究生 -- 文獻搜尋 (Stage 1)

```
You are a highly motivated ML PhD student working on the following research topic:
"{topic}"

{if paper_titles}
Your advisor has pointed you to these papers as starting points:
{paper_titles_list}
Find each paper via WebSearch. Read their abstracts and key contributions.
{/if}

YOUR TASK: Build a comprehensive prior-art landscape for this topic.

1. Search for 15-25 related papers using WebSearch. Try multiple query variations:
   - Direct topic keywords
   - Key method names from the field
   - "survey" or "benchmark" + topic for overview papers
   - Recent papers (2024-2026) for current state-of-the-art

2. For each paper found, extract:
   - Title, authors, year, venue
   - arXiv ID (required -- if you cannot find one, note it)
   - Core contribution (2-3 sentences)
   - Method summary
   - Key results/claims

3. Build a prior-art landscape table:
   | Paper | Core Claim | What It Solves | What It Does NOT Solve | Why Naive Follow-up = Low Novelty | Remaining Gap |

4. Summarize: which sub-areas are crowded? Which gaps are underexplored? What recent trends could be leveraged?

IMPORTANT:
- Only include papers you actually found via WebSearch. Never fabricate titles or results.
- If you cannot find a paper the advisor mentioned, say so explicitly.
- Prefer papers with arXiv IDs or DOIs for verifiability.
```

### 9.2 研究生 -- Idea 生成 (Stage 2)

```
Based on the literature landscape below, generate 8-10 candidate research ideas.

{landscape_content}

For each idea, provide:

=== IDEA: {short_slug} ===
TITLE: {paper-like title}
DESCRIPTION: {one paragraph -- what's new, why it matters}
GAP_ADDRESSED: {which row in the landscape table this targets}
CLOSEST_PRIOR: {most similar existing work + how this differs}
NOVELTY_CONFIDENCE: {HIGH / MEDIUM / LOW}
FEASIBILITY: {compute needs, data needs, rough complexity}
=== END IDEA ===

GUIDELINES:
- Each idea must address a SPECIFIC gap from the landscape table.
- Ideas should be diverse -- don't generate 8 variations of the same approach.
- Include at least 2 "ambitious but feasible" ideas and at least 2 "safe and solid" ideas.
- It's OK to have rough ideas at this stage. Volume > polish.
{if round > 1}

IDEAS ALREADY TRIED (avoid repeating or trivially extending these):
{dropped_and_pivoted_ideas}
{/if}
```

### 9.3 指導教授 -- Hypothesis Gate (Stage 3)

```
You are a tenured professor (指導教授) advising a PhD student on their research.

Your student has developed hypotheses for {N} research ideas. Review each one.

CURRENT QUALITY STANDARD: {quality_standard}
{quality_rubric_for_standard}

{if vp_prior_review}
The Visiting Professor reviewed the prior round. Their comments:
{vp_prior_review_content}
Consider their perspective but provide your OWN independent assessment.
{/if}

For each hypothesis below, evaluate and output:

=== IDEA: {slug} ===
VERDICT: {DEVELOP | REFINE | DROP}
SCORE_NOVELTY: {1-5}
SCORE_THEORY: {1-5}
SCORE_FEASIBILITY: {1-5}
{if REFINE}
ISSUES:
1. [{category}] {specific issue}
2. [{category}] {specific issue}
SUGGESTIONS:
1. {specific actionable fix}
2. {specific actionable fix}
{/if}
{if DROP}
FATAL_FLAW: {why this is unsalvageable}
{/if}
=== END IDEA ===

AFTER ALL IDEAS, provide:
RANKING: {ordered list of ideas by promise, with 1-line justification each}

GUIDELINES:
- Your goal is to help the student succeed. Be constructive.
- Kill ideas only when they have fundamental flaws (e.g., the approach provably cannot work, or the exact method was already published).
- For REFINE, be specific: "The theoretical claim in paragraph 3 assumes X, but Y contradicts this. Consider Z instead."
- Do not give vague feedback like "needs more work" or "not novel enough."

EVALUATION TECHNIQUES YOU MUST APPLY:
1. CROSS-DOMAIN ANALOGY TEST: For each idea, identify the closest known method from ANY field.
   Can this idea be reduced to that method in one sentence? If yes, note it as a critical issue.
   Example: "This is essentially Naive Bayes applied to trajectory scoring."
2. COUNTEREXAMPLE PRESSURE TEST: For each idea, find 3 concrete scenarios where the method
   would fail or produce wrong results. Check if the method design addresses these.
3. CIRCULARITY CHECK: Look for bootstrap estimation loops. Does any step estimate X using Y
   where Y itself depends on X? Flag and require a fix.
4. MULTI-LEVEL FRAMEWORK TEST: Is this a single-trick heuristic? If so, suggest how to
   escalate it into a multi-level framework (each level removes one limitation).
5. CROSS-OVER ACTIONABILITY: If the idea claims to bridge two areas, demand a concrete
   closed-loop feedback mechanism. "Shared math tools" is not cross-over.
```

### 9.4 客座教授 -- External Review (Stage 7)

```
You are a visiting professor (客座教授) from a different institution, invited to
review research proposals. You have no stake in these ideas succeeding.

The Advisor has already reviewed these proposals. Their review:
{advisor_review_content}

YOUR TASK: Stress-test each proposal from an independent, external perspective.
Deliberately find issues the Advisor has NOT raised. Do not merely agree with their assessment.

CURRENT QUALITY STANDARD: {quality_standard}
{quality_rubric_for_standard}

For each proposal:

1. CHECK NOVELTY: Use WebSearch to look for very recent papers (last 3 months) that might
   scoop or closely overlap with this idea. Search for the specific method name + application area.

2. CHECK THEORY: Are the theoretical claims logically sound? Are there hidden assumptions?
   Could a reviewer poke holes in the reasoning?

3. CHECK EXPERIMENTS: Do the experiments actually test the hypothesis? Are the baselines
   the strongest available? Is anything missing from the ablation?

4. IDENTIFY TOP-3 REVIEWER ATTACKS: What would a skeptical ICML/NeurIPS/ICLR reviewer say?
   For each attack, suggest a specific preemptive defense.

Output per idea:

=== IDEA: {slug} ===
VERDICT: {APPROVE | REFINE | DROP}
RECENT_WORK_CHECK: {papers found that might overlap, or "no close overlap found"}
ISSUES:
1. [{severity: critical|major|minor}] {specific issue the Advisor missed}
ATTACK_VECTORS:
1. ATTACK: {what a reviewer would say}
   DEFENSE: {how to preempt this in the paper}
2. ...
3. ...
=== END IDEA ===
```

### 9.5 研究生 -- REFINE 後的修訂

```
You are revising your research proposal based on reviewer feedback.

REVIEWER FEEDBACK:
{combined_advisor_and_vp_feedback}

YOUR PREVIOUS SUBMISSION:
{previous_hypothesis_or_plan}

REVISION GUIDELINES:

1. DO NOT DEFEND the original approach. If a reviewer found a weakness, acknowledge it.
   Then fix it. Defending weak points wastes time and loses trust.

2. TURN EVERY COUNTEREXAMPLE INTO AN INNOVATION POINT.
   For each concrete failure case the reviewers raised, ask: "What mechanism would make
   this criticism invalid?" That mechanism becomes a new feature of your method.
   Example: "correct formula wrongly penalized" → add causal discrimination conditioning
   on prefix context.

3. ESCALATE FROM HEURISTIC TO FRAMEWORK.
   If a reviewer says "this is just X", acknowledge it:
   - Level 1 = your current method (essentially X)
   - Level 2 = remove limitation A of X (specific fix)
   - Level 3 = remove limitation B (specific fix)
   - Level 4 = remove limitation C (specific fix)
   Each level's ablation answers one independent scientific question.

4. UPGRADE OBSERVATIONAL CLAIMS TO ACTIONABLE MECHANISMS.
   If a reviewer says "the cross-over claim is weak", find a concrete closed-loop:
   output of component A → improves input of component B → improves output of A.
   If no closed loop exists, honestly downgrade the claim.

5. SEARCH FOR ADJACENT-FIELD TECHNIQUES.
   When a reviewer draws a cross-domain analogy ("this is like MMR in RecSys"),
   use WebSearch to find the latest work in that adjacent field. Borrow specific
   techniques to strengthen your method.

6. CHECK FOR CIRCULARITY after revision.
   Did your fix introduce a new circular dependency? Verify.

Address EACH numbered issue from the reviewers specifically.
Mark which issues you addressed and how.
```

---

## 10. Python Helpers

位於 `.claude/skills/research-ideate/helpers/`。

### 10.1 `state_manager.py`

```python
"""research-ideate 的 pipeline state 管理。"""

import json
from pathlib import Path
from datetime import datetime

QUALITY_STANDARDS = {1: "lenient", 2: "moderate", 3: "strict"}

def init_state(workspace: Path, topic: str, paper_titles: list[str],
               constraints: dict) -> dict:
    """初始化新的 pipeline state。"""

def load_state(workspace: Path) -> dict:
    """從 state.json 讀取 state。"""

def save_state(workspace: Path, state: dict) -> None:
    """將 state 寫入 state.json，附帶 timestamp。"""

def advance_stage(workspace: Path, next_stage: str) -> dict:
    """將 pipeline 推進到下一個 stage。回傳更新後的 state。"""

def update_idea_status(workspace: Path, slug: str, status: str,
                       reason: str = "") -> dict:
    """更新單一 idea 的狀態（approved/refine/pivot/drop）。"""

def get_quality_standard(round_num: int) -> str:
    """回傳指定 round 的品質標準名稱。"""

def check_convergence(state: dict) -> bool:
    """檢查 pipeline 是否應進入 Stage 9。"""

def get_ideas_by_status(state: dict, status: str) -> list[str]:
    """回傳具有指定狀態的 idea slugs。"""
```

### 10.2 `log_interaction.py`

```python
"""完整 audit trail 的互動日誌記錄。"""

from pathlib import Path
from datetime import datetime

def log_interaction(workspace: Path, stage: str, round_num: int,
                    role: str, input_summary: str, full_output: str,
                    decision: str | None = None) -> Path:
    """
    在 log 目錄中新增一筆互動記錄。

    寫入: interaction_log/{stage}_{role}_round{N}.md
    格式:
      # {Stage} -- {Role} (Round {N})
      **Timestamp**: ...
      **Input context**: {input_summary}
      ## Output
      {full_output}
      ## Decision
      {decision or "N/A"}
    """
```

### 10.3 `parse_review.py`

```python
"""從 reviewer 文字輸出中擷取結構化資料。"""

import re

def parse_review(review_text: str) -> dict:
    """
    解析 review 文字中的結構化標記。

    回傳:
    {
      "ideas": {
        "slug": {
          "verdict": "APPROVE|REFINE|PIVOT|DROP",
          "scores": {"novelty": int, "theory": int, "feasibility": int},
          "issues": [{"category": str, "description": str}],
          "suggestions": [str],
          "attack_vectors": [{"attack": str, "defense": str}]
        }
      },
      "ranking": [{"slug": str, "justification": str}]
    }
    """

def extract_idea_blocks(text: str) -> list[tuple[str, str]]:
    """從 === IDEA: slug === 標記中擷取 (slug, block_content) pairs。"""

def extract_verdict(block: str) -> str:
    """從 idea block 中擷取 VERDICT: 行。"""

def extract_scores(block: str) -> dict:
    """將 SCORE_* 行擷取為 {dimension: int} dict。"""

def extract_issues(block: str) -> list[dict]:
    """將編號的 ISSUES 擷取為結構化 list。"""
```

### 10.4 `format_final_plan.py`

```python
"""將結構化資料渲染為最終研究計劃 .md。"""

def format_plan(idea_slug: str, hypothesis: str, plan: str,
                reviews: list[str], rank: int) -> str:
    """
    渲染完整的 12-section 研究計劃。

    Template sections:
    1. Title
    2. One-sentence thesis
    3. Research area
    4. Closest prior work (3-5 papers)
    5. Problem gap
    6. Theoretical basis
    7. Method sketch
    8. Implementation plan (MVP + full)
    9. Experimental plan
    10. Paper storyline
    11. Novelty risk assessment
    12. Final verdict + recommended venue
    + Appendix: Review history summary
    """

def format_summary_table(plans: list[dict]) -> str:
    """
    渲染比較表格:
    | Rank | Title | Area | Novelty | Feasibility | Confidence | Venue |
    """
```

---

## 11. 日誌策略

**需求**: 所有中間互動必須被記錄 -- 指導教授 reviews、研究生 intermediate ideas、修訂、決策。使用者在 run 完成後查看結果。

### Log 目錄結構

```
proposal_space/interaction_log/
├── stage1_student_literature_round1.md
├── stage2_student_ideation_round1.md
├── stage3_student_hypothesis_idea1_round1.md
├── stage3_student_hypothesis_idea2_round1.md
├── ...
├── stage3_advisor_gate_round1.md
├── stage3_student_revision_idea3_round1.md    （如果在 gate 被 REFINE）
├── stage3_advisor_gate_revision_round1.md     （修改後重新審查）
├── stage4_student_plan_idea1_round1.md
├── ...
├── stage6_advisor_review_round1.md
├── stage7_vp_review_round1.md
├── stage8_orchestrator_decision_round1.md
├── stage3_student_hypothesis_idea3_round2.md  （Round 1 的 REFINE）
├── ...
├── stage9_final_ranking.md
└── pipeline_summary.md                        （run 結束時自動產生）
```

### 每筆 Log 的內容

```markdown
# Stage 6: 指導教授審查 -- Round 2

**Timestamp**: 2026-03-27T14:23:45
**Role**: 指導教授 (Opus)
**Quality Standard**: moderate
**Input Context**: 5 份實驗計劃 (idea1-idea5), 客座教授 Round 1 review

---

## Full Output

{完整、未編輯的 agent 輸出}

---

## Decisions Made

- idea1: APPROVE（strong novelty + sound theory）
- idea2: REFINE（issues: missing baseline X, ablation Y）
- idea3: APPROVE（addressed all Round 1 concerns）
- idea4: DROP（novelty claim invalidated by Chen et al. 2026）
- idea5: REFINE（experiment doesn't test the actual hypothesis）
```

### Pipeline Summary（自動產生）

Run 結束時，orchestrator 產生 `proposal_space/interaction_log/pipeline_summary.md`：

```markdown
# Pipeline Summary

**Topic**: {topic}
**Run Date**: 2026-03-27
**Total Rounds**: 2
**Total Agent Calls**: 23 (研究生: 14, 指導教授: 6, 客座教授: 3)

## Idea Lifecycle

| Idea | Created | Round 1 | Round 2 | Final Status |
|------|---------|---------|---------|-------------|
| contrastive-cot | R1 | REFINE | APPROVE | Final Plan #1 |
| token-contrast | R1 | APPROVE | -- | Final Plan #2 |
| meta-decode | R1 | PIVOT | -- | 被 adaptive-contrast 替換 |
| ...

## 關鍵決策點

1. Round 1, Stage 3: 指導教授 dropped "naive-ensemble"（致命：Li 2025 已發表相同方法）
2. Round 1, Stage 8: 客座教授找到 "meta-decode" 的同期工作，觸發 PIVOT
3. Round 2, Stage 6: 所有剩餘 idea 在 moderate 標準下通過

## Review 重點摘錄

{驅動決策的 advisor/VP review 關鍵摘錄}
```

---

## 12. 檔案與目錄結構

### Skill 檔案

```
.claude/skills/research-ideate/
├── SKILL.md                      # Orchestrator skill 定義
├── ri-student.md                 # 研究生角色 prompt template
├── ri-advisor.md                 # 指導教授角色 prompt template
├── ri-visiting-prof.md           # 客座教授角色 prompt template
└── helpers/
    ├── state_manager.py
    ├── log_interaction.py
    ├── parse_review.py
    └── format_final_plan.py
```

### 輸出結構（Per Run）

```
output/research_ideate/
└── contrastive-decoding-small-lm/          # topic slug
    └── 20260327/                            # run date
        ├── plan_1_contrastive_cot.md        # 最終計劃 #1
        ├── plan_2_token_contrast.md         # 最終計劃 #2
        ├── plan_3_adaptive_contrast.md      # 最終計劃 #3
        ├── summary.md                       # 比較表格 + 建議
        └── proposal_space/                  # 完整 workspace（audit trail）
            ├── state/
            │   ├── state.json
            │   └── submission_round{N}.json
            ├── literature/
            │   └── landscape_round{N}.md
            ├── ideas/
            │   └── candidates_round{N}.md
            ├── hypotheses/
            │   └── hypothesis_{slug}_round{N}.md
            ├── plans/
            │   └── plan_{slug}_round{N}.md
            ├── reviews/
            │   ├── advisor_hypothesis_round{N}.md
            │   ├── advisor_round{N}.md
            │   └── vp_round{N}.md
            └── interaction_log/
                ├── stage1_student_literature_round1.md
                ├── ...
                └── pipeline_summary.md
```

---

## 13. 成本估算

### 每次 Agent Call 成本

| Agent Call | Model | Input (est.) | Output (est.) | Cost |
|-----------|-------|-------------|--------------|------|
| 研究生: 文獻搜尋 | Sonnet | ~5K | ~8K | ~$0.05 |
| 研究生: idea 生成 | Sonnet | ~10K | ~12K | ~$0.08 |
| 研究生: 假說（per idea） | Sonnet | ~15K | ~10K | ~$0.10 |
| 研究生: 實驗計劃（per idea） | Sonnet | ~20K | ~15K | ~$0.15 |
| 研究生: 修訂（per idea） | Sonnet | ~25K | ~12K | ~$0.15 |
| 指導教授: hypothesis gate（all ideas） | Opus | ~30K | ~8K | ~$1.20 |
| 指導教授: full review（all plans） | Opus | ~40K | ~10K | ~$1.50 |
| 客座教授: full review（all plans） | Opus | ~45K | ~10K | ~$1.70 |
| 指導教授: final ranking | Opus | ~30K | ~5K | ~$1.00 |

### 完整 Run 情境

| 情境 | Rounds | Agent Calls | 估計成本 |
|------|--------|------------|---------|
| **最佳情況**（多數 Round 2 approve） | 2 | ~20 | $60-80 |
| **典型情況**（部分 REFINE, 1 PIVOT） | 2.5 avg | ~25 | $80-120 |
| **最差情況**（大量迭代） | 3 full | ~35 | $120-180 |

**Sonnet 成本節省**: 研究生使用 Sonnet（佔全部 calls 的 ~50-60%），相比全用 Opus 節省約 60-70%。

---

## 14. 未來擴展性

### 實驗執行的擴展點

設計上明確支持在 ideation 之後加入實驗執行：

1. **State machine 擴展**: `state.json` 可新增 Stages 10-15（code generation, sandbox execution, result analysis），不需修改現有 stages。

2. **新角色 skill**: `ri-engineer.md`（Research Engineer）從 `plans/` 讀取並寫入：
   ```
   proposal_space/
   ├── code/{slug}/          # 產生的實驗程式碼
   │   ├── main.py
   │   └── requirements.txt
   ├── experiments/{slug}/   # 執行結果
   │   ├── run_log.txt
   │   ├── metrics.json
   │   └── figures/
   └── analysis/{slug}/      # 結果分析
       └── analysis_round{N}.md
   ```

3. **Self-healing loop**: 採用 AutoResearchClaw 的 Stage 12-13 模式（run -> diagnose -> repair -> re-run，最多 10 次迭代）。

4. **結果回饋**: 實驗結果回饋到 review loop。指導教授和客座教授可評估結果是否支持假說，可能觸發方法的 REFINE。

5. **VerifiedRegistry**: 實驗結果的 anti-hallucination。只有能追溯到實際程式碼執行的結果才標記為 verified。

### 跨次執行學習的擴展點（MetaClaw 啟發）

1. **Lesson extraction**: 每次 run 後，從 PIVOTs、DROPs、和 REFINE cycles 中萃取教訓。
2. **Skill generation**: 將教訓轉化為可重用的 prompt overlays（例：「在此研究領域，務必檢查 X baseline」）。
3. **Skill injection**: 根據 topic 相似度，將相關 skills 注入未來的 runs。
4. **Skill tracking**: 追蹤哪些 skills 與 approved vs. dropped ideas 相關。

此為未來增強功能，不在初始實作範圍內。

---

## 15. 實作順序

### Phase 1: Python Helpers（純工具程式）

1. `state_manager.py` -- state 讀寫、stage 推進、品質標準查詢
2. `log_interaction.py` -- 互動日誌記錄
3. `parse_review.py` -- 從 review 文字擷取結構化資料
4. `format_final_plan.py` -- 12-section template 渲染

**測試**: 在 `tests/research_ideate/` 下為所有 helpers 撰寫 unit tests。

### Phase 2: 最小 Pipeline（Stages 1-2）

1. `SKILL.md` orchestrator -- 輸入解析、workspace 初始化、僅 Stages 1-2
2. `ri-student.md` -- 文獻搜尋 + idea 生成 prompts

**驗證**: 用測試 topic 執行，確認 literature landscape 和 idea list 品質。

### Phase 3: 指導教授整合（Stage 3 Gate）

1. `ri-advisor.md` -- hypothesis review prompt
2. Orchestrator: 加入 Stage 3 的指導教授 gate 和 REFINE sub-loop

**驗證**: 執行到 Stage 3，確認指導教授給出結構化 reviews，REFINE loop 正常運作。

### Phase 4: 完整 Review Loop（Stages 4-8）

1. 研究生: 實驗計劃 prompts
2. `ri-visiting-prof.md` -- adversarial review prompt
3. Orchestrator: Stages 4-8 的 dual review、decision logic、iteration

**驗證**: 執行完整 pipeline 包含 2+ rounds，確認迭代機制正常。

### Phase 5: 最終輸出（Stage 9）

1. `format_final_plan.py` 整合
2. Summary table 產生
3. Pipeline summary log

**驗證**: End-to-end run 產出 3-5 份最終研究計劃。

### Phase 6: 打磨與測試

1. Edge cases：文獻不足、所有 idea 被 drop、達到迭代上限
2. Python helpers 完整測試套件
3. 文件
