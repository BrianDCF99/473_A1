#!/usr/bin/env python3
import argparse
import csv
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


PATTERN_BY_TYPE = {
    "literal": "foo",
    "char_class": "[f]oo",
    "negated_class": "[^0-9]",
    "anchor_start": "^foo",
    "anchor_end": "foo$",
    "alternation": "foo|bar",
    "repetition": "f+o+",
    "unicode_property": r"\p{Ll}+",
    "empty": "",
    "invalid": "(",
}


@dataclass
class OracleResult:
    expected_exit: int
    expected_stdout: str
    reason: str


def parse_bool(v: str) -> bool:
    return str(v).strip() in {"1", "true", "True", "yes", "Y"}


def load_lines(path: Path):
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)


def _line_matches(line: str, pattern_type: str, ignore_case: bool) -> bool:
    """Python-side oracle match for a single line (no trailing newline)."""
    body = line.rstrip("\n").rstrip("\r")

    if pattern_type == "empty":
        return True

    flags = re.IGNORECASE if ignore_case else 0

    if pattern_type == "unicode_property":
        # icgrep \p{Ll}+ always matches Unicode lowercase letters only,
        # even under -i (empirically verified against icgrep behavior).
        return any(ch.islower() for ch in body)

    if pattern_type == "literal":
        return re.search("foo", body, flags) is not None
    if pattern_type == "char_class":
        return re.search(r"[f]oo", body, flags) is not None
    if pattern_type == "negated_class":
        return re.search(r"[^0-9]", body, flags) is not None
    if pattern_type == "anchor_start":
        return re.match(r"foo", body, flags) is not None
    if pattern_type == "anchor_end":
        return re.search(r"foo\Z", body, flags) is not None
    if pattern_type == "alternation":
        return re.search(r"foo|bar", body, flags) is not None
    if pattern_type == "repetition":
        return re.search(r"f+o+", body, flags) is not None

    return False


def compute_selected_lines(lines, pattern_type: str, ignore_case: bool, invert: bool):
    if pattern_type == "invalid":
        return None
    selected = []
    for line in lines:
        matched = _line_matches(line, pattern_type, ignore_case)
        if invert:
            matched = not matched
        if matched:
            selected.append(line)
    return selected


FILE_MAP_NAMES = {
    "empty": "empty.txt",
    "no_match": "no_match.txt",
    "one_match": "one_match.txt",
    "many_match": "many_match.txt",
    "unicode_content": "unicode_content.txt",
    "missing_path": "this_path_should_not_exist.txt",
}


def resolve_input_path(file_type: str, data_dir: Path) -> Path:
    return data_dir / FILE_MAP_NAMES[file_type]


def build_icgrep_command(icgrep: Path, row: dict, data_dir: Path, project_root: Path):
    pattern_type = row["pattern_type"]
    file_type = row["file_type"]    
    source_type = row["source_type"]
    count = parse_bool(row["count"])
    invert = parse_bool(row["invert"])
    ignore_case = parse_bool(row["ignore_case"])
    line_numbers = parse_bool(row["line_numbers"])

    # Executed command (absolute paths for reliability)
    cmd = [str(icgrep), "-colors=never"]
    if count:
        cmd.append("-c")
    if invert:
        cmd.append("-v")
    if ignore_case:
        cmd.append("-i")
    if line_numbers and not count:
        cmd.append("-n")

    pattern = PATTERN_BY_TYPE[pattern_type]
    regex_file = None
    if source_type == "file_flag":
        fd, regex_file = tempfile.mkstemp(prefix="acts_regex_", suffix=".txt")
        os.close(fd)
        Path(regex_file).write_text(pattern + "\n", encoding="utf-8")
        cmd.extend(["-f", regex_file])
    else:
        cmd.append(pattern)

    input_path = resolve_input_path(file_type, data_dir)
    cmd.append(str(input_path))

    # Display cmd (for CSV): short form using "icgrep" and relative paths
    display = ["icgrep", "-colors=never"]
    if count:
        display.append("-c")
    if invert:
        display.append("-v")
    if ignore_case:
        display.append("-i")
    if line_numbers and not count:
        display.append("-n")
    if source_type == "file_flag":
        display.extend(["-f", f"<regex-file:{pattern_type}>"])
    else:
        display.append(_shell_quote(pattern))
    try:
        rel_input = input_path.resolve().relative_to(project_root)
        display.append(str(rel_input))
    except (ValueError, OSError):
        display.append(str(input_path))
    display_cmd = " ".join(display)

    return cmd, regex_file, input_path, display_cmd


def _shell_quote(s: str) -> str:
    if s == "":
        return "''"
    if re.search(r"[^A-Za-z0-9_./\-+@%]", s):
        return "'" + s.replace("'", "'\\''") + "'"
    return s


def oracle_for_icgrep(row: dict, input_path: Path) -> OracleResult:
    pattern_type = row["pattern_type"]
    file_type = row["file_type"]
    count = parse_bool(row["count"])
    invert = parse_bool(row["invert"])
    ignore_case = parse_bool(row["ignore_case"])
    line_numbers = parse_bool(row["line_numbers"])

    if file_type == "missing_path":
        return OracleResult(2, "", "missing input path should return error")
    if pattern_type == "invalid":
        return OracleResult(2, "", "invalid regex should return error")

    lines = load_lines(input_path)
    if lines is None:
        return OracleResult(2, "", "input path unreadable")
    selected = compute_selected_lines(lines, pattern_type, ignore_case, invert)
    selected_count = len(selected)

    expected_exit = 0 if selected_count > 0 else 1

    if count:
        expected_stdout = f"{selected_count}\n"
        return OracleResult(expected_exit, expected_stdout, "count mode")

    if line_numbers:
        numbered = []
        line_no = 1
        selected_set = {id(l): True for l in selected}
        for line in lines:
            if id(line) in selected_set:
                numbered.append(f"{line_no}:{line}")
            line_no += 1
        expected_stdout = "".join(numbered)
        return OracleResult(expected_exit, expected_stdout, "line-number mode")

    expected_stdout = "".join(selected)
    return OracleResult(expected_exit, expected_stdout, "normal mode")


def main():
    parser = argparse.ArgumentParser(description="Run combinatorial functional tests for Parabix tools.")
    parser.add_argument("--icgrep", required=True, help="Absolute path to icgrep binary.")
    parser.add_argument("--frames", required=True, help="CSV file of test frames.")
    parser.add_argument("--data-dir", default=None, help="Data directory (default: project/data).")
    parser.add_argument("--out", default="results/results.csv", help="Output CSV report.")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    data_dir = Path(args.data_dir) if args.data_dir else project_root / "data"
    frames_path = Path(args.frames)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    icgrep = Path(args.icgrep)
    if not icgrep.exists():
        raise SystemExit(f"icgrep binary not found: {icgrep}")
    if not frames_path.exists():
        raise SystemExit(f"frames CSV not found: {frames_path}")

    rows_out = []
    with frames_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            case_id = row.get("id", "")
            tool = row["tool"]
            if tool != "icgrep":
                rows_out.append({
                    "id": case_id,
                    "tool": tool,
                    "status": "SKIP",
                    "reason": "tool not implemented in runner yet",
                })
                continue

            cmd, regex_file, input_path, display_cmd = build_icgrep_command(
                icgrep, row, data_dir, project_root
            )
            oracle = oracle_for_icgrep(row, input_path)

            proc = subprocess.run(cmd, text=False, capture_output=True)
            actual_exit = proc.returncode
            actual_stdout = proc.stdout.decode("utf-8", errors="replace")
            actual_stderr = proc.stderr.decode("utf-8", errors="replace")

            exit_ok = (actual_exit == oracle.expected_exit)
            stdout_ok = (actual_stdout == oracle.expected_stdout)
            status = "PASS" if (exit_ok and stdout_ok) else "FAIL"

            rows_out.append({
                "id": case_id,
                "tool": tool,
                "status": status,
                "reason": oracle.reason,
                "cmd": display_cmd,
                "expected_exit": oracle.expected_exit,
                "actual_exit": actual_exit,
                "expected_stdout": oracle.expected_stdout.encode("unicode_escape").decode("ascii"),
                "actual_stdout": actual_stdout.encode("unicode_escape").decode("ascii"),
                "stderr": actual_stderr.encode("unicode_escape").decode("ascii"),
            })

            if regex_file:
                Path(regex_file).unlink(missing_ok=True)

    fieldnames = [
        "id", "tool", "status", "reason", "cmd",
        "expected_exit", "actual_exit",
        "expected_stdout", "actual_stdout", "stderr",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_out)

    total = len(rows_out)
    fails = sum(1 for r in rows_out if r["status"] == "FAIL")
    skips = sum(1 for r in rows_out if r["status"] == "SKIP")
    passes = total - fails - skips
    print(f"Done. PASS={passes} FAIL={fails} SKIP={skips} TOTAL={total}")
    print(f"Report: {out_path}")


if __name__ == "__main__":
    main()
