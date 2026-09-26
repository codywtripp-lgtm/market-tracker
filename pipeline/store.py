"""Monthly CSV partitions: data/raw/<source>/<YYYY>/<YYYY-MM>.csv, deduplicated by row_id."""

import csv
import logging
from collections import Counter, defaultdict
from pathlib import Path

from .normalize import COLUMNS

log = logging.getLogger(__name__)

DATA = Path(__file__).resolve().parent.parent / "data"


def partition_path(source, report_date):
    return DATA / "raw" / source / report_date[:4] / f"{report_date[:7]}.csv"


def read_partition(path):
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["row_id"]: r for r in csv.DictReader(f)}


def write_rows(source, rows):
    """Upsert rows into their monthly files. Returns (new, updated) counts."""
    ids = Counter(r["row_id"] for r in rows)
    dupes = sum(n - 1 for n in ids.values() if n > 1)
    if dupes:
        # Two incoming rows share a key: the key is missing a distinguishing field.
        log.warning("%s: %d incoming rows collided on row_id (last one kept)", source, dupes)
    by_path = defaultdict(list)
    for r in rows:
        if r.get("report_date"):
            by_path[partition_path(source, r["report_date"])].append(r)
    new = updated = 0
    for path, batch in by_path.items():
        existing = read_partition(path)
        for r in batch:
            r = {k: str(v) for k, v in r.items()}
            old = existing.get(r["row_id"])
            if old is None:
                new += 1
            elif {k: v for k, v in old.items() if k != "fetched_at"} != \
                 {k: v for k, v in r.items() if k != "fetched_at"}:
                updated += 1
            else:
                continue  # unchanged: keep the original fetched_at so files don't churn
            existing[r["row_id"]] = r
        path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(existing.values(), key=lambda r: (r["report_date"], r["market"], r["commodity"],
                                                           r["variety"], r["pack_size"], r["item_size"], r["row_id"]))
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
            w.writeheader()
            w.writerows(ordered)
    return new, updated


def iter_all(source=None):
    root = DATA / "raw"
    pattern = f"{source}/*/*.csv" if source else "*/*/*.csv"
    for path in sorted(root.glob(pattern)):
        with open(path, newline="", encoding="utf-8") as f:
            yield from csv.DictReader(f)
