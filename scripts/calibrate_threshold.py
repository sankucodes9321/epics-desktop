"""Summarize cosine scores for distinct pairs of enrolled templates."""
import argparse
import csv
import sys

import numpy as np
from redis.exceptions import RedisError

from scripts.exports import new_export, save_json
from privacy.runtime import startup
from privacy.errors import PipelineError
from privacy.config import load_key, redis_client
from privacy.store import Store
from privacy.matching import references


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv")
    parser.add_argument("--json")
    args = parser.parse_args()
    startup()
    try:
        records = Store(redis_client()).all_records()
        if len(records) < 2:
            print("Enroll at least two users to measure impostor comparisons.")
            return 0
        with references(records, load_key()) as matrix:
            similarities = np.clip(matrix @ matrix.T, -1, 1)
        row, col = np.triu_indices(len(similarities), k=1)
        owners = np.repeat(np.arange(len(records)), np.array([r.count for r in records], dtype=int)).astype(int)
        same = owners[row] == owners[col]
        for label, mask in (("genuine", same), ("impostor", ~same)):
            values = similarities[row[mask], col[mask]]
            if values.size:
                print(f"{label}: n={values.size} mean={values.mean():.4f} "
                      f"min={values.min():.4f} median={np.median(values):.4f} max={values.max():.4f}")
            else:
                print(f"{label}: no pairs")
        if not same.any():
            print("Enroll a second template for at least one user to estimate FRR.")
            return 0
        rows = []
        genuine, impostor = similarities[row[same], col[same]], similarities[row[~same], col[~same]]
        for i in range(30, 96):
            cutoff = i / 100
            rows.append((cutoff, float((impostor >= cutoff).mean()), float((genuine < cutoff).mean())))
        best = min(rows, key=lambda r: abs(r[1] - r[2]))
        eer = (best[1] + best[2]) / 2
        print("threshold FAR FRR")
        for entry in rows:
            print(*entry)
        print("estimated EER", eer, "at", best[0])
        if args.csv:
            with new_export(args.csv) as handle:
                writer = csv.writer(handle)
                writer.writerow(("threshold", "far", "frr", "eer_estimate", "eer_threshold"))
                writer.writerows((*entry, eer, best[0]) for entry in rows)
        if args.json:
            save_json(args.json, dict(threshold_far_frr=rows, eer=eer, eer_threshold=best[0]))
        return 0
    except OSError:
        print("Cannot create export. Choose fresh writable paths.", file=sys.stderr)
    except RedisError:
        print("Redis unavailable. Check connection and credentials.", file=sys.stderr)
    except PipelineError as error:
        print(error, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
