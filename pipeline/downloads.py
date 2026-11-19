"""Terminal market price downloads (wholesale produce): one CSV per market (written nightly by pipeline.board into data/board/downloads/) and
one Excel workbook with a tab per market (built by scripts/build_site.py from those CSVs at deploy time, so the
repo only stores text files that diff well).

Same numbers as the market pages: USDA's latest quote for each item's main pack from its main growing area. Offering
the data in more than one format, with its source, license and column meanings next to it, follows the W3C's Data on
the Web Best Practices. Standard library only: the site deploy runs without pandas.
"""
import csv
import datetime as dt
import io
import zipfile
from xml.sax.saxutils import escape

FOLDER = "downloads"
ARCHIVE = "archive"  # data/board/downloads/archive/<market day>/<file>.csv, one folder per market day, kept for good
XLSX = "terminal-market-prices.xlsx"
CLICK = "download-"  # GoatCounter event name prefix (data-goatcounter-click), so downloads show in the dashboard
# the "New" line at the top of the wholesale pages comes down on its own after three weeks
NEW_UNTIL = dt.date(2026, 12, 10)
QUOTES_ONLY = ("Days before full files began have USDA's quotes only: the usual range, season and outlook columns are "
               "blank, because those were not kept day by day.")

COLUMNS = [
    "Item", "Pack", "Growing area", "Grade or lot", "USDA quote date",
    "Low ($)", "High ($)", "Mostly low ($)", "Mostly high ($)", "Case price ($)",
    "Change from previous quote (%)", "Usual low for this time of year ($)", "Usual high for this time of year ($)",
    "Versus usual (%)", "For the season", "Next 2 weeks", "Expected price in 2 weeks ($)", "Other areas quoted that day",
]

ABOUT = [
    ("What this is", "Terminal market prices: wholesale produce prices at eight U.S. terminal markets, one tab per market, from FoodPricePal (foodpricepal.com)."),
    ("Source", "USDA Agricultural Marketing Service, Market News terminal market reports. Each row is USDA's latest quote "
               "for the item's main trade pack from its main growing area."),
    ("Prices", "U.S. dollars per package as USDA quotes it (a case, carton, sack or bin), not per pound."),
    ("Low, High, Mostly", "USDA's price range for the day, and the range most sales fell in when USDA reports one."),
    ("Case price", "The price shown on the site for that day's quote."),
    ("Change from previous quote", "Against the previous quote from the same growing area. Blank when there is no "
                                   "earlier quote; 'New growing area' when the area changed."),
    ("Usual range", "The middle half of prices in the same weeks of past years, in today's dollars."),
    ("For the season", "Low, normal or high against that usual range."),
    ("Next 2 weeks", "FoodPricePal's two-week outlook. 'No forecast' when the item has too little history or a poor record."),
    ("License", "Free to use with a link to foodpricepal.com (Creative Commons Attribution 4.0). USDA data is public."),
]


def file_name(market_slug):
    return f"terminal-market-prices-{market_slug}.csv"


OLD_NAMES = ("wholesale-produce-prices-{}.csv",)  # kept days saved before the 2026-11-19 rename


def find(folder, market_slug):
    """A market's CSV in a kept day's folder, under its current name or the name it was saved with."""
    for name in (file_name(market_slug),) + tuple(n.format(market_slug) for n in OLD_NAMES):
        if (folder / name).exists():
            return folder / name
    return None


def dated(name, day):
    """'terminal-market-prices.xlsx' -> 'terminal-market-prices-2026-11-18.xlsx': saved files don't overwrite
    each other in a buyer's Downloads folder."""
    stem, dot, ext = name.rpartition(".")
    return f"{stem}-{day}.{ext}"


def _r(v, places=2):
    return "" if v is None else round(v, places)


def rows(items, today, words):
    """One row per item for one market, in the site's item order. `words` gives the page's own wording
    (name, season, direction, expected price) so the download and the page never disagree."""
    out = []
    for i in sorted(items, key=lambda i: words["name"](i["commodity"])):
        q = i.get("quote") or {}
        chg = today.get(i["series_id"])
        out.append([
            words["name"](i["commodity"]), i["pack"], q.get("area", ""), q.get("lot", ""),
            q["date"].isoformat() if q.get("date") else "",
            _r(q.get("low")), _r(q.get("high")), _r(q.get("mostly_low")), _r(q.get("mostly_high")), _r(i["price"]),
            "New growing area" if chg == words["new_area"] else ("" if chg is None else round(100 * chg, 1)),
            _r(i.get("usual_low")), _r(i.get("usual_high")), _r(i.get("vs_norm"), 1),
            words["season"](i), words["direction"](i), _r(words["expected"](i)),
            "; ".join(f"{a or 'Not stated'}: {lo:.2f}" + (f" to {hi:.2f}" if hi and hi > lo else "") for a, lo, hi in
                      q.get("other_lots", []) + [a for a in q.get("areas", []) if a[0] != q.get("area")]),
        ])
    return out


def to_csv(table):
    """UTF-8 with a byte-order mark, so Excel opens it with the right characters."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(COLUMNS)
    w.writerows(table)
    return "﻿" + buf.getvalue()


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = list(csv.reader(f))
    return r[0], [[_num(v) for v in row] for row in r[1:]]


def _num(v):
    try:
        return float(v) if v.strip() and v.strip().lstrip("-").replace(".", "", 1).isdigit() else v
    except AttributeError:
        return v


# ---------- a minimal .xlsx (Office Open XML) writer ----------
def _col(n):
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref, v, style=0):
    st = f' s="{style}"' if style else ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return f'<c r="{ref}"{st}><v>{v:g}</v></c>' if float(v).is_integer() else f'<c r="{ref}"{st}><v>{v}</v></c>'
    if v in ("", None):
        return ""
    return f'<c r="{ref}" t="inlineStr"{st}><is><t xml:space="preserve">{escape(str(v))}</t></is></c>'


def _sheet(header, table, widths):
    cols = "".join(f'<col min="{n + 1}" max="{n + 1}" width="{w}" customWidth="1"/>' for n, w in enumerate(widths))
    body = []
    for r, row in enumerate([header] + table):
        cells = "".join(_cell(f"{_col(c)}{r + 1}", v, 1 if r == 0 else 0) for c, v in enumerate(row))
        body.append(f'<row r="{r + 1}">{cells}</row>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
            'state="frozen"/></sheetView></sheetViews>'
            f'<cols>{cols}</cols><sheetData>{"".join(body)}</sheetData></worksheet>')


def _widths(header, table):
    return [min(60, max(8, max(len(str(r[c])) for r in [header] + table) + 2)) for c in range(len(header))]


def xlsx(sheets):
    """sheets: [(tab name, header, rows)] -> bytes of an .xlsx workbook, header row bold and frozen."""
    names = [n[:31] for n, _, _ in sheets]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{n + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                             for n in range(len(sheets))) + "</Types>")
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   '</Relationships>')
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{escape(n)}" sheetId="{k + 1}" r:id="rId{k + 1}"/>' for k, n in enumerate(names))
                   + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{k + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{k + 1}.xml"/>'
                             for k in range(len(sheets)))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   "</Relationships>")
        z.writestr("xl/styles.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
                   '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
                   '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                   '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                   '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                   '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
                   '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
                   '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
                   "</styleSheet>")
        for k, (_, header, table) in enumerate(sheets):
            z.writestr(f"xl/worksheets/sheet{k + 1}.xml", _sheet(header, table, _widths(header, table)))
    return buf.getvalue()


def full(folder):
    """True when a day's files carry the usual range and outlook (kept nightly), False for quote-only history."""
    for f in sorted(folder.glob("*.csv")):
        header, table = read_csv(f)
        k = header.index("For the season")
        return any(row[k] for row in table)
    return False


def workbook(markets, folder, as_of):
    """markets: [(tab name, market slug)] in site order. Markets without a CSV are left out."""
    sheets = []
    for tab, slug in markets:
        path = find(folder, slug)
        if path:
            header, table = read_csv(path)
            sheets.append((tab, header, table))
    if not sheets:
        return None
    about = [list(r) for r in ABOUT] + [["Prices as of", as_of.isoformat() if isinstance(as_of, dt.date) else str(as_of)]]
    if not full(folder):
        about.append(["This day", QUOTES_ONLY])
    sheets.append(("About this data", ["Topic", "Details"], about))
    return xlsx(sheets)
