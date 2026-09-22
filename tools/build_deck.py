#!/usr/bin/env python3
"""Build a self-contained HTML slide deck from a small JSON outline.

Usage:
    python tools/build_deck.py templates/deck-outline-example.json outputs/example-deck.html
    python tools/build_deck.py my-outline.json outputs/my-deck.html --title-suffix "draft"

Open the result in a browser (or Devin Desktop's preview). Arrow keys / space / click to move, P to print.
No external files, fonts, scripts, or network. Standard library only.

Outline format (see templates/deck-outline-example.json):
{
  "title": "...", "subtitle": "...", "footer": "...", "accent": "#2600FF",   # accent is optional
  "slides": [
    {"type": "title"},                                   # uses deck title/subtitle
    {"type": "bullets", "title": "...", "bullets": ["...", "..."], "note": "optional footnote"},
    {"type": "section", "title": "...", "subtitle": "..."},
    {"type": "two-column", "title": "...", "left_title": "Pros", "left": [...], "right_title": "Cons", "right": [...]},
    {"type": "table", "title": "...", "columns": ["A", "B"], "rows": [["1", "2"], ...]},
    {"type": "stats", "title": "...", "stats": [{"value": "28.1", "label": "days battery life"}, ...]},
    {"type": "bars", "title": "...", "bars": [{"label": "...", "value": 2.4, "max": 3.0}, ...], "unit": "mA"},
    {"type": "quote", "text": "...", "source": "..."}
  ]
}
Any slide may carry "notes": "speaker notes" (used by tools/export_pptx.py, ignored here).
validate() is the single shape check shared by this tool and export_pptx.py.
"""

import argparse
import html
import json
import math
import re
import sys
from pathlib import Path

ALLOWED_TYPES = {"title", "bullets", "two-column", "table", "stats", "bars", "quote", "section"}
MAX_SLIDES = 60
MAX_BULLETS = 8
MAX_TABLE_ROWS = 12  # what still fits on one PPTX slide
MAX_TEXT = 2000
DEFAULT_ACCENT = "#2600FF"
ACCENT_RE = re.compile(r"#[0-9A-Fa-f]{6}")
REQUIRED = {  # per type: keys that must be present (types are checked in validate)
    "title": (), "section": ("title",), "bullets": ("title", "bullets"), "two-column": ("title", "left", "right"),
    "table": ("title", "columns", "rows"), "stats": ("title", "stats"), "bars": ("title", "bars"), "quote": ("text",),
}
OPTIONAL_TEXT = ("title", "subtitle", "left_title", "right_title", "unit", "source", "text", "note", "notes")

CSS = """
:root{--bg:#FCFCFC;--ink:#141414;--muted:#7D7D7D;--accent:#2600FF;--line:#E7E7E7;--card:#F7F6F5;--fill:#97ACFF}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:#141414;font-family:-apple-system,"Segoe UI",Helvetica,Arial,sans-serif;color:var(--ink)}
.deck{position:relative;width:100vw;height:100vh;overflow:hidden}
.slide{position:absolute;inset:0;display:none;padding:56px 72px;background:var(--bg);flex-direction:column}
.slide.active{display:flex}
.slide h1{font-size:44px;margin:0 0 12px;font-weight:650;letter-spacing:-.5px}
.slide h2{font-size:34px;margin:0 0 28px;font-weight:650;letter-spacing:-.3px;border-bottom:2px solid var(--accent);padding-bottom:12px}
.slide .sub{font-size:22px;color:var(--muted)}
.slide ul{font-size:24px;line-height:1.5;margin:0;padding-left:28px}
.slide li{margin-bottom:10px}
.cols{display:flex;gap:40px;flex:1}.cols>div{flex:1;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:20px 24px}
.cols h3{margin:0 0 12px;font-size:22px;color:var(--accent)}
table{border-collapse:collapse;width:100%;font-size:19px}th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line)}th{color:var(--muted);font-weight:600;font-size:16px;text-transform:uppercase;letter-spacing:.5px}
.stats{display:flex;gap:28px;flex:1;align-items:center}.stat{flex:1;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:28px;text-align:center}
.stat .v{font-size:56px;font-weight:700;color:var(--accent)}.stat .l{font-size:18px;color:var(--muted);margin-top:8px}
.bars{display:flex;flex-direction:column;gap:14px;flex:1;justify-content:center}.bar{display:grid;grid-template-columns:220px 1fr 90px;align-items:center;gap:14px;font-size:20px}
.bar .track{height:26px;background:#F3F3F3;border-radius:4px;overflow:hidden}.bar .fill{height:100%;background:var(--fill);border-right:2px solid var(--accent)}.bar .val{text-align:right;font-variant-numeric:tabular-nums}
.quote{flex:1;display:flex;flex-direction:column;justify-content:center}.quote p{font-size:34px;line-height:1.35;margin:0 0 20px;font-weight:500}.quote .src{font-size:20px;color:var(--muted)}
.note{margin-top:auto;font-size:15px;color:var(--muted)}
.footer{position:absolute;left:72px;right:72px;bottom:22px;display:flex;justify-content:space-between;font-size:14px;color:var(--muted)}
.title-slide{justify-content:center}.section{justify-content:center}.section h1{color:var(--accent)}
@media print{body{background:#fff}.slide{display:flex;position:relative;page-break-after:always;height:100vh}.footer{position:absolute}}
"""

JS = """
(function(){var s=document.querySelectorAll('.slide'),i=0;
function show(n){i=(n+s.length)%s.length;s.forEach(function(e,k){e.classList.toggle('active',k===i)});location.hash='#'+(i+1)}
document.addEventListener('keydown',function(e){if(e.key==='ArrowRight'||e.key===' '||e.key==='PageDown'){show(i+1)}else if(e.key==='ArrowLeft'||e.key==='PageUp'){show(i-1)}else if(e.key==='Home'){show(0)}else if(e.key==='End'){show(s.length-1)}else if(e.key==='p'||e.key==='P'){window.print()}});
document.addEventListener('click',function(e){if(e.clientX>window.innerWidth/2){show(i+1)}else{show(i-1)}});
var h=parseInt(location.hash.slice(1),10);show(isNaN(h)?0:h-1);})();
"""


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def _scalar(v, where: str) -> None:
    if isinstance(v, bool) or not isinstance(v, (str, int, float)):
        raise SystemExit(f"{where}: expected text or a number, got {type(v).__name__}")
    if len(str(v)) > MAX_TEXT:
        raise SystemExit(f"{where}: text longer than {MAX_TEXT} characters")
    try:
        str(v).encode("utf-8")  # JSON allows lone surrogates; UTF-8 output does not
    except UnicodeEncodeError:
        raise SystemExit(f"{where}: text is not valid Unicode")


def _items(v, where: str, limit: int = MAX_BULLETS) -> None:
    if not isinstance(v, list) or not v:
        raise SystemExit(f"{where}: expected a non-empty list")
    if len(v) > limit:
        raise SystemExit(f"{where}: more than {limit} items: split the slide")
    for i, x in enumerate(v):
        _scalar(x, f"{where}[{i}]")


def _number(v, where: str) -> None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise SystemExit(f"{where}: expected a finite number")


def validate(outline) -> dict:
    """Reject anything that is not a well-formed outline. Returns the outline unchanged."""
    if not isinstance(outline, dict) or not isinstance(outline.get("title"), str):
        raise SystemExit("outline must be a JSON object with a text 'title'")
    for k in ("title", "subtitle", "footer"):
        if k in outline:
            _scalar(outline[k], k)
    accent = outline.get("accent", DEFAULT_ACCENT)
    if not isinstance(accent, str) or not ACCENT_RE.fullmatch(accent):
        raise SystemExit("accent must look like '#RRGGBB'")
    slides = outline.get("slides")
    if not isinstance(slides, list) or not 1 <= len(slides) <= MAX_SLIDES:
        raise SystemExit(f"deck must have 1-{MAX_SLIDES} slides")
    for n, s in enumerate(slides, 1):
        if not isinstance(s, dict):
            raise SystemExit(f"slide {n}: expected an object")
        t = s.get("type")
        if t not in ALLOWED_TYPES:
            raise SystemExit(f"slide {n}: unknown type {t!r}; allowed: {sorted(ALLOWED_TYPES)}")
        for k in REQUIRED[t]:
            if k not in s:
                raise SystemExit(f"slide {n} ({t}): missing {k!r}")
        for k in OPTIONAL_TEXT:
            if k in s:
                _scalar(s[k], f"slide {n}.{k}")
        for k in ("bullets", "left", "right"):
            if k in s:
                _items(s[k], f"slide {n}.{k}")
        if t == "table":
            _items(s["columns"], f"slide {n}.columns", limit=12)
            if not isinstance(s["rows"], list) or not 1 <= len(s["rows"]) <= MAX_TABLE_ROWS:
                raise SystemExit(f"slide {n}.rows: expected 1-{MAX_TABLE_ROWS} rows: split the slide")
            for i, r in enumerate(s["rows"]):
                if not isinstance(r, list) or len(r) != len(s["columns"]):
                    raise SystemExit(f"slide {n}.rows[{i}]: expected {len(s['columns'])} cells")
                _items(r, f"slide {n}.rows[{i}]", limit=12)
        if t == "stats":
            if not isinstance(s["stats"], list) or not 1 <= len(s["stats"]) <= 6:
                raise SystemExit(f"slide {n}.stats: expected 1-6 items")
            for i, x in enumerate(s["stats"]):
                if not isinstance(x, dict) or "value" not in x or "label" not in x:
                    raise SystemExit(f"slide {n}.stats[{i}]: expected {{value, label}}")
                _scalar(x["value"], f"slide {n}.stats[{i}].value")
                _scalar(x["label"], f"slide {n}.stats[{i}].label")
        if t == "bars":
            if not isinstance(s["bars"], list) or not 1 <= len(s["bars"]) <= MAX_BULLETS:
                raise SystemExit(f"slide {n}.bars: expected 1-{MAX_BULLETS} items")
            for i, b in enumerate(s["bars"]):
                if not isinstance(b, dict) or "label" not in b or "value" not in b:
                    raise SystemExit(f"slide {n}.bars[{i}]: expected {{label, value[, max]}}")
                _scalar(b["label"], f"slide {n}.bars[{i}].label")
                _number(b["value"], f"slide {n}.bars[{i}].value")
                if "max" in b:
                    _number(b["max"], f"slide {n}.bars[{i}].max")
    return outline


def li(items) -> str:
    if len(items) > MAX_BULLETS:
        raise SystemExit(f"more than {MAX_BULLETS} bullets on one slide: split it")
    return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ul>"


def render_slide(s: dict, deck: dict, n: int, total: int) -> str:
    t = s.get("type")
    if t not in ALLOWED_TYPES:
        raise SystemExit(f"slide {n}: unknown type {t!r}; allowed: {sorted(ALLOWED_TYPES)}")
    body = ""
    cls = "slide"
    if t == "title":
        cls += " title-slide"
        body = f"<h1>{esc(deck['title'])}</h1><div class='sub'>{esc(deck.get('subtitle', ''))}</div>"
    elif t == "section":
        cls += " section"
        body = f"<h1>{esc(s['title'])}</h1><div class='sub'>{esc(s.get('subtitle', ''))}</div>"
    elif t == "bullets":
        body = f"<h2>{esc(s['title'])}</h2>{li(s['bullets'])}"
    elif t == "two-column":
        body = (f"<h2>{esc(s['title'])}</h2><div class='cols'>"
                f"<div><h3>{esc(s.get('left_title', ''))}</h3>{li(s['left'])}</div>"
                f"<div><h3>{esc(s.get('right_title', ''))}</h3>{li(s['right'])}</div></div>")
    elif t == "table":
        head = "".join(f"<th>{esc(c)}</th>" for c in s["columns"])
        rows = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in s["rows"])
        body = f"<h2>{esc(s['title'])}</h2><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"
    elif t == "stats":
        cards = "".join(f"<div class='stat'><div class='v'>{esc(x['value'])}</div><div class='l'>{esc(x['label'])}</div></div>" for x in s["stats"])
        body = f"<h2>{esc(s['title'])}</h2><div class='stats'>{cards}</div>"
    elif t == "bars":
        unit = esc(s.get("unit", ""))
        rows = []
        for b in s["bars"]:
            value = float(b["value"])
            maximum = float(b.get("max", max(float(x["value"]) for x in s["bars"])))
            pct = 0 if maximum <= 0 else max(0.0, min(100.0, value / maximum * 100))
            rows.append(f"<div class='bar'><div>{esc(b['label'])}</div><div class='track'><div class='fill' style='width:{pct:.1f}%'></div></div><div class='val'>{value:g} {unit}</div></div>")
        body = f"<h2>{esc(s['title'])}</h2><div class='bars'>{''.join(rows)}</div>"
    elif t == "quote":
        body = f"<div class='quote'><p>&ldquo;{esc(s['text'])}&rdquo;</p><div class='src'>{esc(s.get('source', ''))}</div></div>"
    if s.get("note"):
        body += f"<div class='note'>{esc(s['note'])}</div>"
    footer = f"<div class='footer'><span>{esc(deck.get('footer', ''))}</span><span>{n} / {total}</span></div>"
    return f"<section class='{cls}' id='s{n}'>{body}{footer}</section>"


def build(outline: dict) -> str:
    validate(outline)
    slides = outline["slides"]
    total = len(slides)
    css = CSS.replace(DEFAULT_ACCENT, outline.get("accent", DEFAULT_ACCENT).upper())
    rendered = "".join(render_slide(s, outline, i + 1, total) for i, s in enumerate(slides))
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{esc(outline['title'])}</title>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><style>{css}</style></head>"
            f"<body><div class='deck'>{rendered}</div><script>{JS}</script></body></html>")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outline", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--title-suffix", default="")
    a = ap.parse_args(argv)
    try:
        outline = json.loads(a.outline.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"{a.outline}: cannot read outline JSON ({e})")
    validate(outline)
    if a.title_suffix:
        outline["title"] = f"{outline['title']} ({a.title_suffix})"
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(build(outline), encoding="utf-8")
    print(f"wrote {a.output} ({len(outline['slides'])} slides)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
