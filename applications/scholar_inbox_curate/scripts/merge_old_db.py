"""One-shot merge of an older scholar_curate.db into the current one.

Merge rules:
- Papers absent from the local db are inserted from the old db.
- Papers present in both: old citation_snapshots are merged in (deduplicated
  on paper_id+checked_at+source). The local paper row is retained unless its
  citation_count is NULL or 0, in which case the old row replaces it so the
  historical citation data is not lost.
- Operational tables (ingestion_runs, scraped_dates) are left untouched to
  avoid auto-increment / foreign-key collisions.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

PAPER_COLUMNS = [
    "id", "title", "authors", "abstract", "url", "arxiv_id", "doi",
    "venue", "year", "published_date", "scholar_inbox_score", "status",
    "manual_status", "ingested_at", "last_cited_check", "citation_count",
    "citation_velocity", "category", "resolve_failures",
]


def merge(old_path: Path, new_path: Path, dry_run: bool = False) -> None:
    if not old_path.exists():
        sys.exit(f"old db not found: {old_path}")
    if not new_path.exists():
        sys.exit(f"new db not found: {new_path}")

    conn = sqlite3.connect(new_path)
    conn.row_factory = sqlite3.Row
    conn.execute(f"ATTACH DATABASE '{old_path}' AS old")

    # 1. Classify papers.
    only_in_old = [r["id"] for r in conn.execute(
        "SELECT id FROM old.papers o "
        "WHERE NOT EXISTS (SELECT 1 FROM main.papers n WHERE n.id = o.id)"
    )]
    overlapping = [r["id"] for r in conn.execute(
        "SELECT id FROM old.papers o "
        "WHERE EXISTS (SELECT 1 FROM main.papers n WHERE n.id = o.id)"
    )]

    # Subset of overlapping papers whose local citation_count is NULL or 0.
    to_replace = [r["id"] for r in conn.execute(
        "SELECT n.id FROM main.papers n JOIN old.papers o ON n.id = o.id "
        "WHERE n.citation_count IS NULL OR n.citation_count = 0"
    )]

    print(f"papers only in old: {len(only_in_old)}")
    print(f"overlapping papers: {len(overlapping)}")
    print(f"  -> will replace local row (citation_count NULL/0): {len(to_replace)}")

    cols_csv = ", ".join(PAPER_COLUMNS)
    placeholders = ", ".join(["?"] * len(PAPER_COLUMNS))

    inserted_papers = 0
    replaced_papers = 0
    inserted_snaps = 0
    skipped_snaps = 0

    try:
        conn.execute("BEGIN")

        # 2. Insert papers only in old.
        for pid in only_in_old:
            row = conn.execute(
                f"SELECT {cols_csv} FROM old.papers WHERE id = ?", (pid,)
            ).fetchone()
            conn.execute(
                f"INSERT INTO main.papers ({cols_csv}) VALUES ({placeholders})",
                tuple(row),
            )
            inserted_papers += 1

        # 3. Replace rows for overlapping papers where new.citation_count is null/0.
        assignments = ", ".join(f"{c}=?" for c in PAPER_COLUMNS if c != "id")
        update_cols = [c for c in PAPER_COLUMNS if c != "id"]
        for pid in to_replace:
            row = conn.execute(
                f"SELECT {', '.join(update_cols)} FROM old.papers WHERE id = ?", (pid,)
            ).fetchone()
            conn.execute(
                f"UPDATE main.papers SET {assignments} WHERE id = ?",
                tuple(row) + (pid,),
            )
            replaced_papers += 1

        # 4. Merge citation_snapshots for every paper present in old
        #    (which, after step 2, is also present in main). Dedup on
        #    (paper_id, checked_at, source).
        snap_rows = conn.execute(
            "SELECT paper_id, checked_at, total_citations, yearly_breakdown, source "
            "FROM old.citation_snapshots"
        ).fetchall()
        for snap in snap_rows:
            exists = conn.execute(
                "SELECT 1 FROM main.citation_snapshots "
                "WHERE paper_id = ? AND checked_at = ? AND source = ? LIMIT 1",
                (snap["paper_id"], snap["checked_at"], snap["source"]),
            ).fetchone()
            if exists:
                skipped_snaps += 1
                continue
            conn.execute(
                "INSERT INTO main.citation_snapshots "
                "(paper_id, checked_at, total_citations, yearly_breakdown, source) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    snap["paper_id"], snap["checked_at"], snap["total_citations"],
                    snap["yearly_breakdown"], snap["source"],
                ),
            )
            inserted_snaps += 1

        if dry_run:
            conn.execute("ROLLBACK")
            print("\n[dry-run] rolled back")
        else:
            conn.execute("COMMIT")
            print("\ncommitted")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        print(f"  inserted papers:           {inserted_papers}")
        print(f"  replaced paper rows:       {replaced_papers}")
        print(f"  inserted snapshot rows:    {inserted_snaps}")
        print(f"  skipped snapshot rows:     {skipped_snaps}  (already present)")

    # Final totals.
    p = conn.execute("SELECT COUNT(*) FROM main.papers").fetchone()[0]
    s = conn.execute("SELECT COUNT(*) FROM main.citation_snapshots").fetchone()[0]
    print(f"\nfinal main.papers:            {p}")
    print(f"final main.citation_snapshots: {s}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--old", required=True, type=Path)
    parser.add_argument("--new", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    merge(args.old, args.new, dry_run=args.dry_run)
