"""Tests for tools/export_pptx.py. Run: python -m unittest discover -s tools/tests -q"""

import io
import json
import posixpath
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import export_pptx  # noqa: E402

EXAMPLE = ROOT / "templates" / "deck-outline-example.json"
NS_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
NS_CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"


def export(outline: dict, tmp: Path, name: str = "deck.pptx") -> Path:
    src = tmp / f"{name}.json"
    src.write_text(json.dumps(outline), encoding="utf-8")
    out = tmp / "nested" / name
    with redirect_stdout(io.StringIO()):
        assert export_pptx.main([str(src), str(out)]) == 0
    return out


def slide_text(root: ET.Element) -> str:
    return "".join(t.text or "" for t in root.iter(f"{NS_A}t"))


class ExportPptxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.outline = json.loads(EXAMPLE.read_text())

    def test_example_round_trip(self):
        out = export(self.outline, self.tmp)
        with zipfile.ZipFile(out) as z:
            names = z.namelist()
            parsed = {n: ET.fromstring(z.read(n)) for n in names}  # every part must be XML
        slides = sorted(n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
        self.assertEqual(len(slides), len(self.outline["slides"]))
        for i, s in enumerate(self.outline["slides"], 1):
            text = slide_text(parsed[f"ppt/slides/slide{i}.xml"])
            title = self.outline["title"] if s["type"] == "title" else s.get("title", s.get("text"))
            self.assertIn(title, text, f"slide {i}")
        # [Content_Types].xml covers every part, by Override or by Default extension
        types = parsed["[Content_Types].xml"]
        overrides = {o.get("PartName") for o in types.iter(f"{NS_CT}Override")}
        defaults = {d.get("Extension") for d in types.iter(f"{NS_CT}Default")}
        for n in names:
            if n != "[Content_Types].xml":
                self.assertTrue(f"/{n}" in overrides or n.rsplit(".", 1)[-1] in defaults, n)
        # every relationship target resolves to a part in the package
        for n, root in parsed.items():
            if not n.endswith(".rels"):
                continue
            base = posixpath.dirname(posixpath.dirname(n))  # ppt/slides/_rels/x.rels -> ppt/slides
            for rel in root.iter(f"{NS_REL}Relationship"):
                target = posixpath.normpath(posixpath.join(base, rel.get("Target")))
                self.assertIn(target, names, f"{n}: {rel.get('Target')}")
        # required fixed parts, master/layout pair, notes only where asked for
        for req in ("_rels/.rels", "docProps/core.xml", "docProps/app.xml", "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels",
                    "ppt/slideMasters/slideMaster1.xml", "ppt/slideLayouts/slideLayout1.xml", "ppt/theme/theme1.xml",
                    "ppt/presProps.xml", "ppt/viewProps.xml", "ppt/tableStyles.xml"):
            self.assertIn(req, names)
        notes = [i for i, s in enumerate(self.outline["slides"], 1) if s.get("notes")]
        self.assertTrue(notes, "example outline should exercise speaker notes")
        self.assertEqual(sorted(n for n in names if n.startswith("ppt/notesSlides/notesSlide")),
                         sorted(f"ppt/notesSlides/notesSlide{i}.xml" for i in notes))
        self.assertIn("ppt/notesMasters/notesMaster1.xml", names)
        self.assertIn(self.outline["slides"][notes[0] - 1]["notes"], slide_text(parsed[f"ppt/notesSlides/notesSlide{notes[0]}.xml"]))

    def test_no_notes_means_no_notes_parts(self):
        out = export({"title": "t", "slides": [{"type": "title"}]}, self.tmp)
        with zipfile.ZipFile(out) as z:
            self.assertFalse([n for n in z.namelist() if "notes" in n.lower()])

    def test_xml_special_characters_are_escaped(self):
        nasty = 'Risk <&"> "quoted" & <tag>'
        out = export({"title": nasty, "subtitle": "a & b", "slides": [
            {"type": "title"},
            {"type": "bullets", "title": nasty, "bullets": ["<script>x</script>", "1 < 2 && 3 > 2"], "notes": nasty},
            {"type": "table", "title": nasty, "columns": ["<A>", "&B"], "rows": [["\"1\"", "'2'"]]},
        ]}, self.tmp)
        with zipfile.ZipFile(out) as z:
            for n in z.namelist():
                root = ET.fromstring(z.read(n))  # must parse despite the raw characters
                if n.endswith(".xml") and (n.startswith("ppt/slides/") or n.startswith("ppt/notesSlides/")):
                    self.assertIn(nasty, slide_text(root), n)
            self.assertIn("&lt;script&gt;", z.read("ppt/slides/slide2.xml").decode())

    def test_output_is_deterministic(self):
        a = export(self.outline, self.tmp, "a.pptx").read_bytes()
        b = export(self.outline, self.tmp, "b.pptx").read_bytes()
        self.assertEqual(a, b)
        with zipfile.ZipFile(io.BytesIO(a)) as z:
            self.assertEqual(sorted(z.namelist()), z.namelist())
            self.assertEqual({i.date_time for i in z.infolist()}, {export_pptx.ZIP_DATE})

    def test_accent_from_outline(self):
        self.outline["accent"] = "#00aa55"
        out = export(self.outline, self.tmp)
        with zipfile.ZipFile(out) as z:
            self.assertIn('val="00AA55"', z.read("ppt/theme/theme1.xml").decode())
            self.assertIn('val="00AA55"', z.read("ppt/slides/slide2.xml").decode())

    def test_invalid_shapes_exit_1(self):
        bad = [
            [],                                                       # not an object
            {"title": "t"},                                           # no slides
            {"title": "t", "slides": []},                             # empty
            {"title": "t", "slides": [{"type": "video"}]},            # unknown type
            {"title": "t", "slides": [{"type": "bullets", "title": "t"}]},          # missing bullets
            {"title": "t", "slides": [{"type": "bullets", "title": "t", "bullets": "x"}]},  # not a list
            {"title": "t", "slides": [{"type": "bullets", "title": "t", "bullets": list("abcdefghi")}]},
            {"title": "t", "slides": [{"type": "table", "title": "t", "columns": ["a"], "rows": [["1", "2"]]}]},
            {"title": "t", "slides": [{"type": "bars", "title": "t", "bars": [{"label": "a", "value": "x"}]}]},
            {"title": "t", "slides": [{"type": "stats", "title": "t", "stats": [{"value": 1}]}]},
            {"title": "t", "slides": [{"type": "title", "notes": ["not", "text"]}]},
            {"title": "t", "accent": "blue", "slides": [{"type": "title"}]},
            {"title": {"nested": 1}, "slides": [{"type": "title"}]},
        ]
        for i, outline in enumerate(bad):
            src = self.tmp / f"bad{i}.json"
            src.write_text(json.dumps(outline))
            with self.subTest(i=i), redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as cm:
                export_pptx.main([str(src), str(self.tmp / "bad.pptx")])
            msg = cm.exception.code
            self.assertIsInstance(msg, str)  # one-line reason, not a traceback
            self.assertNotIn("\n", msg.strip())
            self.assertFalse((self.tmp / "bad.pptx").exists())

    def test_cli_exit_codes(self):
        src = self.tmp / "bad.json"
        src.write_text(json.dumps({"title": "t", "slides": [{"type": "video"}]}))
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "export_pptx.py"), str(src), str(self.tmp / "x.pptx")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "export_pptx.py"), str(EXAMPLE), str(self.tmp / "ok.pptx")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_unreadable_json_exits_1(self):
        src = self.tmp / "broken.json"
        src.write_text("{not json")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            export_pptx.main([str(src), str(self.tmp / "x.pptx")])
        self.assertIsInstance(cm.exception.code, str)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            export_pptx.main([str(self.tmp / "missing.json"), str(self.tmp / "x.pptx")])


if __name__ == "__main__":
    unittest.main()
