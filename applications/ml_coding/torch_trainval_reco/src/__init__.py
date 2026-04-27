"""Two-Tower recommendation model on MovieLens-100K.

Layout:
    config.py     - hyperparameters and paths
    data.py       - dataset download, parsing, torch Dataset
    model.py      - Two-Tower model with pluggable towers
    trainer.py    - BCE + negative-sampling training loop
    evaluator.py  - HR@K and NDCG@K under leave-one-out protocol
    run.py        - CLI entry point
"""
