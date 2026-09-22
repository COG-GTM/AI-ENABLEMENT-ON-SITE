#!/usr/bin/env python3
"""Export the deck outline JSON (same input as build_deck.py) to a .pptx file.

Usage:
    python tools/export_pptx.py templates/deck-outline-example.json outputs/example-deck.pptx

Standard library only: the .pptx is a ZIP of hand-written OOXML parts. No images, no network.
Widescreen 16:9 (12192000 x 6858000 EMU), one slide master, one slide layout, dark text on white,
one accent colour ("accent" in the outline, else build_deck.DEFAULT_ACCENT).
A slide with "notes" gets a speaker-notes part; "note" stays an on-slide footnote as in the HTML deck.
Output is deterministic: fixed ZIP timestamps, fixed core.xml dates, parts written in sorted order.
Exit 0 on success, 1 with a one-line reason on bad input (validation lives in build_deck.validate).

Part names, content types and relationship types below were checked against these references
(ECMA-376 1st edition as published by c-rex.net, and Microsoft's Open XML documentation):
  Package structure ... https://learn.microsoft.com/en-us/office/open-xml/presentation/structure-of-a-presentationml-document
  Presentation part ... https://c-rex.net/samples/ooxml/e1/Part1/OOXML_P1_Fundamentals_Presentation_topic_ID0ECWHM.html
  Slide part .......... https://c-rex.net/samples/ooxml/e1/Part1/OOXML_P1_Fundamentals_Slide_topic_ID0E2OIM.html
  Slide layout part ... https://c-rex.net/samples/ooxml/e1/Part1/OOXML_P1_Fundamentals_Slide_topic_ID0EAHJM.html
  Slide master part ... https://c-rex.net/samples/ooxml/e1/Part1/OOXML_P1_Fundamentals_Slide_topic_ID0E52JM.html
  Notes slide part .... https://c-rex.net/samples/ooxml/e1/Part1/OOXML_P1_Fundamentals_Notes_topic_ID0EACHM.html
  Notes master part ... https://c-rex.net/samples/ooxml/e1/Part1/OOXML_P1_Fundamentals_Notes_topic_ID0ENOGM.html
  Presentation props .. https://c-rex.net/samples/ooxml/e1/Part1/OOXML_P1_Fundamentals_Presentation_topic_ID0EJJIM.html
  View props part ..... https://c-rex.net/samples/ooxml/e1/Part1/OOXML_P1_Fundamentals_View_topic_ID0E13KM.html
  Table styles part ... https://c-rex.net/samples/ooxml/e1/Part1/OOXML_P1_Fundamentals_Table_topic_ID0EONOM.html
  Theme part .......... https://c-rex.net/samples/ooxml/e1/Part1/OOXML_P1_Fundamentals_Theme_topic_ID0EUYNM.html
  Core properties ..... https://c-rex.net/samples/ooxml/e1/Part1/OOXML_P1_Fundamentals_Core_topic_ID0ED3CO.html
  Extended properties . https://c-rex.net/samples/ooxml/e1/Part1/OOXML_P1_Fundamentals_Extended_topic_ID0EFIDO.html
  OPC namespaces ...... https://c-rex.net/samples/ooxml/e1/Part2/OOXML_P2_Open_Packaging_Conventions_Standard_topic_ID0E3EGM.html
Two places where the 1st-edition text and shipping files differ; this tool follows shipping files:
  - core-properties relationship type: Part 2 Annex F (and every producer) uses the
    .../package/2006/relationships/metadata/core-properties URI; Part 1 prints an officedocument variant.
  - presProps content type: 1st edition prints ...presentationml.presentationProperties+xml; PowerPoint and
    LibreOffice write ...presentationml.presProps+xml (checked in a LibreOffice 7.3 export), used here.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_deck  # noqa: E402

# --- package constants ---------------------------------------------------------------------------
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
URI_TABLE = "http://schemas.openxmlformats.org/drawingml/2006/table"
XMLNS = f'xmlns:a="{NS_A}" xmlns:r="{NS_R}" xmlns:p="{NS_P}"'
RT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
REL = {
    "officeDocument": RT + "officeDocument",
    "core": "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties",
    "app": RT + "extended-properties",
    "slideMaster": RT + "slideMaster",
    "slideLayout": RT + "slideLayout",
    "slide": RT + "slide",
    "notesSlide": RT + "notesSlide",
    "notesMaster": RT + "notesMaster",
    "theme": RT + "theme",
    "presProps": RT + "presProps",
    "viewProps": RT + "viewProps",
    "tableStyles": RT + "tableStyles",
}
CT_PML = "application/vnd.openxmlformats-officedocument.presentationml."
CT = {
    "presentation": CT_PML + "presentation.main+xml",
    "slide": CT_PML + "slide+xml",
    "slideLayout": CT_PML + "slideLayout+xml",
    "slideMaster": CT_PML + "slideMaster+xml",
    "notesSlide": CT_PML + "notesSlide+xml",
    "notesMaster": CT_PML + "notesMaster+xml",
    "presProps": CT_PML + "presProps+xml",
    "viewProps": CT_PML + "viewProps+xml",
    "tableStyles": CT_PML + "tableStyles+xml",
    "theme": "application/vnd.openxmlformats-officedocument.theme+xml",
    "core": "application/vnd.openxmlformats-package.core-properties+xml",
    "app": "application/vnd.openxmlformats-officedocument.extended-properties+xml",
}
ZIP_DATE = (1980, 1, 1, 0, 0, 0)
FIXED_TIME = "2000-01-01T00:00:00Z"

# --- geometry (EMU) and palette -----------------------------------------------------------------
W, H = 12192000, 6858000
MX, MY = 685800, 457200          # page margins
BODY_Y, BODY_H = 1676400, 4267200   # body ends where the footnote starts
FOOT_Y = 6400800
INK, MUTED, LINE, CARD, TRACK = "141414", "7D7D7D", "E7E7E7", "F7F6F5", "F3F3F3"
CTRL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]")
EMPTY_PARA = '<a:p><a:endParaRPr lang="en-US"/></a:p>'


def esc(s) -> str:
    """XML-escape text and drop characters XML 1.0 cannot carry."""
    return escape(CTRL_RE.sub("", str(s)), {'"': "&quot;"})


# --- DrawingML text ------------------------------------------------------------------------------
def run(text, sz: int, color: str = INK, bold: bool = False) -> str:
    b = ' b="1"' if bold else ""
    return (f'<a:r><a:rPr lang="en-US" sz="{sz}"{b} dirty="0"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
            f"</a:rPr><a:t>{esc(text)}</a:t></a:r>")


def para(text, sz: int, color: str = INK, bold: bool = False, algn: str = "l", bullet: bool = False,
         space_before: int = 0) -> str:
    ppr = f'<a:pPr algn="{algn}"' + (' marL="342900" indent="-342900"' if bullet else "") + ">"
    if space_before:
        ppr += f'<a:spcBef><a:spcPts val="{space_before}"/></a:spcBef>'
    ppr += ('<a:buClr><a:srgbClr val="%s"/></a:buClr><a:buFont typeface="Arial"/><a:buChar char="&#8226;"/>' % MUTED
            if bullet else "<a:buNone/>")
    ppr += "</a:pPr>"
    return f"<a:p>{ppr}{run(text, sz, color, bold)}</a:p>"


def sp(sid: int, name: str, x: int, y: int, w: int, h: int, paras: str = "", fill: str | None = None,
       line: str | None = None, anchor: str = "t", ph: str | None = None, inset: int = 91440) -> str:
    fill_xml = f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else "<a:noFill/>"
    line_xml = f'<a:ln w="9525"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>' if line else "<a:ln><a:noFill/></a:ln>"
    nvpr = f'<p:nvPr><p:ph type="{ph}"/></p:nvPr>' if ph else "<p:nvPr/>"
    cnv = '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>' if ph else '<p:cNvSpPr txBox="1"/>'
    body = ""
    if paras or ph:
        body = (f'<p:txBody><a:bodyPr wrap="square" lIns="{inset}" tIns="{inset}" rIns="{inset}" bIns="{inset}" '
                f'anchor="{anchor}"><a:normAutofit/></a:bodyPr><a:lstStyle/>{paras or EMPTY_PARA}</p:txBody>')
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{esc(name)}"/>{cnv}{nvpr}</p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>{fill_xml}{line_xml}</p:spPr>{body}</p:sp>')


def table(sid: int, x: int, y: int, w: int, columns: list, rows: list) -> str:
    ncol = len(columns)
    col_w = w // ncol
    body_sz, head_sz = 1400, 1200
    sizes = [head_sz] + [body_sz] * len(rows)
    # row = cell margins + wrapped lines at 1.2 spacing (sz is in 1/100 pt, 12700 EMU per pt); spare height is shared out
    heights = [91440 + lines * sz * 1524 // 10 for lines, sz in zip(build_deck.table_lines(columns, rows), sizes)]
    slack = min(152400, max(0, BODY_H - sum(heights)) // len(heights))
    heights = [h + slack for h in heights]
    grid = "".join(f'<a:gridCol w="{col_w}"/>' for _ in columns)

    def cell(text, sz, color, bold, upper=False):
        t = str(text).upper() if upper else text
        return (f'<a:tc><a:txBody><a:bodyPr/><a:lstStyle/>{para(t, sz, color, bold)}</a:txBody>'
                f'<a:tcPr marL="91440" marR="91440" marT="45720" marB="45720"><a:lnB w="9525"><a:solidFill>'
                f'<a:srgbClr val="{LINE}"/></a:solidFill></a:lnB><a:noFill/></a:tcPr></a:tc>')

    head = f'<a:tr h="{heights[0]}">' + "".join(cell(c, head_sz, MUTED, True, upper=True) for c in columns) + "</a:tr>"
    body = "".join(f'<a:tr h="{h}">' + "".join(cell(c, body_sz, INK, False) for c in r) + "</a:tr>"
                   for h, r in zip(heights[1:], rows))
    return (f'<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="{sid}" name="Table"/>'
            f'<p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr><p:nvPr/></p:nvGraphicFramePr>'
            f'<p:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{col_w * ncol}" cy="{sum(heights)}"/></p:xfrm>'
            f'<a:graphic><a:graphicData uri="{URI_TABLE}"><a:tbl><a:tblPr firstRow="1" bandRow="1"/>'
            f"<a:tblGrid>{grid}</a:tblGrid>{head}{body}</a:tbl></a:graphicData></a:graphic></p:graphicFrame>")


# --- slides --------------------------------------------------------------------------------------
def heading(s: dict, sid: int, accent: str) -> str:
    """Title placeholder plus the accent rule under it (mirrors the HTML h2)."""
    return (sp(sid, "Title", MX, MY, W - 2 * MX, 914400, para(s["title"], 3200, INK, True), anchor="b", ph="title", inset=0)
            + sp(sid + 1, "Rule", MX, MY + 960120, W - 2 * MX, 25400, fill=accent))


def bullets(items, sz: int = 2000) -> str:
    return "".join(para(x, sz, INK, bullet=True, space_before=600) for x in items)


def slide_shapes(s: dict, deck: dict, n: int, total: int, accent: str) -> str:
    t = s["type"]
    cw = W - 2 * MX
    out = []
    sid = 2
    if t == "title":
        out.append(sp(sid, "Title", MX, 1828800, cw, 1828800, para(deck["title"], 4400, INK, True), anchor="b", ph="title", inset=0))
        out.append(sp(sid + 1, "Subtitle", MX, 3733800, cw, 914400, para(deck.get("subtitle", ""), 2000, MUTED), inset=0))
    elif t == "section":
        out.append(sp(sid, "Title", MX, 1828800, cw, 1828800, para(s["title"], 4000, accent, True), anchor="b", ph="title", inset=0))
        out.append(sp(sid + 1, "Subtitle", MX, 3733800, cw, 914400, para(s.get("subtitle", ""), 2000, MUTED), inset=0))
    elif t == "quote":
        out.append(sp(sid, "Quote", MX, BODY_Y, cw, 3200400, para(f"\u201c{s['text']}\u201d", 2800, INK), anchor="ctr", inset=0))
        out.append(sp(sid + 1, "Source", MX, BODY_Y + 3200400, cw, 609600, para(s.get("source", ""), 1600, MUTED), inset=0))
    else:
        out.append(heading(s, sid, accent))
        sid += 2
        if t == "bullets":
            out.append(sp(sid, "Body", MX, BODY_Y, cw, BODY_H, bullets(s["bullets"]), inset=0))
        elif t == "two-column":
            gap = 457200
            col = (cw - gap) // 2
            for i, (side, key) in enumerate((("left", "left_title"), ("right", "right_title"))):
                x = MX + i * (col + gap)
                paras = para(s.get(key, ""), 1800, accent, True) + bullets(s[side], 1800)
                out.append(sp(sid + i, f"Column {i + 1}", x, BODY_Y, col, BODY_H, paras, fill=CARD, line=LINE, inset=182880))
        elif t == "table":
            out.append(table(sid, MX, BODY_Y, cw, s["columns"], s["rows"]))
        elif t == "stats":
            gap = 304800
            k = len(s["stats"])
            card_w = (cw - gap * (k - 1)) // k
            card_h = 2286000
            y = BODY_Y + (BODY_H - card_h) // 2
            for i, x in enumerate(s["stats"]):
                paras = para(x["value"], 4400, accent, True, algn="ctr") + para(x["label"], 1400, MUTED, algn="ctr", space_before=600)
                out.append(sp(sid + i, f"Stat {i + 1}", MX + i * (card_w + gap), y, card_w, card_h, paras, fill=CARD, line=LINE, anchor="ctr"))
        elif t == "bars":
            unit = s.get("unit", "")
            label_w, val_w, gap, row_gap = 2743200, 1097280, 182880, 182880
            track_x = MX + label_w + gap
            track_w = cw - label_w - val_w - 2 * gap
            k = len(s["bars"])
            row_h = min(457200, (BODY_H - (k - 1) * row_gap) // k)
            y = BODY_Y + (BODY_H - (k * row_h + (k - 1) * row_gap)) // 2
            default_max = max(float(b["value"]) for b in s["bars"])
            for i, b in enumerate(s["bars"]):
                value = float(b["value"])
                maximum = float(b.get("max", default_max))
                pct = 0.0 if maximum <= 0 else max(0.0, min(1.0, value / maximum))
                ry = y + i * (row_h + row_gap)
                out.append(sp(sid, "Label", MX, ry, label_w, row_h, para(b["label"], 1600, INK), anchor="ctr", inset=0))
                out.append(sp(sid + 1, "Track", track_x, ry + 91440, track_w, row_h - 182880, fill=TRACK))
                if pct > 0:
                    out.append(sp(sid + 2, "Fill", track_x, ry + 91440, int(track_w * pct), row_h - 182880, fill=accent))
                out.append(sp(sid + 3, "Value", track_x + track_w + gap, ry, val_w, row_h, para(f"{value:g} {unit}".rstrip(), 1600, INK, algn="r"), anchor="ctr", inset=0))
                sid += 4
    sid += 20
    if s.get("note"):
        out.append(sp(sid, "Note", MX, 5943600, cw, 381000, para(s["note"], 1200, MUTED), anchor="b", inset=0))
    out.append(sp(sid + 1, "Footer", MX, FOOT_Y, cw // 2, 304800, para(deck.get("footer", ""), 1000, MUTED), inset=0))
    out.append(sp(sid + 2, "Page", W - MX - cw // 2, FOOT_Y, cw // 2, 304800, para(f"{n} / {total}", 1000, MUTED, algn="r"), inset=0))
    return "".join(out)


SPTREE_HEAD = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm>'
               '<a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')


def slide_xml(s: dict, deck: dict, n: int, total: int, accent: str) -> str:
    return (f'<p:sld {XMLNS}><p:cSld><p:spTree>{SPTREE_HEAD}{slide_shapes(s, deck, n, total, accent)}</p:spTree></p:cSld>'
            "<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>")


def notes_xml(text) -> str:
    return (f'<p:notes {XMLNS}><p:cSld><p:spTree>{SPTREE_HEAD}'
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Slide Image"/><p:cNvSpPr><a:spLocks noGrp="1" noRot="1" noChangeAspect="1"/>'
            '</p:cNvSpPr><p:nvPr><p:ph type="sldImg"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp>'
            '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Notes"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>'
            f"{para(text, 1200)}</p:txBody></p:sp></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>")


# --- master, layout, theme and the small fixed parts ------------------------------------------------
CLR_MAP = ('bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" '
           'accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"')
BG = '<p:bg><p:bgPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>'


def lvl(sz: int, color: str, bold: bool = False) -> str:
    b = ' b="1"' if bold else ""
    return (f'<a:lvl1pPr algn="l"><a:defRPr sz="{sz}"{b}><a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
            '<a:latin typeface="+mn-lt"/></a:defRPr></a:lvl1pPr>')


def master_xml() -> str:
    return (f'<p:sldMaster {XMLNS}><p:cSld>{BG}<p:spTree>{SPTREE_HEAD}'
            + sp(2, "Title", MX, MY, W - 2 * MX, 914400, ph="title", inset=0)
            + sp(3, "Body", MX, BODY_Y, W - 2 * MX, BODY_H, ph="body", inset=0)
            + f"</p:spTree></p:cSld><p:clrMap {CLR_MAP}/>"
            '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
            f"<p:txStyles><p:titleStyle>{lvl(3200, INK, True)}</p:titleStyle><p:bodyStyle>{lvl(2000, INK)}</p:bodyStyle>"
            f"<p:otherStyle>{lvl(1800, INK)}</p:otherStyle></p:txStyles></p:sldMaster>")


def layout_xml() -> str:
    return (f'<p:sldLayout {XMLNS} type="obj" preserve="1"><p:cSld name="Title and Content"><p:spTree>{SPTREE_HEAD}'
            + sp(2, "Title", MX, MY, W - 2 * MX, 914400, ph="title", inset=0)
            + sp(3, "Body", MX, BODY_Y, W - 2 * MX, BODY_H, ph="body", inset=0)
            + "</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>")


def notes_master_xml() -> str:
    return (f'<p:notesMaster {XMLNS}><p:cSld>{BG}<p:spTree>{SPTREE_HEAD}'
            '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Slide Image"/><p:cNvSpPr><a:spLocks noGrp="1" noRot="1" noChangeAspect="1"/>'
            '</p:cNvSpPr><p:nvPr><p:ph type="sldImg"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x="1143000" y="685800"/>'
            '<a:ext cx="4572000" cy="2571750"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/>'
            f'<a:ln w="12700"><a:solidFill><a:srgbClr val="{LINE}"/></a:solidFill></a:ln></p:spPr></p:sp>'
            + sp(3, "Notes", 685800, 3429000, 5486400, 4572000, ph="body")
            + f"</p:spTree></p:cSld><p:clrMap {CLR_MAP}/><p:notesStyle>{lvl(1200, INK)}</p:notesStyle></p:notesMaster>")


def theme_xml(accent: str) -> str:
    fill = '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
    ln = '<a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>'
    effect = "<a:effectStyle><a:effectLst/></a:effectStyle>"
    return (f'<a:theme xmlns:a="{NS_A}" name="Neutral"><a:themeElements><a:clrScheme name="Neutral">'
            f'<a:dk1><a:srgbClr val="{INK}"/></a:dk1><a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>'
            f'<a:dk2><a:srgbClr val="{MUTED}"/></a:dk2><a:lt2><a:srgbClr val="{CARD}"/></a:lt2>'
            f'<a:accent1><a:srgbClr val="{accent}"/></a:accent1><a:accent2><a:srgbClr val="{MUTED}"/></a:accent2>'
            f'<a:accent3><a:srgbClr val="{LINE}"/></a:accent3><a:accent4><a:srgbClr val="{CARD}"/></a:accent4>'
            f'<a:accent5><a:srgbClr val="{TRACK}"/></a:accent5><a:accent6><a:srgbClr val="{INK}"/></a:accent6>'
            f'<a:hlink><a:srgbClr val="{accent}"/></a:hlink><a:folHlink><a:srgbClr val="{MUTED}"/></a:folHlink></a:clrScheme>'
            '<a:fontScheme name="Neutral"><a:majorFont><a:latin typeface="Arial"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
            '<a:minorFont><a:latin typeface="Arial"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
            f'<a:fmtScheme name="Neutral"><a:fillStyleLst>{fill * 3}</a:fillStyleLst><a:lnStyleLst>{ln * 3}</a:lnStyleLst>'
            f"<a:effectStyleLst>{effect * 3}</a:effectStyleLst>"
            f"<a:bgFillStyleLst>{fill * 3}</a:bgFillStyleLst></a:fmtScheme></a:themeElements>"
            "<a:objectDefaults/><a:extraClrSchemeLst/></a:theme>")


def rels(pairs: list[tuple[str, str]]) -> str:
    """pairs of (relationship key, target) -> rId1.. in the given order."""
    body = "".join(f'<Relationship Id="rId{i}" Type="{REL[k]}" Target="{t}"/>' for i, (k, t) in enumerate(pairs, 1))
    return f'<Relationships xmlns="{NS_REL}">{body}</Relationships>'


def presentation_xml(count: int, has_notes: bool) -> str:
    # rels order: master, slides 1..N, presProps, viewProps, theme, tableStyles[, notesMaster]
    sld_ids = "".join(f'<p:sldId id="{256 + i}" r:id="rId{2 + i}"/>' for i in range(count))
    notes = f'<p:notesMasterIdLst><p:notesMasterId r:id="rId{count + 6}"/></p:notesMasterIdLst>' if has_notes else ""
    return (f'<p:presentation {XMLNS} saveSubsetFonts="1">'
            '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
            f"{notes}<p:sldIdLst>{sld_ids}</p:sldIdLst>"
            f'<p:sldSz cx="{W}" cy="{H}"/><p:notesSz cx="6858000" cy="9144000"/>'
            '<p:defaultTextStyle><a:defPPr><a:defRPr lang="en-US"/></a:defPPr></p:defaultTextStyle></p:presentation>')


def core_xml(title) -> str:
    return ('<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f"<dc:title>{esc(title)}</dc:title><dc:creator>export_pptx.py</dc:creator>"
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{FIXED_TIME}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{FIXED_TIME}</dcterms:modified></cp:coreProperties>')


def app_xml(count: int) -> str:
    return ('<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            f"<Application>export_pptx.py</Application><Slides>{count}</Slides>"
            "<PresentationFormat>Widescreen</PresentationFormat></Properties>")


PRES_PROPS = f"<p:presentationPr {XMLNS}/>"
VIEW_PROPS = (f"<p:viewPr {XMLNS}><p:slideViewPr><p:cSldViewPr><p:cViewPr><p:scale><a:sx n=\"1\" d=\"1\"/><a:sy n=\"1\" d=\"1\"/>"
              "</p:scale><p:origin x=\"0\" y=\"0\"/></p:cViewPr></p:cSldViewPr></p:slideViewPr></p:viewPr>")
TABLE_STYLES = f'<a:tblStyleLst xmlns:a="{NS_A}" def="{{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}}"/>'


# --- package -------------------------------------------------------------------------------------
def build_parts(outline: dict) -> dict[str, str]:
    """Return {part name: xml text} for a validated outline. Content types are derived from this map."""
    build_deck.validate(outline)
    accent = outline.get("accent", build_deck.DEFAULT_ACCENT)[1:].upper()
    slides = outline["slides"]
    total = len(slides)
    has_notes = any(s.get("notes") for s in slides)
    parts: dict[str, str] = {
        "_rels/.rels": rels([("officeDocument", "ppt/presentation.xml"), ("core", "docProps/core.xml"), ("app", "docProps/app.xml")]),
        "docProps/core.xml": core_xml(outline["title"]),
        "docProps/app.xml": app_xml(total),
        "ppt/presentation.xml": presentation_xml(total, has_notes),
        "ppt/presProps.xml": PRES_PROPS,
        "ppt/viewProps.xml": VIEW_PROPS,
        "ppt/tableStyles.xml": TABLE_STYLES,
        "ppt/theme/theme1.xml": theme_xml(accent),
        "ppt/slideMasters/slideMaster1.xml": master_xml(),
        "ppt/slideMasters/_rels/slideMaster1.xml.rels": rels([("slideLayout", "../slideLayouts/slideLayout1.xml"), ("theme", "../theme/theme1.xml")]),
        "ppt/slideLayouts/slideLayout1.xml": layout_xml(),
        "ppt/slideLayouts/_rels/slideLayout1.xml.rels": rels([("slideMaster", "../slideMasters/slideMaster1.xml")]),
    }
    pres_rels = [("slideMaster", "slideMasters/slideMaster1.xml")]
    pres_rels += [("slide", f"slides/slide{i}.xml") for i in range(1, total + 1)]
    pres_rels += [("presProps", "presProps.xml"), ("viewProps", "viewProps.xml"), ("theme", "theme/theme1.xml"), ("tableStyles", "tableStyles.xml")]
    if has_notes:
        pres_rels.append(("notesMaster", "notesMasters/notesMaster1.xml"))
        parts["ppt/notesMasters/notesMaster1.xml"] = notes_master_xml()
        parts["ppt/notesMasters/_rels/notesMaster1.xml.rels"] = rels([("theme", "../theme/theme2.xml")])
        parts["ppt/theme/theme2.xml"] = theme_xml(accent)
    parts["ppt/_rels/presentation.xml.rels"] = rels(pres_rels)
    for i, s in enumerate(slides, 1):
        parts[f"ppt/slides/slide{i}.xml"] = slide_xml(s, outline, i, total, accent)
        slide_rels = [("slideLayout", "../slideLayouts/slideLayout1.xml")]
        if s.get("notes"):
            slide_rels.append(("notesSlide", f"../notesSlides/notesSlide{i}.xml"))
            parts[f"ppt/notesSlides/notesSlide{i}.xml"] = notes_xml(s["notes"])
            parts[f"ppt/notesSlides/_rels/notesSlide{i}.xml.rels"] = rels([("notesMaster", "../notesMasters/notesMaster1.xml"), ("slide", f"../slides/slide{i}.xml")])
        parts[f"ppt/slides/_rels/slide{i}.xml.rels"] = rels(slide_rels)
    parts["[Content_Types].xml"] = content_types(parts)
    return parts


def content_type_of(name: str) -> str | None:
    if name.endswith(".rels"):
        return None  # covered by the Default for the rels extension
    if name == "ppt/presentation.xml":
        return CT["presentation"]
    if name.startswith("ppt/theme/"):
        return CT["theme"]
    if name.startswith("docProps/"):
        return CT[name[len("docProps/"):-4]]
    key = re.sub(r"\d+\.xml$", "", name.rsplit("/", 1)[-1]).removesuffix(".xml")  # slide3.xml -> slide
    return CT[key]


def content_types(parts: dict[str, str]) -> str:
    overrides = "".join(f'<Override PartName="/{n}" ContentType="{content_type_of(n)}"/>'
                        for n in sorted(parts) if content_type_of(n))
    return (f'<Types xmlns="{NS_CT}"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            f'<Default Extension="xml" ContentType="application/xml"/>{overrides}</Types>')


def write_pptx(parts: dict[str, str], out: Path) -> None:
    """Encode everything first, then write a private sibling temp file and swap it in, so a failure never leaves a half-written deck."""
    encoded = {n: ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + x).encode("utf-8") for n, x in parts.items()}
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=out.name + ".", suffix=".tmp", dir=out.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f, zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as z:
            for name in sorted(encoded):
                info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                z.writestr(info, encoded[name])
        os.chmod(tmp, 0o644)  # mkstemp creates 0600
        os.replace(tmp, out)
    finally:
        if tmp.exists():
            tmp.unlink()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outline", type=Path)
    ap.add_argument("output", type=Path)
    a = ap.parse_args(argv)
    try:
        outline = json.loads(a.outline.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"{a.outline}: cannot read outline JSON ({e})")
    parts = build_parts(outline)  # raises SystemExit(one-line reason) on a bad shape
    write_pptx(parts, a.output)
    print(f"wrote {a.output} ({len(outline['slides'])} slides)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
