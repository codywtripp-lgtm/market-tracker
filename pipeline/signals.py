"""Shared building blocks for the signal backtest and the forecast (pandas).

Weekly price index per commodity x market = mean weekly log change across every
standard-grade series (pack/size) quoted in both weeks. Using changes rather than
levels lets packs with different prices be combined.
"""

import math
import re

import pandas as pd

from . import store

NON_STANDARD = re.compile(r"fair|poor|ordinary|holdover|decay|damage|scar|fine|mixed condition", re.I)
UP_WORDS = re.compile(r"\b(higher|firmer|stronger|advanc|increas)", re.I)
DOWN_WORDS = re.compile(r"\b(lower|weaker|declin|decreas)", re.I)
COLS = ["report_date", "commodity", "variety", "pack_size", "item_size", "properties", "organic",
        "appearance", "condition", "quality", "unit_price", "market", "market_tone"]


def tone_score(text):
    """+1 higher, -1 lower, 0 steady/mixed, None if no comment."""
    if not text:
        return None
    up, down = bool(UP_WORDS.search(text)), bool(DOWN_WORDS.search(text))
    return 1 if up and not down else -1 if down and not up else 0


def load(source, since=None):
    """Standard-grade rows with a price, plus week (Monday), series id and tone score."""
    frames = []
    for path in sorted((store.DATA / "raw" / source).glob("*/*.csv")):
        if since and path.stem < since[:7]:
            continue
        frames.append(pd.read_csv(path, usecols=COLS, dtype=str, keep_default_na=False))
    if not frames:
        return pd.DataFrame(columns=COLS + ["week", "series", "tone"])
    df = pd.concat(frames, ignore_index=True)
    if since:
        df = df[df["report_date"] >= since]
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df = df[df["unit_price"] > 0]
    std = ~(df["appearance"].str.contains(NON_STANDARD) | df["condition"].str.contains(NON_STANDARD)
            | df["quality"].str.contains(NON_STANDARD))
    df = df[std].copy()
    df["week"] = pd.to_datetime(df["report_date"]).dt.to_period("W-SUN").dt.start_time
    df["series"] = df[["market", "variety", "pack_size", "item_size", "properties", "organic"]].agg("|".join, axis=1)
    df["tone"] = df["market_tone"].map(tone_score).astype(float)
    return df


def index_changes(df):
    """(commodity, market, week) -> mean weekly log price change across series."""
    wk = df.groupby(["commodity", "market", "series", "week"])["unit_price"].median().reset_index()
    wk = wk.sort_values("week")
    g = wk.groupby(["commodity", "market", "series"])
    wk["prev_week"] = g["week"].shift()
    wk["prev_price"] = g["unit_price"].shift()
    wk = wk[(wk["week"] - wk["prev_week"]).dt.days == 7].copy()
    wk["chg"] = (wk["unit_price"] / wk["prev_price"]).map(math.log)
    return wk.groupby(["commodity", "market", "week"])["chg"].mean()


def weekly_tone(df):
    """(commodity, market, week) -> mean USDA tone score (-1..1)."""
    return df.dropna(subset=["tone"]).groupby(["commodity", "market", "week"])["tone"].mean()
