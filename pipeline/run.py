"""Fetch USDA reports and store them.

Daily:     python -m pipeline.run
Backfill:  python -m pipeline.run --start 2016-01-01 --end 2016-12-31 [--sources terminal beef]

One failing report never stops the others; failures are listed at the end and
the exit code is non-zero only if every report failed.
"""

import argparse
import datetime as dt
import logging
import os
import sys

from . import config, normalize, store
from .usda import Client, USDAError

log = logging.getLogger("pipeline")

SOURCES = ["terminal", "shipping_point", "retail", "beef", "chicken", "movement"]


def run(client, start, end, sources):
    fetched_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    results, failures = [], []

    def job(source, name, fn):
        try:
            rows = [r for r in fn() if r]
            new, updated = store.write_rows(source, rows)
            results.append((source, name, len(rows), new, updated))
            log.info("%-15s %-28s rows=%-6d new=%-6d updated=%d", source, name, len(rows), new, updated)
        except (USDAError, ValueError, KeyError) as e:
            failures.append((source, name, str(e)[:300]))
            log.error("%-15s %-28s FAILED: %s", source, name, e)

    if "terminal" in sources:
        for slug, market in config.TERMINAL_REPORTS.items():
            job("terminal", f"{slug} {market}", lambda slug=slug, market=market: [
                normalize.terminal(r, market, fetched_at)
                for r in client.mars(slug, "Report Details", start, end)
                if r.get("commodity") in config.PRODUCE_COMMODITIES])

    if "shipping_point" in sources:
        for slug in config.SHIPPING_POINT_REPORTS:
            job("shipping_point", slug, lambda slug=slug: [
                normalize.shipping_point(r, fetched_at)
                for r in client.mars(slug, "Report Details", start, end)
                if r.get("commodity") in config.PRODUCE_COMMODITIES])

    if "retail" in sources:
        for slug in config.RETAIL_REPORTS:
            job("retail", slug, lambda slug=slug: [
                normalize.retail(r, fetched_at)
                for r in client.mars(slug, "Report Details", start, end)
                if r.get("commodity") in config.RETAIL_COMMODITIES])

    if "movement" in sources:
        for slug in config.MOVEMENT_REPORTS:
            job("movement", slug, lambda slug=slug: [
                normalize.movement(r, fetched_at)
                for r in client.mars(slug, "Report Details", start, end)
                if r.get("commodity") in config.PRODUCE_COMMODITIES])

    if "beef" in sources:
        for section in config.BEEF_SECTIONS:
            job("beef", section, lambda section=section: [
                row
                for r in client.datamart(config.BEEF_REPORT, section, start, end)
                for row in normalize.beef(r, section, fetched_at)])

    if "chicken" in sources:
        job("chicken", config.CHICKEN_REPORT, lambda: [
            normalize.chicken(r, fetched_at)
            for r in client.mars(config.CHICKEN_REPORT, config.CHICKEN_SECTION, start, end)])

    return results, failures


def write_summary(start, end, results, failures):
    lines = [f"## USDA fetch {start} to {end}", "",
             "| source | report | rows | new | updated |", "|---|---|---|---|---|"]
    lines += [f"| {s} | {n} | {rows} | {new} | {up} |" for s, n, rows, new, up in results]
    if failures:
        lines += ["", "### Failed (will retry next run)", ""]
        lines += [f"- **{s} {n}**: {e}" for s, n, e in failures]
    text = "\n".join(lines) + "\n"
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
    print(text)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=dt.date.fromisoformat)
    p.add_argument("--end", type=dt.date.fromisoformat)
    p.add_argument("--sources", nargs="+", choices=SOURCES, default=SOURCES)
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    end = a.end or dt.date.today()
    start = a.start or end - dt.timedelta(days=config.DAILY_LOOKBACK_DAYS)
    results, failures = run(Client(), start, end, a.sources)
    write_summary(start, end, results, failures)
    if failures and not results:
        sys.exit(1)


if __name__ == "__main__":
    main()
