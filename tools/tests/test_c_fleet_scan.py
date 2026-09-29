"""c_fleet_scan.py: lexer, definitions, resolution, target markers, classification, backlog, gcc cross-check, and --check."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import c_fleet_scan as c  # noqa: E402

PY = sys.executable


def write(tree: Path, rel: str, text: str) -> None:
    p = tree / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


class Lexer(unittest.TestCase):
    def test_comments_strings_continuations_and_if0(self):
        code, pp, strings, disabled = c.strip_code(
            '#include "a.h" // trailing f(1)\n/* block g(2)\n still */ int x = h("s(3)", \'(\');\n#define M(a) \\\n  a + 1\n#if 0\nk(4);\n#endif\n')
        joined = "\n".join(code)
        self.assertNotIn("f(1)", joined)
        self.assertNotIn("g(2)", joined)
        self.assertNotIn("s(3)", joined)
        self.assertIn('h("", \'x\')', joined)
        self.assertEqual(strings, ["s(3)"])
        self.assertIn('#include "a.h"', pp)          # string kept on preprocessor lines
        self.assertTrue(any(d.startswith("#define M(a)") and d.endswith("a + 1") for d in pp))    # continuation joined
        self.assertEqual(disabled, 1)
        self.assertNotIn("k(4)", joined)

    def test_definitions_prototypes_calls(self):
        toks = c.tokens_of(c.strip_code(
            "int add(int a, int b);\nstatic int twice(int a) { return add(a, a); }\n"
            "int32_t old_step(f, x)\nold_t *f;\nint32_t x;\n{ return (int32_t)(x + f->k); }\n"
            "namespace hub {\nclass P {\npublic:\n  P() : n_(0) {}\n  int run(const char *l) const { return cb_(l) + std::strlen(l); }\n};\n}\n"
            "int P::go(int q) { return q; }\nvoid ISR_tick(void) { ADC_IRQHandler(); }\n")[0])
        p = c.parse_tokens(toks)
        names = [d["name"] for d in p["defs"]]
        self.assertEqual(names, ["twice", "old_step", "P", "run", "P::go", "ISR_tick"])
        self.assertTrue(next(d for d in p["defs"] if d["name"] == "twice")["static"])
        self.assertTrue(next(d for d in p["defs"] if d["name"] == "old_step")["knr"])
        self.assertEqual(p["protos"], ["add"])
        self.assertEqual(sorted(x["name"] for x in p["calls"]), ["ADC_IRQHandler", "add", "cb_", "std::strlen"])
        self.assertEqual(p["classes"], ["P"])
        self.assertEqual(p["namespaces"], 1)
        self.assertGreaterEqual(p["max_nesting"], 1)

    def test_casts_operators_and_attributes_are_not_calls(self):
        toks = c.tokens_of(c.strip_code(
            "static uint8_t v __attribute__((section(\".noinit\")));\nint f(int x) { int y = (uint8_t)(x) & ~(1u << 2); "
            "return sizeof(y) + (int)(y * (x)); }\n")[0])
        p = c.parse_tokens(toks)
        self.assertEqual([x["name"] for x in p["calls"]], [])
        self.assertEqual([d["name"] for d in p["defs"]], ["f"])


class Resolution(unittest.TestCase):
    def scan(self, files: dict, **kw) -> dict:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tree = Path(tmp.name)
        for rel, text in files.items():
            write(tree, rel, text)
        return c.scan_tree(tree, use_gcc=False, **kw)

    def rows(self, result):
        return {r["path"]: r for r in result["rows"]}

    def test_includes_resolve_relative_then_by_basename(self):
        r = self.scan({
            "app/a.c": '#include "a.h"\n#include "../inc/cfg.h"\n#include "util.h"\n#include <stdint.h>\n#include <stm32f4xx.h>\n#include "nowhere.h"\nint main(void){return 0;}\n',
            "app/a.h": "int a(void);\n", "inc/cfg.h": "#define X 1\n", "lib/util.h": "int u(void);\n",
        })
        rows = self.rows(r)
        self.assertEqual(rows["app/a.c"]["includes_tree"], "app/a.h;inc/cfg.h;lib/util.h")
        self.assertEqual(rows["app/a.c"]["includes_system"], "stdint.h")
        self.assertEqual(rows["app/a.c"]["includes_vendor"], "stm32f4xx.h")
        self.assertEqual(rows["app/a.c"]["includes_unresolved"], "nowhere.h")
        self.assertEqual(rows["app/a.c"]["classification"], "retain")   # vendor header = target build only
        self.assertEqual(rows["inc/cfg.h"]["callers_count"], 1)

    def test_ambiguous_include_and_definition_are_never_picked(self):
        r = self.scan({
            "a/x.h": "int x(void);\n", "b/x.h": "int x(void);\n", "m.c": '#include "x.h"\nint f(void){return x() + g();}\n',
            "p/g.c": "int g(void){return 1;}\n", "q/g.c": "int g(void){return 2;}\n",
        })
        rows = self.rows(r)
        self.assertIn("ambiguous", rows["m.c"]["includes_unresolved"])
        self.assertEqual(rows["m.c"]["calls_tree"], "g (ambiguous)")
        kinds = sorted(e["kind"] for e in r["dep_map"]["edges"])
        self.assertEqual(kinds, ["ambiguous", "ambiguous", "ambiguous-include", "ambiguous-include"])
        self.assertIn("x (declared in the tree, defined elsewhere)", rows["m.c"]["calls_unresolved"])

    def test_static_header_inline_and_macro_resolution(self):
        r = self.scan({
            "fp.h": "static inline int clamp(int v){return v;}\n#define SQ(a) ((a)*(a))\n",
            "u.c": '#include "fp.h"\nint f(int v){return clamp(v) + SQ(v);}\n',
            "other.c": "int g(int v){return clamp(v);}\n",   # does not include fp.h; still resolves (single definition)
        })
        rows = self.rows(r)
        self.assertEqual(rows["u.c"]["calls_tree"], "clamp;SQ (macro)")
        self.assertEqual(rows["other.c"]["calls_tree"], "clamp")
        self.assertEqual(rows["u.c"]["calls_unresolved"], "")

    def test_libc_vendor_unresolved_and_prototypes_in_headers(self):
        r = self.scan({
            "d.h": "void d_init(void);\nint d_read(int ch);\n",
            "d.c": '#include "d.h"\nvoid d_init(void){HAL_Init(); NVIC_EnableIRQ(3);}\nint d_read(int ch){return memcmp(&ch,&ch,1) + mystery(ch);}\n',
        })
        rows = self.rows(r)
        self.assertEqual(rows["d.h"]["calls_tree"], "")          # prototypes are not calls
        self.assertEqual(rows["d.h"]["functions"], 0)
        self.assertEqual(rows["d.c"]["calls_vendor"], "HAL_Init;NVIC_EnableIRQ")
        self.assertEqual(rows["d.c"]["calls_libc"], "memcmp")
        self.assertEqual(rows["d.c"]["calls_unresolved"], "mystery")
        self.assertEqual(rows["d.c"]["classification"], "wrap")
        self.assertIn("vendor/RTOS calls to stub", rows["d.c"]["reasons"])

    def test_target_markers_make_retain_and_propagate_as_wrap(self):
        r = self.scan({
            "board.h": "#define REG32(a) (*(volatile uint32_t *)(a))\n#define ODR REG32(0x40020014u)\n",
            "gpio.c": '#include "board.h"\nvoid gpio_set(int p){ODR |= p;}\n',
            "isr.c": "void TIM2_IRQHandler(void){__asm volatile(\"nop\");}\n",
            "start.c": "extern unsigned _sidata, _sdata; void Reset_Handler(void){}\n",
            "logic.c": "int twice(int v){return v*2;}\n",
            "tests/test_logic.c": "int twice(int); int main(void){return twice(2)==4?0:1;}\n",
        })
        rows = self.rows(r)
        self.assertEqual(rows["board.h"]["classification"], "retain")
        self.assertIn("register", rows["board.h"]["reasons"])
        self.assertEqual(rows["isr.c"]["classification"], "retain")
        self.assertIn("ISR handler(s): TIM2_IRQHandler", rows["isr.c"]["reasons"])
        self.assertIn("inline asm", rows["isr.c"]["reasons"])
        self.assertEqual(rows["start.c"]["classification"], "retain")
        self.assertEqual(rows["gpio.c"]["classification"], "wrap")
        self.assertIn("includes target-only header(s): board.h", rows["gpio.c"]["reasons"])
        self.assertEqual(rows["logic.c"]["classification"], "port")
        self.assertEqual(rows["logic.c"]["missing_inputs"], "vectors")       # a test references it
        self.assertEqual(rows["tests/test_logic.c"]["role"], "test")
        self.assertEqual(r["summary"]["target_only"], ["board.h", "isr.c", "start.c"])
        self.assertEqual(r["summary"]["entry_points"], ["isr.c", "start.c", "tests/test_logic.c"])

    def test_cpp_methods_templates_overloads_and_method_name_edges(self):
        r = self.scan({
            "rb.hpp": "template <typename T> class RB {\npublic:\n RB() : n_(0) {}\n bool push(const T &v) { return n_++ < 4; }\nprivate:\n int n_;\n};\n",
            "log.hpp": '#include "rb.hpp"\nclass Log {\npublic:\n explicit Log(int s);\n void log(const char *m);\n void log(int v);\nprivate:\n RB<int> q_;\n};\n',
            "log.cpp": '#include "log.hpp"\nLog::Log(int s) : q_() {}\nvoid Log::log(const char *m) { q_.push(1); }\nvoid Log::log(int v) { q_.push(v); std::strlen("x"); }\n',
        })
        rows = self.rows(r)
        self.assertEqual(rows["rb.hpp"]["functions"], 2)
        self.assertIn("1 template", rows["rb.hpp"]["cpp_constructs"])
        self.assertEqual(rows["log.cpp"]["functions"], 3)
        self.assertIn("1 overload", rows["log.cpp"]["cpp_constructs"])
        self.assertEqual(rows["log.cpp"]["indirect_calls"], "push")
        self.assertEqual(rows["log.cpp"]["calls_libc"], "std::strlen")
        self.assertEqual(rows["log.cpp"]["calls_unresolved"], "")
        self.assertEqual([e for e in r["dep_map"]["edges"] if e["kind"] == "method-name"],
                         [{"from": "log.cpp", "to": "rb.hpp", "kind": "method-name", "via": ["push"]}])

    def test_non_utf8_and_seams_and_test_definitions_do_not_shadow(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tree = Path(tmp.name)
        (tree / "g.c").write_bytes(b"/* caf\xe9 */\nint g(void){return 1;}\n")
        write(tree, "main.c", 'int main(void){return hal_w(1);}\n')
        write(tree, "hal.c", 'void ISR_x(void){}\nint hal_w(int v){return v;}\n')
        write(tree, "app.c", 'int app(void){return hal_w(2);}\n')
        write(tree, "tests/t.c", 'int main(void){return 0;}\n')
        write(tree, "boot.c", 'extern int main(void); void Reset_Handler(void){(void)main();}\n')
        r = c.scan_tree(tree, use_gcc=False)
        rows = {x["path"]: x for x in r["rows"]}
        self.assertIn("not valid UTF-8", rows["g.c"]["reasons"])
        self.assertEqual(rows["boot.c"]["calls_tree"], "main")       # test main does not make it ambiguous
        self.assertEqual(r["dep_map"]["seam_candidates"], [{"function": "hal_w", "defined_in": "hal.c", "callers": ["app.c", "main.c"]}])

    def test_leaf_first_order_and_cycles(self):
        r = self.scan({"a.c": "int b(void); int a(void){return b();}\n", "b.c": "int c(void); int b(void){return c();}\n",
                       "c.c": "int a(void); int c(void){return a();}\n", "leaf.c": "int leaf(void){return 1;}\n"})
        self.assertEqual(r["dep_map"]["leaf_first_order"][0], "leaf.c")
        self.assertEqual(r["dep_map"]["cycles"], [["a.c", "b.c", "c.c"]])

    def test_skipped_dirs_and_build_files(self):
        r = self.scan({"build/gen.c": "int g(void){return 1;}\n", ".git/x.c": "int x(void){return 1;}\n", "src/a.c": "int a(void){return 1;}\n",
                       "Makefile": "CC=arm-none-eabi-gcc\n", "link.ld": "ENTRY(Reset_Handler)\n", "CMakeLists.txt": "project(x)\n"})
        self.assertEqual([n["path"] for n in r["dep_map"]["nodes"]], ["src/a.c"])
        self.assertEqual(r["dep_map"]["build_files"], ["CMakeLists.txt", "Makefile", "link.ld"])


class Backlog(unittest.TestCase):
    def test_backlog_shape_and_ordering(self):
        result = c.scan_tree(c.FIXTURE, use_gcc=False)
        items = c.build_backlog(result["rows"], 50, "FW", "2026-01-05")
        self.assertTrue(items)
        self.assertTrue(all(i["type"] == "capability" and i["status"] == "proposed" for i in items))
        self.assertTrue(all(not i["notes"].startswith("retain") for i in items))
        self.assertFalse(any("test_scheduler" in i["title"] for i in items))
        self.assertFalse(any(i["title"].endswith(("median.h", "pid.h", "config.h")) for i in items))   # declaration-only headers excluded
        pr = [int(i["notes"].split("priority ")[1].split(",")[0]) for i in items]
        self.assertEqual(pr, sorted(pr, reverse=True))
        self.assertEqual(items[0]["id"], "FW-CAP-001")

    def test_rescan_keeps_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = c.scan_tree(c.FIXTURE, use_gcc=False)
            out = Path(tmp)
            p1 = c.write_outputs(result, out, "fw", 50, "FW", "2026-01-05")
            items = json.loads(p1["backlog"].read_text(encoding="utf-8"))["items"]
            items[0]["status"] = "open"
            p1["backlog"].write_text(json.dumps({"items": items}), encoding="utf-8")
            p2 = c.write_outputs(result, out, "fw", 50, "FW", "2026-02-01")
            again = json.loads(p2["backlog"].read_text(encoding="utf-8"))["items"]
            self.assertEqual(again[0]["status"], "open")
            self.assertEqual(again[0]["opened"], "2026-01-05")


class GccCrossCheck(unittest.TestCase):
    @unittest.skipUnless(shutil.which("gcc"), "gcc not on PATH")
    def test_gcc_confirms_static_closure_and_reports_error_directive(self):
        result = c.scan_tree(c.FIXTURE, use_gcc=True)
        ic = result["dep_map"]["include_check"]
        self.assertEqual(ic["files_checked"], 16)
        self.assertEqual([x["path"] for x in ic["failed"]], ["bsp/system_init.c"])
        self.assertIn("unknown board", ic["failed"][0]["error"])
        self.assertEqual(ic["extra_headers"], {})
        with_flags = c.scan_tree(c.FIXTURE, cflags=["-DBOARD_REV_C", "-DUSE_HAL_DRIVER"], use_gcc=True)["dep_map"]["include_check"]
        self.assertEqual(with_flags["failed"], [])
        self.assertEqual(with_flags["confirmed"], 16)

    def test_no_gcc_reports_absent(self):
        result = c.scan_tree(c.FIXTURE, use_gcc=False)
        self.assertEqual(result["summary"]["include_reader"], "gcc disabled (--no-gcc)")


class Check(unittest.TestCase):
    def test_check_passes_on_fixture(self):
        r = subprocess.run([PY, str(ROOT / "tools" / "c_fleet_scan.py"), "--check"], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("c-fleet check ok", r.stdout)
        self.assertIn("validate against templates/tracker-item.json", r.stdout)

    def test_cli_writes_all_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run([PY, str(ROOT / "tools" / "c_fleet_scan.py"), str(c.FIXTURE), "--name", "fw", "--out-dir", tmp, "--opened", "2026-01-05",
                                "--no-gcc", "--json"], capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(r.returncode, 0, r.stderr)
            s = json.loads(r.stdout)
            for key in ("inventory", "summary", "dependency_map", "dependency_dot", "repo_map", "backlog", "backlog_csv"):
                self.assertTrue((ROOT / s["outputs"][key]).is_file() if not Path(s["outputs"][key]).is_absolute() else Path(s["outputs"][key]).is_file(), key)
            md = (Path(tmp) / "fw-c-repo-map.md").read_text(encoding="utf-8")
            self.assertIn("This repository has no C-to-Python translator", md)
            self.assertIn("## Seam candidates", md)
            self.assertIn("arm-none-eabi-gcc", md)
            dot = (Path(tmp) / "fw-c-dependency-map.dot").read_text(encoding="utf-8")
            self.assertIn("digraph c_tree", dot)


if __name__ == "__main__":
    unittest.main()
