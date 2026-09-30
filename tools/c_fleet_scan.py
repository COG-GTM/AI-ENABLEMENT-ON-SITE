#!/usr/bin/env python3
"""Repository-scale C/C++ discovery: walk a firmware or application tree, build the candidate include and call graph,
mark what only a target build can compile, classify each file for host testing and migration, and write the inventory,
dependency map, repo map, and tracker-shaped backlog. Standard library only; uses `gcc -MM` as a cross-check when a
compiler is on PATH and says so when it is not. Deterministic (sorted traversal, stable ids).

    python tools/c_fleet_scan.py <tree> [--name N] [--top 50] [--prefix FW] [--out-dir outputs] [--cflags=-DBOARD_REV_C] [--json]
    python tools/c_fleet_scan.py --check

What it reads, statically (a *lexical* scanner, not a compiler; it does not expand macros or evaluate #if):
  files        .c .cc .cpp .cxx .h .hpp .hh .hxx; build files (Makefile, CMakeLists.txt, *.ld, *.icf, project files) are listed
  definitions  functions defined at file scope (C and C++, `Class::method`, inline methods in a class body, K&R style),
               function-like macros, classes, templates, namespaces, overloads
  includes     `#include "x.h"` resolved to a tree file (relative to the includer, then by unique basename; two matches
               are `ambiguous-include`); `<x.h>` is libc/C++ standard or a vendor header
  calls        identifiers followed by `(` that are not keywords, casts, definitions, or attributes; `a->f(` / `a.f(` are
               indirect or method calls and are matched by method name only
  resolution   same file > unique tree definition > function-like macro in the tree > C/C++ standard library > vendor/RTOS
               prefix (HAL_, LL_, NVIC_, __enable_irq, nrf_, xTask, osDelay, k_) > unresolved. Two definitions in two files
               are `ambiguous`, never picked.
  target-only  ISR handlers, inline asm, memory-mapped register access, linker symbols and section attributes, vendor headers,
               board/architecture conditionals: the evidence that a file cannot compile on a host as-is

Classification (evidence in `reasons`):
  retain     target-only code: ISR, asm, registers, startup, linker symbols - stays in the target build; the host harness
             replaces it with a stub (templates/host-harness/hal_stub.c)
  wrap       compiles on a host once HAL/vendor calls are stubbed, or third-party/vendor code kept as a dependency
  port       host-testable logic: builds with a host compiler as-is (may still need a test and vectors)
  unreadable file could not be read at all

complexity = code_lines/10 + 2*structures + 3*out_edges + 5*unresolved + 4*indirect_calls + 3*target_conditionals + 2*max_nesting
             + 2*function_like_macros + 3*templates + 2*overloads
priority   = 100 + 10*min(callers, 5) + 20 if vectors sit beside the unit + 10 if a test file references it - min(complexity, 60)

Outputs (outputs/<name>-c-*): inventory CSV (every file), summary JSON, dependency-map JSON + DOT (include and call edges,
external calls by group, unresolved, seam candidates, entry points, cycles, leaf-first order), repo-map Markdown (the
deterministic facts an agent documents from), migration-backlog JSON + CSV (top --top port/wrap units, templates/tracker-item.json
shape; rescans keep ids and statuses). None of this proves behaviour: the host harness (/bring-your-firmware) and a Python
behavioural twin proven with shared vectors (/tdd --lang both) do that. This repository has no C-to-Python translator; the twin
is a reference model kept in lock-step by tests.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

from fleet_common import (
    BACKLOG_COLUMNS, OUT_DIR, ROOT, backlog_about, backlog_csv_rows, call_tree_lines, check_prefix, component_slug, csv_text,
    dot_text, finish_backlog, leaf_first_order, rel, safe_name, severity_for,
)

FIXTURE = ROOT / "example-system" / "firmware-repo"
EXPECTED = FIXTURE / "expected"
TOOL = "tools/c_fleet_scan.py"

COLUMNS = [
    "path", "name", "kind", "language", "role", "size_bytes", "sha256", "lines", "code_lines", "functions", "defines",
    "includes_tree", "includes_system", "includes_vendor", "includes_unresolved", "calls_tree", "calls_libc", "calls_vendor",
    "calls_unresolved", "indirect_calls", "structures", "max_nesting", "volatile", "isr", "asm", "registers", "linker",
    "target_conditionals", "cpp_constructs", "callers_count", "classification", "reasons", "complexity", "priority",
    "missing_inputs", "notes",
]

SOURCE_EXT = {".c": "c", ".cc": "c++", ".cpp": "c++", ".cxx": "c++"}
HEADER_EXT = {".h": "c", ".hpp": "c++", ".hh": "c++", ".hxx": "c++"}
BUILD_NAMES = {"makefile", "gnumakefile", "cmakelists.txt", "meson.build", "build.ninja", "sconstruct", "project.yml", "west.yml", "kconfig"}
BUILD_EXT = {".mk", ".cmake", ".ld", ".icf", ".ewp", ".eww", ".uvprojx", ".uvproj", ".cproject", ".sct", ".scat"}
SKIP_DIRS = {".git", ".svn", ".hg", "build", "_build", "out", "cmake-build-debug", "cmake-build-release", "__pycache__", "node_modules", ".lvkit"}

KEYWORDS = frozenset("""alignas alignof and asm auto bool break case catch char class const constexpr const_cast continue decltype
default delete do double dynamic_cast else enum explicit export extern false float for friend goto if inline int long mutable
namespace new noexcept not nullptr operator or private protected public register reinterpret_cast return short signed sizeof
static static_assert static_cast struct switch template this throw true try typedef typeid typename union unsigned using
virtual void volatile wchar_t while _Alignas _Alignof _Atomic _Bool _Complex _Generic _Noreturn _Static_assert _Thread_local
__asm __asm__ __attribute__ __declspec __extension__ __inline __inline__ __typeof__ __volatile__ typeof override final
int8_t int16_t int32_t int64_t uint8_t uint16_t uint32_t uint64_t size_t ssize_t ptrdiff_t intptr_t uintptr_t uint_fast8_t
uint_fast16_t uint_fast32_t int_fast8_t int_fast16_t int_fast32_t uint_least8_t uint_least16_t uint_least32_t""".split())
STRUCT_KW = frozenset("if for while switch do".split())
ASM_KW = frozenset("asm __asm __asm__".split())
ATTR_KW = frozenset("__attribute__ __declspec alignas".split())

LIBC = frozenset("""abort abs acos asin assert atan atan2 atexit atof atoi atol bsearch calloc ceil clock cos cosh div exit exp
fabs fclose feof ferror fflush fgetc fgets floor fmod fopen fprintf fputc fputs fread free frexp fscanf fseek ftell fwrite
getc getchar getenv isalnum isalpha isdigit islower isprint isspace isupper isxdigit labs ldexp ldiv log log10 longjmp
malloc memchr memcmp memcpy memmove memset modf perror pow printf putc putchar puts qsort raise rand realloc remove rename
rewind scanf setbuf setjmp setvbuf signal sin sinh snprintf sprintf sqrt srand sscanf strcat strchr strcmp strcpy strcspn
strerror strlen strncat strncmp strncpy strpbrk strrchr strspn strstr strtod strtok strtol strtoul tan tanh time tolower
toupper ungetc vfprintf vprintf vsnprintf vsprintf va_start va_end va_arg va_copy offsetof
fmin fmax fminf fmaxf sqrtf fabsf floorf ceilf roundf round lround lrint rint truncf trunc powf expf logf sinf cosf tanf
atan2f hypot hypotf isnan isinf isfinite signbit copysign nan nanf INFINITY NAN
static_assert _Static_assert strnlen memccpy strdup strndup
""".split())
CPP_STD = frozenset("""move forward swap min max clamp abs size begin end data make_pair make_unique make_shared get tie
array vector string string_view span optional pair tuple function bind ref cref initializer_list numeric_limits fill copy
sort find find_if for_each accumulate distance advance next prev memcpy memset memcmp strlen strcmp strncmp strchr strncpy
static_cast reinterpret_cast const_cast dynamic_cast atomic_load atomic_store""".split())

VENDOR_PREFIX = ("HAL_", "LL_", "NVIC_", "SysTick_", "SystemCoreClock", "SystemInit", "SystemCoreClockUpdate", "__enable_irq",
                 "__disable_irq", "__WFI", "__WFE", "__DSB", "__DMB", "__ISB", "__NOP", "__get_", "__set_", "__BKPT", "__REV",
                 "nrf_", "nrfx_", "sd_", "app_", "esp_", "gpio_set_", "gpio_get_", "uart_", "spi_", "i2c_", "adc_", "dma_",
                 "CMSIS_", "RCC_", "GPIO_", "TIM_", "USART_", "SPI_", "I2C_", "ADC_", "DMA_", "EXTI_", "FLASH_", "PWR_",
                 "xTask", "vTask", "xQueue", "xSemaphore", "vSemaphore", "xTimer", "pvPortMalloc", "vPortFree", "taskENTER_",
                 "taskEXIT_", "portYIELD", "osDelay", "osThread", "osMutex", "osSemaphore", "osKernel", "k_sleep", "k_thread",
                 "k_sem", "k_mutex", "k_msleep", "k_work", "device_get_binding", "DEVICE_DT_GET", "printk", "tx_thread_",
                 "tx_semaphore_", "OSTaskCreate", "OSTimeDly", "sl_", "am_hal_", "Chip_", "R_", "MXC_", "XMC_", "Cy_", "cy_",
                 "wolfSSL_", "mbedtls_", "lwip_", "netif_", "tcpip_")
VENDOR_HEADER_MARKERS = ("stm32", "nrf", "cmsis", "core_cm", "hal_", "freertos", "task.h", "queue.h", "semphr.h", "cmsis_os", "zephyr",
                         "esp_", "driver/", "sdk_", "sl_", "am_mcu", "xmc", "cy_", "fsl_", "msp430", "avr/", "pico/", "hardware/",
                         "tx_api", "ucos", "lwip", "mbedtls")
LIBC_HEADERS = frozenset("""assert.h complex.h ctype.h errno.h fenv.h float.h inttypes.h iso646.h limits.h locale.h math.h setjmp.h
signal.h stdalign.h stdarg.h stdatomic.h stdbool.h stddef.h stdint.h stdio.h stdlib.h stdnoreturn.h string.h tgmath.h threads.h
time.h uchar.h wchar.h wctype.h unistd.h fcntl.h sys/types.h sys/stat.h pthread.h
cassert cctype cerrno cfloat climits cmath csetjmp csignal cstdarg cstddef cstdint cstdio cstdlib cstring ctime cwchar cwctype
algorithm array atomic bitset chrono functional initializer_list iterator limits memory new numeric optional ratio span string
string_view tuple type_traits typeinfo utility variant vector map set unordered_map unordered_set deque list queue stack iostream
sstream fstream ostream istream iomanip exception stdexcept system_error""".split())
TARGET_COND_RE = re.compile(r"\b(BOARD|STM32|NRF5|NRF|CORTEX|__ARM_ARCH|__arm__|__thumb__|__AVR|__MSP430|ESP32|__XTENSA|TARGET|"
                            r"USE_HAL_DRIVER|__GNUC__|__ICCARM__|__CC_ARM|__ARMCC_VERSION|CONFIG_|ZEPHYR|FREERTOS|__riscv|__linux__|_WIN32)", re.I)
ISR_NAME_RE = re.compile(r"^(?:\w+_IRQHandler|\w+_Handler|ISR_\w+|isr_\w+|\w+_isr|\w+_ISR)$")
REGISTER_RE = re.compile(r"\(\s*volatile\s+\w+\s*\*\s*\)\s*(?:\(|0x)|\b0x[24]\d{7}u?\b")
LINKER_RE = re.compile(r"\b_s(?:i)?data\b|\b_e(?:data|bss|stack)\b|\b_sbss\b|__attribute__\s*\(\s*\(\s*section|\bsection\s*\(|__bss_start|"
                       r"__data_start|__StackTop|__vector_table|\bReset_Handler\b|__isr_vector")
FUNC_MACRO_RE = re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)\(")
OBJ_MACRO_RE = re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)\b(?!\()")
INCLUDE_RE = re.compile(r'^\s*#\s*include\s*(?:"([^"]+)"|<([^>]+)>)')
TOKEN_RE = re.compile(r"[A-Za-z_]\w*(?:::[A-Za-z_~]\w*)*|\d[\w.]*|->|::|[{}()\[\];,=<>!&|+\-*/%^~?:.#]")
TEST_DIR_RE = re.compile(r"(^|/)(tests?|unittests?|unit_tests?|test_\w+|spec)(/|$)", re.I)
VENDOR_DIR_RE = re.compile(r"(^|/)(third[_-]?party|vendor|external|externals|sdk|cmsis|hal_driver|drivers/(?:cmsis|stm32\w*|nrfx))(/|$)", re.I)


# --- lexing -----------------------------------------------------------------------------------------------------


def strip_code(text: str) -> tuple[list[str], list[str], list[str], int]:
    """Remove comments, blank string/char literals, join `\\` continuations, and drop `#if 0` blocks. Returns
    (code lines, preprocessor lines, string literals, disabled-line count). Line count is preserved for code lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out, strings = [], []
    i, n = 0, len(text)
    buf: list[str] = []
    line_start, pp_line = True, False
    while i < n:
        c = text[i]
        if line_start and c not in " \t":
            pp_line = c == "#"
            line_start = False
        if c == "\n":
            line_start = True
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            block = text[i:(n if j < 0 else j + 2)]
            buf.append("\n" * block.count("\n"))
            i = n if j < 0 else j + 2
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            lit = text[i + 1:j]
            if c == '"' and not pp_line:
                strings.append(lit)
            buf.append(text[i:j + 1] if pp_line else ('""' if c == '"' else "'x'"))
            i = j + 1
        else:
            buf.append(c)
            i += 1
    raw = "".join(buf).replace("\\\n", " ")
    lines = raw.split("\n")
    code, pp, disabled = [], [], 0
    skip_depth, depth_stack = 0, []
    for line in lines:
        s = line.strip()
        if s.startswith("#"):
            d = re.sub(r"^#\s*", "#", s)
            word = d.split(None, 1)[0] if d else ""
            if word in ("#if", "#ifdef", "#ifndef"):
                zero = word == "#if" and re.fullmatch(r"#if\s+0", d) is not None
                depth_stack.append(zero)
                if zero:
                    skip_depth += 1
            elif word in ("#else", "#elif") and depth_stack and depth_stack[-1]:
                depth_stack[-1] = False
                skip_depth -= 1
            elif word == "#endif" and depth_stack:
                if depth_stack.pop():
                    skip_depth -= 1
            pp.append(d)
            code.append("")
            continue
        if skip_depth:
            disabled += 1
            code.append("")
        else:
            code.append(line)
    return code, pp, strings, disabled


def tokens_of(code_lines: list[str]) -> list[tuple[str, int]]:
    toks = []
    for ln, line in enumerate(code_lines, 1):
        for m in TOKEN_RE.finditer(line):
            toks.append((m.group(0), ln))
    return toks


def is_ident(t: str) -> bool:
    return bool(re.match(r"[A-Za-z_]|~[A-Za-z_]", t))


def parse_tokens(toks: list[tuple[str, int]]) -> dict:
    """One pass over the token stream: function definitions, prototypes, calls, indirect calls, structures, nesting, C++ facts."""
    defs, protos, calls, indirect, classes = [], [], [], [], []
    structures, max_nest, depth = 0, 0, 0
    templates = namespaces = overloads = 0
    i, n = 0, len(toks)
    paren_stack: list[str] = []  # what each open paren belongs to: "call", "def", "ctl", "attr", "other"
    seen_def_names: dict[str, int] = defaultdict(int)
    transparent_braces: list[bool] = []  # namespace/extern "C"/class bodies do not count as nesting

    def matching_paren(k: int) -> int:
        d = 0
        while k < n:
            if toks[k][0] == "(":
                d += 1
            elif toks[k][0] == ")":
                d -= 1
                if d == 0:
                    return k
            k += 1
        return -1

    while i < n:
        t, ln = toks[i]
        if t == "template":
            templates += 1
        elif t == "namespace":
            namespaces += 1
        elif t in ("class", "struct") and i + 1 < n and is_ident(toks[i + 1][0]):
            # class Name { ... }  (declaration only when followed by ';' or used as a type)
            k = i + 2
            while k < n and toks[k][0] not in ("{", ";", "(", ")", ","):
                k += 1
            if k < n and toks[k][0] == "{" and t == "class":
                classes.append(toks[i + 1][0])
        if t == "{":
            transparent = False
            k = i - 1
            while k >= 0 and toks[k][0] in (")", "]"):
                k -= 1
            if k >= 0 and (toks[k][0] in ("namespace", '""') or (is_ident(toks[k][0]) and k >= 1 and toks[k - 1][0] in ("namespace", "class", "struct", "union", "enum"))
                           or toks[k][0] in ("class", "struct", "union", "enum")):
                transparent = True
            if k >= 1 and toks[k - 1][0] == "extern" and toks[k][0] == '""':
                transparent = True
            transparent_braces.append(transparent)
            if not transparent:
                depth += 1
                max_nest = max(max_nest, depth)
        elif t == "}":
            if transparent_braces and not transparent_braces.pop():
                depth = max(0, depth - 1)
        elif t in STRUCT_KW:
            structures += 1
        elif t == "(":
            paren_stack.append("other")
        elif t == ")":
            if paren_stack:
                paren_stack.pop()
        if is_ident(t) and i + 1 < n and toks[i + 1][0] == "(":
            prev = toks[i - 1][0] if i > 0 else ""
            close = matching_paren(i + 1)
            if t in ATTR_KW:
                i = close + 1 if close > 0 else i + 1
                continue
            if t in KEYWORDS or t in ASM_KW:
                i += 1
                continue
            if prev in ("->", "."):
                indirect.append({"name": t.split("::")[-1], "line": ln})
                i += 1
                continue
            if close < 0:
                i += 1
                continue
            after = toks[close + 1][0] if close + 1 < n else ""
            access_ctor = prev == ":" and i >= 2 and toks[i - 2][0] in ("public", "private", "protected")
            decl_prev = is_ident(prev) or prev in ("*", "&", ">", "", ";", "{", "}", ")") or access_ctor
            operand_prev = prev in ("=", "return", ",", "(", "+", "-", "/", "!", "<", "|", "?", "[", "->", ".", "sizeof") or (prev == ":" and not access_ctor)
            if prev in ("*", "&"):   # `int *f(` is a declaration; `x * f(` is arithmetic - the token before decides
                decl_prev = i >= 2 and (is_ident(toks[i - 2][0]) or toks[i - 2][0] in (")", ">"))
            params = [x for x, _ in toks[i + 2:close]]
            knr_params = bool(params) and all(is_ident(p) for p in params[::2]) and all(p == "," for p in params[1::2]) and is_ident(after)
            # definition: `)` then `{`, possibly after const/noexcept/override/attributes/ctor init-list, or K&R declarations
            k = close + 1
            while k < n and toks[k][0] not in ("{", "}") and (toks[k][0] != ";" or knr_params):
                k += 1
            body_follows = k < n and toks[k][0] == "{"
            if depth == 0 and body_follows and decl_prev and not operand_prev:
                is_static = any(toks[j][0] == "static" for j in range(max(0, i - 4), i))
                defs.append({"name": t, "line": ln, "static": is_static, "knr": knr_params and toks[close + 1][0] != "{", "params": " ".join(params)})
                seen_def_names[t.split("::")[-1]] += 1
                i = k
                continue
            if depth == 0 and after == ";" and decl_prev and not operand_prev:
                protos.append(t)
                i = close + 1
                continue
            calls.append({"name": t, "line": ln})
        i += 1
    overloads = sum(1 for c in seen_def_names.values() if c > 1)
    return {"defs": defs, "protos": sorted(set(protos)), "calls": calls, "indirect": indirect, "structures": structures,
            "max_nesting": max_nest, "templates": templates, "namespaces": namespaces, "overloads": overloads, "classes": classes}


# --- per-file ---------------------------------------------------------------------------------------------------


def parse_file(path: Path, tree: Path) -> dict:
    raw = path.read_bytes()
    notes = []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
        notes.append("not valid UTF-8; decoded with replacement characters")
    if "\r\n" in text:
        notes.append("CRLF line endings")
    ext = path.suffix.lower()
    kind = "source" if ext in SOURCE_EXT else "header"
    language = SOURCE_EXT.get(ext) or HEADER_EXT.get(ext, "c")
    code, pp, strings, disabled = strip_code(text)
    if disabled:
        notes.append(f"{disabled} line(s) inside `#if 0`, ignored")
    toks = tokens_of(code)
    parsed = parse_tokens(toks)
    joined = "\n".join(code)
    relp = path.relative_to(tree).as_posix()
    includes_q, includes_a = [], []
    func_macros, obj_macros, target_cond, has_error = [], [], 0, False
    for d in pp:
        m = INCLUDE_RE.match(d)
        if m:
            (includes_q if m.group(1) else includes_a).append(m.group(1) or m.group(2))
            continue
        m = FUNC_MACRO_RE.match(d)
        if m:
            func_macros.append(m.group(1))
            continue
        m = OBJ_MACRO_RE.match(d)
        if m:
            obj_macros.append(m.group(1))
            continue
        if d.startswith(("#if", "#elif")) and TARGET_COND_RE.search(d):
            target_cond += 1
        if d.startswith("#error"):
            has_error = True
    if language == "c++" and "std::" in joined:
        cpp = True
    else:
        cpp = language == "c++"
    isr_names = sorted({d["name"] for d in parsed["defs"] if ISR_NAME_RE.match(d["name"].split("::")[-1])})
    if re.search(r"__attribute__\s*\(\s*\(\s*(interrupt|isr|signal)\b|\bISR\s*\(|\b__irq\b|\b__interrupt\b", joined):
        isr_names.append("(interrupt attribute)")
    asm_count = len(re.findall(r"\b(?:__asm__|__asm|asm)\b", joined))
    registers = len(REGISTER_RE.findall(joined)) + sum(1 for d in pp if REGISTER_RE.search(d))
    linker = len(LINKER_RE.findall(joined))
    volatile = len(re.findall(r"\bvolatile\b", joined)) + sum(1 for d in pp if "volatile" in d)
    role = "test" if TEST_DIR_RE.search(relp) or path.stem.startswith("test_") or path.stem.endswith("_test") else \
        "vendor" if VENDOR_DIR_RE.search(relp) else "source"
    code_lines = sum(1 for l in code if l.strip())
    return {
        "path": relp, "name": path.name, "kind": kind, "language": language, "role": role, "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest()[:16], "lines": text.count("\n") + (1 if text and not text.endswith("\n") else 0),
        "code_lines": code_lines, "defs": parsed["defs"], "protos": parsed["protos"], "calls": parsed["calls"], "indirect": parsed["indirect"],
        "structures": parsed["structures"], "max_nesting": parsed["max_nesting"], "templates": parsed["templates"],
        "namespaces": parsed["namespaces"], "overloads": parsed["overloads"], "classes": parsed["classes"], "cpp": cpp,
        "includes_quoted": includes_q, "includes_angle": includes_a, "func_macros": func_macros, "obj_macros": obj_macros,
        "target_conditionals": target_cond, "has_error_directive": has_error, "isr": isr_names, "asm": asm_count,
        "registers": registers, "linker": linker, "volatile": volatile, "strings": strings, "notes": notes, "callers": set(),
        "includers": set(),
    }


def discover(tree: Path) -> tuple[list[Path], list[Path]]:
    code, build = [], []
    for p in sorted(tree.rglob("*")):
        if not p.is_file():
            continue
        parts = p.relative_to(tree).parts
        if any(part in SKIP_DIRS or (part.startswith(".") and part not in (".", "..")) for part in parts[:-1]):
            continue
        ext = p.suffix.lower()
        if ext in SOURCE_EXT or ext in HEADER_EXT:
            code.append(p)
        elif p.name.lower() in BUILD_NAMES or ext in BUILD_EXT:
            build.append(p)
    return code, build


# --- resolution -------------------------------------------------------------------------------------------------


def resolve(files: list[dict], extra_libc: frozenset[str]) -> dict:
    by_path = {f["path"]: f for f in files}
    by_basename: dict[str, list[str]] = defaultdict(list)
    for f in files:
        by_basename[Path(f["path"]).name].append(f["path"])
    def_files: dict[str, set[str]] = defaultdict(set)          # plain name -> files defining a non-static function
    method_files: dict[str, set[str]] = defaultdict(set)       # method name (Class::m or inline in class) -> files
    macro_files: dict[str, set[str]] = defaultdict(set)
    header_static: dict[str, set[str]] = defaultdict(set)     # static/inline functions defined in headers
    for f in files:
        for d in f["defs"]:
            name = d["name"]
            if "::" in name:
                method_files[name.split("::")[-1]].add(f["path"])
            elif not d["static"]:
                def_files[name].add(f["path"])
            elif f["kind"] == "header":
                header_static[name].add(f["path"])
            if f["classes"] and "::" not in name and f["kind"] == "header":
                method_files[name].add(f["path"])
        for mname in f["func_macros"]:
            macro_files[mname].add(f["path"])
    edges: list[dict] = []
    seen_edges: set[tuple[str, str, str]] = set()

    def add(frm: str, to: str, kind: str, via: str) -> None:
        key = (frm, to, kind)
        if frm == to:
            return
        if key not in seen_edges:
            seen_edges.add(key)
            edges.append({"from": frm, "to": to, "kind": kind, "via": [via]})
        else:
            e = next(e for e in edges if (e["from"], e["to"], e["kind"]) == key)
            if via not in e["via"]:
                e["via"].append(via)

    for f in files:
        f["includes_tree"], f["includes_system"], f["includes_vendor"], f["includes_unresolved"] = [], [], [], []
        base_dir = Path(f["path"]).parent
        for inc in f["includes_quoted"]:
            cand = (base_dir / inc).as_posix().replace("./", "") if not inc.startswith("/") else inc
            cand = Path(cand).as_posix()
            # normalise ../
            parts: list[str] = []
            for part in cand.split("/"):
                if part == "..":
                    if parts:
                        parts.pop()
                elif part and part != ".":
                    parts.append(part)
            cand = "/".join(parts)
            if cand in by_path:
                f["includes_tree"].append(cand)
                add(f["path"], cand, "include", inc)
                by_path[cand]["includers"].add(f["path"])
                continue
            matches = by_basename.get(Path(inc).name, [])
            if len(matches) == 1:
                f["includes_tree"].append(matches[0])
                add(f["path"], matches[0], "include", inc)
                by_path[matches[0]]["includers"].add(f["path"])
            elif len(matches) > 1:
                for m_ in matches:
                    add(f["path"], m_, "ambiguous-include", inc)
                f["includes_unresolved"].append(inc + " (ambiguous: " + ", ".join(matches) + ")")
            elif any(k in inc.lower() for k in VENDOR_HEADER_MARKERS):
                f["includes_vendor"].append(inc)
            else:
                f["includes_unresolved"].append(inc)
        for inc in f["includes_angle"]:
            if inc in LIBC_HEADERS or inc.split("/")[-1] in LIBC_HEADERS:
                f["includes_system"].append(inc)
            elif any(k in inc.lower() for k in VENDOR_HEADER_MARKERS):
                f["includes_vendor"].append(inc)
            else:
                matches = by_basename.get(Path(inc).name, [])
                if len(matches) == 1:
                    f["includes_tree"].append(matches[0])
                    add(f["path"], matches[0], "include", inc)
                    by_path[matches[0]]["includers"].add(f["path"])
                else:
                    f["includes_unresolved"].append("<" + inc + ">")
    closure_of: dict[str, set[str]] = {}

    def closure(p: str) -> set[str]:
        if p not in closure_of:
            seen_h, stack = set(), list(by_path[p]["includes_tree"])
            while stack:
                h = stack.pop()
                if h not in seen_h and h in by_path:
                    seen_h.add(h)
                    stack += by_path[h]["includes_tree"]
            closure_of[p] = seen_h
        return closure_of[p]

    for f in files:
        local = {d["name"] for d in f["defs"]} | {d["name"].split("::")[-1] for d in f["defs"]} | set(f["func_macros"]) | set(f["classes"])
        local_types = set(f["obj_macros"])
        f["calls_tree"], f["calls_libc"], f["calls_vendor"], f["calls_unresolved"], f["calls_local"], f["calls_macro"] = [], [], [], [], [], []
        seen: set[str] = set()
        for c in f["calls"]:
            name = c["name"]
            plain = name.split("::")[-1]
            if name in seen:
                continue
            seen.add(name)
            if name.startswith("std::") or name.startswith("::"):
                if plain in LIBC or plain in CPP_STD or plain in extra_libc:
                    f["calls_libc"].append(name)
                else:
                    f["calls_unresolved"].append(name)
                continue
            if name in local or plain in local or name in local_types:
                f["calls_local"].append(name)
                continue
            if name in def_files:
                targets = sorted(def_files[name])
                non_test = [t for t in targets if by_path[t]["role"] != "test"]
                targets = non_test or targets
                if len(targets) == 1:
                    f["calls_tree"].append(name)
                    add(f["path"], targets[0], "call", name)
                    by_path[targets[0]]["callers"].add(f["path"])
                else:
                    f["calls_tree"].append(name + " (ambiguous)")
                    for t in targets:
                        add(f["path"], t, "ambiguous", name)
                continue
            if name in header_static:
                targets = sorted(header_static[name] & closure(f["path"])) or sorted(header_static[name])
                if len(targets) == 1:
                    f["calls_tree"].append(name)
                    add(f["path"], targets[0], "call", name)
                    by_path[targets[0]]["callers"].add(f["path"])
                else:
                    f["calls_tree"].append(name + " (ambiguous)")
                    for t in targets:
                        add(f["path"], t, "ambiguous", name)
                continue
            if name in macro_files:
                targets = sorted(macro_files[name])
                f["calls_macro"].append(name)
                if len(targets) == 1:
                    add(f["path"], targets[0], "macro", name)
                    by_path[targets[0]]["callers"].add(f["path"])
                continue
            if name in LIBC or name in extra_libc or (f["cpp"] and name in CPP_STD):
                f["calls_libc"].append(name)
                continue
            if name.startswith(VENDOR_PREFIX):
                f["calls_vendor"].append(name)
                continue
            if name in protos_everywhere(files) and name not in def_files:
                f["calls_unresolved"].append(name + " (declared in the tree, defined elsewhere)")
                continue
            f["calls_unresolved"].append(name)
        f["indirect_names"] = sorted({c["name"] for c in f["indirect"]})
        for name in f["indirect_names"]:
            targets = sorted(method_files.get(name, set()) - {f["path"]})
            if len(targets) == 1:
                add(f["path"], targets[0], "method-name", name)
                by_path[targets[0]]["callers"].add(f["path"])
    # declared-but-defined-elsewhere: functions a header declares whose definition is in a retain file are seam candidates
    seams = []
    for f in files:
        for d in f["defs"]:
            if d["static"] or "::" in d["name"]:
                continue
            callers = sorted({e["from"] for e in edges if e["to"] == f["path"] and e["kind"] == "call" and d["name"] in e["via"]})
            if callers:
                seams.append({"function": d["name"], "defined_in": f["path"], "callers": callers})
    return {"edges": edges, "seams": seams, "def_files": {k: sorted(v) for k, v in def_files.items()}}


_PROTOS_CACHE: dict[int, set[str]] = {}


def protos_everywhere(files: list[dict]) -> set[str]:
    key = id(files)
    if key not in _PROTOS_CACHE:
        _PROTOS_CACHE[key] = {p for f in files for p in f["protos"]}
    return _PROTOS_CACHE[key]


# --- classification ---------------------------------------------------------------------------------------------


def classify(f: dict, retain_paths: set[str]) -> tuple[str, list[str]]:
    reasons = []
    if not f["code_lines"] and not f["defs"] and not f["obj_macros"] and not f["func_macros"]:
        return "unreadable", ["no code after stripping comments"]
    target = []
    if f["isr"]:
        target.append("ISR handler(s): " + ", ".join(f["isr"]))
    if f["asm"]:
        target.append(f"inline asm x{f['asm']}")
    if f["registers"]:
        target.append(f"memory-mapped register access x{f['registers']}")
    if f["linker"]:
        target.append(f"linker symbols / section attributes x{f['linker']}")
    if f["includes_vendor"]:
        target.append("vendor headers: " + ", ".join(f["includes_vendor"][:3]))
    if f["has_error_directive"]:
        target.append("#error unless a board macro is defined")
    if target:
        reasons = ["target-only: " + "; ".join(target)]
        if f["calls_vendor"]:
            reasons.append("vendor/RTOS calls: " + ", ".join(f["calls_vendor"][:4]))
        return "retain", reasons
    cls = "port"
    if f["role"] == "vendor":
        cls = "wrap"
        reasons.append("third-party code: keep as a dependency or replace with a vetted equivalent, do not rewrite")
    if f["calls_vendor"]:
        cls = "wrap"
        reasons.append("vendor/RTOS calls to stub on a host: " + ", ".join(f["calls_vendor"][:4]))
    retained_deps = sorted(p for p in f["includes_tree"] if p in retain_paths)
    if retained_deps and cls == "port":
        cls = "wrap"
        reasons.append("includes target-only header(s): " + ", ".join(retained_deps))
    if f["target_conditionals"]:
        reasons.append(f"{f['target_conditionals']} board/architecture #if block(s); the host build must pick one")
    if f["indirect_names"]:
        reasons.append("calls through pointers / by method name: " + ", ".join(f["indirect_names"][:4]))
    if f["calls_unresolved"]:
        reasons.append(f"{len(f['calls_unresolved'])} unresolved call(s)")
    if f["volatile"] and cls == "port":
        reasons.append(f"volatile x{f['volatile']} (shared with an ISR? check before host testing)")
    if f["templates"]:
        reasons.append(f"C++ template(s) x{f['templates']}: needs an explicit instantiation to test")
    if f["overloads"]:
        reasons.append(f"{f['overloads']} overloaded name(s): call edges are by name, not signature")
    if any(d["knr"] for d in f["defs"]):
        reasons.append("K&R-style definition(s)")
    if f["kind"] == "header" and not f["defs"] and cls == "port":
        reasons.append("declarations and macros only")
    elif not f["defs"] and f["kind"] == "source":
        reasons.append("no function definitions found")
    if f["role"] == "test":
        reasons.append("existing test: reuse it, do not add a second framework")
    if any("UTF-8" in n_ for n_ in f["notes"]):
        reasons.append("not valid UTF-8: confirm the encoding with the owner before editing")
    if not reasons:
        reasons.append("host-testable as-is: every call resolved, no hardware markers")
    return cls, reasons


def complexity(f: dict, out_edges: int) -> int:
    return (f["code_lines"] // 10 + 2 * f["structures"] + 3 * out_edges + 5 * len(f["calls_unresolved"]) + 4 * len(f["indirect_names"])
            + 3 * f["target_conditionals"] + 2 * f["max_nesting"] + 2 * len(f["func_macros"]) + 3 * f["templates"] + 2 * f["overloads"])


def priority(callers: int, missing: list[str], score: int) -> int:
    return 100 + 10 * min(callers, 5) + (0 if "vectors" in missing else 20) + (0 if "test" in missing else 10) - min(score, 60)


def missing_inputs(f: dict, tree: Path, files: list[dict], edges: list[dict]) -> list[str]:
    missing = []
    stem = Path(f["path"]).stem
    vec = [p for p in tree.rglob(f"*{stem}*vector*") if p.is_file()] + [p for p in tree.rglob(f"*{stem}*.csv") if p.is_file() and "vector" in p.parent.name]
    if not vec:
        missing.append("vectors")
    tests = {e["from"] for e in edges if e["to"] == f["path"] and e["kind"] in ("call", "include", "method-name", "macro")}
    if not any(next((x for x in files if x["path"] == t), {}).get("role") == "test" for t in tests):
        missing.append("test")
    return missing


# --- gcc -MM cross-check ----------------------------------------------------------------------------------------


def gcc_check(tree: Path, files: list[dict], cflags: list[str], enabled: bool) -> dict:
    gcc = shutil.which("gcc") if enabled else None
    if not gcc:
        return {"reader": "gcc absent" if enabled else "gcc disabled (--no-gcc)", "files_checked": 0, "failed": [], "extra_headers": {}, "confirmed": 0}
    try:
        ver = subprocess.run([gcc, "--version"], capture_output=True, text=True, timeout=20).stdout.splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        return {"reader": "gcc present but not runnable", "files_checked": 0, "failed": [], "extra_headers": {}, "confirmed": 0}
    inc_dirs = sorted({str(tree / Path(f["path"]).parent) for f in files if f["kind"] == "header"})
    args_inc = [a for d in inc_dirs for a in ("-I", d)]
    checked, failed, extra, confirmed = 0, [], {}, 0
    for f in files:
        if f["kind"] != "source":
            continue
        cmd = [gcc, "-MM", "-MG", "-x", "c++" if f["language"] == "c++" else "c"] + cflags + args_inc + [str(tree / f["path"])]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as e:
            failed.append({"path": f["path"], "error": type(e).__name__})
            continue
        checked += 1
        if r.returncode:
            err_lines = r.stderr.strip().splitlines() or ["non-zero exit"]
            msg = next((l for l in err_lines if "error" in l), err_lines[-1])
            failed.append({"path": f["path"], "error": msg.split(":", 3)[-1].strip()[:120] if "error" in msg else msg[:120]})
            continue
        deps = r.stdout.replace("\\\n", " ").split(":", 1)[-1].split()
        gcc_headers = set()
        for d in deps:
            p = Path(d)
            try:
                gcc_headers.add(p.resolve().relative_to(tree).as_posix())
            except ValueError:
                gcc_headers.add(p.name)
        static_direct = set(f["includes_tree"])
        # transitive static closure
        stack, closure = list(static_direct), set()
        by_path = {x["path"]: x for x in files}
        while stack:
            h = stack.pop()
            if h in closure:
                continue
            closure.add(h)
            stack += by_path[h]["includes_tree"] if h in by_path else []
        missing_static = sorted(h for h in gcc_headers if h not in closure and h != f["path"] and not h.endswith((".c", ".cpp", ".cc", ".cxx")))
        if missing_static:
            extra[f["path"]] = missing_static
        else:
            confirmed += 1
    return {"reader": ver, "files_checked": checked, "failed": failed, "extra_headers": extra, "confirmed": confirmed, "cflags": cflags}


# --- scan -------------------------------------------------------------------------------------------------------


def scan_tree(tree: Path, extra_libc: frozenset[str] = frozenset(), cflags: list[str] | None = None, use_gcc: bool = True) -> dict:
    tree = tree.resolve()
    if not tree.is_dir():
        raise SystemExit(f"{tree} is not a directory")
    paths, build_files = discover(tree)
    files, unreadable = [], []
    for p in paths:
        try:
            files.append(parse_file(p, tree))
        except (OSError, RecursionError, ValueError, IndexError) as e:
            unreadable.append({"path": p.relative_to(tree).as_posix(), "error": f"{type(e).__name__}: {str(e)[:80]}"})
    _PROTOS_CACHE.clear()
    graph = resolve(files, extra_libc)
    out_edges = defaultdict(list)
    for e in graph["edges"]:
        out_edges[e["from"]].append(e)
    # two passes: target-only files first, then files that include them
    retain_paths: set[str] = set()
    for f in files:
        f["classification"], f["reasons"] = classify(f, set())
        if f["classification"] == "retain":
            retain_paths.add(f["path"])
    rows = []
    for f in files:
        f["classification"], f["reasons"] = classify(f, retain_paths)
        callers = f["callers"] | (f["includers"] if f["kind"] == "header" else set())
        score = complexity(f, len({e["to"] for e in out_edges[f["path"]] if e["kind"] in ("call", "macro", "method-name")}))
        missing = missing_inputs(f, tree, files, graph["edges"])
        cppc = [x for x in (f"{len(f['classes'])} class" if f["classes"] else "", f"{f['templates']} template" if f["templates"] else "",
                            f"{f['namespaces']} namespace" if f["namespaces"] else "", f"{f['overloads']} overload" if f["overloads"] else "") if x]
        rows.append({
            "path": f["path"], "name": f["name"], "kind": f["kind"], "language": f["language"], "role": f["role"], "size_bytes": f["size_bytes"],
            "sha256": f["sha256"], "lines": f["lines"], "code_lines": f["code_lines"], "functions": len(f["defs"]),
            "defines": len(f["obj_macros"]) + len(f["func_macros"]), "includes_tree": ";".join(f["includes_tree"]),
            "includes_system": ";".join(f["includes_system"]), "includes_vendor": ";".join(f["includes_vendor"]),
            "includes_unresolved": ";".join(f["includes_unresolved"]), "calls_tree": ";".join(f["calls_tree"] + [m + " (macro)" for m in f["calls_macro"]]),
            "calls_libc": ";".join(f["calls_libc"]), "calls_vendor": ";".join(f["calls_vendor"]), "calls_unresolved": ";".join(f["calls_unresolved"]),
            "indirect_calls": ";".join(f["indirect_names"]), "structures": f["structures"], "max_nesting": f["max_nesting"], "volatile": f["volatile"],
            "isr": ";".join(f["isr"]), "asm": f["asm"], "registers": f["registers"], "linker": f["linker"], "target_conditionals": f["target_conditionals"],
            "cpp_constructs": ";".join(cppc), "callers_count": len(callers), "classification": f["classification"], "reasons": "; ".join(f["reasons"]),
            "complexity": score, "priority": priority(len(callers), missing, score), "missing_inputs": ";".join(missing), "notes": "; ".join(f["notes"]),
        })
        f["callers_count"] = len(callers)
    for u in unreadable:
        rows.append({**{c: "" for c in COLUMNS}, "path": u["path"], "name": Path(u["path"]).name, "kind": "unreadable", "role": "source",
                     "classification": "unreadable", "reasons": u["error"], "complexity": 0, "priority": 0, "callers_count": 0, "notes": u["error"]})
    rows.sort(key=lambda r: r["path"])
    rows_by_path = {r["path"]: r for r in rows}
    call_edges = [e for e in graph["edges"] if e["kind"] in ("call", "macro", "method-name", "ambiguous")]
    order, cycles = leaf_first_order(sorted(f["path"] for f in files), call_edges)
    entry = sorted(f["path"] for f in files if any(d["name"] == "main" for d in f["defs"]) or f["isr"])
    orphans = sorted(f["path"] for f in files if f["kind"] == "source" and f["role"] != "test" and not f["callers"] and f["path"] not in entry)
    tests = sorted(f["path"] for f in files if f["role"] == "test")
    gcc = gcc_check(tree, files, cflags or [], use_gcc)
    classification = {k: sum(1 for r in rows if r["classification"] == k) for k in ("port", "wrap", "retain", "unreadable")}
    external: dict[str, list[str]] = {"libc": sorted({c for f in files for c in f["calls_libc"]}), "vendor": sorted({c for f in files for c in f["calls_vendor"]})}
    vendor_headers = sorted({h for f in files for h in f["includes_vendor"]})
    cls_of = {f["path"]: f["classification"] for f in files}
    seam = [{**x, "callers": [cp for cp in x["callers"] if cls_of[cp] != "retain"]} for x in graph["seams"] if cls_of[x["defined_in"]] in ("retain", "wrap")]
    seam = [x for x in seam if x["callers"]]
    dep_map = {
        "_about": f"Candidate include and call graph written by {TOOL}. Edges are static: `include` = #include resolved to a tree file, "
                  "`ambiguous-include` = two tree files share the name, `call` = identifier( resolved to the one file that defines it, "
                  "`macro` = function-like macro defined in the tree, `method-name` = a->f( / a.f( matched by method name only, "
                  "`ambiguous` = two files define the name. Macros are not expanded, #if is not evaluated, function pointers are "
                  "reported per file and not followed.",
        "tree": str(tree),
        "nodes": [{"path": f["path"], "name": f["name"], "kind": f["kind"], "language": f["language"], "role": f["role"], "classification": f["classification"],
                   "complexity": rows_by_path[f["path"]]["complexity"], "callers": f["callers_count"], "functions": sorted(d["name"] for d in f["defs"])} for f in files],
        "edges": graph["edges"],
        "external_calls": external, "vendor_headers": vendor_headers,
        "unresolved": {f["path"]: f["calls_unresolved"] for f in files if f["calls_unresolved"]},
        "unresolved_includes": {f["path"]: f["includes_unresolved"] for f in files if f["includes_unresolved"]},
        "indirect_calls": {f["path"]: f["indirect_names"] for f in files if f["indirect_names"]},
        "target_only": sorted(retain_paths),
        "seam_candidates": seam,
        "entry_points": entry, "orphans": orphans, "tests": tests, "cycles": cycles, "leaf_first_order": order,
        "build_files": sorted(p.relative_to(tree).as_posix() for p in build_files),
        "include_check": gcc, "unreadable": unreadable,
    }
    summary = {
        "tool": TOOL, "tree": str(tree),
        "counts": {"files": len(paths), "parsed": len(files), "unreadable": len(unreadable), "sources": sum(1 for f in files if f["kind"] == "source"),
                   "headers": sum(1 for f in files if f["kind"] == "header"), "cpp_files": sum(1 for f in files if f["language"] == "c++"),
                   "functions": sum(len(f["defs"]) for f in files), "tests": len(tests), "build_files": len(build_files),
                   "include_edges": sum(1 for e in graph["edges"] if e["kind"] == "include"),
                   "call_edges": sum(1 for e in graph["edges"] if e["kind"] in ("call", "macro", "method-name")),
                   "ambiguous_edges": sum(1 for e in graph["edges"] if e["kind"] in ("ambiguous", "ambiguous-include")),
                   "unresolved_calls": sum(len(f["calls_unresolved"]) for f in files), "indirect_calls": sum(len(f["indirect_names"]) for f in files),
                   "vendor_calls": len(external["vendor"]), "target_only_files": len(retain_paths), "seam_candidates": len(seam), "cycles": len(cycles)},
        "classification": classification, "complexity_total": sum(int(r["complexity"]) for r in rows),
        "entry_points": entry, "orphans": orphans, "target_only": sorted(retain_paths), "vendor_headers": vendor_headers,
        "include_reader": gcc["reader"],
        "notes": [
            "static candidate graph: identifiers followed by `(`; macros were not expanded, #if was not evaluated, function pointers and "
            "virtual calls were not followed",
            f"C/C++ standard-library list has {len(LIBC | CPP_STD | extra_libc)} names; vendor/RTOS calls matched by prefix; anything else is `unresolved`",
            f"include cross-check: {gcc['reader']}"
            + (f", {gcc['confirmed']} of {gcc['files_checked']} sources confirmed, {len(gcc['failed'])} could not be preprocessed" if gcc["files_checked"] else ""),
        ],
    }
    if gcc["extra_headers"]:
        summary["notes"].append(f"gcc found headers the static include walk did not for {len(gcc['extra_headers'])} source(s); see dependency map include_check")
    if unreadable:
        summary["notes"].append(f"{len(unreadable)} file(s) could not be read; see the inventory")
    if any(f["notes"] for f in files):
        summary["notes"].append(f"{sum(1 for f in files if f['notes'])} file(s) carry notes (encoding, CRLF, #if 0)")
    return {"rows": rows, "summary": summary, "dep_map": dep_map, "files": files, "out_edges": out_edges, "build_files": build_files, "tree": tree}


# --- outputs ---------------------------------------------------------------------------------------------------


def build_backlog(rows: list[dict], top: int, prefix: str, opened: str) -> list[dict]:
    check_prefix(prefix)
    candidates = [r for r in rows if r["classification"] in ("port", "wrap") and r["role"] != "test" and not (r["kind"] == "header" and not r["functions"])]
    candidates.sort(key=lambda r: (-int(r["priority"]), r["classification"] != "port", r["path"]))
    items = []
    for n, r in enumerate(candidates[: min(top, 999)], start=1):
        component = component_slug(r["path"].split("/")[0] if "/" in r["path"] else "root")
        verb = "Host-test and port" if r["classification"] == "port" else "Stub and wrap"
        items.append({
            "id": f"{prefix}-CAP-{n:03d}", "type": "capability", "title": f"{verb} {r['name']}"[:120],
            "severity": severity_for(int(r["complexity"])), "status": "proposed", "component": component,
            "requirements": [], "hazards": [], "opened": opened, "closed": None, "owner": "test-automation",
            "notes": (f"{r['classification']}: {r['reasons']}. complexity {r['complexity']}, priority {r['priority']}, "
                      f"callers {r['callers_count']}. missing: {r['missing_inputs'] or 'none'}. path: {r['path']}"),
        })
    return items


C_EDGE_STYLE = {"include": 'style=dotted color="#777777"', "ambiguous-include": 'style=dotted color=red label="ambiguous"', "call": "",
                "macro": 'style=dashed label="macro"', "method-name": 'style=dashed label="method?"', "ambiguous": 'color=red style=dashed label="ambiguous"'}


def c_dot(dep_map: dict, cap: int) -> str:
    nodes = [{"id": n["path"], "label": f"{n['name']}\\n{n['kind']}", "classification": n["classification"], "rank": n["callers"] + n["complexity"]}
             for n in dep_map["nodes"]]
    return dot_text("c_tree", nodes, dep_map["edges"], C_EDGE_STYLE, cap)


def repo_map_md(name: str, result: dict) -> str:
    s, m = result["summary"], result["dep_map"]
    files_by_path = {f["path"]: f for f in result["files"]}
    rows_by_path = {r["path"]: r for r in result["rows"]}
    c, k = s["counts"], s["classification"]
    L = [f"# Repo map: {name}", "",
         f"Generated by `{TOOL}` from `{s['tree']}`. Every statement below is a static fact about the source text; nothing was "
         "compiled for a target or executed. The agent that documents this tree, or writes its host harness, starts from this file "
         "and the per-unit prompt packs, not from the whole tree.", "",
         "## Shape", "",
         f"- {c['files']} files: {c['sources']} sources, {c['headers']} headers ({c['cpp_files']} C++), {c['functions']} function definitions, "
         f"{c['tests']} test files, {c['build_files']} build/linker files, {c['unreadable']} unreadable",
         f"- classification: port {k['port']} (host-testable), wrap {k['wrap']} (stub HAL or keep vendor code), retain {k['retain']} (target-only), "
         f"unreadable {k['unreadable']}",
         f"- {c['include_edges']} include edges, {c['call_edges']} call edges, {c['ambiguous_edges']} ambiguous, {c['unresolved_calls']} unresolved calls, "
         f"{c['indirect_calls']} indirect/method-name calls, {c['cycles']} cycle(s)",
         f"- include cross-check: {s['include_reader']}", ""]
    L += ["## Build and target", ""]
    L += [f"- `{b}`" for b in m["build_files"]] or ["- no build files found (Makefile, CMakeLists.txt, linker script, IDE project)"]
    for b in result["build_files"]:
        if b.name.lower() in ("makefile", "cmakelists.txt") and b.stat().st_size < 200_000:
            try:
                txt = b.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            hits = sorted({h for h in re.findall(r"(arm-none-eabi-\w+|iccarm|armclang|xtensa-\w+|riscv\d*-\w+|-mcpu=\S+|-mthumb|-D[A-Z_][A-Z0-9_]*)", txt)})
            if hits:
                L.append(f"  - `{b.relative_to(result['tree']).as_posix()}` toolchain/target hints: " + ", ".join(f"`{h}`" for h in hits[:10]))
    L += ["", "## Target-only files (retain in the target build; the host harness stubs their interface)", ""]
    L += [f"- `{p}`: {rows_by_path[p]['reasons']}" for p in m["target_only"]] or ["- none: every file compiles on a host as-is"]
    L += ["", "## Seam candidates (functions defined in target-only or wrap files and called from host-side code)", "",
          "This is the line `templates/host-harness/hal_stub.h` redeclares: keep the prototypes, replace the bodies with the stub.", ""]
    L += [f"- `{x['function']}` in `{x['defined_in']}` <- " + ", ".join(f"`{cpath}`" for cpath in x["callers"]) for x in m["seam_candidates"]] or ["- none found"]
    L += ["", "## Entry points (main, interrupt handlers) and their call trees", ""]

    def label_of(p: str) -> str:
        f = files_by_path[p]
        return f"{f['path']} [{f['kind']}, {f['classification']}]"

    def extras_of(p: str) -> list[str]:
        f = files_by_path[p]
        return [x for x in (f"vendor calls: {', '.join(f['calls_vendor'])}" if f["calls_vendor"] else "",
                            f"unresolved: {', '.join(f['calls_unresolved'])}" if f["calls_unresolved"] else "",
                            f"indirect: {', '.join(f['indirect_names'])}" if f["indirect_names"] else "") if x]

    call_out = defaultdict(list)
    for e in m["edges"]:
        if e["kind"] in ("call", "macro", "method-name"):
            call_out[e["from"]].append(e)
    if not m["entry_points"]:
        L.append("- none found (no `main` and no interrupt handler; a library tree)")
    for p in m["entry_points"]:
        L += call_tree_lines(p, call_out, label_of, extras_of) + [""]
    L += ["## Leaf-first order for host testing and porting", "",
          "Units whose callees are already covered come first: build a host test for each in this order and every dependency has a "
          "proven twin or stub when its own vectors are replayed. Retain items are listed so the boundary is visible.", ""]
    for i, p in enumerate(m["leaf_first_order"], 1):
        r = rows_by_path[p]
        L.append(f"{i}. `{p}` - {r['kind']}, {r['classification']}, complexity {r['complexity']}, callers {r['callers_count']}")
    if m["cycles"]:
        L += ["", "Cycles (test together, or break the cycle first):"] + [f"- {' <-> '.join(g)}" for g in m["cycles"]]
    L += ["", "## External calls", "",
          f"- C/C++ standard library ({len(m['external_calls']['libc'])}): " + (", ".join(m["external_calls"]["libc"]) or "none"),
          f"- vendor / RTOS ({len(m['external_calls']['vendor'])}): " + (", ".join(m["external_calls"]["vendor"]) or "none"),
          f"- vendor headers: " + (", ".join(m["vendor_headers"]) or "none")]
    L += ["", "## Indirect and method-name calls (not followed)", ""]
    L += [f"- `{p}`: " + ", ".join(v) for p, v in m["indirect_calls"].items()] or ["- none"]
    L += ["", "## Unresolved calls", "", "Not defined in the tree, not standard library, not a known vendor prefix. Each is a question for the owner: "
          "a library, generated code, a macro the scanner did not expand, or a name it mistook for a call.", ""]
    L += [f"- `{p}`: " + ", ".join(v) for p, v in m["unresolved"].items()] or ["- none"]
    if m["unresolved_includes"]:
        L += ["", "## Unresolved includes", ""] + [f"- `{p}`: " + ", ".join(v) for p, v in m["unresolved_includes"].items()]
    L += ["", "## Orphans (sources nothing in the tree calls)", ""]
    L += [f"- `{p}`" for p in m["orphans"]] or ["- none"]
    ic = m["include_check"]
    L += ["", "## Include cross-check", "", f"- reader: {ic['reader']}"]
    if ic["files_checked"]:
        L.append(f"- {ic['confirmed']} of {ic['files_checked']} sources: gcc's header list is inside the static include closure")
        for x in ic["failed"]:
            L.append(f"- could not preprocess `{x['path']}`: {x['error']} (pass the target's -D/-I with --cflags=\"-D... -I...\", as the Makefile does)")
        for p, hs in ic["extra_headers"].items():
            L.append(f"- `{p}`: gcc also saw " + ", ".join(hs))
    if m["unreadable"]:
        L += ["", "## Unreadable", ""] + [f"- `{u['path']}`: {u['error']}" for u in m["unreadable"]]
    L += ["", "## What this map does not know", "",
          "- what a macro expands to, which `#if` branch the target build takes, or where a function pointer points at run time",
          "- overload resolution, templates, and virtual dispatch: C++ edges are by name",
          "- whether a `volatile` is shared with an ISR or just a register: read the file before moving it to the host",
          "- behaviour: the host harness (`/bring-your-firmware`) runs the code; a Python behavioural twin proven with shared vectors "
          "(`/tdd --lang both`) is a reference model, not a translation. This repository has no C-to-Python translator.", ""]
    return "\n".join(L)


def write_outputs(result: dict, out_dir: Path, name: str, top: int, prefix: str, opened: str, fresh: bool = False, dot_cap: int = 60) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "inventory": out_dir / f"{name}-c-fleet-inventory.csv",
        "summary": out_dir / f"{name}-c-fleet-summary.json",
        "dependency_map": out_dir / f"{name}-c-dependency-map.json",
        "dependency_dot": out_dir / f"{name}-c-dependency-map.dot",
        "repo_map": out_dir / f"{name}-c-repo-map.md",
        "backlog": out_dir / f"{name}-c-migration-backlog.json",
        "backlog_csv": out_dir / f"{name}-c-migration-backlog.csv",
    }
    items = build_backlog(result["rows"], top, prefix, opened)
    notes = list(result["summary"]["notes"])
    items = finish_backlog(items, paths["backlog"], prefix, notes, fresh)
    paths["inventory"].write_text(csv_text(result["rows"], COLUMNS), encoding="utf-8")
    summary = {**result["summary"], "notes": notes, "name": name, "backlog_items": len(items), "outputs": {k: str(rel(v)) for k, v in paths.items()}}
    paths["summary"].write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    paths["dependency_map"].write_text(json.dumps(result["dep_map"], indent=2) + "\n", encoding="utf-8")
    paths["dependency_dot"].write_text(c_dot(result["dep_map"], dot_cap), encoding="utf-8")
    paths["repo_map"].write_text(repo_map_md(name, result), encoding="utf-8")
    about = backlog_about(TOOL, name, paths["backlog"], paths["backlog_csv"], "top port/wrap units by priority (tests and declaration-only headers excluded)")
    paths["backlog"].write_text(json.dumps({"_about": about, "items": items}, indent=2) + "\n", encoding="utf-8")
    paths["backlog_csv"].write_text(csv_text(backlog_csv_rows(items), BACKLOG_COLUMNS), encoding="utf-8")
    return paths


def render_text(summary: dict, paths: dict[str, Path]) -> str:
    c, k = summary["counts"], summary["classification"]
    lines = [
        f"{summary['name']}: {c['files']} files ({c['sources']} sources, {c['headers']} headers, {c['cpp_files']} C++, {c['tests']} tests); "
        f"{c['functions']} functions, {c['include_edges']} include edges, {c['call_edges']} call edges, {c['unresolved_calls']} unresolved",
        f"classification: port {k['port']}, wrap {k['wrap']}, retain {k['retain']}, unreadable {k['unreadable']}; complexity total {summary['complexity_total']}",
        f"target-only: {', '.join(summary['target_only']) or 'none'}; seam candidates: {c['seam_candidates']}; include reader: {summary['include_reader']}",
        f"backlog: {summary['backlog_items']} items -> {paths['backlog']}",
        f"repo map: {paths['repo_map']}; dependency map: {paths['dependency_map']}",
    ]
    lines += [f"note: {n}" for n in summary["notes"]]
    return "\n".join(lines)


# --- --check ---------------------------------------------------------------------------------------------------


def check(write: bool = False) -> int:
    meta_path = EXPECTED / "c-fleet.json"
    with tempfile.TemporaryDirectory() as tmp:
        result = scan_tree(FIXTURE, use_gcc=False)   # static only: the expected files must not depend on the machine's compiler
        paths = write_outputs(result, Path(tmp), "firmware-repo", 50, "FW", "2026-01-05")
        actual = {"counts": result["summary"]["counts"], "classification": result["summary"]["classification"],
                  "entry_points": result["summary"]["entry_points"], "orphans": result["summary"]["orphans"],
                  "target_only": result["summary"]["target_only"], "seam_candidates": result["dep_map"]["seam_candidates"],
                  "backlog_items": len(json.loads(paths["backlog"].read_text(encoding="utf-8"))["items"])}
        inventory = paths["inventory"].read_text(encoding="utf-8")
        if write:
            EXPECTED.mkdir(exist_ok=True)
            meta_path.write_text(json.dumps({"_about": f"Expected shape of `python {TOOL} --check` over example-system/firmware-repo/ (static include walk, "
                                             f"no gcc). Regenerate with --check --write-expected after a deliberate change.", **actual}, indent=2) + "\n", encoding="utf-8")
            (EXPECTED / "c-fleet-inventory.csv").write_text(inventory, encoding="utf-8")
            print(f"wrote {rel(meta_path)} and {rel(EXPECTED / 'c-fleet-inventory.csv')}")
            return 0
        if not meta_path.is_file():
            print(f"c-fleet check FAILED: missing {rel(meta_path)}; run --check --write-expected")
            return 1
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        problems = [f"{k}: {actual[k]} != expected {meta.get(k)}" for k in actual if actual[k] != meta.get(k)]
        if (EXPECTED / "c-fleet-inventory.csv").read_text(encoding="utf-8") != inventory:
            problems.append("c-fleet-inventory.csv differs from a fresh scan")
        if problems:
            print("c-fleet check FAILED:\n  " + "\n  ".join(problems))
            return 1
        c = actual["counts"]
        print(f"c-fleet check ok: {c['files']} C/C++ files, {c['include_edges']} include edges, {c['call_edges']} call edges, "
              f"{c['unresolved_calls']} unresolved, {c['target_only_files']} target-only under example-system/firmware-repo/; "
              f"{actual['backlog_items']} backlog items validate against templates/tracker-item.json")
        return 0


# --- main -------------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tree", nargs="?", type=Path, help="directory holding C/C++ sources")
    ap.add_argument("--name", help="output prefix (default: the tree's folder name)")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    ap.add_argument("--top", type=int, default=50, help="backlog size (max 999)")
    ap.add_argument("--prefix", default="FW", help="tracker id prefix, 2-6 upper-case letters")
    ap.add_argument("--opened", default=dt.date.today().isoformat(), help="date stamped on backlog items (YYYY-MM-DD)")
    ap.add_argument("--libc", type=Path, help="text file with extra library function names to treat as resolved, one per line")
    ap.add_argument("--cflags", default="", help="extra flags for the gcc -MM cross-check; write it as --cflags=\"-DBOARD_REV_C -Iinclude\" (the leading dash needs the = form)")
    ap.add_argument("--no-gcc", action="store_true", help="skip the gcc -MM cross-check even if gcc is on PATH")
    ap.add_argument("--dot-top", type=int, default=60, help="max nodes drawn in the DOT file (JSON map is always complete)")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    ap.add_argument("--fresh", action="store_true", help="ignore an existing <name>-c-migration-backlog.json instead of preserving ids and statuses")
    ap.add_argument("--check", action="store_true", help="scan example-system/firmware-repo and compare with its expected/ files")
    ap.add_argument("--write-expected", action="store_true", help="with --check: rewrite the expected files")
    a = ap.parse_args(argv)
    if a.check:
        return check(a.write_expected)
    if not a.tree:
        ap.error("tree is required unless --check")
    extra = frozenset()
    if a.libc:
        extra = frozenset(l.strip() for l in a.libc.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#"))
    result = scan_tree(a.tree, extra, a.cflags.split(), not a.no_gcc)
    name = a.name or safe_name(a.tree)
    paths = write_outputs(result, a.out_dir, name, a.top, a.prefix, a.opened, a.fresh, a.dot_top)
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    print(json.dumps(summary, indent=2) if a.json else render_text(summary, paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
