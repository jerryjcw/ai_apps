# torch_trainval_reco — PyTorch 雙塔推薦範例

以 **MovieLens-100K** 真實資料集為基礎，示範業界最常見的檢索式推薦（retrieval-style recommendation）訓練流程：Two-Tower 模型 + BCE Loss + 隨機負採樣，並以 HR@K / NDCG@K 做 leave-one-out 評估。整個訓練流程在 CPU 上約 10 秒完成，適合做為 PyTorch 訓練與推論的入門範例，也保留了清楚的擴充點。

英文版請見 [README.en.md](README.en.md)。

---

## 為什麼選這個範例

| 選擇 | 理由 |
| --- | --- |
| MovieLens-100K | 學術與業界通用的真實推薦基準資料集，10 萬筆真實評分，下載僅 5 MB，完全非合成 |
| Two-Tower 模型 | YouTube、Google、Pinterest、TikTok 的實務標準檢索架構；雙塔獨立，天然支援 ANN serving |
| BCE + 負採樣 | NCF (He et al., 2017) 論文後最常見的訓練範式，實作直觀、容易除錯，是業界入門的起點 |
| HR@K / NDCG@K | 推薦檢索階段最常用的評估指標，leave-one-out 採樣評估快且可信 |

---

## 專案結構

```
applications/ml_coding/torch_trainval_reco/
├── README.md              # 本檔案（中文）
├── README.en.md           # 英文版
├── requirements.txt
├── src/
│   ├── config.py          # 所有超參數與路徑
│   ├── data.py            # 下載、解析、切分、Dataset
│   ├── model.py           # UserTower / ItemTower / TwoTowerModel
│   ├── trainer.py         # 訓練迴圈（可替換 loss / optimizer）
│   ├── evaluator.py       # HR@K / NDCG@K、top-K 推論
│   └── run.py             # CLI 進入點
├── data/                  # 第一次執行時自動下載解壓
└── checkpoints/           # 訓練完成後的權重

tests/ml_coding/torch_trainval_reco/
├── conftest.py            # 把 src/ 掛到 sys.path
├── test_data.py           # 解析、切分、負採樣
├── test_model.py          # 雙塔前向 shape
├── test_evaluator.py      # HR/NDCG 數學驗證
└── test_trainer.py        # 單 epoch smoke test
```

---

## 資料處理

`src/data.py` 會在第一次執行時從 `https://files.grouplens.org/datasets/movielens/ml-100k.zip` 下載 MovieLens-100K（已存在就跳過），並：

1. 解析 `u.data`（`user\titem\trating\ttimestamp`）與 `u.item`（含 19 維電影類型 multi-hot）。
2. 把互動視為**隱式回饋**（任何評分都算正樣本），依 NCF 慣例丟掉互動少於 5 次的使用者。
3. 把 user_id / item_id 重新編號為連續 `0..N-1`，方便丟進 `nn.Embedding`。
4. **Leave-one-out 切分**：每位使用者最晚的互動保留做 test，其他做 train。
5. 對每個 test 正樣本抽 99 個使用者沒看過的負樣本，合成 100 候選做 ranking 評估（NCF 論文標準協定）。

訓練用的 `InteractionDataset` 每個 epoch 會呼叫 `resample_negatives()` 重抽一批負樣本（每個正樣本配 4 個負樣本），讓模型看得到多樣的 pair。

要快速試跑可以限定使用者數：

```bash
python -m src.run --max-users 100 --epochs 1
```

---

## 模型

`src/model.py` 的 Two-Tower 架構：

```
UserTower:   user_id  -> Embedding(num_users, D) -> MLP -> user_vec (D)
ItemTower:   item_id  -> Embedding(num_items, D)
                         concat( genre multi-hot, 19 )
                      -> MLP -> item_vec (D)
score(u, i) = dot(user_vec, item_vec)   # 一個 scalar
```

- 雙塔是兩個獨立的 `nn.Module`，可各自抽換（例如把 UserTower 換成 Transformer 編序列）。
- Item tower 的 genre 特徵展示了「如何加 side feature」；若 `use_item_genres=False` 就只用 ID embedding。
- 打分數採 dot product，訓練完後可以直接把所有 item 向量塞到 ANN（FAISS / ScaNN）做線上檢索——這是 Two-Tower 之所以為業界標準的主因。

---

## 訓練範式

`src/trainer.py` 使用業界入門最常見的配方：

- **Loss**：`BCEWithLogitsLoss`（對 `score(u, i)` 做 sigmoid 後視為點擊機率）。
- **負採樣**：每個正樣本配 4 個隨機未看過的 item 作為負樣本，每個 epoch 重抽。
- **Optimizer**：Adam，`lr=1e-3`，`weight_decay=1e-6`。
- **Batch**：1024 或 2048（CPU 上也夠快）。

想改成其他訓練範式只要換一個參數：

```python
# 換成 BPR pairwise loss
trainer = Trainer(model, bundle, cfg, loss_fn=MyBPRLoss())

# 換成 in-batch sampled softmax
trainer = Trainer(model, bundle, cfg, loss_fn=MyInBatchSoftmax())

# 換 optimizer
trainer = Trainer(
    model, bundle, cfg,
    optimizer=torch.optim.AdamW(model.parameters(), lr=3e-4),
)
```

---

## 評估

`src/evaluator.py` 採用 NCF 論文標準 leave-one-out 協定：

對每位 test 使用者，用模型對 **1 個正樣本 + 99 個負樣本** 共 100 個候選打分數，計算：

- **HR@K** = 正樣本落在前 K 名的機率。
- **NDCG@K** = `1 / log2(rank + 2)` 的期望值，rank 為正樣本 0-indexed 排名。

本實作的 `evaluate()` 用向量化方式一批批算，CPU 上評估 943 位使用者不到 0.1 秒。

---

## 快速開始

```bash
# 1. 啟動 venv（已假設在 applications/ml_coding/.venv）
source /Users/jerry/projects/ai_apps/applications/ml_coding/.venv/bin/activate

# 2. 安裝依賴（如果尚未安裝）
pip install -r requirements.txt

# 3. 進入專案目錄，跑完整訓練（5 epochs, 約 10 秒）
cd /Users/jerry/projects/ai_apps/applications/ml_coding/torch_trainval_reco
python -m src.run --epochs 5 --batch-size 2048

# 4. 跑單元測試
cd /Users/jerry/projects/ai_apps
pytest tests/ml_coding/torch_trainval_reco/ -v
```

範例輸出（完整 MovieLens-100K，5 epochs）：

```
[init] num_users=943 num_items=1682 train_pairs=98306 test_users=943
[train] epoch 1 avg_loss=0.4115 time=2.5s
[eval]  epoch 1 HR@10=0.4008 NDCG@10=0.2217
...
[train] epoch 5 avg_loss=0.3515 time=2.4s
[eval]  epoch 5 HR@10=0.3998 NDCG@10=0.2239
[save]  checkpoint -> checkpoints/two_tower.pt
[infer] top-10 recommendations for user 0:
   1. item  287  logit=+1.756
   ...
```

---

## 推論（Inference）

訓練完成後 `checkpoints/two_tower.pt` 可直接拿來產出推薦清單。`src/evaluator.top_k_for_user` 封裝了最簡流程：

```python
from src.evaluator import top_k_for_user

recs = top_k_for_user(
    model=model,
    user_id=42,
    num_items=bundle.num_items,
    exclude=bundle.user_positive_set[42],  # 過濾看過的
    k=10,
)
for item_id, score in recs:
    print(item_id, score)
```

實務上線時會把 `item_tower` 先把所有 item 向量離線算出、灌進 FAISS，線上只跑 `user_tower(u)` 再做 ANN 查詢。

---

## 擴充指南

| 你想做的事 | 動到哪 |
| --- | --- |
| 換模型（加入序列、注意力） | `src/model.py` 裡的 `UserTower` / `ItemTower` |
| 換 loss（BPR、in-batch softmax、focal） | 傳 `loss_fn=` 給 `Trainer` |
| 加入更多 side feature（文字、圖片） | 在 `ItemTower.__init__` 加入特徵 encoder；在 `data.py` 的 `DatasetBundle` 塞新張量 |
| 換資料集（MovieLens-1M、Amazon Reviews） | 改 `data.py` 裡的 URL 與解析函式；其餘不動 |
| GPU 訓練 | 傳 `--device cuda` 即可（`Trainer` 會呼叫 `.to(device)`） |
| 更換評估指標（Recall@K、MRR） | 在 `evaluator.py` 加新函式；`Trainer.fit` 的呼叫點替換 |

---

## 參考資料

- He et al., *Neural Collaborative Filtering*, WWW 2017（評估協定來源）。
- Covington et al., *Deep Neural Networks for YouTube Recommendations*, RecSys 2016（Two-Tower 檢索架構）。
- GroupLens, *MovieLens-100K Dataset*, https://grouplens.org/datasets/movielens/100k/
