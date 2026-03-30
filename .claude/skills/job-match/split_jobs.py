#!/usr/bin/env python3
"""Split fetched LinkedIn jobs JSON into batch files for parallel agent matching.

Pure mechanical split — no filtering or intelligence. All filtering is done
by the LLM agents that process each batch.
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Split LinkedIn jobs JSON into batch files")
    parser.add_argument("--input", required=True, help="Path to full jobs JSON file")
    parser.add_argument("--output-dir", required=True, help="Directory for batch output files")
    parser.add_argument("--batch-size", type=int, default=50, help="Jobs per batch file (default: 50)")

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with open(input_path) as f:
        jobs = json.load(f)

    print(f"Loaded {len(jobs)} jobs from {input_path}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    batches = [jobs[i:i + args.batch_size] for i in range(0, len(jobs), args.batch_size)]

    manifest = {
        "total_jobs": len(jobs),
        "batch_size": args.batch_size,
        "num_batches": len(batches),
        "batch_files": [],
    }

    for idx, batch in enumerate(batches):
        filename = f"batch_{idx + 1:03d}.json"
        batch_path = output_dir / filename
        with open(batch_path, "w") as f:
            json.dump(batch, f, indent=2)
        manifest["batch_files"].append(filename)
        print(f"  Wrote {len(batch)} jobs to {batch_path}")

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n=== Done ===")
    print(f"  {len(batches)} batch file(s) in {output_dir}/")
    print(f"  Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
