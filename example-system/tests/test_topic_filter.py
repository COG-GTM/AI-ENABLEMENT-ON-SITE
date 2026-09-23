"""Tests for the real-VI reconstruction (example-system/real-vi/topic_filter.py and inventory.py).

Two layers: (1) the Python behaves as the block diagram reads, case by case; (2) the checked-in
cases.csv, the reconstruction, and sources.json cannot drift apart.
"""

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REAL = HERE.parent / "real-vi"
sys.path.insert(0, str(REAL))
import inventory  # noqa: E402
import topic_filter as tf  # noqa: E402

PY = sys.executable
CASES = REAL / "cases.csv"
TWO_BYTE_CHAR = "\u00e9"


class CreateTopicFilter(unittest.TestCase):
    def err(self, s: str) -> int:
        with self.assertRaises(tf.TopicFilterError) as cm:
            tf.create_topic_filter(s)
        return cm.exception.code

    def test_plain_filters_are_valid(self):
        for s in ("sport", "sport/tennis", "/", "a/b/c", "$SYS/broker", "/finance"):
            self.assertFalse(tf.create_topic_filter(s).universal, s)

    def test_lone_wildcards(self):
        # The Default frame compares the filter with the constant '+': in this project '+' is the catch-all.
        self.assertTrue(tf.create_topic_filter("+").universal)
        self.assertFalse(tf.create_topic_filter("#").universal)

    def test_empty_null_and_length(self):
        self.assertEqual(self.err(""), 55041)
        self.assertEqual(self.err("a\x00b"), 55040)
        self.assertEqual(self.err("a" * 65536), 55042)
        self.assertEqual(self.err("\xe9" * 32768), 55042)  # 65536 UTF-8 bytes, 32768 characters
        self.assertFalse(tf.create_topic_filter("a" * 65535).universal)

    def test_plus_must_be_last_and_after_separator(self):
        self.assertEqual(self.err("MQTT/+/Topic"), 55043)  # project's own test expects this code
        self.assertEqual(self.err("MQTT+"), 55044)  # and this one
        self.assertEqual(self.err("sport+"), 55044)
        for ok in ("sport/+", "/+", "+/+", "+"):
            tf.create_topic_filter(ok)

    def test_hash_must_occupy_a_whole_level(self):
        self.assertEqual(self.err("MQTT#"), 55045)
        self.assertEqual(self.err("sport/tennis#"), 55045)
        self.assertEqual(self.err("MQTT/#Topic"), 55045)
        tf.create_topic_filter("MQTT/#/Topic")  # accepted by the diagram (spec disagrees; see cases.csv U3b)

    def test_bytes_and_str_are_equivalent(self):
        self.assertEqual(tf.create_topic_filter("a/#/b"), tf.create_topic_filter(b"a/#/b"))


class Evaluate(unittest.TestCase):
    def match(self, filt: str, topic: str) -> bool:
        return tf.evaluate(tf.create_topic_filter(filt), topic)

    def test_exact_and_level_matching(self):
        self.assertTrue(self.match("sport/tennis", "sport/tennis"))
        self.assertFalse(self.match("sport/tennis", "sport/golf"))
        self.assertFalse(self.match("sport/tennis", "sport"))
        self.assertTrue(self.match("sport/tennis", "sport/tennis/player1"))  # diagram: only the filter's levels are compared

    def test_universal_and_dollar(self):
        self.assertTrue(self.match("+", "a/b/c"))
        self.assertFalse(self.match("+", "$SYS/broker"))
        self.assertFalse(self.match("#/monitor", "$SYS/monitor"))
        self.assertTrue(self.match("$SYS", "$SYS"))
        self.assertFalse(self.match("$SYS/#", "$SYS/monitor"))  # any wildcard level is blocked by a leading '$', even after a literal '$SYS'

    def test_wildcards_as_the_diagram_reads_them(self):
        self.assertTrue(self.match("sport/#", "sport/tennis"))
        self.assertTrue(self.match("MQTT/#/Topic", "MQTT/x/Topic"))
        self.assertFalse(self.match("MQTT/#/Topic", "MQTT/x/Other"))
        self.assertTrue(self.match("sport/+", "sport/tennis"))
        self.assertTrue(self.match("sport/+", "sport"))  # missing level reads as empty, so '+' matches it
        self.assertTrue(self.match("+", "/finance"))

    def test_case_sensitive(self):
        self.assertFalse(self.match("Sport", "sport"))

    def test_topic_length_bound(self):
        self.assertFalse(self.match("a", "a" * 65535))
        with self.assertRaises(ValueError):
            self.match("a", "a" * 65536)


class CasesFile(unittest.TestCase):
    def rows(self):
        return tf.read_cases(CASES)

    def test_reconstruction_agrees_with_every_diagram_derived_row(self):
        rows = self.rows()
        replayed = tf.replay(rows)
        for exp, act in zip(rows, replayed):
            self.assertEqual((exp["valid"], exp["error_code"], exp["match"]),
                             (act["valid"], act["error_code"], act["match"]), exp["case"])

    def test_every_deviation_is_flagged_in_its_note(self):
        rows = self.rows()
        flagged = {r["case"] for r in tf.spec_deviations(rows)}
        noted = {r["case"] for r in rows if r["note"].startswith("DEVIATION")}
        self.assertEqual(flagged, noted)
        self.assertGreater(len(flagged), 0)

    def test_review_counts_match_the_table(self):
        rows = self.rows()
        text = (REAL / "VI-REVIEW.md").read_text(encoding="utf-8")
        self.assertIn(f"PASS on all {len(tf.CASE_COLUMNS)} columns, {len(rows)} rows", text)
        self.assertIn(f"({len(tf.spec_deviations(rows))} rows:", text)
        n_upstream = sum(r["case"].startswith("U") for r in rows)
        self.assertIn(f"- {n_upstream} rows (`U2a`-`U3e`)", text)
        self.assertIn(f"- {len(rows) - n_upstream} rows (`S01`-`S{len(rows) - n_upstream:02d}`)", text)
        readme = (REAL.parent.parent / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"`cases.csv` ({len(rows)} expected rows: {n_upstream} from the project's own test VIs, {len(rows) - n_upstream} from the MQTT specification)", readme)
        self.assertIn(f"on {len(rows)} of {len(rows)} rows, including the {n_upstream} verdicts", readme)
        table = [r for r in text.split("## Not proven")[1].split("## Retain")[0].splitlines() if r.startswith("| ")]
        unknowns = len(table) - 2  # header and separator
        self.assertIn(f"lists the {('two', 'three', 'four', 'five', 'six')[unknowns - 2]} diagram readings", readme)

    def test_upstream_cases_have_their_source_vi(self):
        for r in self.rows():
            if r["case"].startswith("U"):
                self.assertRegex(r["source"], r"^Test MQTT-4\.7\.1-[23]\.vi frame \d")
            else:
                self.assertIn("spec 4.7", r["source"])

    def test_rejects_malformed_case_files(self):
        head = "case,topic_filter,topic,valid,error_code,match,spec_valid,spec_match,source,note\n"
        good = "A1,a,a,TRUE,0,TRUE,TRUE,TRUE,spec 4.7.3,\n"
        bad = {
            "header": "case,topic\nA1,a\n",
            "no rows": head,
            "duplicate id": head + good + good,
            "bad id": head + "a b,a,a,TRUE,0,TRUE,TRUE,TRUE,s,\n",
            "bad tri-state": head + "A1,a,a,yes,0,TRUE,TRUE,TRUE,s,\n",
            "bad code": head + "A1,a,a,FALSE,1,-,FALSE,-,s,\n",
            "note too long": head + f"A1,a,a,TRUE,0,TRUE,TRUE,TRUE,s,{'x' * 2000}\n",
            "filter two over": head + f"A1,{'x' * (tf.MAX_FILTER_BYTES + 2)},a,FALSE,55042,-,FALSE,-,s,\n",
            "topic one over": head + f"A1,a,{'x' * (tf.MAX_TOPIC_BYTES + 1)},TRUE,0,FALSE,TRUE,FALSE,s,\n",
            "topic multibyte over": head + f"A1,a,{TWO_BYTE_CHAR * (tf.MAX_TOPIC_BYTES // 2 + 1)},TRUE,0,FALSE,TRUE,FALSE,s,\n",
            "too many": head + "".join(f"A{i},a,a,TRUE,0,TRUE,TRUE,TRUE,s,\n" for i in range(tf.MAX_CASE_ROWS + 1)),
        }
        for name, text in bad.items():
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / "c.csv"
                p.write_text(text, encoding="utf-8")
                with self.assertRaises(SystemExit, msg=name):
                    tf.read_cases(p)

    def test_replay_reaches_the_length_boundaries(self):
        head = "case,topic_filter,topic,valid,error_code,match,spec_valid,spec_match,source,note\n"
        rows = (
            f"L1,{'a' * tf.MAX_FILTER_BYTES},{'a' * tf.MAX_TOPIC_BYTES},TRUE,0,TRUE,TRUE,TRUE,spec 4.7.3,\n"
            f"L2,{'a' * (tf.MAX_FILTER_BYTES + 1)},a,FALSE,55042,-,FALSE,-,spec 4.7.3,\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.csv"
            p.write_text(head + rows, encoding="utf-8")
            out = Path(d) / "out.csv"
            r = subprocess.run([PY, str(REAL / "topic_filter.py"), "--replay", str(p), "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            got = {row["case"]: row for row in tf.read_cases(out)}
            self.assertEqual((got["L1"]["valid"], got["L1"]["error_code"], got["L1"]["match"]), ("TRUE", "0", "TRUE"))
            self.assertEqual((got["L2"]["valid"], got["L2"]["error_code"], got["L2"]["match"]), ("FALSE", "55042", "-"))

    def test_cli_replay_then_compare_passes(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.csv"
            r = subprocess.run([PY, str(REAL / "topic_filter.py"), "--replay", str(CASES), "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertRegex(r.stdout, r"\d+ cases replayed .* \d+ differ from MQTT")
            c = subprocess.run([PY, str(REAL.parent.parent / "tools" / "bench_compare.py"), str(CASES), str(out), "--json"], capture_output=True, text=True)
            self.assertEqual(c.returncode, 0, c.stdout)
            self.assertEqual(json.loads(c.stdout)["verdict"], "PASS")
            d2 = subprocess.run([PY, str(REAL / "topic_filter.py"), "--spec-diff", str(out)], capture_output=True, text=True)
            self.assertEqual(d2.returncode, 0)
            self.assertIn("| U2b |", d2.stdout)

    def test_cli_missing_file_is_one_line(self):
        r = subprocess.run([PY, str(REAL / "topic_filter.py"), "--replay", "/nonexistent/x.csv", "--out", "/nonexistent/y.csv"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)


class Inventory(unittest.TestCase):
    def test_sources_match_checked_in_binaries(self):
        src = inventory.load_sources()
        self.assertEqual(inventory.check_hashes(src), [])
        self.assertEqual(len(src["files"]), 4)
        for entry in src["files"]:
            self.assertEqual(hashlib.sha256((REAL / entry["file"]).read_bytes()).hexdigest(), entry["sha256"])

    def test_inventory_mentions_every_file_and_recovered_signature(self):
        text = (REAL / "VI-INVENTORY.md").read_text(encoding="utf-8")
        for entry in inventory.load_sources()["files"]:
            self.assertIn(f"# {entry['file']}", text)
            self.assertIn(entry["upstream_path"], text)
        self.assertIn("Match: TF", text)
        for code_msg in tf.ERRORS:
            self.assertIn(code_msg[1], text)

    def test_trim_drops_properties_and_absolute_paths(self):
        raw = "# /tmp/somewhere/X.vi\n\n## Signature\nsig\n\n## Properties\nfoo\n\n## Constants\n'+'\n"
        out = inventory.trim(raw, "X.vi")
        self.assertTrue(out.startswith("# X.vi\n"))
        self.assertNotIn("Properties", out)
        self.assertNotIn("/tmp", out)
        self.assertIn("## Constants", out)

    def test_check_works_without_lvkit(self):
        r = subprocess.run([PY, str(REAL / "inventory.py"), "--check"], capture_output=True, text=True, env={"PATH": "/nonexistent"})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("4 .vi files match", r.stdout)

    def test_check_skips_text_compare_on_other_lvkit_release(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "lvkit"
            fake.write_text("#!/bin/sh\necho 'lvkit 9.9.9'\n", encoding="utf-8")
            fake.chmod(0o755)
            r = subprocess.run([PY, str(REAL / "inventory.py"), "--check"], capture_output=True, text=True, env={"PATH": d})
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("lvkit 9.9.9 on PATH, inventory was made with", r.stdout)
            self.assertIn("hashes only", r.stdout)
            w = subprocess.run([PY, str(REAL / "inventory.py"), "--write"], capture_output=True, text=True, env={"PATH": d})
            self.assertEqual(w.returncode, 1)
            self.assertIn("update lvkit_version in sources.json", w.stderr)

    def test_check_fails_on_tampered_binary(self):
        with tempfile.TemporaryDirectory() as d:
            here = Path(d)
            for p in REAL.glob("*.vi"):
                (here / p.name).write_bytes(p.read_bytes())
            (here / "Evaluate.vi").write_bytes(b"not a vi")
            src = inventory.load_sources()
            orig = inventory.HERE
            try:
                inventory.HERE = here
                problems = inventory.check_hashes(src)
            finally:
                inventory.HERE = orig
            self.assertEqual(problems, ["Evaluate.vi: sha256 differs from sources.json"])


if __name__ == "__main__":
    unittest.main()
