#!/usr/bin/env python3
"""Python reconstruction of two real LabVIEW VIs: `Create TopicFilter.vi` and `Evaluate.vi`
(MQTT topic-filter validation and matching), the output of /labview-to-python on a `.vi` that was
read with `lvkit` only - no LabVIEW, no HTML export, no recording.

    # Replay every case in cases.csv through the port, then compare with the values read off the
    # block diagram (bench_compare.py says PASS when the port and the diagram reading agree).
    python example-system/real-vi/topic_filter.py --replay example-system/real-vi/cases.csv --out outputs/topic-filter-python.csv
    python tools/bench_compare.py example-system/real-vi/cases.csv outputs/topic-filter-python.csv

    # List the rows where the diagram (and therefore the port) disagrees with MQTT 3.1.1 section 4.7.
    python example-system/real-vi/topic_filter.py --spec-diff outputs/topic-filter-python.csv

What this proves: the Python agrees with what the block diagram says, on every case, and the
project's own requirement tests (recovered from `Test MQTT-4.7.1-2.vi` / `-3.vi`) pass against it.
What it does NOT prove: that the diagram was read correctly. Only running the original VIs and
recording their outputs can do that. See VI-REVIEW.md for the residual unknowns.
"""

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path

MAX_CASE_ROWS = 1_000
MAX_CSV_FIELD_CHARS = 1_024  # metadata columns (case, source, note, verdicts)
CASE_ID = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
TRI_STATE = ("TRUE", "FALSE", "-")

# Constants as the VIs name them. Byte values from the block-diagram comment "/ = byte 47, + = byte 43, # = byte 35".
LEVEL_SEPARATOR = b"/"
END_ONLY_WILDCARD = b"+"     # the diagram AND the project's own tests use '+' as the wildcard that must be last (MQTT 3.1.1 says '#')
WHOLE_LEVEL_WILDCARD = b"#"  # ... and '#' as the wildcard that must fill one level (MQTT 3.1.1 says '+')
DOLLAR = b"$"
MAX_FILTER_BYTES = 65535
MAX_TOPIC_BYTES = 65535  # port guard only: Evaluate.vi does not check the topic length (MQTT 3.1.1 section 4.7.3 does)
# CSV data columns: a filter row may be one byte over the VI's limit (to exercise error 55042); a topic may not.
MAX_FIELD_BYTES = {"topic_filter": MAX_FILTER_BYTES + 1, "topic": MAX_TOPIC_BYTES}

# Error codes and messages, verbatim from `Create TopicFilter.vi` (Error Cluster From Error Code.vi frames 0..5).
# The Build Array order on the diagram decides precedence: the first True check wins.
ERRORS = (
    (55041, "Topic filter must be at least one character long"),
    (55040, "Invalid use of null character in topic filter."),
    (55042, "Encoded topic filter cannot be more than 65535 bytes long"),
    (55043, "Multi-Level Wildcard Character can only be used at the end of the topic filter"),
    (55044, "Multi-Level Wildcard Character can only be used on its own or after a level separator."),
    (55045, "Single-Level Wildcard Character can only occupy a whole level."),
)

CASE_COLUMNS = ("case", "topic_filter", "topic", "valid", "error_code", "match", "spec_valid", "spec_match", "source", "note")
COMPUTED_COLUMNS = ("valid", "error_code", "match")


class TopicFilterError(Exception):
    """The VI's error cluster: code and message exactly as `Create TopicFilter.vi` produces them."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class TopicFilter:
    """The `_TopicFilter.lvclass` private data as the Default frame bundles it (the DVR cache is dropped)."""

    topic_filter: bytes
    universal: bool

    @property
    def levels(self) -> list[bytes]:
        return split_levels(self.topic_filter)


def split_levels(s: bytes) -> list[bytes]:
    """Spreadsheet String To Array with '/' as delimiter and a 1-D string array type, as the diagram wires it.
    ASSUMPTION: elements are taken verbatim (no whitespace trimming) and a trailing '/' yields an empty last
    level. Neither is visible in the diagram; cases.csv avoids both until a recording settles them."""
    return s.split(LEVEL_SEPARATOR)


def _checks(data: bytes) -> list[bool]:
    """The six booleans that `Create TopicFilter.vi` builds into an array, in diagram order."""
    empty = len(data) == 0
    has_null = 0 in data
    too_long = len(data) > MAX_FILTER_BYTES
    # Match Pattern with pattern "+$" -> offset past match, -1 when the filter does not end in '+'.
    # ASSUMPTION: LabVIEW's Match Pattern treats a leading '+' literally here.
    end_offset = len(data) if data.endswith(END_ONLY_WILDCARD) else -1
    plus_not_last = END_ONLY_WILDCARD[0] in data and end_offset < 0
    # Case "2..2147483647" on that offset: the byte before the final '+' must be '/'.
    plus_not_after_separator = end_offset >= 2 and data[end_offset - 2 : end_offset - 1] != LEVEL_SEPARATOR
    # For Loop over bytes, case "35": both neighbours of every '#' must be '/' or off the end of the array
    # (Index Array returns 0 out of range; the inner cases pass 0 and 47 through, everything else is True).
    hash_not_whole_level = False
    for i, b in enumerate(data):
        if b == WHOLE_LEVEL_WILDCARD[0]:
            before = data[i - 1] if i - 1 >= 0 else 0
            after = data[i + 1] if i + 1 < len(data) else 0
            if before not in (0, LEVEL_SEPARATOR[0]) or after not in (0, LEVEL_SEPARATOR[0]):
                hash_not_whole_level = True
                break  # the loop's conditional terminal stops at the first offending '#'
    return [empty, has_null, too_long, plus_not_last, plus_not_after_separator, hash_not_whole_level]


def create_topic_filter(topic_filter: str | bytes) -> TopicFilter:
    """`Create TopicFilter.vi`, No Error frame. Raises TopicFilterError like the VI sets error out."""
    data = topic_filter.encode("utf-8") if isinstance(topic_filter, str) else bytes(topic_filter)
    checks = _checks(data)
    if True in checks:  # Search 1D Array for the first True
        code, message = ERRORS[checks.index(True)]
        raise TopicFilterError(code, message)
    return TopicFilter(topic_filter=data, universal=data == END_ONLY_WILDCARD)


def evaluate(topic_filter: TopicFilter, topic: str | bytes) -> bool:
    """`Evaluate.vi`, No Error frame: one boolean per filter level, AND-ed together.

    ASSUMPTION: the For Loop's conditional terminal is read as "Continue if True" (stop at the first level that
    fails); the alternative reading would compare only the first level. The loop is auto-indexed on the filter
    levels only, so a topic with more levels than the filter is not checked past the filter's last level."""
    data = topic.encode("utf-8") if isinstance(topic, str) else bytes(topic)
    if len(data) > MAX_TOPIC_BYTES:
        raise ValueError(f"topic longer than {MAX_TOPIC_BYTES} bytes")
    filter_levels = topic_filter.levels
    topic_levels = split_levels(data)
    topic_not_dollar = data[0:1] != DOLLAR  # String Subset(topic, 0, 1) != '$', computed once outside the loop
    results: list[bool] = []
    for i, level in enumerate(filter_levels):
        if level in (WHOLE_LEVEL_WILDCARD, END_ONLY_WILDCARD):
            ok = topic_not_dollar
        else:
            ok = level == (topic_levels[i] if i < len(topic_levels) else b"")  # Index Array default: empty string
        results.append(ok)
        if not ok:
            break
    return all(results)


def run_case(topic_filter: str, topic: str) -> tuple[str, str, str]:
    """(valid, error_code, match) as the CSV columns spell them."""
    try:
        tf = create_topic_filter(topic_filter)
    except TopicFilterError as e:
        return "FALSE", str(e.code), "-"
    return "TRUE", "0", "TRUE" if evaluate(tf, topic) else "FALSE"


def read_cases(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"{path}: not a file")
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None or tuple(header) != CASE_COLUMNS:
            raise SystemExit(f"{path}: header must be exactly {','.join(CASE_COLUMNS)}")
        rows: list[dict[str, str]] = []
        seen: set[str] = set()
        for n, values in enumerate(reader, start=2):
            if len(values) != len(CASE_COLUMNS):
                raise SystemExit(f"{path}:{n}: expected {len(CASE_COLUMNS)} fields, got {len(values)}")
            row = dict(zip(CASE_COLUMNS, values))
            if not CASE_ID.match(row["case"]) or row["case"] in seen:
                raise SystemExit(f"{path}:{n}: case id must be unique and match {CASE_ID.pattern}")
            seen.add(row["case"])
            for col, v in row.items():
                if col in MAX_FIELD_BYTES:
                    if len(v.encode("utf-8")) > MAX_FIELD_BYTES[col]:
                        raise SystemExit(f"{path}:{n}: {col} longer than {MAX_FIELD_BYTES[col]} bytes")
                elif len(v) > MAX_CSV_FIELD_CHARS:
                    raise SystemExit(f"{path}:{n}: {col} longer than {MAX_CSV_FIELD_CHARS} characters")
            for col in ("valid", "match", "spec_valid", "spec_match"):
                if row[col] not in TRI_STATE:
                    raise SystemExit(f"{path}:{n}: {col} must be one of {'/'.join(TRI_STATE)}")
            if not (row["error_code"] == "0" or row["error_code"] in {str(c) for c, _ in ERRORS}):
                raise SystemExit(f"{path}:{n}: error_code must be 0 or one of the VI's codes")
            rows.append(row)
            if len(rows) > MAX_CASE_ROWS:
                raise SystemExit(f"{path}: more than {MAX_CASE_ROWS} rows")
    if not rows:
        raise SystemExit(f"{path}: no cases")
    return rows


def replay(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Recompute the three diagram columns; copy every other column through unchanged so the files line up."""
    out = []
    for row in rows:
        valid, code, match = run_case(row["topic_filter"], row["topic"])
        out.append({**row, "valid": valid, "error_code": code, "match": match})
    return out


def write_cases(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CASE_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def spec_deviations(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Rows where the diagram columns disagree with the MQTT 3.1.1 columns. Rows the spec does not settle
    (spec_valid '-') are never counted."""
    out = []
    for row in rows:
        if row["spec_valid"] == "-":
            continue
        if row["valid"] != row["spec_valid"]:
            out.append(row)
        elif row["valid"] == "TRUE" and row["spec_match"] != "-" and row["match"] != row["spec_match"]:
            out.append(row)
    return out


def deviation_table(rows: list[dict[str, str]]) -> str:
    lines = ["| case | topic filter | topic | diagram: valid / match | MQTT 3.1.1: valid / match | source |",
             "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['case']} | `{r['topic_filter']}` | `{r['topic']}` | {r['valid']} / {r['match']} | "
                     f"{r['spec_valid']} / {r['spec_match']} | {r['source']} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--replay", type=Path, metavar="CASES_CSV", help="run every case through the port")
    g.add_argument("--spec-diff", type=Path, metavar="RESULT_CSV", help="print the rows that differ from MQTT 3.1.1")
    ap.add_argument("--out", type=Path, help="where --replay writes its results (required with --replay)")
    a = ap.parse_args(argv)
    if a.replay is not None:
        if a.out is None:
            ap.error("--replay needs --out")
        rows = replay(read_cases(a.replay))
        write_cases(a.out, rows)
        print(f"{len(rows)} cases replayed -> {a.out}; {len(spec_deviations(rows))} differ from MQTT 3.1.1 section 4.7")
        return 0
    rows = read_cases(a.spec_diff)
    dev = spec_deviations(rows)
    print(deviation_table(dev) if dev else "No rows differ from MQTT 3.1.1 section 4.7.")
    print(f"\n{len(dev)} of {len(rows)} rows differ from MQTT 3.1.1 section 4.7")
    return 0


if __name__ == "__main__":
    sys.exit(main())
