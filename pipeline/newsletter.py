"""The weekly email: this week's best buys, what's in season and what's pricey, with the two-week outlook.

Built from the same numbers as the grocery pages (pipeline/grocery.py) and sent through Kit (kit.com) as a
broadcast to every subscriber. Kit adds the unsubscribe link and the mailing address (set in Kit's account
settings) that CAN-SPAM requires.

Run `python -m pipeline.newsletter` (GitHub Actions does it every Saturday). Without KIT_API_KEY it only writes a
preview to data/newsletter/preview.html. It sends once per grocery week (data/newsletter/last_sent.txt).
"""

import datetime as dt
import html
import json
import os
import urllib.request

from . import cpi, grocery, store

SITE = "https://producepricetracker.com/"
API = "https://api.kit.com/v4/broadcasts"
OUT = store.DATA / "newsletter"
FONT = "font-family:Arial,Helvetica,sans-serif"
GOOD, BAD, INK, INK2, LINE = "#12733b", "#b42318", "#161616", "#484848", "#e2e2e2"


def esc(s):
    return html.escape(str(s), quote=True)


def money(x):
    return f"${x:,.2f}"


def _names(xs):
    n = [x["short"] if x["short"].split()[0] in grocery.KEEP_CAPS else x["short"][:1].lower() + x["short"][1:] for x in xs]
    return n[0] if len(n) == 1 else ", ".join(n[:-1]) + " and " + n[-1]


def _next(i):
    o = i.get("outlook") if i["status"] in ("low", "typical", "high") else None
    if o and o < 0:
        return f'<span style="color:{GOOD};font-weight:bold">likely lower</span>'
    if o and o > 0:
        return f'<span style="color:{BAD};font-weight:bold">likely higher</span>'
    return "no clear change"


def _row(i, when):
    v = i["vs_usual"]
    vs = (f'<span style="color:{GOOD if v < 0 else BAD};font-weight:bold">{abs(v)}% {"below" if v < 0 else "above"} '
          f"usual</span> for {when}") if v is not None and abs(v) >= 3 else f"about usual for {when}"
    url = f"{SITE}grocery/{i['slug']}/?ref=email"
    return (f'<tr><td style="padding:12px 0;border-bottom:1px solid {LINE};{FONT};font-size:16px;line-height:23px;color:{INK2}">'
            f'<a href="{url}" style="color:{INK};font-weight:bold;text-decoration:none">{esc(i["name"])}</a>'
            f'<span style="float:right;color:{INK};font-weight:bold">{money(i["price"])}{esc(i["unit"])}</span><br>'
            f"{vs}<br>Next 2 weeks: {_next(i)}</td></tr>")


def _section(title, rows, note=""):
    if not rows:
        return ""
    return (f'<h2 style="{FONT};font-size:22px;line-height:28px;color:{INK};margin:28px 0 6px">{esc(title)}</h2>'
            + (f'<p style="{FONT};font-size:15px;color:{INK2};margin:0 0 6px">{esc(note)}</p>' if note else "")
            + f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{"".join(rows)}</table>')


def build(today, items):
    """(subject, preview text, HTML body) for the week of `today`."""
    part = "early" if today.day <= 10 else "mid" if today.day <= 20 else "late"
    when = f"{part} {today:%B}"
    live = [i for i in items if i["this_week"]]
    buys = []
    for aisle in ("produce", "meat", "dairy"):
        buys += grocery.best_buys(live, n=4 if aisle == "produce" else 3, aisle=aisle)
    season = [i for i in live if i["in_season"] and i["aisle"] == "produce" and i["status"] in ("low", "typical")
              and grocery.q_rank(i) >= 2 and i not in buys][:6]
    pricey = sorted((i for i in live if i["status"] == "high" and i["stores"] >= grocery.MIN_STORES),
                    key=lambda i: -(i["vs_usual"] or 0))[:5]
    top = sorted(buys, key=lambda i: i["vs_usual"] or 0)[:3]
    subject = f"Best buys this week: {_names(top)}" if top else f"Supermarket prices, week of {today:%B} {today.day}"
    if len(subject) > 70:
        subject = f"Best buys this week: {_names(top[:2])}"
    preview = (f"Pricey right now: {_names(pricey[:2])}." if pricey else "What's cheap and what's pricey this week.")
    body = (f'<div style="max-width:600px;margin:0 auto;padding:8px 16px">'
            f'<p style="{FONT};font-size:14px;color:{INK2};margin:0">Produce Price Tracker</p>'
            f'<h1 style="{FONT};font-size:28px;line-height:34px;color:{INK};margin:4px 0 8px">Week of {today:%B} {today.day}, {today.year}</h1>'
            f'<p style="{FONT};font-size:16px;line-height:24px;color:{INK2};margin:0">Average advertised prices at U.S. '
            "supermarkets this week, compared with the same weeks in past years and adjusted for inflation.</p>"
            + _section("Best buys", [_row(i, when) for i in buys], "Unusually cheap right now, and good quality.")
            + _section("In season, fairly priced", [_row(i, when) for i in season])
            + _section("Pricey right now", [_row(i, when) for i in pricey])
            + f'<p style="{FONT};font-size:16px;margin:28px 0 8px"><a href="{SITE}?ref=email" style="color:#12512f;'
              'font-weight:bold">See every price this week</a></p>'
            f'<p style="{FONT};font-size:13px;line-height:19px;color:{INK2};margin:16px 0 0">Prices are averages of '
            "what supermarkets advertised, reported by USDA; your store's price may differ. Two-week outlooks are "
            "forecasts, not promises.</p></div>")
    return subject, preview, body


def send(subject, preview, body, key, when=None):
    when = when or dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10)
    payload = {"subject": subject, "preview_text": preview, "content": body, "description": f"Weekly: {subject}",
               "public": False, "send_at": when.replace(microsecond=0).isoformat()}
    req = urllib.request.Request(API, data=json.dumps(payload).encode(), method="POST",
                                 headers={"X-Kit-Api-Key": key, "Content-Type": "application/json",
                                          "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode() or "{}")


def main():
    today, items = grocery.build(grocery.rows(), cpi.Deflator(cpi.load()))
    subject, preview, body = build(today, items)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "preview.html").write_text(f"<!-- {subject} | {preview} -->\n{body}", encoding="utf-8")
    key = os.environ.get("KIT_API_KEY")
    last = (OUT / "last_sent.txt").read_text().strip() if (OUT / "last_sent.txt").exists() else ""
    if not key:
        print(f"newsletter: no KIT_API_KEY, preview only: {subject}")
        return
    if last == today.isoformat():
        print(f"newsletter: week of {today} already sent")
        return
    r = send(subject, preview, body, key)
    (OUT / "last_sent.txt").write_text(today.isoformat())
    print(f"newsletter: scheduled '{subject}' (broadcast {r.get('broadcast', {}).get('id')})")


if __name__ == "__main__":
    main()
