#!/usr/bin/env python3
"""BasketryStitch - a coil-and-stitch pattern log with row-shrinkage estimates.

Record a finished sample (reed width, number of rows, total height before and
after finishing), list the log, and project how tall a planned side will
finish - or how many rows a target height needs - from the shrinkage you
actually measured.

One file, the Python standard library only, one JSON log.

Design tokens (see DESIGN.md): terminal-dark surface, monospace type, a single
accent #b26233 reserved for the primary result, aligned columns, box-drawing
rules, and never a colour-only signal.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

__version__ = "1.0.0"

PROGRAM = "basketrystitch.py"
LOG_VERSION = 1
DEFAULT_LOG_PATH = "basketrystitch_log.json"

# Reed width units, converted to millimetres with fixed factors (D6).
UNIT_TO_MM: Dict[str, float] = {"in": 25.4, "cm": 10.0, "mm": 1.0}
UNITS: Tuple[str, ...] = ("in", "cm", "mm")

EXIT_OK = 0
EXIT_LOG = 1  # the log file cannot be read or used
EXIT_USAGE = 2  # bad input: invalid, missing or conflicting flags, unknown id

ADD_EXAMPLE = (
    "python basketrystitch.py add --name \"Willow Coil\" --reed-width 4 "
    "--unit in --sample-rows 10 --row-height-before 100 --row-height-after 88"
)

ACCENT_RGB = (178, 98, 51)  # #b26233, the committed accent


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class CliError(Exception):
    """A failure that ends the run with a one-line message and an exit code."""

    exit_code = EXIT_USAGE


class UsageError(CliError):
    """Bad input: a flag is missing, malformed, conflicting or names nothing."""

    exit_code = EXIT_USAGE


class LogError(CliError):
    """The log file cannot be read, parsed or written."""

    exit_code = EXIT_LOG


# --------------------------------------------------------------------------
# Terminal style (never a colour-only signal; disabled when piped)
# --------------------------------------------------------------------------

_COLOR = False

GLYPHS = {"dash": "\u2014", "dot": "\u00b7", "rule": "\u2500"}


def _glyph(name: str, ascii_fallback: str) -> str:
    """Return the box-drawing glyph, or its ASCII twin for a narrow console."""
    character = GLYPHS[name]
    encoding = sys.stdout.encoding or "utf-8"
    try:
        character.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return ascii_fallback
    return character


def _paint(text: str, sgr: str) -> str:
    if not _COLOR:
        return text
    return "\x1b[{}m{}\x1b[0m".format(sgr, text)


def accent(text: str) -> str:
    """The one accent, used only for the primary result on a line."""
    return _paint(text, "38;2;{};{};{}".format(*ACCENT_RGB))


def bold(text: str) -> str:
    return _paint(text, "1")


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------


def utc_now() -> str:
    """ISO-8601 UTC timestamp with second precision."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def millimetres(value: float) -> str:
    return "{:.2f} mm".format(value)


def reed_width_label(entry: Dict[str, Any]) -> str:
    """'4.00 in (101.60 mm)' - the entered value plus the normalised width."""
    return "{:.2f} {} ({})".format(
        entry["reed_width_value"],
        entry["reed_width_unit"],
        millimetres(entry["reed_width_mm"]),
    )


def shrinkage_pct(entry: Dict[str, Any]) -> float:
    """Percentage of the before height lost to finishing (D4)."""
    before = float(entry["row_height_before_mm"])
    after = float(entry["row_height_after_mm"])
    return (before - after) / before * 100.0


def per_row_after_mm(entry: Dict[str, Any]) -> float:
    """Finished height of a single row of the sample (D3, D4)."""
    return float(entry["row_height_after_mm"]) / int(entry["sample_rows"])


# --------------------------------------------------------------------------
# Log store (D2, D5)
# --------------------------------------------------------------------------


def empty_document() -> Dict[str, Any]:
    return {"version": LOG_VERSION, "next_id": 1, "entries": []}


def _os_error_text(exc: OSError) -> str:
    return exc.strerror or str(exc)


def _entry_problem(entry: Any, index: int) -> Optional[str]:
    """Describe the first structural problem with a stored entry, or None."""
    where = "entries[{}]".format(index)
    if not isinstance(entry, dict):
        return "{} is not an object".format(where)
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        return "{}.name must be a non-blank string".format(where)
    for key in ("id", "sample_rows"):
        value = entry.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            return "{}.{} must be a whole number of 1 or more".format(where, key)
    for key in (
        "reed_width_value",
        "reed_width_mm",
        "row_height_before_mm",
        "row_height_after_mm",
    ):
        value = entry.get(key)
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not ok or not math.isfinite(float(value)) or float(value) <= 0:
            return "{}.{} must be a positive number".format(where, key)
    if entry.get("reed_width_unit") not in UNITS:
        return "{}.reed_width_unit must be one of in, cm, mm".format(where)
    if not isinstance(entry.get("created_at"), str):
        return "{}.created_at must be an ISO-8601 timestamp string".format(where)
    return None


def _validated(document: Any, path: str) -> Dict[str, Any]:
    """Check the document shape and repair a stale next_id, or raise LogError."""
    if not isinstance(document, dict):
        raise LogError(
            "{} is not a BasketryStitch log: expected a JSON object".format(path)
        )
    version = document.get("version")
    if version != LOG_VERSION:
        raise LogError(
            "{} has log version {!r}; this build reads version {}".format(
                path, version, LOG_VERSION
            )
        )
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise LogError(
            "{} is not a BasketryStitch log: 'entries' must be a list".format(path)
        )
    seen: set = set()
    for index, entry in enumerate(entries):
        problem = _entry_problem(entry, index)
        if problem is not None:
            raise LogError(
                "{} is not a BasketryStitch log: {}".format(path, problem)
            )
        if entry["id"] in seen:
            raise LogError(
                "{} is not a BasketryStitch log: duplicate id {}".format(
                    path, entry["id"]
                )
            )
        seen.add(entry["id"])
    next_id = document.get("next_id")
    if not isinstance(next_id, int) or isinstance(next_id, bool) or next_id < 1:
        raise LogError(
            "{} is not a BasketryStitch log: 'next_id' must be a whole number "
            "of 1 or more".format(path)
        )
    highest = max(seen) if seen else 0
    return {
        "version": LOG_VERSION,
        "next_id": max(next_id, highest + 1),
        "entries": entries,
    }


def load_log(path: str) -> Dict[str, Any]:
    """Read the log. A missing file is an empty log; a broken one is LogError."""
    if not os.path.exists(path):
        return empty_document()
    try:
        with open(path, "r", encoding="utf-8") as stream:
            raw = stream.read()
    except OSError as exc:
        raise LogError("cannot read {}: {}".format(path, _os_error_text(exc))) from None
    except UnicodeDecodeError as exc:
        raise LogError(
            "cannot read {}: not UTF-8 text (byte {})".format(path, exc.start)
        ) from None
    if not raw.strip():
        raise LogError(
            "{} is empty; delete it to start a fresh log".format(path)
        )
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LogError(
            "{} is not valid JSON (line {}, column {}: {})".format(
                path, exc.lineno, exc.colno, exc.msg
            )
        ) from None
    return _validated(document, path)


def _discard(temp_path: str) -> None:
    """Best-effort removal of a temp file we failed to rename into place."""
    try:
        os.unlink(temp_path)
    except OSError:
        # Nothing useful can be done: the log itself is already safe.
        pass


def save_log(path: str, document: Dict[str, Any]) -> None:
    """Write the log atomically: temp file in the same directory, then rename."""
    target = os.path.abspath(path)
    directory = os.path.dirname(target) or "."
    try:
        handle, temp_path = tempfile.mkstemp(
            prefix=".basketrystitch-", suffix=".tmp", dir=directory
        )
    except OSError as exc:
        raise LogError(
            "cannot write {}: {}".format(path, _os_error_text(exc))
        ) from None
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, target)
    except OSError as exc:
        _discard(temp_path)
        raise LogError(
            "cannot write {}: {}".format(path, _os_error_text(exc))
        ) from None
    except BaseException:
        # Includes KeyboardInterrupt: leave the previous log untouched.
        _discard(temp_path)
        raise


# --------------------------------------------------------------------------
# Flag validation - every message names the offending flag
# --------------------------------------------------------------------------


def positive_float(raw: Optional[str], flag: str) -> float:
    if raw is None:
        raise UsageError("{} is required".format(flag))
    text = raw.strip()
    try:
        value = float(text)
    except (TypeError, ValueError):
        raise UsageError(
            "{} must be a number, got {!r}".format(flag, raw)
        ) from None
    if not math.isfinite(value) or value <= 0:
        raise UsageError(
            "{} must be greater than zero, got {!r}".format(flag, raw)
        )
    return value


def positive_int(raw: Optional[str], flag: str) -> int:
    if raw is None:
        raise UsageError("{} is required".format(flag))
    text = raw.strip()
    try:
        value = int(text, 10)
    except (TypeError, ValueError):
        raise UsageError(
            "{} must be a whole number, got {!r}".format(flag, raw)
        ) from None
    if value < 1:
        raise UsageError(
            "{} must be 1 or more, got {!r}".format(flag, raw)
        )
    return value


def reed_width_unit(raw: Optional[str]) -> str:
    if raw is None:
        raise UsageError("--unit is required: in, cm or mm")
    unit = raw.strip().lower()
    if unit not in UNIT_TO_MM:
        raise UsageError(
            "--unit must be one of in, cm, mm, got {!r}".format(raw)
        )
    return unit


def sample_name(raw: Optional[str]) -> str:
    name = (raw or "").strip()
    if not name:
        raise UsageError("--name must not be blank; give the sample a name")
    return name


# --------------------------------------------------------------------------
# add
# --------------------------------------------------------------------------


def build_entry(
    entry_id: int,
    name: str,
    reed_width: float,
    unit: str,
    sample_rows: int,
    before_mm: float,
    after_mm: float,
) -> Dict[str, Any]:
    return {
        "id": entry_id,
        "name": name,
        "reed_width_value": reed_width,
        "reed_width_unit": unit,
        "reed_width_mm": round(reed_width * UNIT_TO_MM[unit], 4),
        "sample_rows": sample_rows,
        "row_height_before_mm": before_mm,
        "row_height_after_mm": after_mm,
        "created_at": utc_now(),
    }


def command_add(args: argparse.Namespace, log_path: str) -> int:
    name = sample_name(args.name)
    reed_width = positive_float(args.reed_width, "--reed-width")
    unit = reed_width_unit(args.unit)
    sample_rows = positive_int(args.sample_rows, "--sample-rows")
    before_mm = positive_float(args.row_height_before, "--row-height-before")
    after_mm = positive_float(args.row_height_after, "--row-height-after")

    document = load_log(log_path)
    entry = build_entry(
        document["next_id"], name, reed_width, unit, sample_rows, before_mm, after_mm
    )
    document["entries"].append(entry)
    document["next_id"] = entry["id"] + 1
    save_log(log_path, document)

    if args.json:
        print(json.dumps(entry, indent=2, ensure_ascii=False))
        return EXIT_OK
    print("Added entry {}: {}".format(accent(str(entry["id"])), entry["name"]))
    print("reed width: {}".format(reed_width_label(entry)))
    return EXIT_OK


# --------------------------------------------------------------------------
# list
# --------------------------------------------------------------------------


TABLE_HEADER = ("ID", "NAME", "REED WIDTH", "ROWS", "BEFORE (mm)", "AFTER (mm)", "SHRINK")
TABLE_ALIGN = ("right", "left", "left", "right", "right", "right", "right")


def entry_cells(entry: Dict[str, Any]) -> List[str]:
    return [
        str(entry["id"]),
        entry["name"],
        reed_width_label(entry),
        str(entry["sample_rows"]),
        "{:.2f}".format(entry["row_height_before_mm"]),
        "{:.2f}".format(entry["row_height_after_mm"]),
        "{:.1f}%".format(shrinkage_pct(entry)),
    ]


def render_table(entries: List[Dict[str, Any]]) -> List[str]:
    rows = [entry_cells(entry) for entry in entries]
    widths = [
        max(len(TABLE_HEADER[index]), *(len(row[index]) for row in rows))
        for index in range(len(TABLE_HEADER))
    ]

    def format_row(cells: Sequence[str]) -> str:
        padded = []
        for index, cell in enumerate(cells):
            width = widths[index]
            padded.append(
                cell.rjust(width) if TABLE_ALIGN[index] == "right" else cell.ljust(width)
            )
        return "  ".join(padded).rstrip()

    rule = "  ".join(_glyph("rule", "-") * width for width in widths)
    lines = [format_row(TABLE_HEADER), rule]
    lines.extend(format_row(row) for row in rows)
    return lines


def command_list(args: argparse.Namespace, log_path: str) -> int:
    document = load_log(log_path)
    entries = sorted(document["entries"], key=lambda item: item["id"])

    if args.json:
        payload = {
            "log": log_path,
            "count": len(entries),
            "entries": [
                dict(
                    entry,
                    shrinkage_pct=round(shrinkage_pct(entry), 6),
                    per_row_after_mm=round(per_row_after_mm(entry), 6),
                )
                for entry in entries
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return EXIT_OK

    if not entries:
        print("No entries yet.")
        print("Log: {}".format(os.path.abspath(log_path)))
        print("")
        print("Add your first sample:")
        print("  {}".format(ADD_EXAMPLE))
        return EXIT_OK

    count = len(entries)
    print(
        bold("BasketryStitch log")
        + " {} {} sample{} {} {}".format(
            _glyph("dash", "-"),
            count,
            "" if count == 1 else "s",
            _glyph("dot", "|"),
            log_path,
        )
    )
    print("")
    for line in render_table(entries):
        print(line)
    return EXIT_OK


# --------------------------------------------------------------------------
# estimate
# --------------------------------------------------------------------------


def find_entry(document: Dict[str, Any], entry_id: int) -> Dict[str, Any]:
    for entry in document["entries"]:
        if entry["id"] == entry_id:
            return entry
    known = ", ".join(str(item["id"]) for item in sorted(
        document["entries"], key=lambda item: item["id"]
    ))
    raise UsageError(
        "no entry with id {} (the log holds: {})".format(entry_id, known)
    )


def command_estimate(args: argparse.Namespace, log_path: str) -> int:
    entry_id = positive_int(args.id, "--id")
    wants_rows = args.target_rows is not None
    wants_height = args.target_height is not None
    if wants_rows == wants_height:
        raise UsageError("give exactly one of --target-rows or --target-height")

    target_rows: Optional[int] = None
    target_height: Optional[float] = None
    if wants_rows:
        target_rows = positive_int(args.target_rows, "--target-rows")
    else:
        target_height = positive_float(args.target_height, "--target-height")

    document = load_log(log_path)
    if not document["entries"]:
        raise LogError(
            "No entries yet {} add one first: {}".format(
                _glyph("dash", "-"), ADD_EXAMPLE
            )
        )
    entry = find_entry(document, entry_id)

    per_row = per_row_after_mm(entry)
    shrink = shrinkage_pct(entry)
    projected_height = target_rows * per_row if target_rows is not None else None
    projected_rows = (
        int(round(target_height / per_row)) if target_height is not None else None
    )

    if args.json:
        payload: Dict[str, Any] = {
            "entry_id": entry["id"],
            "name": entry["name"],
            "reed_width": reed_width_label(entry),
            "sample_rows": entry["sample_rows"],
            "row_height_before_mm": entry["row_height_before_mm"],
            "row_height_after_mm": entry["row_height_after_mm"],
            "per_row_after_mm": round(per_row, 6),
            "shrinkage_pct": round(shrink, 6),
            "target_rows": target_rows,
            "target_height_mm": target_height,
            "projected_finished_height_mm": (
                round(projected_height, 6) if projected_height is not None else None
            ),
            "projected_rows": projected_rows,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return EXIT_OK

    print("Entry {}: {}".format(entry["id"], entry["name"]))
    print("reed width: {}".format(reed_width_label(entry)))
    print(
        "sample: {} rows, {} before, {} after".format(
            entry["sample_rows"],
            millimetres(entry["row_height_before_mm"]),
            millimetres(entry["row_height_after_mm"]),
        )
    )
    print("per-row after: {}".format(millimetres(per_row)))
    print("shrinkage: {:.1f}%".format(shrink))
    if target_rows is not None and projected_height is not None:
        print("target rows: {}".format(target_rows))
        print(
            "projected finished height: {}".format(
                accent(millimetres(projected_height))
            )
        )
    else:
        print("target height: {}".format(millimetres(float(target_height or 0))))
        print("projected rows: {}".format(accent(str(projected_rows))))
    return EXIT_OK


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

DESCRIPTION = (
    "Log a coil-and-stitch basketry sample and project its row shrinkage."
)

EPILOG = """\
examples:
  {add}
  python basketrystitch.py list
  python basketrystitch.py estimate --id 1 --target-rows 50
  python basketrystitch.py estimate --id 1 --target-height 440
  python basketrystitch.py --log ~/samples.json list

  A 10-row sample measuring 100 mm before and 88 mm after finishing shrinks
  12.0%, keeps 8.80 mm per row, so 50 rows finish 440.00 mm tall.

exit codes:
  0  success
  1  the log cannot be read or used (corrupt JSON, permissions, empty log)
  2  bad input (invalid, missing or conflicting flags, unknown id)
""".format(
    add=ADD_EXAMPLE
)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--log",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="log file to read or write (default: ./{})".format(DEFAULT_LOG_PATH),
    )
    common.add_argument(
        "--no-color",
        action="store_true",
        default=argparse.SUPPRESS,
        help="never emit ANSI colour, even on a terminal",
    )

    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[common],
    )
    parser.add_argument(
        "--version", action="version", version="BasketryStitch {}".format(__version__)
    )
    subparsers = parser.add_subparsers(dest="command", metavar="{add,list,estimate}")

    add_parser = subparsers.add_parser(
        "add",
        parents=[common],
        help="record one finished sample",
        description=(
            "Record one finished sample: its name, the reed width and unit, how "
            "many rows it was, and its total measured height in millimetres "
            "before and after finishing. The new id is echoed back."
        ),
    )
    add_parser.add_argument("--name", metavar="NAME", help="sample name (required)")
    add_parser.add_argument(
        "--reed-width", metavar="N", dest="reed_width", help="reed width (required)"
    )
    add_parser.add_argument(
        "--unit",
        metavar="UNIT",
        help="unit for --reed-width: in, cm or mm (default: in)",
        default="in",
    )
    add_parser.add_argument(
        "--sample-rows",
        metavar="N",
        dest="sample_rows",
        help="rows in the finished sample (required)",
    )
    add_parser.add_argument(
        "--row-height-before",
        metavar="MM",
        dest="row_height_before",
        help="total sample height in mm before finishing (required)",
    )
    add_parser.add_argument(
        "--row-height-after",
        metavar="MM",
        dest="row_height_after",
        help="total sample height in mm after finishing (required)",
    )
    add_parser.add_argument(
        "--json", action="store_true", help="print the stored entry as JSON"
    )

    list_parser = subparsers.add_parser(
        "list",
        parents=[common],
        help="print the log as an aligned table",
        description=(
            "Print every saved sample as an aligned table, ascending by id, or "
            "an empty-state prompt with a copy-pasteable add example."
        ),
    )
    list_parser.add_argument(
        "--json", action="store_true", help="print the log as JSON"
    )

    estimate_parser = subparsers.add_parser(
        "estimate",
        parents=[common],
        help="project a finished height or a row count",
        description=(
            "Turn one sample's measured shrinkage into a projection: the "
            "finished height of a target row count, or the row count for a "
            "target height. Give exactly one of the two targets."
        ),
    )
    estimate_parser.add_argument(
        "--id", metavar="ID", help="id of the sample to project from (required)"
    )
    estimate_parser.add_argument(
        "--target-rows",
        metavar="N",
        dest="target_rows",
        help="planned number of rows",
    )
    estimate_parser.add_argument(
        "--target-height",
        metavar="MM",
        dest="target_height",
        help="planned finished height in mm",
    )
    estimate_parser.add_argument(
        "--json", action="store_true", help="print the projection as JSON"
    )

    return parser


HANDLERS = {
    "add": command_add,
    "list": command_list,
    "estimate": command_estimate,
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    global _COLOR
    parser = build_parser()
    args = parser.parse_args(argv)

    log_path = getattr(args, "log", DEFAULT_LOG_PATH)
    _COLOR = bool(
        sys.stdout.isatty()
        and not getattr(args, "no_color", False)
        and not os.environ.get("NO_COLOR")
        and os.environ.get("TERM") != "dumb"
    )

    handler = HANDLERS.get(getattr(args, "command", None))
    if handler is None:
        parser.print_help()
        return EXIT_OK

    try:
        return handler(args, log_path)
    except CliError as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return exc.exit_code
    except BrokenPipeError:
        # A closed pipe (`| head`) is not an error worth a traceback.
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass
        return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
