# torch_trainval_reco — PyTorch Two-Tower Recommender

A compact, runnable PyTorch example that covers the full training / evaluation / inference loop for a retrieval-style recommender on the **real MovieLens-100K** dataset. The architecture (Two-Tower + BCE + random negative sampling) is the most common entry-level recipe used in industry tutorials and is extensible to production setups.

Chinese version: [README.md](README.md).

---

## Why this example

| Choice | Reason |
| --- | --- |
| MovieLens-100K | Real, widely-cited benchmark (100K ratings from 943 users on 1,682 movies). 5 MB download, zero synthetic data |
| Two-Tower model | Industry-standard retrieval architecture used at YouTube / Google / Pinterest / TikTok; the two towers serve cleanly via ANN indices |
| BCE + negative sampling | The canonical recipe since NCF (He et al., 2017) — simple to implement, easy to debug, the default starting point |
| HR@K / NDCG@K | Standard leave-one-out retrieval metrics; fast and trustworthy for offline eval |

---

## Layout

```
applications/ml_coding/torch_trainval_reco/
├── README.md              # Chinese
├── README.en.md           # this file
├── requirements.txt
├── src/
│   ├── config.py          # all tunable knobs + paths
│   ├── data.py            # download, parse, split, torch Dataset
│   ├── model.py           # UserTower / ItemTower / TwoTowerModel
│   ├── trainer.py         # training loop (pluggable loss / optimizer)
│   ├── evaluator.py       # HR@K / NDCG@K + top-K inference
│   └── run.py             # CLI entry point
├── data/                  # auto-downloaded on first run
└── checkpoints/           # saved weights

tests/ml_coding/torch_trainval_reco/
├── conftest.py
├── test_data.py
├── test_model.py
├── test_evaluator.py
└── test_trainer.py
```

---

## Data pipeline

`src/data.py` downloads MovieLens-100K on first run from `https://files.grouplens.org/datasets/movielens/ml-100k.zip`, caches it under `data/`, and:

1. Parses `u.data` (`user_id\titem_id\trating\ttimestamp`) and `u.item` (19-dim genre multi-hot).
2. Treats interactions as **implicit feedback** (any rating counts as a positive). Drops users with <5 interactions — standard NCF filtering.
3. Reindexes user / item ids into contiguous `0..N-1` for `nn.Embedding`.
4. **Leave-one-out split**: each user's most-recent interaction → test, the rest → train.
5. Samples 99 unseen items per test positive for the ranking protocol (NCF paper standard).

The training `InteractionDataset` resamples random negatives (4 per positive) each epoch.

To iterate quickly on a subset:

```bash
python -m src.run --max-users 100 --epochs 1
```

---

## Model

```
UserTower:   user_id  -> Embedding(num_users, D) -> MLP -> user_vec (D)
ItemTower:   item_id  -> Embedding(num_items, D)
                         concat( genre multi-hot, 19 )
                      -> MLP -> item_vec (D)
score(u, i) = dot(user_vec, item_vec)   # one scalar
```

- The two towers are independent `nn.Module`s — swap either side (e.g. Transformer for the user tower, text encoder on the item tower) without touching the rest of the pipeline.
- The item tower demonstrates how to add side features (genres); flip `use_item_genres=False` for ID-only.
- Dot-product scoring is ANN-friendly — after training you precompute item vectors into FAISS / ScaNN and serve the user tower online. This is the reason Two-Tower is the de-facto production retrieval architecture.

---

## Training paradigm

`src/trainer.py` uses the simplest industry-standard recipe:

- **Loss:** `BCEWithLogitsLoss` on `score(u, i)` (treated as click logits).
- **Negatives:** 4 random unseen items per positive, resampled each epoch.
- **Optimizer:** Adam, `lr=1e-3`, `weight_decay=1e-6`.
- **Batch:** 1024–2048 (CPU-friendly).

Swap the paradigm by passing one argument:

```python
# BPR pairwise loss
trainer = Trainer(model, bundle, cfg, loss_fn=MyBPRLoss())

# in-batch sampled softmax
trainer = Trainer(model, bundle, cfg, loss_fn=MyInBatchSoftmax())

# AdamW
trainer = Trainer(
    model, bundle, cfg,
    optimizer=torch.optim.AdamW(model.parameters(), lr=3e-4),
)
```

---

## Evaluation

Standard NCF leave-one-out protocol (`src/evaluator.py`): for each test user, score 1 positive + 99 sampled negatives and compute

- **HR@K**: probability the positive lands in the top-K.
- **NDCG@K**: `1 / log2(rank + 2)` averaged over users (rank is 0-indexed).

The vectorized `evaluate()` finishes all 943 users in <0.1 s on CPU.

---

## Quickstart

```bash
# 1. activate the project venv
source /Users/jerry/projects/ai_apps/applications/ml_coding/.venv/bin/activate

# 2. install deps (first time only)
pip install -r requirements.txt

# 3. full training (5 epochs, ~10s on CPU)
cd /Users/jerry/projects/ai_apps/applications/ml_coding/torch_trainval_reco
python -m src.run --epochs 5 --batch-size 2048

# 4. run the test suite
cd /Users/jerry/projects/ai_apps
pytest tests/ml_coding/torch_trainval_reco/ -v
```

Sample output (full MovieLens-100K, 5 epochs):

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

## Inference

After training, `checkpoints/two_tower.pt` holds the weights. The simplest path:

```python
from src.evaluator import top_k_for_user

recs = top_k_for_user(
    model=model,
    user_id=42,
    num_items=bundle.num_items,
    exclude=bundle.user_positive_set[42],  # filter already-seen items
    k=10,
)
for item_id, score in recs:
    print(item_id, score)
```

In production you would precompute every item vector via `item_tower`, build an ANN index, and serve the `user_tower` plus ANN lookup online.

---

## Extensibility cheat-sheet

| What you want | Where to touch |
| --- | --- |
| Different model (sequences, attention) | `UserTower` / `ItemTower` in `src/model.py` |
| Different loss (BPR, in-batch softmax, focal) | Pass `loss_fn=` to `Trainer` |
| More side features (text, image) | Add encoders to `ItemTower.__init__`; add tensors to `DatasetBundle` |
| Different dataset (MovieLens-1M, Amazon Reviews) | Edit URL + parsers in `src/data.py`; rest stays the same |
| GPU training | `python -m src.run --device cuda` |
| Other metrics (Recall@K, MRR) | Add function in `evaluator.py`; update `Trainer.fit` call site |

---

## References

- He et al., *Neural Collaborative Filtering*, WWW 2017 — source of the LOO evaluation protocol.
- Covington et al., *Deep Neural Networks for YouTube Recommendations*, RecSys 2016 — Two-Tower retrieval at scale.
- GroupLens, *MovieLens-100K Dataset*, https://grouplens.org/datasets/movielens/100k/
