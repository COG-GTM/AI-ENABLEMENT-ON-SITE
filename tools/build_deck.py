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
    {"type": "quote", "text": "...", "source": "..."},
    {"type": "flow", "title": "...", "caption": "one sentence under the diagram",     # flow chart, drawn as inline SVG
     "columns": [{"label": "Inputs", "nodes": [{"id": "tree", "label": "Tree of .vi files", "sub": "read only", "kind": "input"}]},
                 {"label": "Scan", "nodes": [{"id": "scan", "label": "Fleet scan", "sub": "tools/vi_fleet_scan.py"}]}],
     "edges": [{"from": "tree", "to": "scan", "label": "optional edge text"}]}
  ]
}
A flow node's "kind" is one of input, step (default), skill, gate, output, pending; each has its own look and
the legend under the diagram names them. Nodes are laid out left to right by column, stacked inside a column,
labels wrapped to the node width; text that would not fit is rejected instead of clipped (see flow_layout).
Any slide may carry "notes": "speaker notes" (used by tools/export_pptx.py, ignored here).
validate() is the single shape check shared by this tool and export_pptx.py.
"""

import argparse
import html
import itertools
import json
import math
import re
import sys
import unicodedata
from pathlib import Path

ALLOWED_TYPES = {"title", "bullets", "two-column", "table", "stats", "bars", "quote", "section", "flow"}
MAX_SLIDES = 60
MAX_BULLETS = 8
MAX_TABLE_COLS, MAX_TABLE_ROWS = 12, 12  # one slide's worth in both outputs (HTML clips past 13 rows at 1280x720)
TABLE_LINES = 14  # wrapped table lines (header included) both outputs can show
TABLE_PX, CELL_PAD_PX, CELL_FONT_PX, HEAD_FONT_PX = 1136, 24, 19, 16  # HTML table at 1280x720; the PPTX cells are a little wider
# Flow diagrams: drawn in a 1136 x 380 box (the HTML body width at 1280x720; the PPTX scales it), columns left to
# right with a gap, nodes stacked and centred in their column. Fonts shrink as columns are added so labels keep
# about twelve characters per line; anything that still does not fit is refused, never clipped.
FLOW_W, FLOW_H, FLOW_GAP, FLOW_ROW_GAP, FLOW_PAD, FLOW_HEAD, FLOW_HEAD_PX = 1136, 380, 28, 16, 8, 26, 11
FLOW_MAX_COLS, FLOW_MAX_ROWS, FLOW_MAX_NODES, FLOW_MAX_EDGES = 7, 4, 20, 30
FLOW_MAX_LABEL_LINES, FLOW_MAX_SUB_LINES, FLOW_MAX_LABEL, FLOW_MAX_EDGE_LABEL = 3, 2, 80, 32
FLOW_FONT = {1: 20, 2: 20, 3: 20, 4: 19, 5: 18, 6: 15, 7: 14}  # label px by column count; sub is 3 px smaller
FLOW_KINDS = {  # kind -> legend text
    "input": "Your files, read only",
    "step": "Tool or step in this repository",
    "skill": "Skill: a slash command",
    "gate": "Proof: PASS / FAIL from a comparison or test run",
    "output": "File left in outputs/",
    "pending": "Not merged yet: landing in the next PR",
}
FLOW_ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}")
NARROW = set(" ijl.,:;!|'`fIt()[]{}-")
# Emoji_Modifier_Base ranges from Unicode 15.1 emoji-data.txt: the only glyphs a skin-tone modifier merges into.
MODIFIER_BASE = (
    "261D-261D 26F9-26F9 270A-270D 1F385-1F385 1F3C2-1F3C4 1F3C7-1F3C7 1F3CA-1F3CC 1F442-1F443 1F446-1F450"
    " 1F466-1F478 1F47C-1F47C 1F481-1F483 1F485-1F487 1F48F-1F48F 1F491-1F491 1F4AA-1F4AA 1F574-1F575"
    " 1F57A-1F57A 1F590-1F590 1F595-1F596 1F645-1F647 1F64B-1F64F 1F6A3-1F6A3 1F6B4-1F6B6 1F6C0-1F6C0"
    " 1F6CC-1F6CC 1F90C-1F90C 1F90F-1F90F 1F918-1F91F 1F926-1F926 1F930-1F939 1F93C-1F93E 1F977-1F977"
    " 1F9B5-1F9B6 1F9B8-1F9B9 1F9BB-1F9BB 1F9CD-1F9CF 1F9D1-1F9DD 1FAC3-1FAC5 1FAF0-1FAF8"
)
# Emoji outside _pictograph's ranges (Unicode 15.1 emoji-data.txt): Emoji_Presentation glyphs are always one em,
# text-default ones (©, ↔, ™ ...) only with VS16 after them. # * 0-9 are emoji only as keycaps.
EMOJI_DEFAULT = "231A-231B 23E9-23EC 23F0-23F0 23F3-23F3 25FD-25FE 2B1B-2B1C 2B50-2B50 2B55-2B55"
EMOJI_TEXT = (
    "00A9-00A9 00AE-00AE 203C-203C 2049-2049 2122-2122 2139-2139 2194-2199 21A9-21AA 2328-2328 23CF-23CF 23ED-23EF"
    " 23F1-23F2 23F8-23FA 24C2-24C2 25AA-25AB 25B6-25B6 25C0-25C0 25FB-25FC 2934-2935 2B05-2B07 3030-3030 303D-303D"
    " 3297-3297 3299-3299"
)
# All 254 RGI zero-width-joiner sequences of Unicode 15.1 emoji-zwj-sequences.txt with skin tones, VS16 and the
# joiners removed. One line per pattern; [a b -] is a choice, "-" meaning nothing.
ZWJ_SEQUENCES = """
[26F9 1F3C4 1F3CA 1F3CB 1F3CC 1F46E 1F46F 1F470 1F471 1F473 1F477 1F481 1F482 1F486 1F487 1F575 1F645 1F646 1F647 1F64B
 1F64D 1F64E 1F6A3 1F6B4 1F6B5 1F926 1F935 1F937 1F938 1F939 1F93C 1F93D 1F93E 1F9B8 1F9B9 1F9CD 1F9CF 1F9D4 1F9D6 1F9D7
 1F9D8 1F9D9 1F9DA 1F9DB 1F9DC 1F9DD 1F9DE 1F9DF] [2640 2642]
[1F3C3 1F6B6 1F9CE] [2640 2642]
[1F3C3 1F6B6 1F9CE] [2640 2642 -] 27A1
[1F468 1F469 1F9D1] [1F9AF 1F9BC 1F9BD] [27A1 -]
[1F468 1F469 1F9D1] [2695 2696 2708 1F33E 1F373 1F37C 1F393 1F3A4 1F3A8 1F3EB 1F3ED 1F4BB 1F4BC 1F527 1F52C 1F680 1F692
 1F9B0 1F9B1 1F9B2 1F9B3]
1F468 2764 [1F48B -] 1F468
1F469 2764 [1F48B -] [1F468 1F469]
1F9D1 2764 [1F48B -] 1F9D1
1F468 1F91D 1F468
1F469 1F91D [1F468 1F469]
1F9D1 1F91D 1F9D1
1F468 [1F468 1F469 -] 1F466 [1F466 -]
1F468 [1F468 1F469 -] 1F467 [1F466 1F467 -]
1F469 [1F469 -] 1F466 [1F466 -]
1F469 [1F469 -] 1F467 [1F466 1F467 -]
1F9D1 [1F9D1 -] 1F9D2 [1F9D2 -]
1F9D1 1F384
2764 [1F525 1FA79]
1FAF1 1FAF2
26D3 1F4A5
1F344 1F7EB
1F34B 1F7E9
1F3F3 [26A7 1F308]
1F3F4 2620
1F408 2B1B
1F415 1F9BA
1F426 [2B1B 1F525]
1F43B 2744
1F441 1F5E8
1F62E 1F4A8
1F635 1F4AB
1F636 1F32B
1F642 [2194 2195]
"""
ZWJ_SEQUENCES = {
    tuple(chr(int(c, 16)) for c in combo if c != "-")
    for line in ZWJ_SEQUENCES.replace("\n ", " ").strip().splitlines()
    for combo in itertools.product(*(t.strip("[]").split() for t in re.findall(r"\[[^]]*]|\S+", line)))
}
ZWJ_LONGEST = max(map(len, ZWJ_SEQUENCES))
MAX_TEXT = 2000
DEFAULT_ACCENT = "#2600FF"
ACCENT_RE = re.compile(r"#[0-9A-Fa-f]{6}")
REQUIRED = {  # per type: keys that must be present (types are checked in validate)
    "title": (), "section": ("title",), "bullets": ("title", "bullets"), "two-column": ("title", "left", "right"),
    "table": ("title", "columns", "rows"), "stats": ("title", "stats"), "bars": ("title", "bars"), "quote": ("text",),
    "flow": ("title", "columns"),
}
OPTIONAL_TEXT = ("title", "subtitle", "left_title", "right_title", "unit", "source", "text", "note", "notes", "caption")

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
.flow{flex:0 1 auto;min-height:0;width:100%}.flow svg{width:100%;height:100%;display:block;overflow:visible}
.flow text{font-family:inherit;fill:var(--ink)}.flow .colhead{font-size:11px;font-weight:600;letter-spacing:.8px;text-transform:uppercase;fill:var(--muted)}
.flow .nsub{fill:var(--muted)}.flow .edge{fill:none;stroke:#8A8A8A;stroke-width:1.8}.flow .edge.dashed{stroke-dasharray:6 5}
.flow .elabel{font-size:12px;fill:var(--muted);paint-order:stroke;stroke:var(--bg);stroke-width:5px;stroke-linejoin:round}
.flow .arrow{fill:#8A8A8A}
.flow .n-input rect{fill:#F3F3F3;stroke:var(--ink);stroke-width:1.5}
.flow .n-step rect{fill:#FFFFFF;stroke:var(--ink);stroke-width:1.5}
.flow .n-skill rect{fill:#EEF1FF;stroke:var(--accent);stroke-width:2}.flow .n-skill .label{font-weight:650}
.flow .n-gate rect{fill:var(--accent);stroke:var(--accent)}.flow .n-gate text{fill:#FFFFFF}.flow .n-gate .nsub{fill:#DDE3FF}.flow .n-gate .label{font-weight:650}
.flow .n-output rect{fill:var(--card);stroke:var(--muted);stroke-width:1.5}
.flow .n-pending rect{fill:none;stroke:var(--muted);stroke-width:1.5;stroke-dasharray:7 5}.flow .n-pending text{fill:var(--muted)}
.legend{display:flex;flex-wrap:wrap;gap:6px 22px;margin-top:14px;font-size:13px;color:var(--muted)}
.legend i{display:inline-block;width:13px;height:13px;border-radius:3px;margin-right:6px;vertical-align:-2px;border:1.5px solid var(--ink);background:#FFF}
.legend .k-input i{background:#F3F3F3}.legend .k-skill i{background:#EEF1FF;border-color:var(--accent)}.legend .k-gate i{background:var(--accent);border-color:var(--accent)}
.legend .k-output i{background:var(--card);border-color:var(--muted)}.legend .k-pending i{background:none;border:1.5px dashed var(--muted)}
.caption{font-size:20px;line-height:1.35;margin:12px 0 0}
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
    try:
        finite = not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)
    except OverflowError:  # JSON ints are unbounded; the renderers need a float
        finite = False
    if not finite:
        raise SystemExit(f"{where}: expected a finite number")


def _in(ch: str, ranges: str) -> bool:
    """True when ch falls in one of the space-separated hex ranges "LO-HI"."""
    return bool(ch) and any(int(lo, 16) <= ord(ch) <= int(hi, 16) for lo, hi in (r.split("-") for r in ranges.split()))


def _pictograph(ch: str) -> bool:
    return "\U0001F000" <= ch <= "\U0001FAFF" or "\u2600" <= ch <= "\u27bf"


def _mark(ch: str) -> bool:
    return unicodedata.category(ch) in ("Mn", "Me", "Cf")


def _component(text: str, i: int) -> int:
    """End of the emoji component at text[i]: the glyph, an optional VS16, and a skin tone if the glyph takes one."""
    j = i + 1 + (text[i + 1:i + 2] == "\ufe0f")
    return j + ("\U0001F3FB" <= text[j:j + 1] <= "\U0001F3FF" and _in(text[i], MODIFIER_BASE))


def glyph_units(text: str) -> list:
    """Per code point advance width in tenths of an em, rounded up for an Arial-class sans font.

    Marks and format characters are 0, and so is the rest of an emoji sequence that renders as one glyph: a
    skin tone on an Emoji_Modifier_Base, the second half of a flag pair, and the components joined by ZWJ into
    an RGI sequence (longest match in ZWJ_SEQUENCES; a chain that is no RGI sequence shows every component).
    A keycap widens its digit to a full em; a keycap mark on anything else is an ordinary zero-width mark.
    Linear in len(text): a chain is matched at most ZWJ_LONGEST components at a time.
    """
    units, i = [], 0
    while i < len(text):
        if _mark(text[i]):
            units.append(0)
            i += 1
            continue
        heads, j = [i], _component(text, i)  # start of each component in the ZWJ chain; end of the chain
        while text[j:j + 1] == "\u200d" and j + 1 < len(text) and not _mark(text[j + 1]):
            heads.append(j + 1)
            j = _component(text, j + 1)
        if len(heads) == 1 and text[j:j + 1] == "\u20e3" and text[i] in "#*0123456789":  # keycap: digit, VS16?, mark
            units += [_advance(text[i])] + [0] * (j - i - 1) + [4]
            i = j + 1
        elif len(heads) == 1 and j == i + 1 and all("\U0001F1E6" <= c <= "\U0001F1FF" for c in text[i:j + 1]) and j < len(text):
            units += [10, 0]  # flag: a regional-indicator pair
            i = j + 1
        else:
            seg, k = [0] * (j - i), 0
            while k < len(heads):
                n = 1  # components the (sub)sequence starting at heads[k] spans; its first one carries the width
                for m in range(min(ZWJ_LONGEST, len(heads) - k), 1, -1):
                    if tuple(text[h] for h in heads[k:k + m]) in ZWJ_SEQUENCES:
                        n = m
                        break
                h = heads[k]
                seg[h - i] = _advance(text[h], text[h + 1:h + 2] == "\ufe0f")
                k += n
            units += seg
            i = j
    return units


def _advance(ch: str, vs16: bool = False) -> int:
    if _pictograph(ch) or "\U0001F1E6" <= ch <= "\U0001F1FF" or unicodedata.east_asian_width(ch) in ("W", "F"):
        return 10
    if _in(ch, EMOJI_DEFAULT) or (vs16 and _in(ch, EMOJI_TEXT)):
        return 10
    if ch in NARROW:
        return 3
    if ch in "MWmw@%&":
        return 9
    return 7 if ch.isupper() else 6


def wrapped_lines(text, width: int) -> int:
    """Greedy word wrap: lines a cell `width` units wide needs for text; over-long words break by glyph."""
    lines, used = 1, 0
    for w in str(text).split():
        units = glyph_units(w)
        if used and used + 3 + sum(units) <= width:
            used += 3 + sum(units)
            continue
        lines += used > 0
        used = 0
        for u in units:
            if used and used + u > width:
                lines, used = lines + 1, 0
            used += u
    return lines


def wrap_text(text, width: int) -> list:
    """The lines wrapped_lines counts: greedy word wrap into `width` units, over-long words broken by glyph."""
    lines, line, used = [], "", 0
    for w in str(text).split():
        units = glyph_units(w)
        if used and used + 3 + sum(units) <= width:
            line, used = line + " " + w, used + 3 + sum(units)
            continue
        if used:
            lines.append(line)
        line, used = "", 0
        for ch, u in zip(w, units):
            if used and used + u > width:
                lines.append(line)
                line, used = "", 0
            line, used = line + ch, used + u
    return lines + [line] if line else lines


def _fits(text, width: int, where: str) -> None:
    """A word wider than the node would be broken mid-word; refuse it so file names stay readable."""
    for w in str(text).split():
        if sum(glyph_units(w)) > width:
            raise SystemExit(f"{where}: {w!r} is wider than the node: shorten it or use fewer columns")


def flow_layout(s: dict, where: str = "flow") -> dict:
    """Validate a flow slide and place it in the FLOW_W x FLOW_H box (HTML pixels; export_pptx scales to EMU).

    Returns {"font", "sub_font", "h" (box height used, at most FLOW_H), "columns": [{"label", "x", "w"}], "nodes": [{"id", "kind", "label", "sub", "x", "y",
    "w", "h", "lines", "sub_lines", "col"}], "edges": [{"from", "to", "label", "dashed", "x1", "y1", "x2", "y2",
    "route"}], "kinds": [kinds used, legend order]}. route is "right" (to a later column), "down" / "up" (same column)
    or "back" (to an earlier column, drawn below the nodes). Raises SystemExit on anything that would not fit.
    """
    cols = s.get("columns")
    if not isinstance(cols, list) or not 1 <= len(cols) <= FLOW_MAX_COLS:
        raise SystemExit(f"{where}.columns: expected 1-{FLOW_MAX_COLS} columns")
    edges = s.get("edges", [])
    if not isinstance(edges, list) or len(edges) > FLOW_MAX_EDGES:
        raise SystemExit(f"{where}.edges: expected a list of at most {FLOW_MAX_EDGES} edges")
    font = FLOW_FONT[len(cols)]
    sub_font = font - 3
    col_w = (FLOW_W - FLOW_GAP * (len(cols) - 1)) / len(cols)
    text_units = int((col_w - 2 * FLOW_PAD) / font * 10)
    sub_units = int((col_w - 2 * FLOW_PAD) / sub_font * 10)
    has_head = any(isinstance(c, dict) and c.get("label") for c in cols)
    top = FLOW_HEAD if has_head else 0
    out_cols, nodes, seen, totals = [], [], {}, []
    for ci, c in enumerate(cols):
        if not isinstance(c, dict) or not isinstance(c.get("nodes"), list) or not 1 <= len(c["nodes"]) <= FLOW_MAX_ROWS:
            raise SystemExit(f"{where}.columns[{ci}]: expected {{label?, nodes: [1-{FLOW_MAX_ROWS} nodes]}}")
        if "label" in c:
            _scalar(c["label"], f"{where}.columns[{ci}].label")
            if wrapped_lines(str(c["label"]).upper(), int((col_w - 2 * FLOW_PAD) / FLOW_HEAD_PX * 10)) > 1:
                raise SystemExit(f"{where}.columns[{ci}].label: does not fit on one line above the column: shorten it")
        x = ci * (col_w + FLOW_GAP)
        out_cols.append({"label": str(c.get("label", "")), "x": x, "w": col_w})
        placed, total = [], 0
        for ni, nd in enumerate(c["nodes"]):
            at = f"{where}.columns[{ci}].nodes[{ni}]"
            if not isinstance(nd, dict) or "id" not in nd or "label" not in nd:
                raise SystemExit(f"{at}: expected {{id, label, sub?, kind?}}")
            nid = nd["id"]
            if not isinstance(nid, str) or not FLOW_ID_RE.fullmatch(nid):
                raise SystemExit(f"{at}.id: expected a letter followed by up to 31 letters, digits, '_' or '-'")
            if nid in seen:
                raise SystemExit(f"{at}.id: {nid!r} is used twice")
            kind = nd.get("kind", "step")
            if kind not in FLOW_KINDS:
                raise SystemExit(f"{at}.kind: {kind!r}; allowed: {sorted(FLOW_KINDS)}")
            _scalar(nd["label"], f"{at}.label")
            if not str(nd["label"]).strip() or len(str(nd["label"])) > FLOW_MAX_LABEL:
                raise SystemExit(f"{at}.label: expected 1-{FLOW_MAX_LABEL} characters")
            lines = wrap_text(nd["label"], text_units)
            _fits(nd["label"], text_units, f"{at}.label")
            if len(lines) > FLOW_MAX_LABEL_LINES:
                raise SystemExit(f"{at}.label: wraps to {len(lines)} lines in a {len(cols)}-column diagram (max {FLOW_MAX_LABEL_LINES}): shorten it")
            sub_lines = []
            if nd.get("sub"):
                _scalar(nd["sub"], f"{at}.sub")
                if len(str(nd["sub"])) > FLOW_MAX_LABEL:
                    raise SystemExit(f"{at}.sub: longer than {FLOW_MAX_LABEL} characters")
                sub_lines = wrap_text(nd["sub"], sub_units)
                _fits(nd["sub"], sub_units, f"{at}.sub")
                if len(sub_lines) > FLOW_MAX_SUB_LINES:
                    raise SystemExit(f"{at}.sub: wraps to {len(sub_lines)} lines (max {FLOW_MAX_SUB_LINES}): shorten it")
            h = 2 * FLOW_PAD + len(lines) * font * 1.25 + (4 + len(sub_lines) * sub_font * 1.2 if sub_lines else 0)
            node = {"id": nid, "kind": kind, "label": str(nd["label"]), "sub": str(nd.get("sub", "")), "x": x, "w": col_w,
                    "h": h, "lines": lines, "sub_lines": sub_lines, "col": ci}
            seen[nid] = node
            placed.append(node)
            total += h + (FLOW_ROW_GAP if placed[:-1] else 0)
        if total > FLOW_H - top:
            raise SystemExit(f"{where}.columns[{ci}]: nodes need {total:.0f} px of {FLOW_H - top}: fewer nodes or shorter text")
        totals.append((placed, total))
        nodes += placed
    if len(nodes) > FLOW_MAX_NODES:
        raise SystemExit(f"{where}: {len(nodes)} nodes (max {FLOW_MAX_NODES}): split the diagram")
    height = top + max(t for _, t in totals) + 2  # the box shrinks to the tallest column; the slide keeps the caption close
    for placed, total in totals:
        y = top + (height - top - total) / 2
        for node in placed:
            node["y"] = y
            y += node["h"] + FLOW_ROW_GAP
    out_edges = []
    for ei, e in enumerate(edges):
        at = f"{where}.edges[{ei}]"
        if not isinstance(e, dict) or e.get("from") not in seen or e.get("to") not in seen:
            raise SystemExit(f"{at}: expected {{from, to, label?}} naming node ids on this slide")
        if e["from"] == e["to"]:
            raise SystemExit(f"{at}: an edge cannot start and end on the same node")
        extra = set(e) - {"from", "to", "label"}
        if extra:
            raise SystemExit(f"{at}: unknown key {sorted(extra)[0]!r}; the route is derived from the columns")
        label = ""
        if e.get("label"):
            _scalar(e["label"], f"{at}.label")
            label = str(e["label"])
            if len(label) > FLOW_MAX_EDGE_LABEL:
                raise SystemExit(f"{at}.label: longer than {FLOW_MAX_EDGE_LABEL} characters")
        a, b = seen[e["from"]], seen[e["to"]]
        if a["col"] < b["col"]:
            route, x1, y1, x2, y2 = "right", a["x"] + a["w"], a["y"] + a["h"] / 2, b["x"], b["y"] + b["h"] / 2
        elif a["col"] == b["col"]:
            if a["y"] < b["y"]:
                route, x1, y1, x2, y2 = "down", a["x"] + a["w"] / 2, a["y"] + a["h"], b["x"] + b["w"] / 2, b["y"]
            else:
                route, x1, y1, x2, y2 = "up", a["x"] + a["w"] / 2, a["y"], b["x"] + b["w"] / 2, b["y"] + b["h"]
        else:
            route, x1, y1, x2, y2 = "back", a["x"] + a["w"] / 2, a["y"] + a["h"], b["x"] + b["w"] / 2, b["y"] + b["h"]
        dashed = bool(e.get("dashed", False)) or "pending" in (a["kind"], b["kind"])
        out_edges.append({"from": a["id"], "to": b["id"], "label": label, "dashed": dashed, "route": route,
                          "x1": x1, "y1": y1, "x2": x2, "y2": y2})
    kinds = [k for k in FLOW_KINDS if any(n["kind"] == k for n in nodes)]
    return {"font": font, "sub_font": sub_font, "h": height, "columns": out_cols, "nodes": nodes, "edges": out_edges, "kinds": kinds}


def table_lines(columns: list, rows: list) -> list:
    """Wrapped line count of the header (upper-cased, smaller font) and of each row, columns sharing the width equally."""
    width = max(1, int((TABLE_PX / len(columns) - CELL_PAD_PX) / CELL_FONT_PX * 10))
    head = width * CELL_FONT_PX // HEAD_FONT_PX
    return [max(wrapped_lines(str(c).upper(), head) for c in columns)] + [
        max(wrapped_lines(c, width) for c in r) for r in rows
    ]


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
            _items(s["columns"], f"slide {n}.columns", limit=MAX_TABLE_COLS)
            if not isinstance(s["rows"], list) or not 1 <= len(s["rows"]) <= MAX_TABLE_ROWS:
                raise SystemExit(f"slide {n}.rows: expected 1-{MAX_TABLE_ROWS} rows: split the slide")
            for i, r in enumerate(s["rows"]):
                if not isinstance(r, list) or len(r) != len(s["columns"]):
                    raise SystemExit(f"slide {n}.rows[{i}]: expected {len(s['columns'])} cells")
                _items(r, f"slide {n}.rows[{i}]", limit=MAX_TABLE_COLS)
            if sum(table_lines(s["columns"], s["rows"])) > TABLE_LINES:
                raise SystemExit(f"slide {n}: table text wraps to more than {TABLE_LINES} lines: shorten cells or split the slide")
        if t == "flow":
            flow_layout(s, f"slide {n}")
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


def flow_svg(s: dict, n: int) -> str:
    """Inline SVG of a flow slide plus its legend. Every string goes through esc(); no href, no image, no script."""
    lay = flow_layout(s, f"slide {n}")
    font, sub_font = lay["font"], lay["sub_font"]
    parts = [f"<svg viewBox='0 0 {FLOW_W} {lay['h']:.0f}' preserveAspectRatio='xMidYMid meet' role='img' aria-label='{esc(s['title'])}'>",
             f"<defs><marker id='arrow-s{n}' viewBox='0 0 10 10' refX='9' refY='5' markerWidth='8' markerHeight='8' orient='auto-start-reverse'>"
             "<path d='M0,0 L10,5 L0,10 z' class='arrow'/></marker></defs>"]
    for c in lay["columns"]:
        if c["label"]:
            parts.append(f"<text class='colhead' x='{c['x'] + c['w'] / 2:.1f}' y='13' text-anchor='middle'>{esc(c['label'])}</text>")
    for e in lay["edges"]:
        x1, y1, x2, y2 = e["x1"], e["y1"], e["x2"], e["y2"]
        if e["route"] == "right":
            mx = (x1 + x2) / 2
            d = f"M{x1:.1f},{y1:.1f} C{mx:.1f},{y1:.1f} {mx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"
            lx, ly = mx, (y1 + y2) / 2 - 6
        elif e["route"] == "back":
            dy = 34
            d = f"M{x1:.1f},{y1:.1f} C{x1:.1f},{y1 + dy:.1f} {x2:.1f},{y2 + dy:.1f} {x2:.1f},{y2:.1f}"
            lx, ly = (x1 + x2) / 2, max(y1, y2) + dy * 0.75 + 4
        else:
            d = f"M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}"
            lx, ly = x1 + 8, (y1 + y2) / 2 + 4
        cls = "edge dashed" if e["dashed"] else "edge"
        parts.append(f"<path class='{cls}' d='{d}' marker-end='url(#arrow-s{n})'/>")
        if e["label"]:
            anchor = "start" if e["route"] in ("down", "up") else "middle"
            parts.append(f"<text class='elabel' x='{lx:.1f}' y='{ly:.1f}' text-anchor='{anchor}'>{esc(e['label'])}</text>")
    for nd in lay["nodes"]:
        rx = 20 if nd["kind"] == "gate" else 6
        parts.append(f"<g class='n-{nd['kind']}'><rect x='{nd['x']:.1f}' y='{nd['y']:.1f}' width='{nd['w']:.1f}' height='{nd['h']:.1f}' rx='{rx}'/>")
        cx = nd["x"] + nd["w"] / 2
        block = len(nd["lines"]) * font * 1.25 + (4 + len(nd["sub_lines"]) * sub_font * 1.2 if nd["sub_lines"] else 0)
        y = nd["y"] + (nd["h"] - block) / 2
        parts.append(f"<text class='label' x='{cx:.1f}' y='{y + font * 0.95:.1f}' text-anchor='middle' font-size='{font}'>")
        parts += [f"<tspan x='{cx:.1f}' dy='{0 if i == 0 else font * 1.25:.2f}'>{esc(line)}</tspan>" for i, line in enumerate(nd["lines"])]
        parts.append("</text>")
        if nd["sub_lines"]:
            y += len(nd["lines"]) * font * 1.25 + 4
            parts.append(f"<text class='nsub' x='{cx:.1f}' y='{y + sub_font * 0.95:.1f}' text-anchor='middle' font-size='{sub_font}'>")
            parts += [f"<tspan x='{cx:.1f}' dy='{0 if i == 0 else sub_font * 1.2:.2f}'>{esc(line)}</tspan>" for i, line in enumerate(nd["sub_lines"])]
            parts.append("</text>")
        parts.append("</g>")
    parts.append("</svg>")
    legend = "".join(f"<span class='k-{k}'><i></i>{esc(FLOW_KINDS[k])}</span>" for k in lay["kinds"])
    return f"<div class='flow' style='aspect-ratio:{FLOW_W}/{lay['h']:.0f}'>{''.join(parts)}</div><div class='legend'>{legend}</div>"


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
    elif t == "flow":
        body = f"<h2>{esc(s['title'])}</h2>{flow_svg(s, n)}"
        if s.get("caption"):
            body += f"<p class='caption'>{esc(s['caption'])}</p>"
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
