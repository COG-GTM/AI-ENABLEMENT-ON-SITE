"""Tests for the `flow` slide type and the executive briefing deck built from it.
Run: python -m unittest discover -s tools/tests -q"""

import copy
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import build_deck  # noqa: E402
import export_pptx  # noqa: E402
import golden_path  # noqa: E402

BRIEFING = ROOT / "templates" / "deck-exec-briefing.json"
BRIEFING_HTML = ROOT / "templates" / "deck-exec-briefing.html"
NS_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
NS_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


def flow_slide(**over) -> dict:
    s = {
        "type": "flow", "title": "A flow",
        "columns": [
            {"label": "In", "nodes": [{"id": "a", "label": "Tree", "kind": "input"}]},
            {"label": "Do", "nodes": [{"id": "b", "label": "Scan", "sub": "tool"}, {"id": "c", "label": "Skill", "kind": "skill"}]},
            {"label": "Out", "nodes": [{"id": "d", "label": "Proof", "kind": "gate"}, {"id": "e", "label": "Later", "kind": "pending"}]},
        ],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}, {"from": "c", "to": "d"}, {"from": "d", "to": "e", "label": "next"},
                  {"from": "e", "to": "a"}],
        "caption": "Caption < & >",
    }
    s.update(over)
    return s


def outline(*slides) -> dict:
    return {"title": "T", "subtitle": "S", "footer": "F", "slides": [{"type": "title"}, *slides]}


def build_html(o: dict) -> str:
    with redirect_stdout(io.StringIO()):
        build_deck.validate(o)
        return build_deck.build(o)


class FlowValidation(unittest.TestCase):
    def check(self, slide, fragment):
        with self.assertRaises(SystemExit) as cm:
            build_deck.validate(outline(slide))
        self.assertIn(fragment, str(cm.exception))

    def test_good_flow_validates_and_lays_out(self):
        lay = build_deck.flow_layout(flow_slide())
        self.assertEqual(len(lay["nodes"]), 5)
        self.assertEqual(len(lay["edges"]), 5)
        self.assertEqual(lay["kinds"], ["input", "step", "skill", "gate", "pending"])
        self.assertLessEqual(lay["h"], build_deck.FLOW_H)
        for node in lay["nodes"]:
            self.assertGreaterEqual(node["y"], build_deck.FLOW_HEAD)
            self.assertLessEqual(node["y"] + node["h"], lay["h"])

    def test_limits(self):
        many_cols = [{"label": f"C{i}", "nodes": [{"id": f"n{i}", "label": "x"}]} for i in range(build_deck.FLOW_MAX_COLS + 1)]
        self.check(flow_slide(columns=many_cols, edges=[]), "columns")
        rows = [{"id": f"r{i}", "label": "x"} for i in range(build_deck.FLOW_MAX_ROWS + 1)]
        self.check(flow_slide(columns=[{"label": "A", "nodes": rows}], edges=[]), "1-4 nodes")
        self.check(flow_slide(columns=[]), "1-7 columns")
        self.check(flow_slide(columns=[{"label": "A", "nodes": []}], edges=[]), "1-4 nodes")
        edges = [{"from": "a", "to": "b"}] * (build_deck.FLOW_MAX_EDGES + 1)
        self.check(flow_slide(edges=edges), "at most 30 edges")

    def test_ids_and_edges(self):
        self.check(flow_slide(columns=[{"label": "A", "nodes": [{"id": "1bad", "label": "x"}]}], edges=[]), "id")
        dup = [{"label": "A", "nodes": [{"id": "a", "label": "x"}]}, {"label": "B", "nodes": [{"id": "a", "label": "y"}]}]
        self.check(flow_slide(columns=dup, edges=[]), "is used twice")
        self.check(flow_slide(edges=[{"from": "a", "to": "zz"}]), "naming node ids")
        self.check(flow_slide(edges=[{"from": "a", "to": "a"}]), "same node")
        self.check(flow_slide(edges=[{"from": "a", "to": "b", "label": "x" * 40}]), "longer than 32")
        self.check(flow_slide(edges=[{"from": "a", "to": "b", "route": "sideways"}]), "route")

    def test_heading_caption_and_return_lane(self):
        seven = [{"label": "C" * 40 if i == 0 else f"C{i}", "nodes": [{"id": f"n{i}", "label": "x"}]} for i in range(7)]
        self.check(flow_slide(columns=seven, edges=[]), "wider than the node")
        self.check(flow_slide(caption="word " * 400), "caption: wraps to")
        lay = build_deck.flow_layout(flow_slide())
        back = [e for e in lay["edges"] if e["route"] == "back"]
        self.assertEqual(len(back), 1)
        self.assertGreater(back[0]["lane"], max(nd["y"] + nd["h"] for nd in lay["nodes"]))
        self.assertLessEqual(back[0]["lane"], lay["h"])
        self.assertLess(build_deck.flow_layout(flow_slide(edges=[])).get("h"), lay["h"])
        mid = build_deck.flow_layout(flow_slide(edges=[{"from": "d", "to": "a"}]))["edges"][0]  # a non-bottom source is routed via the gap
        self.assertEqual(mid["route"], "back")
        self.assertTrue(all(nd["x"] >= mid["gx1"] or nd["x"] + nd["w"] <= mid["gx1"] for nd in lay["nodes"]))

    def test_text_limits(self):
        self.check(flow_slide(columns=[{"label": "A", "nodes": [{"id": "a", "label": "x", "kind": "magic"}]}], edges=[]), "kind")
        self.check(flow_slide(columns=[{"label": "A", "nodes": [{"id": "a", "label": "w " * 200}]}], edges=[]), "label")
        long_word = "averyveryveryveryveryveryverylongword_that_cannot_break"
        cols = [{"label": f"C{i}", "nodes": [{"id": f"n{i}", "label": long_word}]} for i in range(6)]
        self.check(flow_slide(columns=cols, edges=[]), "wider than the node")
        cols = [{"label": "A", "nodes": [{"id": "a", "label": "x", "sub": "word " * 60}]}]
        self.check(flow_slide(columns=cols, edges=[]), "sub")
        cols = [{"label": "this column heading is far too long to fit above a narrow column", "nodes": [{"id": "a", "label": "x"}]}] * 1
        cols = cols + [{"label": f"C{i}", "nodes": [{"id": f"n{i}", "label": "x"}]} for i in range(5)]
        self.check(flow_slide(columns=cols, edges=[]), "one line above the column")
        tall = [{"id": f"t{i}", "label": "three words here " * 3, "sub": "more words " * 3} for i in range(4)]
        cols = [{"label": "A", "nodes": tall}] + [{"label": f"C{i}", "nodes": [{"id": f"n{i}", "label": "x"}]} for i in range(5)]
        self.check(flow_slide(columns=cols, edges=[]), "px of")

    def test_flow_counts_toward_deck_limits_like_other_types(self):
        o = outline(flow_slide())
        o["slides"][1].pop("title")
        with self.assertRaises(SystemExit):
            build_deck.validate(o)


class FlowHtml(unittest.TestCase):
    def test_svg_is_inline_and_escaped(self):
        s = flow_slide(title="T <b>&\"", caption="Cap <i>&")
        s["columns"][0]["nodes"][0]["label"] = "<script>alert(1)</script> & co"
        s["columns"][0]["nodes"][0]["sub"] = "sub <x> & \"q\""
        s["edges"][3]["label"] = "<e> & f"
        html = build_html(outline(s))
        self.assertIn("<svg viewBox=", html)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; co", html)
        self.assertIn("sub &lt;x&gt; &amp; &quot;q&quot;", html)
        self.assertIn("&lt;e&gt; &amp; f", html)
        self.assertIn("Cap &lt;i&gt;&amp;", html)
        self.assertEqual(html.count("<script>"), 1)  # the deck's own navigation script only
        self.assertNotIn("src=\"http", html)
        self.assertNotIn("href=\"http", html)
        self.assertNotIn("xlink:href", html)
        self.assertNotIn("<image", html)
        self.assertNotIn("<use", html)
        self.assertNotIn("@import", html)
        self.assertNotRegex(html, r"url\((?!#arrow)")  # only the in-document marker reference

    def test_svg_parses_and_has_one_shape_per_node_and_edge(self):
        html = build_html(outline(flow_slide()))
        svg = re.search(r"<svg[^>]*>.*?</svg>", html, re.S).group(0)
        root = ET.fromstring(svg)  # inline SVG carries no xmlns, so tags parse bare
        ns = ""
        rects = [r for r in root.iter(f"{ns}rect")]
        paths = [p for p in root.iter(f"{ns}path") if (p.get("class") or "").startswith("edge")]
        self.assertEqual(len(rects), 5)
        self.assertEqual(len(paths), 5)
        dashed = [r for r in root.iter(f"{ns}g") if "n-pending" in (r.get("class") or "")]
        self.assertEqual(len(dashed), 1)
        legend = re.search(r"<div class='legend'>(.*?)</div>", html, re.S).group(1)
        for kind in ("input", "step", "skill", "gate", "pending"):
            self.assertIn(build_deck.FLOW_KINDS[kind], legend)
        self.assertNotIn(build_deck.FLOW_KINDS["output"], legend)

    def test_marker_ids_are_unique_per_slide(self):
        html = build_html(outline(flow_slide(), flow_slide(title="Second")))
        ids = re.findall(r"<marker id='([^']+)'", html)
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)


class FlowPptx(unittest.TestCase):
    def test_dense_flow_keeps_shape_ids_unique(self):
        cols = [{"label": f"C{i}", "nodes": [{"id": f"n{i}{j}", "label": "x"} for j in range(3 if i < 6 else 2)]} for i in range(7)]
        ids = [nd["id"] for c in cols for nd in c["nodes"]]
        edges = [{"from": ids[i], "to": ids[(i * 7 + 3) % 20]} for i in range(20)]
        edges = [e for e in edges if e["from"] != e["to"]]
        edges += [{"from": ids[19], "to": ids[k]} for k in range(10)]
        slide = flow_slide(columns=cols, edges=edges[:30])
        slide["note"] = "n"
        with tempfile.TemporaryDirectory() as td:
            src, out = Path(td) / "d.json", Path(td) / "d.pptx"
            src.write_text(json.dumps(outline(slide)), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(export_pptx.main([str(src), str(out)]), 0)
            with zipfile.ZipFile(out) as z:
                xml = z.read("ppt/slides/slide2.xml").decode("utf-8")
        cnv = re.findall(r'<p:cNvPr id="(\d+)"', xml)
        self.assertGreater(len(cnv), 80)
        self.assertEqual(len(cnv), len(set(cnv)))

    def test_native_shapes_connectors_and_legend(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "d.json"
            src.write_text(json.dumps(outline(flow_slide())), encoding="utf-8")
            out = Path(td) / "d.pptx"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(export_pptx.main([str(src), str(out)]), 0)
            with zipfile.ZipFile(out) as z:
                self.assertIsNone(z.testzip())
                xml = z.read("ppt/slides/slide2.xml").decode("utf-8")
                root = ET.fromstring(xml)
            sps = list(root.iter(f"{NS_P}sp"))
            cxns = list(root.iter(f"{NS_P}cxnSp"))
            texts = [t.text or "" for t in root.iter(f"{NS_A}t")]
            self.assertEqual(len(cxns), 9)  # 4 straight edges + 5 segments for the one return edge
            self.assertGreaterEqual(len(sps), 5 + 3 + 1 + 1)  # nodes + column heads + legend + title
            for word in ("Tree", "Scan", "tool", "Skill", "Proof", "Later", "next", "Caption < & >"):
                self.assertIn(word, texts)
            for kind in ("input", "step", "skill", "gate", "pending"):
                self.assertTrue(any(build_deck.FLOW_KINDS[kind] in t for t in texts), kind)
            self.assertIn("roundRect", xml)
            self.assertIn("<a:prstDash val=\"dash\"/>", xml)
            self.assertIn("<a:tailEnd type=\"triangle\"", xml)
            ids = [int(n.get("id")) for n in root.iter(f"{NS_P}cNvPr")]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertIn("Caption &lt; &amp; &gt;", xml)


class ExecBriefingDeck(unittest.TestCase):
    """The committed executive briefing: at most 15 slides, rebuilt HTML matches, numbers come from the tools."""

    @classmethod
    def setUpClass(cls):
        cls.outline = json.loads(BRIEFING.read_text(encoding="utf-8"))
        cls.text = json.dumps(cls.outline)

    def test_size_and_shape(self):
        slides = self.outline["slides"]
        self.assertLessEqual(len(slides), 15)
        self.assertGreaterEqual(sum(s["type"] == "flow" for s in slides), 5)
        self.assertEqual(slides[0]["type"], "title")
        for s in slides:
            self.assertTrue(s.get("notes"), s.get("title"))
        for s in slides:
            if s["type"] == "flow":
                self.assertTrue(s.get("caption"), s["title"])

    def test_committed_html_is_fresh_and_self_contained(self):
        html = build_html(copy.deepcopy(self.outline))
        self.assertEqual(html, BRIEFING_HTML.read_text(encoding="utf-8"))
        self.assertNotRegex(html, r"(src|href)=[\"']https?://")
        self.assertNotIn("@import", html)
        self.assertNotRegex(html, r"url\((?!#arrow)")

    def test_no_pending_boxes_for_merged_tools(self):
        pending = [n["label"] for s in self.outline["slides"] if s["type"] == "flow"
                   for c in s["columns"] for n in c["nodes"] if n.get("kind") == "pending"]
        self.assertEqual(pending, [])
        for name in ("m_fleet_scan.py", "c_fleet_scan.py", "prompt_pack.py", "pipeline_run.py"):
            self.assertTrue((ROOT / "tools" / name).is_file(), name)
            self.assertIn(name, self.text)
        self.assertIn("/repo-discovery", self.text)
        self.assertNotIn("not merged", self.text)
        self.assertNotIn("next PR", self.text)

    def test_paths_named_on_slides_exist(self):
        for m in set(re.findall(r"(?<![\w/])((?:tools|templates|example-system|\.devin|\.github|integrations)/[\w./-]+)", self.text)):
            self.assertTrue((ROOT / m.rstrip(".")).exists(), m)
        for skill in set(re.findall(r"(?<![\w/])/([a-z][a-z-]+)(?=[\s,<)\"])", self.text)):
            if skill in ("vi-fleet-discovery", "labview-to-python", "bring-your-firmware", "tdd", "matlab-to-code",
                         "design-artifacts", "track-and-report", "exec-deck", "tour", "repo-discovery"):
                self.assertTrue((ROOT / ".devin" / "skills" / skill / "SKILL.md").is_file(), skill)

    def test_numbers_match_tool_output(self):
        golden_path.OUT.mkdir(parents=True, exist_ok=True)
        del golden_path.results[:]
        golden_path.progress = io.StringIO()
        with redirect_stdout(io.StringIO()):
            for stage in (golden_path.stage_model, golden_path.stage_bench, golden_path.stage_real_vi,
                          golden_path.stage_fleet, golden_path.stage_host_harness):
                stage()
        detail = {r["stage"]: r["detail"] for r in golden_path.results}
        self.assertTrue(all(r["ok"] for r in golden_path.results), detail)
        stats = next(s for s in self.outline["slides"] if s["type"] == "stats")
        joined = " ".join(f"{x['value']} {x['label']}" for x in stats["stats"]) + " " + stats["note"]
        for pattern in (r"3 soak steps replayed", r"9/9 columns match the VI recording", r"verdicts PASS/PASS/FAIL",
                        r"4 real VIs", r"39 cases replayed", r"10/10 columns match the diagram-derived table",
                        r"12 rows differ from MQTT 3\.1\.1", r"4 VIs, 1 \.lvproj, 1 \.seq", r"unreadable 4"):
            self.assertRegex(" ".join(detail.values()), pattern)
        for fragment in ("4", "1 .lvproj, 1 .seq", "port 4", "unreadable 4", "9/9", "3 soak steps", "PASS/PASS/FAIL", "39", "10/10", "12"):
            self.assertIn(fragment, joined)
        self.assertIn("26 vectors replayed through the python and c twins; python 3/3 columns, c 3/3 columns match exactly",
                      detail["model-to-code"])
        self.assertIn("26 vectors replayed through the python and c twins; python 3/3 columns, c 3/3 columns match exactly", self.text)
        self.assertIn("58 checks", detail["host-harness"])
        self.assertIn("host tests: 58 checks passed", self.text)
        m = json.loads((ROOT / "example-system" / "matlab-repo" / "expected" / "m-fleet.json").read_text(encoding="utf-8"))
        c = json.loads((ROOT / "example-system" / "firmware-repo" / "expected" / "c-fleet.json").read_text(encoding="utf-8"))
        self.assertEqual((m["counts"]["m_files"], m["counts"]["edges"], m["counts"]["dynamic_calls"], m["counts"]["toolboxes"]), (27, 23, 4, 2))
        self.assertEqual(m["classification"], {"port": 24, "wrap": 2, "retain": 1, "unreadable": 0})
        self.assertEqual(c["counts"]["files"], 30)
        self.assertEqual(c["classification"], {"port": 21, "wrap": 4, "retain": 5, "unreadable": 0})
        self.assertEqual(len(c["seam_candidates"]), 2)
        for fragment in ("27 files, 23 call edges, 4 dynamic calls, 2 toolboxes; port 24, wrap 2, retain 1",
                         "30 files; port 21, wrap 4, retain 5; 2 seam candidates"):
            self.assertIn(fragment, self.text)
        expected = json.loads((ROOT / "example-system" / "fleet" / "expected" / "fleet.json").read_text(encoding="utf-8"))
        self.assertEqual(expected["classification_with_lvkit"]["port"], 4)
        if shutil.which("lvkit"):
            r = subprocess.run([sys.executable, "tools/vi_fleet_scan.py", "example-system", "--name", "test-fleet",
                                "--out-dir", str(golden_path.OUT)], cwd=ROOT, capture_output=True, text=True)
            self.assertIn("port 4, wrap 0, retain 0, unreadable 0", r.stdout)


if __name__ == "__main__":
    unittest.main()
