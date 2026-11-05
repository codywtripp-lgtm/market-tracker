"""Two-week boxed beef and chicken calls, walk-forward, on the live method and scored as the site shows them.

    python scripts/backtest_meat.py

Tried 2026-11-05 and dropped: Huber regression alone (beef miss 4.18% vs the blend's 4.07%), and the grocery rule of no
call against an 8-week run (beef calls 83.6% -> 77.2% right, chicken no better).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import cpi, meat  # noqa: E402


def main():
    r = meat.replay(meat.panel(meat.rows(), cpi.Deflator(cpi.load())))
    on = meat.choose(r)
    calls, final, move = meat.called(r, on)
    print(meat.record(r, on))
    r = r.assign(call=calls, right=np.sign(final) == np.sign(move), way=np.sign(final), on=on)
    for kind, g in r[r["call"]].groupby("kind"):
        print(f"\n{kind} calls by year")
        print(g.groupby("year")["right"].agg(["size", "mean"]).round(3).T.to_string())
        # calls on the same item in the same direction under 4 weeks apart are one episode, not separate proof
        spells = sum((x["week"].sort_values().diff() > pd.Timedelta(weeks=4)).sum() + 1 for _, x in g.groupby(["series_id", "way"]))
        print("separate episodes:", spells)
        print(g.groupby("series_id")["right"].agg(["size", "mean"]).round(2).sort_values("size", ascending=False).to_string())


if __name__ == "__main__":
    main()
