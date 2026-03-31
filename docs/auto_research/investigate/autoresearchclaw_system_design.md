# AutoResearchClaw 多智能體系統設計分析

> **專案來源**: [aiming-lab/AutoResearchClaw](https://github.com/aiming-lab/AutoResearchClaw)
> **版本**: v0.3.2 (2026-03-22)
> **分析日期**: 2026-03-26

---

## 目錄

1. [直覺篇：一句話理解整個系統](#1-直覺篇一句話理解整個系統)
2. [核心比喻：把它想成一個研究實驗室](#2-核心比喻把它想成一個研究實驗室)
3. [八大階段概覽](#3-八大階段概覽)
4. [Agent 角色詳解](#4-agent-角色詳解)
5. [Agent 之間如何協作](#5-agent-之間如何協作)
6. [持續內容改進與優化機制](#6-持續內容改進與優化機制)
7. [品質閘門與決策回滾](#7-品質閘門與決策回滾)
8. [跨次執行的學習系統 (MetaClaw)](#8-跨次執行的學習系統-metaclaw)
9. [關鍵設計洞察與總結](#9-關鍵設計洞察與總結)

---

## 1. 直覺篇：一句話理解整個系統

**AutoResearchClaw 就是一條「研究想法 → 會議級論文」的全自動流水線。**

你只需要給它一個研究想法（例如：「用 meta-learning 加速 few-shot 分類」），它就會：
- 自己去搜集真實文獻
- 自己提出假說
- 自己寫實驗程式碼、跑實驗
- 自己分析結果
- 自己撰寫 LaTeX 論文
- 自己做 peer review 並修改
- 最後產出一份可以投稿的完整論文

整個流程有 **23 個階段**，分佈在 **8 個大相位** (Phase) 中，由多個 **專責 Agent** 分工協作完成。

---

## 2. 核心比喻：把它想成一個研究實驗室

想像一個高效率的研究實驗室：

| 實驗室角色 | AutoResearchClaw 對應 |
|---|---|
| **PI（指導教授）** | Pipeline Runner — 統籌全局、決定推進/回退 |
| **文獻調研組** | Literature 模組 — 搜論文、篩選、萃取知識 |
| **理論組** | Synthesis + Hypothesis 階段 — 找 gap、提假說 |
| **工程師** | CodeAgent — 寫實驗程式碼 |
| **實驗操作員** | Sandbox/Docker 執行環境 — 跑程式碼 |
| **數據分析師** | Result Analysis 階段 — 多 Agent 交叉分析 |
| **製圖員** | FigureAgent — 5 個子 Agent 協作產出圖表 |
| **資料集管理員** | BenchmarkAgent — 4 個子 Agent 搜尋和驗證基準 |
| **論文撰寫員** | Paper Writing 階段 — 寫初稿 |
| **審稿委員** | Peer Review — 模擬學術審稿 |
| **品管部門** | Quality Gate + VerifiedRegistry — 三道品質關卡 |
| **實驗室經驗傳承** | Evolution + MetaClaw — 跨次執行知識遷移 |

重點是：**每個角色都是獨立的 Agent，彼此透過明確的「合約」(Contract) 交換結構化資料**，而非直接耦合。

---

## 3. 八大階段概覽

```
Phase A: 研究定義          Phase B: 文獻探索          Phase C: 知識合成
┌─────────────────┐    ┌─────────────────────┐    ┌──────────────┐
│ 1. TOPIC_INIT   │    │ 3. SEARCH_STRATEGY  │    │ 7. SYNTHESIS │
│ 2. PROBLEM_     │───>│ 4. LITERATURE_      │───>│ 8. HYPOTHESIS│
│    DECOMPOSE    │    │    COLLECT           │    │    _GEN      │
└─────────────────┘    │ 5. LITERATURE_      │    │   (辯論式)    │
                       │    SCREEN [閘門]     │    └──────┬───────┘
                       │ 6. KNOWLEDGE_       │           │
                       │    EXTRACT           │           v
                       └─────────────────────┘
Phase D: 實驗設計          Phase E: 實驗執行          Phase F: 分析與決策
┌─────────────────┐    ┌─────────────────────┐    ┌───────────────┐
│ 9. EXPERIMENT_  │    │ 12. EXPERIMENT_RUN  │    │ 14. RESULT_   │
│    DESIGN [閘門] │───>│ 13. ITERATIVE_      │───>│     ANALYSIS  │
│ 10. CODE_       │    │     REFINE          │    │ 15. RESEARCH_ │
│     GENERATION  │    │   (自我修復, ≤10輪)  │    │     DECISION  │
│ 11. RESOURCE_   │    └─────────────────────┘    │  ┌─PIVOT→回到8│
│     PLANNING    │                               │  └─REFINE→回13│
└─────────────────┘                               └───────────────┘

Phase G: 論文撰寫          Phase H: 最終化
┌─────────────────┐    ┌─────────────────────┐
│ 16. PAPER_      │    │ 20. QUALITY_GATE    │
│     OUTLINE     │    │     [閘門]           │
│ 17. PAPER_DRAFT │───>│ 21. KNOWLEDGE_      │
│ 18. PEER_REVIEW │    │     ARCHIVE          │
│ 19. PAPER_      │    │ 22. EXPORT_PUBLISH  │
│     REVISION    │    │ 23. CITATION_VERIFY │
└─────────────────┘    └─────────────────────┘
```

### 三個閘門 (Gate)

系統設置了三道品質關卡，通不過就不會繼續往下走：

| 閘門 | 位置 | 功能 |
|------|------|------|
| **Stage 5** | 文獻篩選後 | 確認搜到的文獻品質和覆蓋度足夠 |
| **Stage 9** | 實驗設計後 | 確認有適當的 baseline、ablation、統計方法 |
| **Stage 20** | 最終品質檢查 | 確認論文達到投稿水準 |

閘門可以設定 `--auto-approve` 自動通過，或暫停等待人類審批。

### 兩種回滾機制

- **PIVOT**（大轉向）：Stage 15 判斷當前方向行不通 → 回到 Stage 8（重新生成假說）
- **REFINE**（小調整）：Stage 15 判斷方向對但實驗不夠好 → 回到 Stage 13（迭代改進）

---

## 4. Agent 角色詳解

### 4.1 基礎架構：BaseAgent 與 AgentOrchestrator

所有 Agent 都繼承自 `BaseAgent`（定義於 `researchclaw/agents/base.py`）：

```
BaseAgent
├── _chat()          # 與 LLM 對話
├── _chat_json()     # 強制 JSON 格式回應
├── _parse_json()    # 三層容錯 JSON 解析
│   ├── 直接解析
│   ├── 提取 code fence 中的 JSON
│   └── 平衡大括號提取
├── _calls / _tokens # 追蹤每個 Agent 的 LLM 使用量
└── _make_result()   # 返回 AgentStepResult，並重置計數器
```

`AgentOrchestrator` 是多 Agent 子系統的協調者基底類別：
- 設定 `max_iterations` 防止無窮迴圈
- 透過 `_accumulate()` 累加所有子 Agent 的 LLM 使用量
- 要求子類別實作 `orchestrate()` 方法

**直覺**：BaseAgent 就像「員工守則」，確保每個 Agent 都會算帳（token 計數）、會溝通（JSON 解析）。AgentOrchestrator 就像「部門主管守則」，確保主管會控管迭代次數和成本。

---

### 4.2 CodeAgent（程式碼生成 Agent）

**職責**：將實驗設計轉化為可執行的 Python 程式碼。

#### 五個執行相位

```
┌─────────────────┐
│ Phase 1:        │  分析實驗需求，產出每個檔案的偽代碼、
│ Blueprint       │  tensor shape、依賴順序
│ Planning        │
└────────┬────────┘
         v
┌─────────────────┐
│ Phase 2:        │  按照依賴 DAG 順序逐一生成檔案，
│ Sequential File │  每生成一個檔案就寫入 CodeMem 摘要，
│ Generation      │  供後續檔案引用
└────────┬────────┘
         v
┌─────────────────┐
│ Phase 3:        │  在沙箱中執行程式碼，
│ Execution-in-   │  把錯誤訊息餵回 LLM 修復
│ the-Loop        │  （最多 10 輪）
└────────┬────────┘
         v
┌─────────────────┐
│ Phase 4:        │  （可選）探索多個候選實作，
│ Solution Tree   │  在沙箱中評估，選最好的
│ Search          │
└────────┬────────┘
         v
┌─────────────────┐
│ Phase 5:        │  Coder ↔ Reviewer 對話式
│ Multi-Agent     │  品質保證
│ Review          │
└─────────────────┘
```

**關鍵設計**：
- **AST 硬驗證**：每個生成的 Python 檔都經過 `ast.parse()` 驗證語法正確性
- **CodeMem**：生成每個檔案後，Agent 會產出該檔案的功能摘要，注入到後續生成的 prompt 中，確保檔案間的介面一致性
- **Dependency DAG**：Blueprint 中定義了檔案間的依賴關係，確保 `utils.py` 在 `model.py` 之前生成

---

### 4.3 BenchmarkAgent（基準測試 Agent）

**職責**：自動搜尋、選擇、獲取、驗證合適的基準數據集和 baseline。

#### 四個子 Agent 流水線

```
SurveyorAgent ──> SelectorAgent ──> AcquirerAgent ──> ValidatorAgent
  (探勘)           (篩選)           (獲取程式碼)       (驗證)
                                                         │
                                                    失敗? ↓ 重試
```

| 子 Agent | 功能 | 輸入 | 輸出 |
|----------|------|------|------|
| **Surveyor** | 搜尋 HuggingFace Datasets、Google Scholar 找 benchmark | 研究主題、領域 | 候選 benchmark 列表 |
| **Selector** | 考慮 GPU/時間/網路限制，選擇最適合的 benchmark 和 baseline | 候選列表 + 硬體資訊 | 選定的 benchmark + baseline |
| **Acquirer** | 產生 data loader、baseline 實作、setup 程式碼 | 選定的 benchmark/baseline | 可執行的程式碼片段 |
| **Validator** | 用 AST 檢查程式碼品質，失敗則觸發重試 | 程式碼片段 | 驗證結果（附重試迴圈） |

**直覺**：就像你要做實驗前，先讓一個助理去調研有哪些常用的 benchmark（Surveyor），然後考量你的硬體條件挑選合適的（Selector），再幫你把數據載入的程式碼寫好（Acquirer），最後確認程式碼跑得動（Validator）。

---

### 4.4 FigureAgent（圖表生成 Agent）

**職責**：為論文自動生成高品質的圖表（300 DPI）。

#### 五個子 Agent + 決策 Agent

```
                    FigureDecisionAgent
                     /              \
            code_figures         image_figures
                |                      |
                v                      v
Phase A: 程式碼圖表             Phase B: 概念圖
┌─────────────┐             ┌──────────────┐
│ Planner     │             │ NanoBanana   │
│  ↓          │             │ (Gemini API) │
│ CodeGen     │             └──────┬───────┘
│  ↓          │                    │
│ Renderer    │                    │
│  ↓          │                    │
│ Critic ─────┤← 不合格? 重做      │
│  (品質評審)  │                    │
└──────┬──────┘                    │
       │                           │
       v                           v
              Phase C: 整合
         ┌──────────────────┐
         │   Integrator     │
         │ (合併所有圖表到    │
         │  manifest)       │
         └──────────────────┘
```

| 子 Agent | 功能 |
|----------|------|
| **DecisionAgent** | 分析論文內容，決定需要哪些圖（數據圖 vs 概念圖） |
| **Planner** | 規劃每張數據圖的內容、數據來源、圖表類型 |
| **CodeGen** | 生成 matplotlib/seaborn 繪圖程式碼 |
| **Renderer** | 在沙箱中執行繪圖程式碼，產出 PNG |
| **Critic** | 評估圖表品質（清晰度、標籤完整性），不合格則觸發 CodeGen 重做 |
| **NanoBanana** | 使用 Gemini API 生成概念架構圖（非數據驅動的圖） |
| **Integrator** | 將所有圖表合併為統一的 manifest，產出 LaTeX 引用 |

**直覺**：Critic Agent 就像論文投稿前，把圖表列印出來給同事看一下，同事說「這個 y 軸標籤太小了」、「顏色對比不夠」，然後你回去改。

---

### 4.5 Pipeline Runner（總指揮）

**職責**：驅動 23 階段依序執行，處理閘門、回滾、異常。

關鍵行為：
- 根據 `STAGE_SEQUENCE` 逐一呼叫 `execute_stage()`
- 在閘門階段（5, 9, 20）暫停等待審批或自動通過
- Stage 15 收到 PIVOT/REFINE 決策時，執行對應的回滾
- PIVOT 最多允許 `MAX_DECISION_PIVOTS` 次（防止無限轉向）
- 對 `NONCRITICAL_STAGES`（Stage 20, 21）的失敗可降級繼續
- **但 Stage 23（引用驗證）刻意不列為 noncritical** — 幻覺引用必須阻擋匯出

---

## 5. Agent 之間如何協作

### 5.1 合約制度 (Contracts)

Agent 間透過 `contracts.py` 定義的結構化資料交換：

```python
# 每個階段產出的 StageResult 包含：
@dataclass
class StageResult:
    stage: Stage           # 哪個階段
    status: StageStatus    # 成功/失敗/被阻擋
    data: dict             # 該階段的結構化輸出
    error: str | None      # 錯誤訊息
    decision: str          # "proceed" / "pivot" / "refine" / "degraded"
```

**直覺**：每個 Agent 完成工作後，把結果放進一個標準格式的「信封」裡，下一個 Agent 打開「信封」讀取上一步的成果。沒有任何 Agent 直接呼叫另一個 Agent 的內部方法。

### 5.2 資料流向

```
Topic (使用者輸入)
  ↓
[Stage 1-2] → topic_summary, sub_problems
  ↓
[Stage 3-6] → search_queries → papers[] → screened_papers[] → knowledge_cards[]
  ↓
[Stage 7-8] → synthesis_report → hypotheses[]
  ↓
[Stage 9-11] → experiment_plan → generated_code{} → resource_plan
  ↓                                    ↑
  ↓                              BenchmarkAgent 的結果
  ↓                              注入到 code generation prompt
  ↓
[Stage 12-13] → experiment_results → refined_results (self-healing loop)
  ↓
[Stage 14-15] → analysis_report → decision: PROCEED/PIVOT/REFINE
  ↓
[Stage 16-19] → outline → draft → review_comments → revised_paper
  ↓                                    ↑
  ↓                              FigureAgent 的結果
  ↓                              整合到論文中
  ↓
[Stage 20-23] → quality_check → archived → latex_output → verified_citations
```

### 5.3 多 Agent 協作模式

系統中出現了三種不同的協作模式：

#### 模式一：流水線式（Sequential Pipeline）
BenchmarkAgent 的 Surveyor → Selector → Acquirer → Validator 就是典型的流水線，每個 Agent 的輸出直接成為下一個的輸入。

#### 模式二：評審迴圈式（Critic Loop）
FigureAgent 的 CodeGen → Renderer → Critic 形成迴圈。Critic 不滿意就打回去讓 CodeGen 重做。CodeAgent 的 Execution-in-the-Loop 也是同樣的模式。

```
生產者 ──產出──> 評審者
  ^                |
  |    不合格      |
  └───修改要求────┘
```

#### 模式三：辯論式（Debate）
Stage 8（假說生成）採用辯論機制——多個觀點交叉檢驗，避免單一 Agent 的偏見。

---

## 6. 持續內容改進與優化機制

這是 AutoResearchClaw 最精巧的設計之一。系統有 **三層** 漸進式的改進機制：

### 6.1 第一層：同次執行內的自我修復 (Intra-run Self-healing)

**位置**：Stage 12-13（實驗執行 + 迭代改進）

```
執行程式碼 → 出錯?
              ├── 是 → 分析錯誤 → 修復程式碼 → 重新執行（最多 10 輪）
              └── 否 → 繼續
```

具體機制：
- **Experiment Diagnosis**（`experiment_diagnosis.py`）：分析實驗失敗的根本原因，分類為語法錯誤、import 錯誤、數值問題、超時等
- **Experiment Repair**（`experiment_repair.py`）：根據診斷結果產生修復方案，在沙箱中驗證修復是否成功
- **VerifiedRegistry**（`verified_registry.py`）：反造假系統，追蹤哪些實驗結果是真正執行過的，防止 LLM 幻覺偽造數據

**直覺**：就像你寫程式 → 跑 → 報錯 → 看 error message → 修改 → 重跑的循環，只不過這裡是 Agent 自己在做。

### 6.2 第二層：同次執行內的學習 (Intra-run Evolution)

**位置**：`evolution.py` — EvolutionStore

每次某個階段完成（無論成功或失敗），系統都會：

1. **萃取教訓** (`extract_lessons()`)：
   - 失敗的階段 → 提取錯誤類別和描述
   - 被阻擋的階段 → 記錄為 pipeline 教訓
   - PIVOT/REFINE 決策 → 記錄為策略教訓（含理由）
   - 實驗執行的 stderr 警告 → 記錄為程式碼品質教訓
   - NaN/Inf 的 metric → 記錄為數值穩定性教訓

2. **注入到後續階段** (`build_overlay()`)：
   萃取出的教訓以「prompt overlay」的形式注入到後續階段的 prompt 中

```
Stage 4 失敗（Semantic Scholar API 超時）
  ↓
extract_lessons() → LessonEntry(category="system", description="API 超時")
  ↓
Stage 6 執行時，build_overlay("knowledge_extract") 注入：
  「## Lessons from Prior Runs
   1. ❌ [system] Stage literature_collect failed: API timeout
   Use these lessons to avoid repeating past mistakes.」
```

**直覺**：就像你在做實驗的過程中邊做邊記筆記，後面的步驟可以參考前面的經驗教訓。

### 6.3 第三層：跨次執行的知識遷移 (Cross-run MetaClaw)

**位置**：`metaclaw_bridge/` 整個子系統

這是最高階的學習機制，讓 **不同次的 pipeline 執行之間可以傳遞知識**。

#### 完整的學習迴路

```
                    Pipeline 執行 #1
                         │
                    失敗 / 警告
                         │
                         v
              ┌──────────────────────┐
              │  extract_lessons()   │  萃取教訓
              └──────────┬───────────┘
                         │
                         v
              ┌──────────────────────┐
              │  convert_lessons_    │  LLM 將教訓轉化為
              │  to_skills()         │  可重用的 SKILL.md
              └──────────┬───────────┘
                         │
                    arc-* 技能檔案
                   (MetaClaw 格式)
                         │
                         v
              ┌──────────────────────┐
              │  Pipeline 執行 #2    │
              │                      │
              │  build_overlay() 注入 │  技能被注入到每個
              │  skills 到每個階段    │  階段的 prompt 中
              └──────────┬───────────┘
                         │
                         v
              ┌──────────────────────┐
              │  record_stage_       │  記錄技能是否
              │  skills()            │  對階段成功有幫助
              └──────────┬───────────┘
                         │
                         v
              ┌──────────────────────┐
              │  compute_skill_      │  計算每個技能的
              │  stats()             │  成功率，淘汰無效技能
              └──────────────────────┘
```

#### Stage-Skill 映射

每個階段都有對應的技能類型和注入數量：

| 階段 | 技能類型 | 偏好技能 | 注入數量 |
|------|----------|----------|----------|
| topic_init | research | literature-search-strategy | 4 |
| hypothesis_gen | research | hypothesis-formulation | 6 |
| code_generation | coding | hardware-aware-coding | 6 |
| experiment_run | automation | experiment-debugging | 4 |
| paper_draft | communication | academic-writing-structure | 6 |
| peer_review | communication | peer-review-methodology | 6 |
| citation_verify | research | citation-integrity | 4 |

#### PRM 品質閘門

MetaClaw 還引入了 **PRM (Process Reward Model)** 作為額外的品質把關：

- 使用 LLM-as-judge 的方式評估閘門階段的輸出品質
- **多數決投票**：平行呼叫多個 judge（預設 3 個），取多數結果
- 每個閘門有專門的評估標準（文獻篩選、實驗設計、整體論文品質各不同）
- 評分：+1（通過）、0（模糊）、-1（不通過）

**效果數據**（來自官方）：
- 階段重試率降低 24.8%
- 改進迴圈次數降低 40%
- Pipeline 完成率提升 5.3%
- 整體穩健性提升 18.3%

---

## 7. 品質閘門與決策回滾

### 狀態機

Pipeline 的每個階段都有完整的狀態機：

```
PENDING → RUNNING → DONE
              ↓        ↑
           RETRYING ───┘
              ↓
           FAILED

RUNNING → BLOCKED_APPROVAL → APPROVED → DONE
                           → REJECTED → (回滾到前一階段)
```

有效的狀態轉換由 `TRANSITION_MAP` 嚴格定義，`advance()` 函數實作完整的狀態機邏輯。

### 閘門回滾映射

```python
GATE_ROLLBACK = {
    Stage.LITERATURE_SCREEN: Stage.SEARCH_STRATEGY,   # 5 → 3
    Stage.EXPERIMENT_DESIGN: Stage.SYNTHESIS,          # 9 → 7
    Stage.QUALITY_GATE: Stage.PAPER_OUTLINE,           # 20 → 16
}
```

**直覺**：就像論文被審稿人拒絕，你不是從頭開始，而是回到對應的環節重來。文獻不夠？回去改搜索策略。實驗設計不佳？回到知識合成重新思考。論文品質不行？回到大綱重寫。

### 非關鍵階段的降級處理

```python
NONCRITICAL_STAGES = frozenset({Stage.QUALITY_GATE, Stage.KNOWLEDGE_ARCHIVE})
# 注意：CITATION_VERIFY 刻意不在此列——幻覺引用必須阻擋匯出
```

品質閘門和知識歸檔失敗時，pipeline 可以降級繼續（`decision = "degraded"`）。但引用驗證失敗時，**必須** 停下來——這是反幻覺的最後防線。

---

## 8. 跨次執行的學習系統 (MetaClaw)

### 教訓的時間衰減

不是所有歷史教訓都同等重要。系統使用 **指數衰減** 來加權：

```
權重 = exp(-天數 * ln(2) / 30)

半衰期: 30 天（30 天前的教訓權重減半）
最大年齡: 90 天（超過 90 天的教訓完全忽略）
```

加上嚴重程度加權：
- `error` 級別教訓 × 1.5 倍權重
- 與當前階段直接相關的教訓 × 2.0 倍權重

**直覺**：越近期的失敗經驗越重要，太久以前的教訓可能已經不適用了（軟體環境已變化）。

### 教訓 → 技能的轉化

`lesson_to_skill.py` 使用 LLM 將原始的失敗記錄轉化為結構化的 MetaClaw 技能：

```
輸入：
  1. [error] [experiment] Stage experiment_run: Sandbox timeout after 300s
  2. [warning] [system] Stage literature_collect: API rate limit hit

LLM 轉化為：

---
name: arc-sandbox-timeout-prevention
description: Prevent experiment sandbox timeouts by adding early termination
metadata:
  category: experiment
---
# Sandbox Timeout Prevention

1. Always add `max_epochs` cap based on available time budget
2. Implement early stopping with patience=3
3. Add periodic checkpoint saving

## Anti-patterns
- Running full training without time budget estimation
- No early stopping mechanism
---
```

### 技能有效性追蹤

`SkillFeedbackStore` 追蹤每個技能在實際 pipeline 執行中的表現：

```
技能 A 被注入到 code_generation 階段
  → 該階段成功 → 記錄 (skill=A, stage=code_generation, success=true)

技能 B 被注入到 experiment_run 階段
  → 該階段失敗 → 記錄 (skill=B, stage=experiment_run, success=false)

統計結果：
  技能 A: 成功率 85% (17/20 次)
  技能 B: 成功率 30% (3/10 次) → 可能需要淘汰或修改
```

---

## 9. 關鍵設計洞察與總結

### 洞察一：分層自癒策略

系統不是只有一種修復機制，而是三層漸進式的：

| 層級 | 範圍 | 機制 | 反應速度 |
|------|------|------|----------|
| L1 | 同一階段內 | Self-healing loop (最多 10 輪) | 即時 |
| L2 | 同次執行跨階段 | Evolution overlay 注入 | 分鐘級 |
| L3 | 跨次執行 | MetaClaw skill 生成與注入 | 天級 |

### 洞察二：反幻覺是一等公民

- **VerifiedRegistry**：只有真正在沙箱中執行過的實驗結果才會被標記為 verified
- **四層引用驗證**：arXiv ID → CrossRef DOI → Semantic Scholar 標題匹配 → LLM 相關性評分
- **Stage 23 不可跳過**：即使其他 noncritical 階段可以降級，引用驗證失敗就必須停止

### 洞察三：Agent 之間是鬆耦合的

- 每個 Agent 只透過結構化的 `StageResult` / `AgentStepResult` 通信
- Agent 不直接呼叫彼此的方法
- 替換任何一個 Agent 的實作不需要修改其他 Agent
- LLM 客戶端使用 Protocol（結構化子類型），支援多種後端

### 洞察四：品質 > 速度

- 三道閘門可以讓 pipeline 暫停
- PIVOT/REFINE 機制允許回頭重來
- 多 Agent 子系統都有 Critic/Validator 角色
- PRM 多數決投票避免單個 judge 的偏差

### 洞察五：領域自適應

- `domains/` 模組包含 10+ 學科的適配器（ML、物理、化學、生物、經濟學、神經科學、機器人學...）
- `DomainDetector` 自動檢測研究主題的學科類別
- 每個學科有專用的 prompt 模板、實驗框架知識、Docker 環境

### 系統整體架構圖

```
使用者: "用 meta-learning 加速 few-shot 分類"
                    │
                    v
         ┌─────────────────────┐
         │   Pipeline Runner   │ ← 總指揮
         │   (23 階段狀態機)    │
         └─────────┬───────────┘
                   │
    ┌──────────────┼──────────────┐
    │              │              │
    v              v              v
┌────────┐  ┌──────────┐  ┌──────────┐
│文獻搜集│  │假說生成  │  │實驗設計  │
│& 篩選  │  │(辯論式)  │  │         │
└────────┘  └──────────┘  └────┬─────┘
                               │
                    ┌──────────┼──────────┐
                    v          v          v
              ┌──────────┐ ┌────────┐ ┌─────────┐
              │CodeAgent │ │Bench-  │ │Figure   │
              │(5 相位)  │ │mark    │ │Agent    │
              │          │ │Agent   │ │(5+1     │
              │Blueprint │ │(4 子   │ │ 子Agent)│
              │→ Gen     │ │Agent)  │ │         │
              │→ Execute │ └────────┘ └─────────┘
              │→ Search  │
              │→ Review  │
              └────┬─────┘
                   │
                   v
         ┌─────────────────────┐
         │  Sandbox / Docker   │ ← 安全執行環境
         │  (自我修復, ≤10輪)   │
         └─────────┬───────────┘
                   │
         ┌─────────┴───────────┐
         │  Result Analysis    │
         │  + Research Decision│
         │  (PROCEED/PIVOT/    │
         │   REFINE)           │
         └─────────┬───────────┘
                   │
                   v
         ┌─────────────────────┐
         │  Paper Writing      │
         │  + Peer Review      │
         │  + Revision         │
         └─────────┬───────────┘
                   │
         ┌─────────┴───────────┐
         │  Quality Gate       │
         │  + Citation Verify  │
         │  + LaTeX Export     │
         └─────────┬───────────┘
                   │
                   v
              最終論文 (.tex)

    ╔══════════════════════════════╗
    ║  跨層學習系統                 ║
    ║  Evolution Store ←→ MetaClaw ║
    ║  (教訓萃取 → 技能生成 →       ║
    ║   技能注入 → 效果追蹤)        ║
    ╚══════════════════════════════╝
```

---

## 附錄：原始碼關鍵檔案對照表

| 模組 | 關鍵檔案 | 功能 |
|------|----------|------|
| 流水線核心 | `pipeline/runner.py` | 23 階段狀態機驅動 |
| 狀態機 | `pipeline/stages.py` | Stage/Status/Transition 定義 |
| 階段執行 | `pipeline/executor.py` | 每個階段的實際執行邏輯 |
| 合約 | `pipeline/contracts.py` | Agent 間資料交換格式 |
| Agent 基類 | `agents/base.py` | BaseAgent + AgentOrchestrator |
| CodeAgent | `pipeline/code_agent.py` | 5 相位程式碼生成 |
| BenchmarkAgent | `agents/benchmark_agent/orchestrator.py` | 4 Agent 基準測試流水線 |
| FigureAgent | `agents/figure_agent/orchestrator.py` | 5+1 Agent 圖表生成 |
| 自我修復 | `pipeline/experiment_diagnosis.py` | 實驗失敗診斷 |
| 自我修復 | `pipeline/experiment_repair.py` | 實驗修復方案生成 |
| 反幻覺 | `pipeline/verified_registry.py` | 實驗結果真實性追蹤 |
| 引用驗證 | `literature/verify.py` | 4 層引用驗證 |
| 論文品質 | `pipeline/paper_verifier.py` | 論文證據檢查 |
| 演化學習 | `evolution.py` | 同次執行教訓萃取與注入 |
| MetaClaw | `metaclaw_bridge/lesson_to_skill.py` | 跨次執行教訓→技能轉化 |
| MetaClaw | `metaclaw_bridge/stage_skill_map.py` | 階段↔技能映射表 |
| MetaClaw | `metaclaw_bridge/skill_feedback.py` | 技能有效性追蹤 |
| MetaClaw | `metaclaw_bridge/prm_gate.py` | PRM 品質閘門 (LLM-as-judge) |
| 領域適配 | `domains/detector.py` | 學科自動檢測 |
| 提示詞 | `prompts.py` (150KB) | 所有 23 階段的 prompt 模板 |
| 設定 | `config.py` (51KB) | 完整設定解析 |
